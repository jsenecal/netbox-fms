"""Regression tests for issue #111: applying a splice plan must honour the
approval workflow.

The API apply action previously required only change_spliceplan and never
checked plan status, so a draft plan could be applied straight to the live
closure. Applying now requires an approved plan AND the approve_spliceplan
permission, and a successful apply archives the plan.
"""

from dcim.models import Cable
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient
from users.models import ObjectPermission

from netbox_fms.choices import SplicePlanStatusChoices
from netbox_fms.models import SplicePlan, SplicePlanEntry
from netbox_fms.services import apply_diff
from tests.conftest import make_closure_with_tray

User = get_user_model()


def _client_with_actions(username, actions):
    """API client for a non-superuser holding the given SplicePlan actions."""
    user = User.objects.create_user(username=username, password="x")  # noqa: S106
    perm = ObjectPermission.objects.create(name=f"perm-{username}", actions=actions)
    perm.object_types.add(ContentType.objects.get_for_model(SplicePlan))
    perm.users.add(user)
    client = APIClient()
    # Re-fetch so no stale permission cache rides along on the user instance
    client.force_authenticate(user=User.objects.get(pk=user.pk))
    return client


class TestApplyApprovalGatingAPI(TestCase):
    """POST /api/plugins/fms/splice-plans/{pk}/apply/ gating (issue #111)."""

    @classmethod
    def setUpTestData(cls):
        cls.rig = make_closure_with_tray("AAG")

    def _make_plan(self, name, status, **kwargs):
        plan = SplicePlan.objects.create(closure=self.rig.closure, name=name, status=status, **kwargs)
        SplicePlanEntry.objects.create(
            plan=plan,
            tray=self.rig.tray,
            fiber_a=self.rig.ports[0],
            fiber_b=self.rig.ports[1],
        )
        return plan

    def _apply(self, client, plan):
        return client.post(f"/api/plugins/fms/splice-plans/{plan.pk}/apply/", format="json")

    def test_apply_draft_plan_rejected(self):
        """A draft plan cannot be applied, even by an approver."""
        plan = self._make_plan("AAG Draft", SplicePlanStatusChoices.DRAFT)
        client = _client_with_actions("aag-approver-draft", ["view", "add", "change", "approve"])

        resp = self._apply(client, plan)

        assert resp.status_code == 409, resp.content
        assert "approved" in resp.json()["error"].lower()
        plan.refresh_from_db()
        assert plan.status == SplicePlanStatusChoices.DRAFT
        assert Cable.objects.count() == 0

    def test_apply_pending_approval_plan_rejected(self):
        """A plan awaiting approval cannot be applied."""
        submitter = User.objects.create_user(username="aag-submitter", password="x")  # noqa: S106
        plan = self._make_plan(
            "AAG Pending",
            SplicePlanStatusChoices.PENDING_APPROVAL,
            submitted_by=submitter,
        )
        client = _client_with_actions("aag-approver-pending", ["view", "add", "change", "approve"])

        resp = self._apply(client, plan)

        assert resp.status_code == 409, resp.content
        plan.refresh_from_db()
        assert plan.status == SplicePlanStatusChoices.PENDING_APPROVAL
        assert Cable.objects.count() == 0

    def test_apply_archived_plan_rejected(self):
        """An archived plan cannot be re-applied."""
        plan = self._make_plan("AAG Archived", SplicePlanStatusChoices.ARCHIVED)
        client = _client_with_actions("aag-approver-archived", ["view", "add", "change", "approve"])

        resp = self._apply(client, plan)

        assert resp.status_code == 409, resp.content
        plan.refresh_from_db()
        assert plan.status == SplicePlanStatusChoices.ARCHIVED
        assert Cable.objects.count() == 0

    def test_apply_without_approve_permission_forbidden(self):
        """change_spliceplan alone is not enough to apply an approved plan."""
        plan = self._make_plan("AAG NoApprove", SplicePlanStatusChoices.APPROVED)
        client = _client_with_actions("aag-editor", ["view", "add", "change"])

        resp = self._apply(client, plan)

        assert resp.status_code == 403, resp.content
        plan.refresh_from_db()
        assert plan.status == SplicePlanStatusChoices.APPROVED
        assert Cable.objects.count() == 0

    def test_apply_approved_plan_succeeds_and_archives(self):
        """An approver applying an approved plan commits the diff and archives it."""
        plan = self._make_plan("AAG Approved", SplicePlanStatusChoices.APPROVED)
        client = _client_with_actions("aag-approver-ok", ["view", "add", "change", "approve"])

        resp = self._apply(client, plan)

        assert resp.status_code == 200, resp.content
        assert resp.json() == {"added": 1, "removed": 0}
        plan.refresh_from_db()
        assert plan.status == SplicePlanStatusChoices.ARCHIVED
        assert Cable.objects.count() == 1


class TestApplyDiffStatusGate(TestCase):
    """apply_diff() itself refuses non-approved plans (issue #111)."""

    @classmethod
    def setUpTestData(cls):
        cls.rig = make_closure_with_tray("AAGS")

    def test_apply_diff_rejects_draft_plan(self):
        """The service layer blocks applying a draft plan on every code path."""
        plan = SplicePlan.objects.create(
            closure=self.rig.closure,
            name="AAGS Draft",
            status=SplicePlanStatusChoices.DRAFT,
        )
        SplicePlanEntry.objects.create(
            plan=plan,
            tray=self.rig.tray,
            fiber_a=self.rig.ports[0],
            fiber_b=self.rig.ports[1],
        )

        with self.assertRaises(ValidationError):
            apply_diff(plan)

        plan.refresh_from_db()
        assert plan.status == SplicePlanStatusChoices.DRAFT
        assert Cable.objects.count() == 0
