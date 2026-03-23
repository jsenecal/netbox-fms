"""Tests for the Insert into Splice Closure workflow (slack loop insertion)."""

from decimal import Decimal

import pytest
from dcim.models import (
    Cable,
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

from netbox_fms.models import (
    ClosureCableEntry,
    FiberCable,
    FiberCableType,
    SlackLoop,
    SplicePlanEntry,
)


@pytest.mark.django_db
class TestInsertSlackLoopIntoClosure:
    """Test insert_slack_loop_into_closure service function."""

    @pytest.fixture(autouse=True)
    def setup_infrastructure(self):
        """Create shared infrastructure: sites, devices, closure with ports."""
        self.site_a = Site.objects.create(name="INS-Site-A", slug="ins-site-a")
        self.site_b = Site.objects.create(name="INS-Site-B", slug="ins-site-b")
        self.site_mid = Site.objects.create(name="INS-Site-Mid", slug="ins-site-mid")

        mfr = Manufacturer.objects.create(name="INS-Mfr", slug="ins-mfr")

        # Device types
        dt_endpoint = DeviceType.objects.create(manufacturer=mfr, model="INS-Endpoint", slug="ins-endpoint")
        dt_closure = DeviceType.objects.create(manufacturer=mfr, model="INS-Closure", slug="ins-closure")
        role = DeviceRole.objects.create(name="INS-Role", slug="ins-role")

        # Endpoint devices with RearPorts
        self.dev_a = Device.objects.create(name="INS-Dev-A", site=self.site_a, device_type=dt_endpoint, role=role)
        self.dev_b = Device.objects.create(name="INS-Dev-B", site=self.site_b, device_type=dt_endpoint, role=role)

        self.rp_a = RearPort.objects.create(device=self.dev_a, name="INS-RP-A", type="lc", positions=1)
        self.rp_b = RearPort.objects.create(device=self.dev_b, name="INS-RP-B", type="lc", positions=1)

        # Closure device with RearPorts, FrontPorts, PortMappings, Module (tray)
        self.closure = Device.objects.create(
            name="INS-Closure-1", site=self.site_mid, device_type=dt_closure, role=role
        )

        # Module (tray) on closure
        mt = ModuleType.objects.create(manufacturer=mfr, model="INS-Tray")
        mb = ModuleBay.objects.create(device=self.closure, name="INS-Bay-1")
        self.tray = Module.objects.create(device=self.closure, module_bay=mb, module_type=mt)

        # A-side rear port + front port on closure
        self.closure_rp_a = RearPort.objects.create(
            device=self.closure, name="INS-Closure-RP-A", type="lc", positions=1
        )
        self.closure_fp_a = FrontPort.objects.create(
            device=self.closure, module=self.tray, name="INS-Closure-FP-A", type="lc"
        )
        PortMapping.objects.create(
            device=self.closure,
            front_port=self.closure_fp_a,
            rear_port=self.closure_rp_a,
            front_port_position=1,
            rear_port_position=1,
        )

        # B-side rear port + front port on closure
        self.closure_rp_b = RearPort.objects.create(
            device=self.closure, name="INS-Closure-RP-B", type="lc", positions=1
        )
        self.closure_fp_b = FrontPort.objects.create(
            device=self.closure, module=self.tray, name="INS-Closure-FP-B", type="lc"
        )
        PortMapping.objects.create(
            device=self.closure,
            front_port=self.closure_fp_b,
            rear_port=self.closure_rp_b,
            front_port_position=1,
            rear_port_position=1,
        )

        # FiberCableType (1-strand tight_buffer)
        self.fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="INS-FCT",
            fiber_type="smf_os2",
            construction="tight_buffer",
            strand_count=1,
        )

    def _make_cable_and_loop(self):
        """Create a fresh Cable, FiberCable, and SlackLoop for each test."""
        cable = Cable(
            a_terminations=[self.rp_a],
            b_terminations=[self.rp_b],
            type="smf-os2",
            status="connected",
        )
        cable.save()

        fc = FiberCable.objects.create(cable=cable, fiber_cable_type=self.fct)
        sl = SlackLoop.objects.create(
            fiber_cable=fc,
            site=self.site_mid,
            start_mark=Decimal("100.00"),
            end_mark=Decimal("120.00"),
            length_unit="m",
        )
        return cable, fc, sl

    def _do_insert(self, sl, express=None):
        """Call the service function with standard parameters."""
        from netbox_fms.views import insert_slack_loop_into_closure

        return insert_slack_loop_into_closure(
            slack_loop=sl,
            closure=self.closure,
            a_side_rear_ports=[self.closure_rp_a],
            b_side_rear_ports=[self.closure_rp_b],
            express_strand_positions=express or set(),
        )

    def test_insert_creates_two_new_cables(self):
        old_cable, fc, sl = self._make_cable_and_loop()
        old_cable_pk = old_cable.pk

        cable_a, cable_b, fc_a, fc_b, plan = self._do_insert(sl)

        # Old cable should be deleted
        assert not Cable.objects.filter(pk=old_cable_pk).exists()
        # Two new cables should exist
        assert Cable.objects.filter(pk=cable_a.pk).exists()
        assert Cable.objects.filter(pk=cable_b.pk).exists()
        assert cable_a.pk != cable_b.pk

    def test_insert_creates_fiber_cables(self):
        old_cable, fc, sl = self._make_cable_and_loop()
        old_fc_pk = fc.pk

        cable_a, cable_b, fc_a, fc_b, plan = self._do_insert(sl)

        # Old FiberCable should be deleted (cascade from cable)
        assert not FiberCable.objects.filter(pk=old_fc_pk).exists()
        # Two new FiberCables with correct type
        assert fc_a.fiber_cable_type == self.fct
        assert fc_b.fiber_cable_type == self.fct
        assert fc_a.cable == cable_a
        assert fc_b.cable == cable_b

    def test_insert_creates_splice_plan_entries(self):
        old_cable, fc, sl = self._make_cable_and_loop()

        cable_a, cable_b, fc_a, fc_b, plan = self._do_insert(sl)

        assert plan.closure == self.closure
        entries = SplicePlanEntry.objects.filter(plan=plan)
        assert entries.count() == 1
        entry = entries.first()
        assert entry.fiber_a == self.closure_fp_a
        assert entry.fiber_b == self.closure_fp_b

    def test_insert_express_strands(self):
        old_cable, fc, sl = self._make_cable_and_loop()

        cable_a, cable_b, fc_a, fc_b, plan = self._do_insert(sl, express={1})

        entries = SplicePlanEntry.objects.filter(plan=plan)
        assert entries.count() == 1
        entry = entries.first()
        assert entry.is_express is True

    def test_insert_creates_closure_cable_entries(self):
        old_cable, fc, sl = self._make_cable_and_loop()

        cable_a, cable_b, fc_a, fc_b, plan = self._do_insert(sl)

        cce = ClosureCableEntry.objects.filter(closure=self.closure)
        assert cce.count() == 2
        fc_ids = set(cce.values_list("fiber_cable_id", flat=True))
        assert fc_ids == {fc_a.pk, fc_b.pk}

    def test_insert_deletes_slack_loop(self):
        old_cable, fc, sl = self._make_cable_and_loop()
        sl_pk = sl.pk

        self._do_insert(sl)

        assert not SlackLoop.objects.filter(pk=sl_pk).exists()
