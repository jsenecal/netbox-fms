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
from django.core.exceptions import ValidationError
from django.test import TransactionTestCase

from netbox_fms.models import FiberCable, FiberCableType, SplicePlan
from netbox_fms.signals import fms_portmapping_bypass
from tests.conftest import make_front_port


class TestDiffCacheInvalidation(TransactionTestCase):
    def setUp(self):
        site = Site.objects.create(name="Sig Site", slug="sig-site")
        mfr = Manufacturer.objects.create(name="Sig Mfr", slug="sig-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Closure", slug="sig-closure")
        role = DeviceRole.objects.create(name="Sig Role", slug="sig-role")
        self.closure = Device.objects.create(name="C-Sig", site=site, device_type=dt, role=role)

        mt = ModuleType.objects.create(manufacturer=mfr, model="Tray")
        bay = ModuleBay.objects.create(device=self.closure, name="Bay 1")
        self.tray = Module.objects.create(device=self.closure, module_bay=bay, module_type=mt)

        self.fp1 = make_front_port(device=self.closure, module=self.tray, name="F1")
        self.fp2 = make_front_port(device=self.closure, module=self.tray, name="F2")

    def _make_cable_with_terminations(self, port_a, port_b):
        fp_ct = ContentType.objects.get_for_model(FrontPort)
        cable = Cable.objects.create(length=0, length_unit="m")
        CableTermination.objects.create(
            cable=cable,
            cable_end="A",
            termination_type=fp_ct,
            termination_id=port_a.pk,
        )
        CableTermination.objects.create(
            cable=cable,
            cable_end="B",
            termination_type=fp_ct,
            termination_id=port_b.pk,
        )
        return cable

    def test_cable_create_invalidates_cache(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Plan")
        plan.diff_stale = False
        plan.cached_diff = {"some": "data"}
        plan.save(update_fields=["diff_stale", "cached_diff"])

        cable = self._make_cable_with_terminations(self.fp1, self.fp2)
        cable.save()  # Trigger post_save again after terminations exist

        plan.refresh_from_db()
        assert plan.diff_stale is True

    def test_cable_delete_invalidates_cache(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Plan")
        cable = self._make_cable_with_terminations(self.fp1, self.fp2)

        plan.diff_stale = False
        plan.cached_diff = {"some": "data"}
        plan.save(update_fields=["diff_stale", "cached_diff"])

        cable.delete()

        plan.refresh_from_db()
        assert plan.diff_stale is True

    def test_unrelated_cable_does_not_invalidate(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Plan")
        plan.diff_stale = False
        plan.cached_diff = {"some": "data"}
        plan.save(update_fields=["diff_stale", "cached_diff"])

        # Cable with no terminations on our closure
        cable = Cable.objects.create(length=10, length_unit="m")
        cable.save()

        plan.refresh_from_db()
        assert plan.diff_stale is False


class TestPortMappingProtection(TransactionTestCase):
    """Test that PortMappings on FMS-managed devices are protected."""

    def setUp(self):
        site = Site.objects.create(name="PM Site", slug="pm-site")
        mfr = Manufacturer.objects.create(name="PM Mfr", slug="pm-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="PM Closure", slug="pm-closure")
        role = DeviceRole.objects.create(name="PM Role", slug="pm-role")
        self.device = Device.objects.create(name="PM-Device", site=site, device_type=dt, role=role)

        self.fct = FiberCableType.objects.create(model="PM-FCT", manufacturer=mfr, strand_count=2)
        cable = Cable.objects.create(label="PM Cable")
        self.fc = FiberCable.objects.create(cable=cable, fiber_cable_type=self.fct)

        self.rp_ct = ContentType.objects.get_for_model(RearPort)
        self.rp = RearPort.objects.create(device=self.device, name="PM Cable", type="splice", positions=2)
        CableTermination.objects.create(
            cable=cable, cable_end="A", termination_type=self.rp_ct, termination_id=self.rp.pk
        )
        self.fp = FrontPort.objects.create(device=self.device, name="PM:F1", type="splice")

    def test_external_portmapping_create_blocked(self):
        with self.assertRaises(ValidationError):
            PortMapping.objects.create(
                device=self.device,
                front_port=self.fp,
                rear_port=self.rp,
                front_port_position=1,
                rear_port_position=1,
            )

    def test_bypass_allows_portmapping_create(self):
        with fms_portmapping_bypass():
            pm = PortMapping.objects.create(
                device=self.device,
                front_port=self.fp,
                rear_port=self.rp,
                front_port_position=1,
                rear_port_position=1,
            )
        assert pm.pk is not None

    def test_external_portmapping_delete_blocked(self):
        with fms_portmapping_bypass():
            pm = PortMapping.objects.create(
                device=self.device,
                front_port=self.fp,
                rear_port=self.rp,
                front_port_position=1,
                rear_port_position=1,
            )
        with self.assertRaises(ValidationError):
            pm.delete()

    def test_non_fms_device_unprotected(self):
        site = Site.objects.create(name="NF Site", slug="nf-site")
        mfr = Manufacturer.objects.create(name="NF Mfr", slug="nf-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="NF Device", slug="nf-device")
        device2 = Device.objects.create(name="NF-Device", site=site, device_type=dt, role=self.device.role)
        rp2 = RearPort.objects.create(device=device2, name="NF-RP", type="8p8c", positions=1)
        fp2 = FrontPort.objects.create(device=device2, name="NF-FP", type="8p8c")
        pm = PortMapping.objects.create(
            device=device2,
            front_port=fp2,
            rear_port=rp2,
            front_port_position=1,
            rear_port_position=1,
        )
        assert pm.pk is not None


class TestPortNaming(TransactionTestCase):
    """Test that FMS-provisioned ports use Cable display label."""

    def setUp(self):
        site = Site.objects.create(name="PN Site", slug="pn-site")
        self.mfr = Manufacturer.objects.create(name="PN Mfr", slug="pn-mfr")
        dt = DeviceType.objects.create(manufacturer=self.mfr, model="PN Closure", slug="pn-closure")
        role = DeviceRole.objects.create(name="PN Role", slug="pn-role")
        self.device = Device.objects.create(name="PN-Device", site=site, device_type=dt, role=role)

    def test_tubed_provisioning_uses_cable_label(self):
        from netbox_fms.models import BufferTubeTemplate, FiberCableType
        from netbox_fms.services import link_cable_topology

        fct = FiberCableType.objects.create(model="PN-FCT", manufacturer=self.mfr, strand_count=2)
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=2)
        cable = Cable.objects.create(label="CO-Downtown")

        fc, _ = link_cable_topology(cable, fct, self.device)

        rp = RearPort.objects.filter(device=self.device).first()
        assert rp.name == "CO-Downtown:T1", f"Got: {rp.name}"

        fp = FrontPort.objects.filter(device=self.device).first()
        assert fp.name.startswith("CO-Downtown:T1:F"), f"Got: {fp.name}"

    def test_no_tube_provisioning_uses_cable_label(self):
        from netbox_fms.models import FiberCableType
        from netbox_fms.services import link_cable_topology

        fct = FiberCableType.objects.create(model="PN-FCT2", manufacturer=self.mfr, strand_count=2)
        cable = Cable.objects.create(label="CO-East")

        fc, _ = link_cable_topology(cable, fct, self.device)

        rp = RearPort.objects.filter(device=self.device).first()
        assert rp.name == "CO-East", f"Got: {rp.name}"

        fp = FrontPort.objects.filter(device=self.device).first()
        assert fp.name.startswith("CO-East:F"), f"Got: {fp.name}"

    def test_no_label_falls_back_to_pk(self):
        from netbox_fms.models import FiberCableType
        from netbox_fms.services import link_cable_topology

        fct = FiberCableType.objects.create(model="PN-FCT3", manufacturer=self.mfr, strand_count=1)
        cable = Cable.objects.create()

        fc, _ = link_cable_topology(cable, fct, self.device)

        rp = RearPort.objects.filter(device=self.device).first()
        assert rp.name == f"#{cable.pk}", f"Got: {rp.name}"


class TestPortNameSync(TransactionTestCase):
    """Test that port names stay in sync with Cable label changes."""

    def setUp(self):
        site = Site.objects.create(name="NS Site", slug="ns-site")
        self.mfr = Manufacturer.objects.create(name="NS Mfr", slug="ns-mfr")
        dt = DeviceType.objects.create(manufacturer=self.mfr, model="NS Closure", slug="ns-closure")
        role = DeviceRole.objects.create(name="NS Role", slug="ns-role")
        self.device = Device.objects.create(name="NS-Device", site=site, device_type=dt, role=role)

    def test_cable_rename_updates_rearport(self):
        from netbox_fms.models import FiberCableType
        from netbox_fms.services import link_cable_topology

        fct = FiberCableType.objects.create(model="NS-FCT", manufacturer=self.mfr, strand_count=2)
        cable = Cable.objects.create(label="Old Label")
        fc, _ = link_cable_topology(cable, fct, self.device)

        rp = RearPort.objects.filter(device=self.device).first()
        assert rp.name == "Old Label"

        cable.label = "New Label"
        cable.save()

        rp.refresh_from_db()
        assert rp.name == "New Label", f"Got: {rp.name}"

    def test_cable_rename_updates_frontports(self):
        from netbox_fms.models import FiberCableType
        from netbox_fms.services import link_cable_topology

        fct = FiberCableType.objects.create(model="NS-FCT2", manufacturer=self.mfr, strand_count=2)
        cable = Cable.objects.create(label="Original")
        fc, _ = link_cable_topology(cable, fct, self.device)

        cable.label = "Renamed"
        cable.save()

        fps = FrontPort.objects.filter(device=self.device).order_by("name")
        for fp in fps:
            assert fp.name.startswith("Renamed:F"), f"Got: {fp.name}"

    def test_cable_rename_updates_tubed_ports(self):
        from netbox_fms.models import BufferTubeTemplate, FiberCableType
        from netbox_fms.services import link_cable_topology

        fct = FiberCableType.objects.create(model="NS-FCT3", manufacturer=self.mfr, strand_count=2)
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=2)
        cable = Cable.objects.create(label="Tubed-Old")
        fc, _ = link_cable_topology(cable, fct, self.device)

        cable.label = "Tubed-New"
        cable.save()

        rp = RearPort.objects.filter(device=self.device).first()
        assert rp.name == "Tubed-New:T1", f"Got: {rp.name}"

        fps = FrontPort.objects.filter(device=self.device).order_by("name")
        for fp in fps:
            assert fp.name.startswith("Tubed-New:T1:F"), f"Got: {fp.name}"

    def test_rename_idempotent(self):
        from netbox_fms.models import FiberCableType
        from netbox_fms.services import link_cable_topology

        fct = FiberCableType.objects.create(model="NS-FCT4", manufacturer=self.mfr, strand_count=1)
        cable = Cable.objects.create(label="Same")
        fc, _ = link_cable_topology(cable, fct, self.device)

        rp = RearPort.objects.filter(device=self.device).first()
        old_name = rp.name

        cable.save()  # No label change

        rp.refresh_from_db()
        assert rp.name == old_name


class TestFiberCableLinkNameSync(TransactionTestCase):
    """Test that linking a FiberCable to a Cable triggers port rename."""

    def setUp(self):
        site = Site.objects.create(name="FL Site", slug="fl-site")
        self.mfr = Manufacturer.objects.create(name="FL Mfr", slug="fl-mfr")
        dt = DeviceType.objects.create(manufacturer=self.mfr, model="FL Closure", slug="fl-closure")
        role = DeviceRole.objects.create(name="FL Role", slug="fl-role")
        self.device = Device.objects.create(name="FL-Device", site=site, device_type=dt, role=role)

    def test_fibercable_save_triggers_rename(self):
        from netbox_fms.models import FiberCable, FiberCableType
        from netbox_fms.signals import fms_portmapping_bypass

        fct = FiberCableType.objects.create(model="FL-FCT", manufacturer=self.mfr, strand_count=1)
        cable = Cable.objects.create(label="Before Link")

        # Manually create ports with old names to simulate pre-existing state
        rp = RearPort.objects.create(device=self.device, name="old-name", type="splice", positions=1)
        rp_ct = ContentType.objects.get_for_model(RearPort)
        CableTermination.objects.create(
            cable=cable,
            cable_end="A",
            termination_type=rp_ct,
            termination_id=rp.pk,
            connector=1,
        )
        fp = FrontPort.objects.create(device=self.device, name="old-fp", type="splice")
        with fms_portmapping_bypass():
            PortMapping.objects.create(
                device=self.device,
                front_port=fp,
                rear_port=rp,
                front_port_position=1,
                rear_port_position=1,
            )

        # Create FiberCable with a strand linked to the FrontPort
        fc = FiberCable.objects.create(cable=cable, fiber_cable_type=fct)
        # Link the strand to the FrontPort so _rename_ports_for_cable can discover it
        strand = fc.fiber_strands.first()
        if strand:
            strand.front_port_b = fp
            strand.save(update_fields=["front_port_b"])
            # Re-save FiberCable to trigger the signal now that strand linkage exists
            fc.save()

        rp.refresh_from_db()
        assert rp.name == "Before Link", f"Got: {rp.name}"
        fp.refresh_from_db()
        assert fp.name == "Before Link:F1", f"Got: {fp.name}"
