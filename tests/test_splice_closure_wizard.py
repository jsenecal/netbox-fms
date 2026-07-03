"""Tests for the splice closure creation wizard (service, form, view)."""

from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Module, ModuleBay, ModuleType, Site
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from netbox_fms.choices import TrayRoleChoices
from netbox_fms.forms import SpliceClosureCreateForm
from netbox_fms.models import TrayProfile
from netbox_fms.services import create_splice_closure


class TestCreateSpliceClosure(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name="Wizard Site", slug="wizard-site")
        mfr = Manufacturer.objects.create(name="Wizard Mfr", slug="wizard-mfr")
        cls.device_type = DeviceType.objects.create(manufacturer=mfr, model="FOSC 450", slug="fosc-450")
        cls.role = DeviceRole.objects.create(name="Splice Closure", slug="splice-closure")
        cls.tray_mt = ModuleType.objects.create(manufacturer=mfr, model="24F Tray")
        TrayProfile.objects.create(module_type=cls.tray_mt, tray_role=TrayRoleChoices.SPLICE_TRAY)
        cls.basket_mt = ModuleType.objects.create(manufacturer=mfr, model="Express Basket")
        TrayProfile.objects.create(module_type=cls.basket_mt, tray_role=TrayRoleChoices.EXPRESS_BASKET)

    def test_creates_device_with_named_tray_bays_and_modules(self):
        device = create_splice_closure(
            name="Closure-W1",
            site=self.site,
            device_type=self.device_type,
            role=self.role,
            status="active",
            tray_module_type=self.tray_mt,
            tray_count=3,
        )
        bays = ModuleBay.objects.filter(device=device).order_by("name")
        assert [b.name for b in bays] == ["Tray 1", "Tray 2", "Tray 3"]
        modules = Module.objects.filter(device=device)
        assert modules.count() == 3
        assert all(m.module_type == self.tray_mt for m in modules)

    def test_creates_optional_basket_bays(self):
        device = create_splice_closure(
            name="Closure-W2",
            site=self.site,
            device_type=self.device_type,
            role=self.role,
            status="active",
            tray_module_type=self.tray_mt,
            tray_count=2,
            basket_module_type=self.basket_mt,
            basket_count=1,
        )
        names = set(ModuleBay.objects.filter(device=device).values_list("name", flat=True))
        assert names == {"Tray 1", "Tray 2", "Basket 1"}
        assert Module.objects.filter(device=device, module_type=self.basket_mt).count() == 1

    def test_no_basket_bays_without_basket_type(self):
        device = create_splice_closure(
            name="Closure-W3",
            site=self.site,
            device_type=self.device_type,
            role=self.role,
            status="active",
            tray_module_type=self.tray_mt,
            tray_count=1,
            basket_count=2,  # ignored without basket_module_type
        )
        assert not ModuleBay.objects.filter(device=device, name__startswith="Basket").exists()

    def test_validation_failure_creates_nothing(self):
        create_splice_closure(
            name="Closure-DUP",
            site=self.site,
            device_type=self.device_type,
            role=self.role,
            status="active",
            tray_module_type=self.tray_mt,
            tray_count=1,
        )
        with self.assertRaises(ValidationError):
            create_splice_closure(
                name="Closure-DUP",  # duplicate name at same site
                site=self.site,
                device_type=self.device_type,
                role=self.role,
                status="active",
                tray_module_type=self.tray_mt,
                tray_count=5,
            )
        # exactly the first closure's objects exist; the failed call left nothing
        assert Device.objects.filter(name="Closure-DUP").count() == 1
        assert ModuleBay.objects.filter(device__name="Closure-DUP").count() == 1


class TestSpliceClosureCreateForm(TestCase):
    @classmethod
    def setUpTestData(cls):
        mfr = Manufacturer.objects.create(name="Form Mfr", slug="form-mfr")
        cls.tray_mt = ModuleType.objects.create(manufacturer=mfr, model="Form 24F Tray")
        TrayProfile.objects.create(module_type=cls.tray_mt, tray_role=TrayRoleChoices.SPLICE_TRAY)
        cls.basket_mt = ModuleType.objects.create(manufacturer=mfr, model="Form Basket")
        TrayProfile.objects.create(module_type=cls.basket_mt, tray_role=TrayRoleChoices.EXPRESS_BASKET)
        cls.plain_mt = ModuleType.objects.create(manufacturer=mfr, model="Form Plain Module")

    def test_tray_queryset_only_offers_splice_tray_profiles(self):
        form = SpliceClosureCreateForm()
        qs = form.fields["tray_module_type"].queryset
        assert self.tray_mt in qs
        assert self.basket_mt not in qs
        assert self.plain_mt not in qs

    def test_basket_queryset_only_offers_express_basket_profiles(self):
        form = SpliceClosureCreateForm()
        qs = form.fields["basket_module_type"].queryset
        assert self.basket_mt in qs
        assert self.tray_mt not in qs
        assert self.plain_mt not in qs


class TestSpliceClosureCreateView(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name="View Site", slug="view-site")
        mfr = Manufacturer.objects.create(name="View Mfr", slug="view-mfr")
        cls.device_type = DeviceType.objects.create(manufacturer=mfr, model="View FOSC", slug="view-fosc")
        cls.role = DeviceRole.objects.create(name="View Closure", slug="view-closure")
        cls.tray_mt = ModuleType.objects.create(manufacturer=mfr, model="View 24F Tray")
        TrayProfile.objects.create(module_type=cls.tray_mt, tray_role=TrayRoleChoices.SPLICE_TRAY)
        cls.url = reverse("plugins:netbox_fms:spliceclosure_add")

    def test_permission_gate_returns_403_without_dcim_perms(self):
        User = get_user_model()
        user = User.objects.create_user("wizard-nobody", "n@test.com", "password")
        self.client.force_login(user)
        assert self.client.get(self.url).status_code == 403

    def test_post_creates_closure_and_redirects_to_fiber_overview(self):
        User = get_user_model()
        admin = User.objects.create_superuser("wizard-admin", "a@test.com", "password")
        self.client.force_login(admin)
        response = self.client.post(
            self.url,
            {
                "name": "Closure-V1",
                "site": self.site.pk,
                "device_type": self.device_type.pk,
                "role": self.role.pk,
                "status": "active",
                "tray_module_type": self.tray_mt.pk,
                "tray_count": 2,
                "basket_count": 1,
            },
        )
        device = Device.objects.get(name="Closure-V1")
        assert ModuleBay.objects.filter(device=device).count() == 2
        assert response.status_code == 302
        assert response.url.endswith(f"/dcim/devices/{device.pk}/fiber-overview/")
