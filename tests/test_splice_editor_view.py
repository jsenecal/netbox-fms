"""
Tests for the splice editor's supporting views.

Covers the closure plan counts the editor reads for its preflight warnings
(issue #115) and the quick-add form fragment its create-plan modal injects
(issue #114).
"""

import re

from dcim.models import Device
from django.contrib.auth import get_user_model
from django.test import TestCase

from netbox_fms.choices import SplicePlanStatusChoices
from netbox_fms.models import SplicePlan
from tests.conftest import make_closure_with_tray, make_infra

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


class TestSplicePlanQuickAddForm(TestCase):
    """The quick-add modal fragment must contain usable inputs.

    Regression tests for issue #114: the fragment rendered fieldset layout
    items as if they were bound fields, so the injected modal showed no
    inputs at all.
    """

    @classmethod
    def setUpTestData(cls):
        infra = make_closure_with_tray("QAF")
        cls.closure = infra.closure
        cls.user = User.objects.create_user(username="qaf_user", password="testpass", is_superuser=True)

    def setUp(self):
        self.client.force_login(self.user)

    def _get_form_html(self):
        response = self.client.get(f"/plugins/fms/splice-plans/quick-add-form/?closure_id={self.closure.pk}")
        assert response.status_code == 200
        return response.content.decode()

    def test_form_renders_hidden_closure_prefilled_from_context(self):
        html = self._get_form_html()
        closure_inputs = [
            tag for tag in re.findall(r"<input[^>]*>", html) if 'name="closure"' in tag and 'type="hidden"' in tag
        ]
        assert closure_inputs, f"no hidden closure input rendered: {html!r}"
        assert f'value="{self.closure.pk}"' in closure_inputs[0]

    def test_form_renders_a_required_name_input(self):
        html = self._get_form_html()
        name_inputs = [tag for tag in re.findall(r"<input[^>]*>", html) if 'name="name"' in tag]
        assert name_inputs, f"no name input rendered: {html!r}"
        assert "required" in name_inputs[0]

    def test_form_carries_no_dynamic_select_widgets(self):
        """Dynamic selects need NetBox JS that never runs on injected markup."""
        html = self._get_form_html()
        assert "data-url" not in html
        assert "tomselect" not in html.lower()

    def test_rendered_fields_create_a_draft_plan_for_the_closure(self):
        """The rendered inputs are exactly what the modal POSTs to quick-add."""
        html = self._get_form_html()
        data = dict(re.findall(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', html))
        for field_name in re.findall(r'<(?:input|textarea)[^>]*name="([^"]+)"', html):
            data.setdefault(field_name, "")
        data.pop("csrfmiddlewaretoken", None)
        data["name"] = "Quick Plan"

        response = self.client.post("/api/plugins/fms/splice-plans/quick-add/", data)
        assert response.status_code == 201, response.content

        plan = SplicePlan.objects.get(name="Quick Plan")
        assert plan.closure_id == self.closure.pk
        assert plan.status == SplicePlanStatusChoices.DRAFT
