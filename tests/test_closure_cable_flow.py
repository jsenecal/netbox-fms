"""Tests for the closure cable flow (service, wizard forms, wizard view)."""

from unittest import mock

from dcim.models import (
    Cable,
    CableTermination,
    Device,
    DeviceRole,
    DeviceType,
    FrontPort,
    Manufacturer,
    PortMapping,
    RearPort,
    Site,
)
from django.core.exceptions import ValidationError
from django.test import TestCase

from netbox_fms.models import BufferTubeTemplate, ClosureCableEntry, FiberCable, FiberCableType
from netbox_fms.services import create_closure_cable


def _make_infra(prefix):
    site = Site.objects.create(name=f"{prefix} Site", slug=f"{prefix.lower()}-site")
    mfr = Manufacturer.objects.create(name=f"{prefix} Mfr", slug=f"{prefix.lower()}-mfr")
    dt = DeviceType.objects.create(manufacturer=mfr, model=f"{prefix} FOSC", slug=f"{prefix.lower()}-fosc")
    role = DeviceRole.objects.create(name=f"{prefix} Closure", slug=f"{prefix.lower()}-closure")
    return site, mfr, dt, role


class TestCreateClosureCable(TestCase):
    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = _make_infra("CCF")
        cls.device_a = Device.objects.create(name="CCF-A", site=site, device_type=dt, role=role)
        cls.device_b = Device.objects.create(name="CCF-B", site=site, device_type=dt, role=role)
        # tight buffer 6F -> builtin profile "single-1c6p"
        cls.fct_tight = FiberCableType.objects.create(
            manufacturer=mfr, model="CCF-TB6", strand_count=6, construction="tight_buffer"
        )
        # loose tube 4x12 -> registered profile "trunk-4c12p"
        cls.fct_tubed = FiberCableType.objects.create(
            manufacturer=mfr, model="CCF-LT48", strand_count=48, construction="loose_tube"
        )
        for i in range(1, 5):
            BufferTubeTemplate.objects.create(fiber_cable_type=cls.fct_tubed, name=f"T{i}", position=i, fiber_count=12)
        # loose tube 3x12 -> no registered profile (warning path)
        cls.fct_noprofile = FiberCableType.objects.create(
            manufacturer=mfr, model="CCF-LT36", strand_count=36, construction="loose_tube"
        )
        for i in range(1, 4):
            BufferTubeTemplate.objects.create(
                fiber_cable_type=cls.fct_noprofile, name=f"T{i}", position=i, fiber_count=12
            )

    def test_creates_structure_on_both_devices(self):
        fc, warnings = create_closure_cable(
            device_a=self.device_a,
            device_b=self.device_b,
            fiber_cable_type=self.fct_tubed,
            cable_attrs={"type": "smf-os2", "label": "CCF-A <-> CCF-B"},
        )
        assert warnings == []
        for device in (self.device_a, self.device_b):
            assert RearPort.objects.filter(device=device).count() == 4
            assert FrontPort.objects.filter(device=device).count() == 48
            assert PortMapping.objects.filter(device=device).count() == 48
        # strands linked A-side to front_port_a, B-side to front_port_b
        assert fc.fiber_strands.filter(front_port_a__device=self.device_a).count() == 48
        assert fc.fiber_strands.filter(front_port_b__device=self.device_b).count() == 48

    def test_cable_terminated_on_both_ends_with_profile(self):
        fc, warnings = create_closure_cable(
            device_a=self.device_a,
            device_b=self.device_b,
            fiber_cable_type=self.fct_tubed,
            cable_attrs={"type": "smf-os2"},
        )
        cable = fc.cable
        cable.refresh_from_db()
        assert cable.profile == "trunk-4c12p"
        a_terms = CableTermination.objects.filter(cable=cable, cable_end="A")
        b_terms = CableTermination.objects.filter(cable=cable, cable_end="B")
        assert a_terms.count() == 4
        assert b_terms.count() == 4
        # connector/positions set for profile-based tracing
        connectors = sorted(t.connector for t in a_terms)
        assert connectors == [1, 2, 3, 4]
        assert all(t.positions == list(range(1, 13)) for t in a_terms)

    def test_creates_blank_gland_entries_on_both_closures(self):
        fc, _ = create_closure_cable(
            device_a=self.device_a,
            device_b=self.device_b,
            fiber_cable_type=self.fct_tight,
            cable_attrs={},
        )
        entries = ClosureCableEntry.objects.filter(fiber_cable=fc)
        assert entries.count() == 2
        assert set(entries.values_list("closure_id", flat=True)) == {self.device_a.pk, self.device_b.pk}
        assert all(e.entrance_label == "" for e in entries)

    def test_unregistered_profile_warns_but_creates(self):
        fc, warnings = create_closure_cable(
            device_a=self.device_a,
            device_b=self.device_b,
            fiber_cable_type=self.fct_noprofile,
            cable_attrs={},
        )
        assert len(warnings) == 1
        assert "profile" in warnings[0].lower()
        fc.cable.refresh_from_db()
        assert not fc.cable.profile
        assert CableTermination.objects.filter(cable=fc.cable).count() == 6  # 3 per end

    def test_invalid_cable_attrs_rejected_and_rolled_back(self):
        with self.assertRaises(ValidationError):
            create_closure_cable(
                device_a=self.device_a,
                device_b=self.device_b,
                fiber_cable_type=self.fct_tight,
                cable_attrs={"type": "bogus"},
            )
        assert Cable.objects.count() == 0
        assert FiberCable.objects.count() == 0
        assert RearPort.objects.count() == 0

    def test_same_device_both_ends_rejected(self):
        with self.assertRaises(ValueError):
            create_closure_cable(
                device_a=self.device_a,
                device_b=self.device_a,
                fiber_cable_type=self.fct_tight,
                cable_attrs={},
            )
        assert Cable.objects.count() == 0

    def test_late_failure_rolls_back_everything(self):
        with (
            # gland creation must remain the service's final step for this to cover the full choreography
            mock.patch.object(ClosureCableEntry.objects, "create", side_effect=RuntimeError("boom")),
            self.assertRaises(RuntimeError),
        ):
            create_closure_cable(
                device_a=self.device_a,
                device_b=self.device_b,
                fiber_cable_type=self.fct_tight,
                cable_attrs={},
            )
        assert Cable.objects.count() == 0
        assert FiberCable.objects.count() == 0
        assert RearPort.objects.count() == 0
        assert FrontPort.objects.count() == 0
        assert PortMapping.objects.count() == 0
        assert ClosureCableEntry.objects.count() == 0
