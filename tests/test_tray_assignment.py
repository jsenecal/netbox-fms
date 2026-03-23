"""Tests for TrayProfile and TubeAssignment models."""

from django.test import TestCase
from django.db import IntegrityError
from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, ModuleType, Module, Site

from netbox_fms.choices import TrayRoleChoices
from netbox_fms.models import TrayProfile, TubeAssignment, FiberCableType, FiberCable, BufferTube, ClosureCableEntry


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

        from dcim.models import ModuleBay

        # Create module type with tray profile
        cls.module_type = ModuleType.objects.create(manufacturer=manufacturer, model="24F Tray")
        cls.tray_profile = TrayProfile.objects.create(
            module_type=cls.module_type, tray_role=TrayRoleChoices.SPLICE_TRAY
        )
        bay1 = ModuleBay.objects.create(device=cls.closure, name="Bay 1")
        cls.tray = Module.objects.create(device=cls.closure, module_bay=bay1, module_type=cls.module_type)

        # Express basket module type
        cls.express_mt = ModuleType.objects.create(manufacturer=manufacturer, model="Express Basket")
        TrayProfile.objects.create(module_type=cls.express_mt, tray_role=TrayRoleChoices.EXPRESS_BASKET)
        bay2 = ModuleBay.objects.create(device=cls.closure, name="Bay 2")
        cls.express_module = Module.objects.create(device=cls.closure, module_bay=bay2, module_type=cls.express_mt)

        # No-profile module type
        cls.plain_mt = ModuleType.objects.create(manufacturer=manufacturer, model="Plain Module")
        bay3 = ModuleBay.objects.create(device=cls.closure, name="Bay 3")
        cls.plain_module = Module.objects.create(device=cls.closure, module_bay=bay3, module_type=cls.plain_mt)

        # Fiber cable with buffer tube
        fct = FiberCableType.objects.create(
            manufacturer=manufacturer, model="12F Cable", construction="loose_tube",
            fiber_type="smf_os2", strand_count=12,
        )
        from dcim.models import Cable
        cable = Cable.objects.create()
        cls.fiber_cable = FiberCable.objects.create(cable=cable, fiber_cable_type=fct)
        cls.tube = BufferTube.objects.create(fiber_cable=cls.fiber_cable, name="Tube 1", position=1)

        # ClosureCableEntry prerequisite
        cls.cable_entry = ClosureCableEntry.objects.create(
            closure=cls.closure, fiber_cable=cls.fiber_cable, entrance_label="Gland A"
        )

    def test_create_tube_assignment(self):
        ta = TubeAssignment.objects.create(
            closure=self.closure, tray=self.tray, buffer_tube=self.tube,
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
        from django.core.exceptions import ValidationError
        from dcim.models import ModuleBay
        other_site = Site.objects.create(name="Other Site", slug="other-site")
        other_dt = DeviceType.objects.create(
            manufacturer=Manufacturer.objects.first(), model="Other DT", slug="other-dt"
        )
        other_device = Device.objects.create(
            name="Other", site=other_site, device_type=other_dt,
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
            manufacturer=Manufacturer.objects.first(), model="Other Cable",
            construction="loose_tube", fiber_type="smf_os2", strand_count=12,
        )
        from dcim.models import Cable
        cable2 = Cable.objects.create()
        fc2 = FiberCable.objects.create(cable=cable2, fiber_cable_type=fct2)
        tube2 = BufferTube.objects.create(fiber_cable=fc2, name="Tube X", position=1)
        ta = TubeAssignment(closure=self.closure, tray=self.tray, buffer_tube=tube2)
        with self.assertRaises(ValidationError):
            ta.full_clean()
