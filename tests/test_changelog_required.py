"""Tests for required changelog message on bulk_update_entries."""
from dcim.models import Device, DeviceRole, DeviceType, FrontPort, Manufacturer, Module, ModuleBay, ModuleType, Site
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

User = get_user_model()

from netbox_fms.choices import SplicePlanStatusChoices
from netbox_fms.models import SplicePlan, SplicePlanEntry


class TestChangelogRequired(TestCase):
    """Test that bulk_update_entries requires X-Changelog-Message header."""

    def setUp(self):
        site = Site.objects.create(name="CL Site", slug="cl-site")
        mfr = Manufacturer.objects.create(name="CL Mfr", slug="cl-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="CL Closure", slug="cl-closure")
        role = DeviceRole.objects.create(name="CL Role", slug="cl-role")
        self.closure = Device.objects.create(name="CL-Closure", site=site, device_type=dt, role=role)

        mt = ModuleType.objects.create(manufacturer=mfr, model="CL Tray")
        bay = ModuleBay.objects.create(device=self.closure, name="Bay 1")
        self.tray = Module.objects.create(device=self.closure, module_bay=bay, module_type=mt)

        self.fp1 = FrontPort.objects.create(device=self.closure, module=self.tray, name="F1", type="splice")
        self.fp2 = FrontPort.objects.create(device=self.closure, module=self.tray, name="F2", type="splice")
        self.fp3 = FrontPort.objects.create(device=self.closure, module=self.tray, name="F3", type="splice")
        self.fp4 = FrontPort.objects.create(device=self.closure, module=self.tray, name="F4", type="splice")

        self.plan = SplicePlan.objects.create(
            closure=self.closure, name="CL Plan", status=SplicePlanStatusChoices.DRAFT,
        )

        self.user = User.objects.create_superuser(username="cl-user", password="test")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = f"/api/plugins/fms/splice-plans/{self.plan.pk}/bulk-update/"

    def test_rejects_missing_changelog_message(self):
        """POST without X-Changelog-Message header returns 400."""
        resp = self.client.post(
            self.url,
            {"add": [{"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk}], "remove": []},
            format="json",
        )
        assert resp.status_code == 400
        assert "changelog message" in resp.json()["error"].lower()

    def test_rejects_empty_changelog_message(self):
        """POST with empty X-Changelog-Message header returns 400."""
        resp = self.client.post(
            self.url,
            {"add": [{"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk}], "remove": []},
            format="json",
            HTTP_X_CHANGELOG_MESSAGE="",
        )
        assert resp.status_code == 400

    def test_rejects_whitespace_only_changelog_message(self):
        """POST with whitespace-only changelog message returns 400."""
        resp = self.client.post(
            self.url,
            {"add": [{"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk}], "remove": []},
            format="json",
            HTTP_X_CHANGELOG_MESSAGE="   ",
        )
        assert resp.status_code == 400

    def test_accepts_valid_changelog_message(self):
        """POST with valid changelog message succeeds."""
        resp = self.client.post(
            self.url,
            {"add": [{"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk}], "remove": []},
            format="json",
            HTTP_X_CHANGELOG_MESSAGE="Rewired T1 fibers",
        )
        assert resp.status_code == 200

    def test_change_note_saved_on_entries(self):
        """Entries created via bulk_update_entries should have change_note set."""
        msg = "Initial splice configuration"
        self.client.post(
            self.url,
            {"add": [{"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk}], "remove": []},
            format="json",
            HTTP_X_CHANGELOG_MESSAGE=msg,
        )
        entry = SplicePlanEntry.objects.get(plan=self.plan, fiber_a=self.fp1, fiber_b=self.fp2)
        assert entry.change_note == msg
