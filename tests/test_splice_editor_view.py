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


class TestDeviceSpliceEditorPlanSelection(TestCase):
    """
    Regression tests for issue #113: the device splice editor loaded an
    arbitrary splice plan (archived or the wrong draft) because selection
    used an unordered, unfiltered .first().
    """

    @classmethod
    def setUpTestData(cls):
        rig = make_closure_with_tray("SEL")
        cls.closure = rig.closure
        other = make_closure_with_tray("OTH")
        cls.other_closure = other.closure
        cls.user = User.objects.create_user(username="sel_user", password="testpass", is_superuser=True)

    def setUp(self):
        self.client.force_login(self.user)

    def _get(self, query=""):
        return self.client.get(f"/dcim/devices/{self.closure.pk}/splice-editor/{query}")

    def _make_plan(self, name, status=SplicePlanStatusChoices.DRAFT, closure=None):
        return SplicePlan.objects.create(closure=closure or self.closure, name=name, status=status)

    def test_draft_plan_wins_over_archived_plan(self):
        archived = self._make_plan("Archived", SplicePlanStatusChoices.ARCHIVED)
        draft = self._make_plan("Draft")
        response = self._get()
        assert response.status_code == 200
        assert response.context["plan"].pk == draft.pk
        assert response.context["plan"].pk != archived.pk
        assert response.context["is_readonly"] is False

    def test_multiple_drafts_pick_the_oldest_by_pk(self):
        first = self._make_plan("First draft")
        self._make_plan("Second draft")
        response = self._get()
        assert response.context["plan"].pk == first.pk

    def test_multiple_drafts_expose_and_render_a_selector(self):
        first = self._make_plan("First draft")
        second = self._make_plan("Second draft")
        response = self._get()
        assert [p.pk for p in response.context["closure_draft_plans"]] == [first.pk, second.pk]
        self.assertContains(response, f"?plan={second.pk}")

    def test_single_draft_renders_no_selector(self):
        only = self._make_plan("Only draft")
        response = self._get()
        assert [p.pk for p in response.context["closure_draft_plans"]] == [only.pk]
        self.assertNotContains(response, f"?plan={only.pk}")

    def test_plan_query_parameter_selects_that_plan(self):
        self._make_plan("First draft")
        second = self._make_plan("Second draft")
        response = self._get(f"?plan={second.pk}")
        assert response.context["plan"].pk == second.pk

    def test_plan_query_parameter_can_select_a_non_draft_plan(self):
        self._make_plan("Draft")
        archived = self._make_plan("Archived", SplicePlanStatusChoices.ARCHIVED)
        response = self._get(f"?plan={archived.pk}")
        assert response.context["plan"].pk == archived.pk
        assert response.context["is_readonly"] is True

    def test_plan_from_another_closure_is_not_found(self):
        self._make_plan("Draft")
        foreign = self._make_plan("Foreign", closure=self.other_closure)
        assert self._get(f"?plan={foreign.pk}").status_code == 404

    def test_unparsable_plan_parameter_is_not_found(self):
        self._make_plan("Draft")
        assert self._get("?plan=not-a-number").status_code == 404

    def test_only_non_draft_plans_load_read_only_with_a_warning(self):
        self._make_plan("Archived", SplicePlanStatusChoices.ARCHIVED)
        response = self._get()
        assert response.context["is_readonly"] is True
        self.assertContains(response, "readOnly: true")
        self.assertContains(response, "cannot be edited")
        self.assertContains(response, f"/plugins/fms/splice-plans/add/?closure={self.closure.pk}")

    def test_pending_approval_beats_archived_when_no_draft_exists(self):
        self._make_plan("Archived", SplicePlanStatusChoices.ARCHIVED)
        pending = self._make_plan("Pending", SplicePlanStatusChoices.PENDING_APPROVAL)
        response = self._get()
        assert response.context["plan"].pk == pending.pk

    def test_no_plans_leaves_the_editor_writable_for_quick_add(self):
        response = self._get()
        assert response.context["plan"] is None
        assert response.context["is_readonly"] is False
        assert response.context["context_mode"] == "view"


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
