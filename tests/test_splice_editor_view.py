"""
Tests for the closure plan counts exposed to the splice editor.

Regression tests for issue #115: the editor needs to know how many splice
plans (and how many draft plans) exist for the closure so it can show
preflight warnings when no plan, or only non-draft plans, exist.
"""

from dcim.models import Device
from django.contrib.auth import get_user_model
from django.test import TestCase

from netbox_fms.choices import SplicePlanStatusChoices
from netbox_fms.models import SplicePlan
from tests.conftest import make_infra

User = get_user_model()


class TestDeviceSpliceEditorPlanCounts(TestCase):
    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = make_infra("SEV")
        cls.device = Device.objects.create(name="SEV-Closure", site=site, device_type=dt, role=role)
        cls.user = User.objects.create_user(username="sev_user", password="testpass", is_superuser=True)

    def setUp(self):
        self.client.force_login(self.user)

    def _get_context(self):
        response = self.client.get(f"/dcim/devices/{self.device.pk}/splice-editor/")
        assert response.status_code == 200
        return response.context

    def test_counts_are_zero_without_plans(self):
        context = self._get_context()
        assert context["closure_plan_count"] == 0
        assert context["closure_draft_plan_count"] == 0

    def test_counts_with_only_non_draft_plans(self):
        SplicePlan.objects.create(closure=self.device, name="Archived", status=SplicePlanStatusChoices.ARCHIVED)
        context = self._get_context()
        assert context["closure_plan_count"] == 1
        assert context["closure_draft_plan_count"] == 0

    def test_counts_include_draft_plans(self):
        SplicePlan.objects.create(closure=self.device, name="Old", status=SplicePlanStatusChoices.ARCHIVED)
        SplicePlan.objects.create(closure=self.device, name="New", status=SplicePlanStatusChoices.DRAFT)
        context = self._get_context()
        assert context["closure_plan_count"] == 2
        assert context["closure_draft_plan_count"] == 1


class TestPlanSpliceEditorPlanCounts(TestCase):
    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = make_infra("SPV")
        cls.device = Device.objects.create(name="SPV-Closure", site=site, device_type=dt, role=role)
        cls.plan = SplicePlan.objects.create(closure=cls.device, name="Plan A", status=SplicePlanStatusChoices.ARCHIVED)
        cls.user = User.objects.create_user(username="spv_user", password="testpass", is_superuser=True)

    def test_counts_cover_all_plans_for_the_closure(self):
        SplicePlan.objects.create(closure=self.device, name="Plan B", status=SplicePlanStatusChoices.DRAFT)
        self.client.force_login(self.user)
        response = self.client.get(f"/plugins/fms/splice-plans/{self.plan.pk}/editor/")
        assert response.status_code == 200
        assert response.context["closure_plan_count"] == 2
        assert response.context["closure_draft_plan_count"] == 1
