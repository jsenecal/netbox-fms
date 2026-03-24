"""Tests for the fiber circuit trace engine.

Uses PortMapping model (NOT FrontPort.rear_port FK which doesn't exist in NetBox 4.5+).
"""

from dcim.models import (
    Cable,
    CableTermination,
    Device,
    DeviceRole,
    DeviceType,
    FrontPort,
    Manufacturer,
    Module,
    ModuleBay,
    ModuleType,
    PortMapping,
    RearPort,
    Site,
)
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from netbox_fms.choices import SplicePlanStatusChoices
from netbox_fms.models import FiberCircuitPath, SplicePlan, SplicePlanEntry


def _make_closure(site, mfr, name):
    dt, _ = DeviceType.objects.get_or_create(manufacturer=mfr, model=f"{name}-Type", slug=f"{name}-type".lower())
    role, _ = DeviceRole.objects.get_or_create(name=f"{name}-Role", slug=f"{name}-role".lower())
    device = Device.objects.create(name=name, site=site, device_type=dt, role=role)
    mt, _ = ModuleType.objects.get_or_create(manufacturer=mfr, model=f"{name}-Tray")
    bay = ModuleBay.objects.create(device=device, name="Bay1")
    tray = Module.objects.create(device=device, module_bay=bay, module_type=mt)
    return device, tray


def _connect_cable(cable, rear_port_a, rear_port_b):
    rp_ct = ContentType.objects.get_for_model(RearPort)
    CableTermination.objects.create(cable=cable, cable_end="A", termination_type=rp_ct, termination_id=rear_port_a.pk)
    CableTermination.objects.create(cable=cable, cable_end="B", termination_type=rp_ct, termination_id=rear_port_b.pk)


def _make_splice(fp_a, fp_b):
    cable = Cable.objects.create(length=0, length_unit="m")
    fp_ct = ContentType.objects.get_for_model(FrontPort)
    CableTermination.objects.create(cable=cable, cable_end="A", termination_type=fp_ct, termination_id=fp_a.pk)
    CableTermination.objects.create(cable=cable, cable_end="B", termination_type=fp_ct, termination_id=fp_b.pk)
    return cable


class TestTraceSingleCable(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Trace1 Site", slug="trace1-site")
        mfr = Manufacturer.objects.create(name="Trace1 Mfr", slug="trace1-mfr")

        cls.dev_a, cls.tray_a = _make_closure(site, mfr, "ClosureA")
        cls.dev_b, cls.tray_b = _make_closure(site, mfr, "ClosureB")

        cls.rp_a = RearPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="RP-A1", type="lc", positions=1)
        cls.fp_a = FrontPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="FP-A1", type="lc")
        PortMapping.objects.create(
            device=cls.dev_a, front_port=cls.fp_a, rear_port=cls.rp_a, front_port_position=1, rear_port_position=1
        )

        cls.rp_b = RearPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="RP-B1", type="lc", positions=1)
        cls.fp_b = FrontPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="FP-B1", type="lc")
        PortMapping.objects.create(
            device=cls.dev_b, front_port=cls.fp_b, rear_port=cls.rp_b, front_port_position=1, rear_port_position=1
        )

        cls.cable = Cable.objects.create()
        _connect_cable(cls.cable, cls.rp_a, cls.rp_b)

    def test_single_cable_trace(self):
        result = FiberCircuitPath.from_origin(self.fp_a)
        assert result.origin == self.fp_a
        assert result.destination == self.fp_b
        assert result.is_complete is True
        assert len(result.path) == 5  # FP, RP, Cable, RP, FP

    def test_path_json_format(self):
        result = FiberCircuitPath.from_origin(self.fp_a)
        assert result.path[0] == {"type": "front_port", "id": self.fp_a.pk}
        assert result.path[1] == {"type": "rear_port", "id": self.rp_a.pk}
        assert result.path[2] == {"type": "cable", "id": self.cable.pk}
        assert result.path[3] == {"type": "rear_port", "id": self.rp_b.pk}
        assert result.path[4] == {"type": "front_port", "id": self.fp_b.pk}


class TestTraceMultiHop(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Trace2 Site", slug="trace2-site")
        mfr = Manufacturer.objects.create(name="Trace2 Mfr", slug="trace2-mfr")

        cls.dev_a, cls.tray_a = _make_closure(site, mfr, "MH-ClosA")
        cls.dev_b, cls.tray_b = _make_closure(site, mfr, "MH-ClosB")
        cls.dev_c, cls.tray_c = _make_closure(site, mfr, "MH-ClosC")

        cls.rp_a = RearPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="RP-A", type="lc", positions=1)
        cls.fp_a = FrontPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="FP-A", type="lc")
        PortMapping.objects.create(
            device=cls.dev_a, front_port=cls.fp_a, rear_port=cls.rp_a, front_port_position=1, rear_port_position=1
        )

        cls.rp_b1 = RearPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="RP-B1", type="lc", positions=1)
        cls.fp_b1 = FrontPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="FP-B1", type="lc")
        PortMapping.objects.create(
            device=cls.dev_b, front_port=cls.fp_b1, rear_port=cls.rp_b1, front_port_position=1, rear_port_position=1
        )
        cls.rp_b2 = RearPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="RP-B2", type="lc", positions=1)
        cls.fp_b2 = FrontPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="FP-B2", type="lc")
        PortMapping.objects.create(
            device=cls.dev_b, front_port=cls.fp_b2, rear_port=cls.rp_b2, front_port_position=1, rear_port_position=1
        )

        cls.rp_c = RearPort.objects.create(device=cls.dev_c, module=cls.tray_c, name="RP-C", type="lc", positions=1)
        cls.fp_c = FrontPort.objects.create(device=cls.dev_c, module=cls.tray_c, name="FP-C", type="lc")
        PortMapping.objects.create(
            device=cls.dev_c, front_port=cls.fp_c, rear_port=cls.rp_c, front_port_position=1, rear_port_position=1
        )

        cls.cable1 = Cable.objects.create()
        _connect_cable(cls.cable1, cls.rp_a, cls.rp_b1)

        cls.splice_cable = _make_splice(cls.fp_b1, cls.fp_b2)
        cls.plan_b = SplicePlan.objects.create(
            closure=cls.dev_b, name="Plan-B", status=SplicePlanStatusChoices.ARCHIVED
        )
        cls.splice_entry = SplicePlanEntry.objects.create(
            plan=cls.plan_b,
            tray=cls.tray_b,
            fiber_a=cls.fp_b1,
            fiber_b=cls.fp_b2,
        )

        cls.cable2 = Cable.objects.create()
        _connect_cable(cls.cable2, cls.rp_b2, cls.rp_c)

    def test_multi_hop_trace(self):
        result = FiberCircuitPath.from_origin(self.fp_a)
        assert result.origin == self.fp_a
        assert result.destination == self.fp_c
        assert result.is_complete is True

    def test_multi_hop_path_length(self):
        result = FiberCircuitPath.from_origin(self.fp_a)
        assert len(result.path) == 11  # FP,RP,Cable,RP,FP,Splice,FP,RP,Cable,RP,FP

    def test_splice_in_path(self):
        result = FiberCircuitPath.from_origin(self.fp_a)
        splice_entries = [e for e in result.path if e["type"] == "splice_entry"]
        assert len(splice_entries) == 1
        assert splice_entries[0]["id"] == self.splice_entry.pk


class TestTraceIncomplete(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Trace3 Site", slug="trace3-site")
        mfr = Manufacturer.objects.create(name="Trace3 Mfr", slug="trace3-mfr")
        cls.dev_a, cls.tray_a = _make_closure(site, mfr, "IC-ClosA")
        cls.dev_b, cls.tray_b = _make_closure(site, mfr, "IC-ClosB")

        cls.rp_a = RearPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="RP-A", type="lc", positions=1)
        cls.fp_a = FrontPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="FP-A", type="lc")
        PortMapping.objects.create(
            device=cls.dev_a, front_port=cls.fp_a, rear_port=cls.rp_a, front_port_position=1, rear_port_position=1
        )

        cls.rp_b = RearPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="RP-B", type="lc", positions=1)
        cls.fp_b = FrontPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="FP-B", type="lc")
        PortMapping.objects.create(
            device=cls.dev_b, front_port=cls.fp_b, rear_port=cls.rp_b, front_port_position=1, rear_port_position=1
        )

        cls.cable = Cable.objects.create()
        _connect_cable(cls.cable, cls.rp_a, cls.rp_b)

    def test_trace_terminates_with_no_splice(self):
        result = FiberCircuitPath.from_origin(self.fp_a)
        assert result.destination == self.fp_b
        assert result.is_complete is True

    def test_no_port_mapping_incomplete(self):
        site = Site.objects.create(name="NoMap Site", slug="nomap-site")
        mfr = Manufacturer.objects.create(name="NoMap Mfr", slug="nomap-mfr")
        dev, tray = _make_closure(site, mfr, "NoMap")
        fp = FrontPort.objects.create(device=dev, module=tray, name="OrphanFP", type="lc")
        result = FiberCircuitPath.from_origin(fp)
        assert result.is_complete is False
        assert len(result.path) == 1
