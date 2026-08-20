"""Tests for carrying the express flag through the splice editor backend.

Regression tests for issue #117: the visual splice editor had no way to set
SplicePlanEntry.is_express, and the bulk-update endpoint silently dropped it.
"""

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
    Site,
)
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from netbox_fms.choices import SplicePlanStatusChoices
from netbox_fms.models import FiberCable, FiberCableType, SplicePlan, SplicePlanEntry

User = get_user_model()


class TestBulkUpdateExpressFlag(TestCase):
    """bulk_update_entries must accept and persist is_express on added entries."""

    def setUp(self):
        site = Site.objects.create(name="EX Site", slug="ex-site")
        mfr = Manufacturer.objects.create(name="EX Mfr", slug="ex-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="EX Closure", slug="ex-closure")
        role = DeviceRole.objects.create(name="EX Role", slug="ex-role")
        self.closure = Device.objects.create(name="EX-Closure", site=site, device_type=dt, role=role)

        mt = ModuleType.objects.create(manufacturer=mfr, model="EX Tray")
        bay = ModuleBay.objects.create(device=self.closure, name="Bay 1")
        self.tray = Module.objects.create(device=self.closure, module_bay=bay, module_type=mt)

        self.fp1 = FrontPort.objects.create(device=self.closure, module=self.tray, name="F1", type="splice")
        self.fp2 = FrontPort.objects.create(device=self.closure, module=self.tray, name="F2", type="splice")

        self.plan = SplicePlan.objects.create(
            closure=self.closure,
            name="EX Plan",
            status=SplicePlanStatusChoices.DRAFT,
        )

        self.user = User.objects.create_superuser(username="ex-user", password="test")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = f"/api/plugins/fms/splice-plans/{self.plan.pk}/bulk-update/"

    def _post(self, add):
        return self.client.post(
            self.url,
            {"add": add, "remove": []},
            format="json",
            HTTP_X_CHANGELOG_MESSAGE="express flag test",
        )

    def test_add_with_is_express_persists(self):
        resp = self._post([{"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk, "is_express": True}])
        assert resp.status_code == 200
        entry = SplicePlanEntry.objects.get(plan=self.plan, fiber_a=self.fp1, fiber_b=self.fp2)
        assert entry.is_express is True

    def test_add_defaults_to_not_express(self):
        resp = self._post([{"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk}])
        assert resp.status_code == 200
        entry = SplicePlanEntry.objects.get(plan=self.plan, fiber_a=self.fp1, fiber_b=self.fp2)
        assert entry.is_express is False

    def test_re_add_updates_express_on_existing_entry(self):
        """Re-adding the same fiber pair with a new flag replaces the entry."""
        self._post([{"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk}])
        resp = self._post([{"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk, "is_express": True}])
        assert resp.status_code == 200
        entry = SplicePlanEntry.objects.get(plan=self.plan, fiber_a=self.fp1, fiber_b=self.fp2)
        assert entry.is_express is True

    def test_response_entries_include_is_express(self):
        resp = self._post([{"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk, "is_express": True}])
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        assert len(entries) == 1
        assert entries[0]["is_express"] is True


class TestClosureStrandsExpressExposure(TestCase):
    """The closure-strands view must expose the plan entry's express flag."""

    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="EXS Site", slug="exs-site")
        mfr = Manufacturer.objects.create(name="EXS Mfr", slug="exs-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="EXS Closure", slug="exs-closure")
        role = DeviceRole.objects.create(name="EXS Role", slug="exs-role")
        cls.closure = Device.objects.create(name="EXS-1", site=site, device_type=dt, role=role)
        far_device = Device.objects.create(name="EXS-Far", site=site, device_type=dt, role=role)

        mt = ModuleType.objects.create(manufacturer=mfr, model="EXS Tray")
        bay = ModuleBay.objects.create(device=cls.closure, name="Bay 1")
        tray = Module.objects.create(device=cls.closure, module_bay=bay, module_type=mt)

        fps = [
            FrontPort.objects.create(device=cls.closure, module=tray, name=f"EXS-F{i}", type="splice")
            for i in range(1, 5)
        ]
        far_fp = FrontPort.objects.create(device=far_device, name="EXS-Far-FP", type="lc")
        cable = Cable.objects.create(a_terminations=[fps[0]], b_terminations=[far_fp])
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="EXS-TB4", strand_count=4, construction="tight_buffer"
        )
        fc = FiberCable.objects.create(cable=cable, fiber_cable_type=fct)

        cls.strands = list(fc.fiber_strands.order_by("position"))
        for strand, fp in zip(cls.strands, fps, strict=True):
            strand.front_port_a = fp
            strand.save()

        cls.plan = SplicePlan.objects.create(
            closure=cls.closure,
            name="EXS Plan",
            status=SplicePlanStatusChoices.DRAFT,
        )
        SplicePlanEntry.objects.create(plan=cls.plan, tray=tray, fiber_a=fps[0], fiber_b=fps[1], is_express=True)
        SplicePlanEntry.objects.create(plan=cls.plan, tray=tray, fiber_a=fps[2], fiber_b=fps[3])

    def setUp(self):
        user = User.objects.create_superuser(username="exs-user", password="test")
        self.client = APIClient()
        self.client.force_authenticate(user=user)

    def test_plan_is_express_exposed_per_strand(self):
        resp = self.client.get(f"/api/plugins/fms/closure-strands/{self.closure.pk}/?plan_id={self.plan.pk}")
        assert resp.status_code == 200
        strands = {s["id"]: s for s in resp.data["cables"][0]["loose_strands"]}
        express_pair = (self.strands[0].pk, self.strands[1].pk)
        normal_pair = (self.strands[2].pk, self.strands[3].pk)
        for pk in express_pair:
            assert strands[pk]["plan_is_express"] is True
        for pk in normal_pair:
            assert strands[pk]["plan_is_express"] is False
