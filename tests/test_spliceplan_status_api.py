"""Status transitions on the splice plan REST endpoint.

Regression tests for issue #112: the visual splice editor's Save & Submit
flow transitions a draft plan to pending_approval with a plain PATCH, but
the serializer declared status read-only, so the write was silently
discarded. Making status writable must not open a side door around the
approve_spliceplan permission that the web transition view enforces.
"""

from dcim.models import Device
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from rest_framework.test import APIClient
from users.models import ObjectPermission

from netbox_fms.choices import SplicePlanStatusChoices
from netbox_fms.models import SplicePlan
from tests.conftest import make_infra

User = get_user_model()


def _plan_client(username, actions):
    """User + APIClient holding an ObjectPermission with ``actions`` on SplicePlan."""
    user = User.objects.create_user(username=username, password="x")  # noqa: S106
    perm = ObjectPermission.objects.create(name=f"perm-{username}", actions=actions)
    perm.object_types.set([ContentType.objects.get_for_model(SplicePlan)])
    perm.users.add(user)
    client = APIClient()
    client.force_authenticate(user=User.objects.get(pk=user.pk))
    return user, client


class TestSplicePlanStatusAPI(TestCase):
    """PATCHing status must honor the plan FSM and the approval permission."""

    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = make_infra("StatusAPI")
        cls.closure = Device.objects.create(name="StatusAPI-Closure", site=site, device_type=dt, role=role)
        cls.editor, cls.editor_client = _plan_client("status-editor", ["view", "add", "change"])
        cls.approver, cls.approver_client = _plan_client("status-approver", ["view", "change", "approve"])

    def _make_plan(self, status=SplicePlanStatusChoices.DRAFT, submitted_by=None):
        return SplicePlan.objects.create(
            closure=self.closure,
            name=f"Plan-{status}",
            status=status,
            submitted_by=submitted_by,
        )

    def _patch_status(self, client, plan, new_status):
        return client.patch(
            f"/api/plugins/fms/splice-plans/{plan.pk}/",
            {"status": new_status},
            format="json",
        )

    def test_submit_draft_sets_pending_and_submitted_by(self):
        """A change-permitted user submits a draft plan; submitted_by is filled in."""
        plan = self._make_plan()
        resp = self._patch_status(self.editor_client, plan, SplicePlanStatusChoices.PENDING_APPROVAL)
        assert resp.status_code == 200, resp.content
        plan.refresh_from_db()
        assert plan.status == SplicePlanStatusChoices.PENDING_APPROVAL
        assert plan.submitted_by == self.editor

    def test_approve_requires_approve_permission(self):
        plan = self._make_plan(SplicePlanStatusChoices.PENDING_APPROVAL, submitted_by=self.approver)
        resp = self._patch_status(self.editor_client, plan, SplicePlanStatusChoices.APPROVED)
        assert resp.status_code == 403, resp.content
        plan.refresh_from_db()
        assert plan.status == SplicePlanStatusChoices.PENDING_APPROVAL

    def test_approve_with_permission_succeeds(self):
        plan = self._make_plan(SplicePlanStatusChoices.PENDING_APPROVAL, submitted_by=self.editor)
        resp = self._patch_status(self.approver_client, plan, SplicePlanStatusChoices.APPROVED)
        assert resp.status_code == 200, resp.content
        plan.refresh_from_db()
        assert plan.status == SplicePlanStatusChoices.APPROVED

    def test_submitter_may_withdraw_without_approve_permission(self):
        plan = self._make_plan(SplicePlanStatusChoices.PENDING_APPROVAL, submitted_by=self.editor)
        resp = self._patch_status(self.editor_client, plan, SplicePlanStatusChoices.DRAFT)
        assert resp.status_code == 200, resp.content
        plan.refresh_from_db()
        assert plan.status == SplicePlanStatusChoices.DRAFT

    def test_non_submitter_may_not_reject_without_approve_permission(self):
        plan = self._make_plan(SplicePlanStatusChoices.PENDING_APPROVAL, submitted_by=self.approver)
        resp = self._patch_status(self.editor_client, plan, SplicePlanStatusChoices.DRAFT)
        assert resp.status_code == 403, resp.content
        plan.refresh_from_db()
        assert plan.status == SplicePlanStatusChoices.PENDING_APPROVAL

    def test_invalid_transition_rejected(self):
        plan = self._make_plan(SplicePlanStatusChoices.ARCHIVED)
        resp = self._patch_status(self.approver_client, plan, SplicePlanStatusChoices.APPROVED)
        assert resp.status_code == 400, resp.content
        plan.refresh_from_db()
        assert plan.status == SplicePlanStatusChoices.ARCHIVED

    def test_create_with_non_draft_status_rejected(self):
        resp = self.editor_client.post(
            "/api/plugins/fms/splice-plans/",
            {
                "name": "Sneaky Plan",
                "closure": self.closure.pk,
                "status": SplicePlanStatusChoices.APPROVED,
            },
            format="json",
        )
        assert resp.status_code == 400, resp.content
        assert not SplicePlan.objects.filter(name="Sneaky Plan").exists()
