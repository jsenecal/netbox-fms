"""Tests for TrayProfile and TubeAssignment models."""

from django.test import TestCase
from django.db import IntegrityError
from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, ModuleType, Module, Site

from netbox_fms.choices import TrayRoleChoices
from netbox_fms.models import TrayProfile


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
