"""Tests for TrayProfile and TubeAssignment models."""

from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Module, ModuleType, Site
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from netbox_fms.choices import TrayRoleChoices
from netbox_fms.models import BufferTube, ClosureCableEntry, FiberCable, FiberCableType, TrayProfile, TubeAssignment
from tests.conftest import make_tray_module, make_tray_type


class TestTrayProfile(TestCase):
    @classmethod
    def setUpTestData(cls):
        manufacturer = Manufacturer.objects.create(name="Tray Mfr", slug="tray-mfr")
        cls.module_type = ModuleType.objects.create(
            manufacturer=manufacturer,
            model="24-Fiber Splice Tray",
        )
        cls.module_type_2 = ModuleType.objects.create(
            manufacturer=manufacturer,
            model="Express Basket 12",
        )

    def test_create_splice_tray_profile(self):
        profile = TrayProfile.objects.create(
            module_type=self.module_type,
            tray_role=TrayRoleChoices.SPLICE_TRAY,
        )
        assert profile.pk is not None
        assert profile.tray_role == TrayRoleChoices.SPLICE_TRAY

    def test_create_express_basket_profile(self):
        profile = TrayProfile.objects.create(
            module_type=self.module_type_2,
            tray_role=TrayRoleChoices.EXPRESS_BASKET,
        )
        assert profile.tray_role == TrayRoleChoices.EXPRESS_BASKET

    def test_one_profile_per_module_type(self):
        TrayProfile.objects.create(
            module_type=self.module_type,
            tray_role=TrayRoleChoices.SPLICE_TRAY,
        )
        with self.assertRaises(IntegrityError):
            TrayProfile.objects.create(
                module_type=self.module_type,
                tray_role=TrayRoleChoices.EXPRESS_BASKET,
            )

    def test_str(self):
        profile = TrayProfile.objects.create(
            module_type=self.module_type,
            tray_role=TrayRoleChoices.SPLICE_TRAY,
        )
        assert "24-Fiber Splice Tray" in str(profile)

    def test_get_absolute_url(self):
        profile = TrayProfile.objects.create(
            module_type=self.module_type,
            tray_role=TrayRoleChoices.SPLICE_TRAY,
        )
        assert "/tray-profiles/" in profile.get_absolute_url()


class TestTubeAssignment(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="TA Site", slug="ta-site")
        manufacturer = Manufacturer.objects.create(name="TA Mfr", slug="ta-mfr")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="Closure TA", slug="closure-ta")
        role = DeviceRole.objects.create(name="Closure TA", slug="closure-ta")
        cls.closure = Device.objects.create(name="Closure-TA", site=site, device_type=device_type, role=role)

        cls.module_type = make_tray_type(manufacturer, "24F Tray")
        cls.tray_profile = cls.module_type.tray_profile
        cls.tray = make_tray_module(cls.closure, cls.module_type, "Bay 1")
        cls.express_mt = make_tray_type(manufacturer, "Express Basket", role=TrayRoleChoices.EXPRESS_BASKET)
        cls.express_module = make_tray_module(cls.closure, cls.express_mt, "Bay 2")
        cls.plain_mt = make_tray_type(manufacturer, "Plain Module", role=None)
        cls.plain_module = make_tray_module(cls.closure, cls.plain_mt, "Bay 3")

        rig = _make_tube_rig("TA", cls.closure, manufacturer, entrance_label="Gland A")
        cls.fiber_cable = rig.fiber_cable
        cls.tube = rig.tube
        cls.cable_entry = rig.entry

    def test_create_tube_assignment(self):
        ta = TubeAssignment.objects.create(
            closure=self.closure,
            tray=self.tray,
            buffer_tube=self.tube,
        )
        assert ta.pk is not None

    def test_unique_tube_per_closure(self):
        TubeAssignment.objects.create(closure=self.closure, tray=self.tray, buffer_tube=self.tube)
        from dcim.models import ModuleBay

        bay_extra = ModuleBay.objects.create(device=self.closure, name="Bay Extra")
        tray2 = Module.objects.create(device=self.closure, module_bay=bay_extra, module_type=self.module_type)
        with self.assertRaises(IntegrityError):
            TubeAssignment.objects.create(closure=self.closure, tray=tray2, buffer_tube=self.tube)

    def test_str(self):
        ta = TubeAssignment.objects.create(closure=self.closure, tray=self.tray, buffer_tube=self.tube)
        assert "Tube 1" in str(ta)

    def test_get_absolute_url(self):
        ta = TubeAssignment.objects.create(closure=self.closure, tray=self.tray, buffer_tube=self.tube)
        assert "/tube-assignments/" in ta.get_absolute_url()

    def test_clean_tray_must_belong_to_closure(self):
        from dcim.models import ModuleBay
        from django.core.exceptions import ValidationError

        other_site = Site.objects.create(name="Other Site", slug="other-site")
        other_dt = DeviceType.objects.create(
            manufacturer=Manufacturer.objects.first(), model="Other DT", slug="other-dt"
        )
        other_device = Device.objects.create(
            name="Other",
            site=other_site,
            device_type=other_dt,
            role=DeviceRole.objects.first(),
        )
        other_bay = ModuleBay.objects.create(device=other_device, name="Other Bay")
        other_tray = Module.objects.create(device=other_device, module_bay=other_bay, module_type=self.module_type)
        ta = TubeAssignment(closure=self.closure, tray=other_tray, buffer_tube=self.tube)
        with self.assertRaises(ValidationError):
            ta.full_clean()

    def test_clean_tray_must_have_profile(self):
        from django.core.exceptions import ValidationError

        ta = TubeAssignment(closure=self.closure, tray=self.plain_module, buffer_tube=self.tube)
        with self.assertRaises(ValidationError):
            ta.full_clean()

    def test_clean_tray_must_be_splice_tray(self):
        from django.core.exceptions import ValidationError

        ta = TubeAssignment(closure=self.closure, tray=self.express_module, buffer_tube=self.tube)
        with self.assertRaises(ValidationError):
            ta.full_clean()

    def test_clean_cable_entry_must_exist(self):
        from django.core.exceptions import ValidationError

        fct2 = FiberCableType.objects.create(
            manufacturer=Manufacturer.objects.first(),
            model="Other Cable",
            construction="loose_tube",
            strand_count=12,
        )
        from dcim.models import Cable

        cable2 = Cable.objects.create()
        fc2 = FiberCable.objects.create(cable=cable2, fiber_cable_type=fct2)
        tube2 = BufferTube.objects.create(fiber_cable=fc2, name="Tube X", position=1)
        ta = TubeAssignment(closure=self.closure, tray=self.tray, buffer_tube=tube2)
        with self.assertRaises(ValidationError):
            ta.full_clean()


class TestClosureCableEntryCascade(TestCase):
    """Deleting a ClosureCableEntry should clean up TubeAssignments for that cable's tubes."""

    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Cascade Site", slug="cascade-site")
        manufacturer = Manufacturer.objects.create(name="Cascade Mfr", slug="cascade-mfr")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="Closure C", slug="closure-c")
        role = DeviceRole.objects.create(name="Closure C", slug="closure-c")
        cls.closure = Device.objects.create(name="Closure-C", site=site, device_type=device_type, role=role)

        cls.tray = make_tray_module(cls.closure, make_tray_type(manufacturer, "Tray C"), "Bay C")

        rig = _make_tube_rig("Cascade", cls.closure, manufacturer)
        cls.fiber_cable = rig.fiber_cable
        cls.tube = rig.tube

    def test_deleting_cable_entry_removes_tube_assignments(self):
        entry = ClosureCableEntry.objects.create(
            closure=self.closure, fiber_cable=self.fiber_cable, entrance_label="G1"
        )
        TubeAssignment.objects.create(closure=self.closure, tray=self.tray, buffer_tube=self.tube)
        assert TubeAssignment.objects.filter(closure=self.closure, buffer_tube=self.tube).exists()

        entry.delete()
        assert not TubeAssignment.objects.filter(closure=self.closure, buffer_tube=self.tube).exists()


class TestTrayProfileAPI(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.user = user_model.objects.create_superuser("apiuser_tp", "api_tp@test.com", "testpass")
        manufacturer = Manufacturer.objects.create(name="API Mfr TP", slug="api-mfr-tp")
        cls.module_type = ModuleType.objects.create(manufacturer=manufacturer, model="API Tray")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_create_tray_profile(self):
        url = reverse("plugins-api:netbox_fms-api:trayprofile-list")
        data = {"module_type": self.module_type.pk, "tray_role": "splice_tray"}
        response = self.client.post(url, data, format="json")
        assert response.status_code == 201

    def test_list_tray_profiles(self):
        TrayProfile.objects.create(module_type=self.module_type, tray_role=TrayRoleChoices.SPLICE_TRAY)
        url = reverse("plugins-api:netbox_fms-api:trayprofile-list")
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.json()["count"] == 1


class TestTubeAssignmentAPI(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.user = user_model.objects.create_superuser("apiuser_ta", "api_ta@test.com", "testpass")

        site = Site.objects.create(name="API TA Site", slug="api-ta-site")
        manufacturer = Manufacturer.objects.create(name="API TA Mfr", slug="api-ta-mfr")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="API Closure", slug="api-closure")
        role = DeviceRole.objects.create(name="API Closure", slug="api-closure")
        cls.closure = Device.objects.create(name="API-Closure", site=site, device_type=device_type, role=role)

        cls.tray = make_tray_module(cls.closure, make_tray_type(manufacturer, "API Tray TA"), "API Bay")

        rig = _make_tube_rig("API", cls.closure, manufacturer, entrance_label="G1")
        cls.fiber_cable = rig.fiber_cable
        cls.tube = rig.tube

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_create_tube_assignment(self):
        url = reverse("plugins-api:netbox_fms-api:tubeassignment-list")
        data = {
            "closure": self.closure.pk,
            "tray": self.tray.pk,
            "buffer_tube": self.tube.pk,
        }
        response = self.client.post(url, data, format="json")
        assert response.status_code == 201

    def test_list_tube_assignments(self):
        TubeAssignment.objects.create(closure=self.closure, tray=self.tray, buffer_tube=self.tube)
        url = reverse("plugins-api:netbox_fms-api:tubeassignment-list")
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.json()["count"] == 1


class TestBufferTubeClosureFilter(TestCase):
    """BufferTubeFilterSet.closure_id narrows tubes to cables entering a closure (#58)."""

    @classmethod
    def setUpTestData(cls):
        from dcim.models import Cable

        site = Site.objects.create(name="BTF Site", slug="btf-site")
        mfr = Manufacturer.objects.create(name="BTF Mfr", slug="btf-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="BTF Closure", slug="btf-closure")
        role = DeviceRole.objects.create(name="BTF Role", slug="btf-role")
        cls.closure_a = Device.objects.create(name="BTF-A", site=site, device_type=dt, role=role)
        cls.closure_b = Device.objects.create(name="BTF-B", site=site, device_type=dt, role=role)

        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="BTF-12F",
            construction="loose_tube",
            strand_count=12,
        )
        cable_a = FiberCable.objects.create(cable=Cable.objects.create(), fiber_cable_type=fct)
        cable_b = FiberCable.objects.create(cable=Cable.objects.create(), fiber_cable_type=fct)
        cls.tube_a = BufferTube.objects.create(fiber_cable=cable_a, name="BTF-T-A", position=1)
        cls.tube_b = BufferTube.objects.create(fiber_cable=cable_b, name="BTF-T-B", position=1)

        ClosureCableEntry.objects.create(closure=cls.closure_a, fiber_cable=cable_a, entrance_label="Gland A")
        ClosureCableEntry.objects.create(closure=cls.closure_b, fiber_cable=cable_b, entrance_label="Gland B")

    def test_closure_id_returns_only_entering_cables_tubes(self):
        from netbox_fms.filters import BufferTubeFilterSet

        qs = BufferTubeFilterSet({"closure_id": [self.closure_a.pk]}, queryset=BufferTube.objects.all()).qs
        assert set(qs) == {self.tube_a}

    def test_unfiltered_returns_all_tubes(self):
        from netbox_fms.filters import BufferTubeFilterSet

        qs = BufferTubeFilterSet({}, queryset=BufferTube.objects.all()).qs
        assert {self.tube_a, self.tube_b} <= set(qs)

    def test_form_buffer_tube_field_chains_on_closure(self):
        from netbox_fms.forms import TubeAssignmentForm

        field = TubeAssignmentForm().fields["buffer_tube"]
        assert field.query_params == {"closure_id": "$closure"}


def _make_tube_rig(prefix, closure, manufacturer, *, entrance_label=None):
    """FiberCableType -> Cable -> FiberCable -> BufferTube, plus an optional gland entry.

    The rig four classes in this file used to hand-roll; new tests should
    consume this instead of adding another copy.
    """
    from types import SimpleNamespace

    from dcim.models import Cable

    fct = FiberCableType.objects.create(
        manufacturer=manufacturer,
        model=f"{prefix} Cable",
        construction="loose_tube",
        strand_count=12,
    )
    fiber_cable = FiberCable.objects.create(cable=Cable.objects.create(), fiber_cable_type=fct)
    tube = BufferTube.objects.create(fiber_cable=fiber_cable, name=f"{prefix} Tube 1", position=1)
    entry = None
    if entrance_label is not None:
        entry = ClosureCableEntry.objects.create(
            closure=closure, fiber_cable=fiber_cable, entrance_label=entrance_label
        )
    return SimpleNamespace(fiber_cable=fiber_cable, tube=tube, entry=entry)


class TestTrayProfileRoleFlipGuard(TestCase):
    """A profile cannot leave the splice_tray role while assignments depend on it (issue #105)."""

    @classmethod
    def setUpTestData(cls):
        from tests.conftest import make_closure_with_tray

        rig = make_closure_with_tray("RF")
        cls.closure = rig.closure
        cls.tray = rig.tray
        cls.module_type = rig.tray.module_type
        cls.profile = TrayProfile.objects.create(module_type=cls.module_type, tray_role=TrayRoleChoices.SPLICE_TRAY)

        tube_rig = _make_tube_rig("RF", cls.closure, rig.mfr, entrance_label="RF Gland")
        cls.assignment = TubeAssignment.objects.create(
            closure=cls.closure, tray=cls.tray, buffer_tube=tube_rig.tube, position=1
        )

        # A second splice-tray profile with no assignments: the control case.
        cls.idle_mt = make_tray_type(rig.mfr, "RF Idle Tray")
        cls.idle_profile = cls.idle_mt.tray_profile

    def test_role_flip_blocked_while_assignments_exist(self):
        from django.core.exceptions import ValidationError

        self.profile.tray_role = TrayRoleChoices.EXPRESS_BASKET
        with self.assertRaises(ValidationError) as ctx:
            self.profile.full_clean()
        # The error must name the offending closure so the operator can act.
        assert "RF-Closure" in str(ctx.exception)

    def test_role_flip_allowed_without_assignments(self):
        self.idle_profile.tray_role = TrayRoleChoices.EXPRESS_BASKET
        self.idle_profile.full_clean()

    def test_new_express_profile_blocked_over_leftover_assignments(self):
        """Deleting the profile and recreating it as an express basket must be
        refused too: the leftover assignments make it the same orphan state.
        """
        from django.core.exceptions import ValidationError

        self.profile.delete()
        replacement = TrayProfile(module_type=self.module_type, tray_role=TrayRoleChoices.EXPRESS_BASKET)
        with self.assertRaises(ValidationError):
            replacement.full_clean()
