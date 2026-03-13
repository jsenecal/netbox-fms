from dcim.models import (
    Device,
    DeviceRole,
    DeviceType,
    FrontPort,
    Manufacturer,
    Module,
    ModuleBay,
    ModuleType,
    Site,
)
from django.test import TestCase
from rest_framework.test import APIClient

from netbox_fms.models import SplicePlan, SplicePlanEntry


class TestBulkUpdateAPI(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="API Site", slug="api-site")
        mfr = Manufacturer.objects.create(name="API Mfr", slug="api-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Closure", slug="api-closure")
        role = DeviceRole.objects.create(name="API Role", slug="api-role")
        cls.closure = Device.objects.create(name="C-API", site=site, device_type=dt, role=role)

        mt = ModuleType.objects.create(manufacturer=mfr, model="Tray")
        bay = ModuleBay.objects.create(device=cls.closure, name="Bay 1")
        cls.tray = Module.objects.create(device=cls.closure, module_bay=bay, module_type=mt)

        cls.fp1 = FrontPort.objects.create(device=cls.closure, module=cls.tray, name="F1", type="lc")
        cls.fp2 = FrontPort.objects.create(device=cls.closure, module=cls.tray, name="F2", type="lc")
        cls.fp3 = FrontPort.objects.create(device=cls.closure, module=cls.tray, name="F3", type="lc")
        cls.fp4 = FrontPort.objects.create(device=cls.closure, module=cls.tray, name="F4", type="lc")

        cls.plan = SplicePlan.objects.create(closure=cls.closure, name="API Plan")

    def setUp(self):
        from django.contrib.auth import get_user_model

        user_model = get_user_model()
        self.user = user_model.objects.create_superuser("testadmin", "test@test.com", "password")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_bulk_add(self):
        url = f"/api/plugins/fms/splice-plans/{self.plan.pk}/bulk-update/"
        resp = self.client.post(
            url,
            {
                "add": [{"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk}],
                "remove": [],
            },
            format="json",
        )
        assert resp.status_code == 200, resp.content
        assert SplicePlanEntry.objects.filter(plan=self.plan).count() == 1

    def test_bulk_remove(self):
        SplicePlanEntry.objects.create(
            plan=self.plan,
            tray=self.tray,
            fiber_a=self.fp3,
            fiber_b=self.fp4,
        )
        url = f"/api/plugins/fms/splice-plans/{self.plan.pk}/bulk-update/"
        resp = self.client.post(
            url,
            {
                "add": [],
                "remove": [{"fiber_a": self.fp3.pk, "fiber_b": self.fp4.pk}],
            },
            format="json",
        )
        assert resp.status_code == 200, resp.content
        assert SplicePlanEntry.objects.filter(plan=self.plan).count() == 0

    def test_bulk_atomic_rollback(self):
        """Invalid add should rollback entire transaction."""
        url = f"/api/plugins/fms/splice-plans/{self.plan.pk}/bulk-update/"
        resp = self.client.post(
            url,
            {
                "add": [
                    {"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk},
                    {"fiber_a": 999999, "fiber_b": self.fp3.pk},  # Invalid
                ],
                "remove": [],
            },
            format="json",
        )
        assert resp.status_code == 400
        assert SplicePlanEntry.objects.filter(plan=self.plan).count() == 0
