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
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from netbox_fms.constants import FIBER_CABLE_TYPES
from netbox_fms.forms import ClosureCableWizardStep1Form, ClosureCableWizardStep2Form
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


class TestClosureCableWizardForms(TestCase):
    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = _make_infra("WF")
        cls.device_a = Device.objects.create(name="WF-A", site=site, device_type=dt, role=role)
        cls.device_b = Device.objects.create(name="WF-B", site=site, device_type=dt, role=role)
        cls.fct = FiberCableType.objects.create(
            manufacturer=mfr, model="WF-TB6", strand_count=6, construction="tight_buffer"
        )

    def test_step1_rejects_near_device_as_far_end(self):
        form = ClosureCableWizardStep1Form(
            {"far_end_device": self.device_a.pk, "fiber_cable_type": self.fct.pk, "port_type": "splice"},
            near_device=self.device_a,
        )
        assert not form.is_valid()
        assert "far_end_device" in form.errors

    def test_step1_accepts_different_device(self):
        form = ClosureCableWizardStep1Form(
            {"far_end_device": self.device_b.pk, "fiber_cable_type": self.fct.pk, "port_type": "splice"},
            near_device=self.device_a,
        )
        assert form.is_valid(), form.errors

    def test_step2_type_choices_are_fiber_only(self):
        values = {value for value, _label in ClosureCableWizardStep2Form().fields["type"].choices if value}
        assert values == set(FIBER_CABLE_TYPES)  # AOC and copper excluded

    def test_step2_length_requires_unit(self):
        form = ClosureCableWizardStep2Form({"status": "connected", "length": "100"})
        assert not form.is_valid()
        form = ClosureCableWizardStep2Form({"status": "connected", "length": "100", "length_unit": "m"})
        assert form.is_valid(), form.errors


class TestClosureCableWizardView(TestCase):
    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = _make_infra("WV")
        cls.device_a = Device.objects.create(name="WV-A", site=site, device_type=dt, role=role)
        cls.device_b = Device.objects.create(name="WV-B", site=site, device_type=dt, role=role)
        cls.fct = FiberCableType.objects.create(
            manufacturer=mfr, model="WV-TB6", strand_count=6, construction="tight_buffer"
        )
        cls.url = reverse("plugins:netbox_fms:fiber_overview_add_cable", kwargs={"pk": cls.device_a.pk})

    def test_permission_gate_returns_403(self):
        User = get_user_model()
        user = User.objects.create_user("ccw-nobody", "n@test.com", "password")
        self.client.force_login(user)
        assert self.client.get(self.url).status_code == 403
        assert self.client.post(self.url, {}).status_code == 403

    def test_full_wizard_walk_creates_cable(self):
        User = get_user_model()
        admin = User.objects.create_superuser("ccw-admin", "a@test.com", "password")
        self.client.force_login(admin)

        # Step 1 renders
        response = self.client.get(self.url)
        assert response.status_code == 200
        assert response.context["current_step"] == 1

        # Step 1 -> 2
        response = self.client.post(
            self.url,
            {"far_end_device": self.device_b.pk, "fiber_cable_type": self.fct.pk, "port_type": "splice"},
        )
        assert response.status_code == 200
        assert response.context["current_step"] == 2
        # label pre-suggested from the device names
        assert response.context["form"].initial["label"] == "WV-A <-> WV-B"

        # Step 2 -> 3 (review)
        response = self.client.post(self.url, {"status": "connected", "type": "smf-os2", "label": "WV-A <-> WV-B"})
        assert response.status_code == 200
        assert response.context["current_step"] == 3
        assert response.context["strand_count"] == 6
        assert response.context["rear_ports_per_device"] == 1

        # Step 3 -> create
        response = self.client.post(self.url, {})
        assert response.status_code == 302
        assert response.url.endswith(f"/dcim/devices/{self.device_a.pk}/fiber-overview/")

        cable = Cable.objects.get(label="WV-A <-> WV-B")
        assert cable.type == "smf-os2"
        fc = FiberCable.objects.get(cable=cable)
        assert CableTermination.objects.filter(cable=cable, cable_end="A").count() == 1
        assert CableTermination.objects.filter(cable=cable, cable_end="B").count() == 1
        assert ClosureCableEntry.objects.filter(fiber_cable=fc).count() == 2

    def test_back_returns_to_previous_step(self):
        User = get_user_model()
        admin = User.objects.create_superuser("ccw-back", "b@test.com", "password")
        self.client.force_login(admin)
        self.client.post(
            self.url,
            {"far_end_device": self.device_b.pk, "fiber_cable_type": self.fct.pk, "port_type": "splice"},
        )
        response = self.client.post(self.url, {"_back": "1"})
        assert response.status_code == 200
        assert response.context["current_step"] == 1

    def test_state_resets_when_switching_devices(self):
        User = get_user_model()
        admin = User.objects.create_superuser("ccw-switch", "s@test.com", "password")
        self.client.force_login(admin)
        # advance device A's wizard to step 2
        self.client.post(
            self.url,
            {"far_end_device": self.device_b.pk, "fiber_cable_type": self.fct.pk, "port_type": "splice"},
        )
        # opening device B's wizard must start fresh at step 1
        url_b = reverse("plugins:netbox_fms:fiber_overview_add_cable", kwargs={"pk": self.device_b.pk})
        response = self.client.get(url_b)
        assert response.status_code == 200
        assert response.context["current_step"] == 1

    def test_step3_service_error_rerenders_with_message(self):
        User = get_user_model()
        admin = User.objects.create_superuser("ccw-err", "e@test.com", "password")
        self.client.force_login(admin)
        self.client.post(
            self.url,
            {"far_end_device": self.device_b.pk, "fiber_cable_type": self.fct.pk, "port_type": "splice"},
        )
        self.client.post(self.url, {"status": "connected"})
        with mock.patch("netbox_fms.views.create_closure_cable", side_effect=ValueError("boom")):
            response = self.client.post(self.url, {})
        assert response.status_code == 200
        assert response.context["current_step"] == 3
        assert response.context["wizard_error"] == "boom"
        assert b"boom" in response.content
