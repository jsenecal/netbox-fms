"""Tests for tube-assignment driven FrontPort module sync (issue #68)."""

from dcim.models import Cable, Device, DeviceRole, DeviceType, Manufacturer, Module, ModuleBay, ModuleType, Site
from django.test import TestCase

from netbox_fms.models import BufferTube, ClosureCableEntry, FiberCable, FiberCableType, FiberStrand, TubeAssignment
from netbox_fms.services import clear_tube_assignment_ports, sync_tube_assignment_ports
from tests.conftest import make_front_port


class PortSyncTestCase(TestCase):
    """Closure with two trays, a far-end device, and a 2-strand tube with ports on both ends."""

    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="PS Site", slug="ps-site")
        mfr = Manufacturer.objects.create(name="PS Mfr", slug="ps-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="PS Closure", slug="ps-closure")
        role = DeviceRole.objects.create(name="PS Role", slug="ps-role")
        cls.closure = Device.objects.create(name="PS-Closure", site=site, device_type=dt, role=role)
        cls.far_end = Device.objects.create(name="PS-FarEnd", site=site, device_type=dt, role=role)

        mt = ModuleType.objects.create(manufacturer=mfr, model="PS Tray")
        bay1 = ModuleBay.objects.create(device=cls.closure, name="Bay 1")
        bay2 = ModuleBay.objects.create(device=cls.closure, name="Bay 2")
        cls.tray1 = Module.objects.create(device=cls.closure, module_bay=bay1, module_type=mt)
        cls.tray2 = Module.objects.create(device=cls.closure, module_bay=bay2, module_type=mt)

        fct = FiberCableType.objects.create(manufacturer=mfr, model="PS-2F", construction="loose_tube", strand_count=2)
        cls.fiber_cable = FiberCable.objects.create(cable=Cable.objects.create(), fiber_cable_type=fct)
        cls.tube = BufferTube.objects.create(fiber_cable=cls.fiber_cable, name="PS-T1", position=1)
        ClosureCableEntry.objects.create(closure=cls.closure, fiber_cable=cls.fiber_cable, entrance_label="G1")

        cls.near_ports = []
        cls.far_ports = []
        for strand in cls.fiber_cable.fiber_strands.all().order_by("position"):
            near = make_front_port(device=cls.closure, name=f"PS-N{strand.position}")
            far = make_front_port(device=cls.far_end, name=f"PS-F{strand.position}")
            strand.buffer_tube = cls.tube
            strand.front_port_a = near
            strand.front_port_b = far
            strand.save()
            cls.near_ports.append(near)
            cls.far_ports.append(far)

    def _assignment(self, tray=None, save=True):
        ta = TubeAssignment(closure=self.closure, tray=tray or self.tray1, buffer_tube=self.tube)
        if save:
            ta.save()
        return ta

    def _refresh_ports(self):
        for port in self.near_ports + self.far_ports:
            port.refresh_from_db()


class TestSyncHelpers(PortSyncTestCase):
    def test_sync_places_closure_side_ports_on_tray(self):
        ta = self._assignment()
        sync_tube_assignment_ports(ta)
        self._refresh_ports()
        assert all(p.module_id == self.tray1.pk for p in self.near_ports)

    def test_sync_leaves_far_end_ports_alone(self):
        ta = self._assignment()
        sync_tube_assignment_ports(ta)
        self._refresh_ports()
        assert all(p.module_id is None for p in self.far_ports)

    def test_sync_tolerates_strands_without_ports(self):
        FiberStrand.objects.create(fiber_cable=self.fiber_cable, buffer_tube=self.tube, name="PS-S3", position=3)
        ta = self._assignment()
        sync_tube_assignment_ports(ta)  # must not raise

    def test_clear_returns_ports_to_device_level(self):
        ta = self._assignment()
        sync_tube_assignment_ports(ta)
        clear_tube_assignment_ports(self.closure.pk, self.tray1.pk, self.tube.pk)
        self._refresh_ports()
        assert all(p.module_id is None for p in self.near_ports)

    def test_clear_leaves_manually_moved_port_alone(self):
        ta = self._assignment()
        sync_tube_assignment_ports(ta)
        moved = self.near_ports[0]
        moved.module = self.tray2
        moved.save()
        clear_tube_assignment_ports(self.closure.pk, self.tray1.pk, self.tube.pk)
        self._refresh_ports()
        assert self.near_ports[0].module_id == self.tray2.pk
        assert self.near_ports[1].module_id is None


class TestConflictDetection(PortSyncTestCase):
    def test_no_conflicts_for_device_level_ports(self):
        ta = self._assignment(save=False)
        assert ta.conflicting_front_ports() == []

    def test_port_on_foreign_module_conflicts(self):
        port = self.near_ports[0]
        port.module = self.tray2
        port.save()
        ta = self._assignment(save=False)
        assert ta.conflicting_front_ports() == [port]

    def test_own_current_tray_is_not_a_conflict(self):
        ta = self._assignment()
        sync_tube_assignment_ports(ta)
        ta.tray = self.tray2  # retargeting; ports sit on tray1, the DB tray
        assert ta.conflicting_front_ports() == []

    def test_target_tray_is_not_a_conflict(self):
        port = self.near_ports[0]
        port.module = self.tray1
        port.save()
        ta = self._assignment(save=False)
        assert ta.conflicting_front_ports() == []
