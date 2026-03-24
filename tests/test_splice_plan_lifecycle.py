from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TransactionTestCase
from rest_framework.test import APIClient
from users.models import ObjectPermission

from netbox_fms.choices import SplicePlanStatusChoices
from netbox_fms.models import SplicePlan

User = get_user_model()


class TestSplicePlanFSM(TransactionTestCase):
    """Test splice plan status transition validation."""

    def setUp(self):
        site = Site.objects.create(name="FSM Site", slug="fsm-site")
        mfr = Manufacturer.objects.create(name="FSM Mfr", slug="fsm-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="FSM Closure", slug="fsm-closure")
        role = DeviceRole.objects.create(name="FSM Role", slug="fsm-role")
        self.closure = Device.objects.create(name="FSM-Closure", site=site, device_type=dt, role=role)
        self.user = User.objects.create_user(username="fsm-user", password="test")

    def _make_plan(self, status=SplicePlanStatusChoices.DRAFT):
        return SplicePlan.objects.create(
            closure=self.closure, name="Test Plan", status=status,
        )

    # Valid transitions
    def test_draft_to_pending_approval(self):
        plan = self._make_plan()
        plan.status = SplicePlanStatusChoices.PENDING_APPROVAL
        plan.submitted_by = self.user
        plan.full_clean()

    def test_pending_approval_to_approved(self):
        plan = self._make_plan(SplicePlanStatusChoices.PENDING_APPROVAL)
        plan.status = SplicePlanStatusChoices.APPROVED
        plan.full_clean()

    def test_pending_approval_to_draft(self):
        plan = self._make_plan(SplicePlanStatusChoices.PENDING_APPROVAL)
        plan.status = SplicePlanStatusChoices.DRAFT
        plan.full_clean()

    def test_approved_to_archived(self):
        plan = self._make_plan(SplicePlanStatusChoices.APPROVED)
        plan.status = SplicePlanStatusChoices.ARCHIVED
        plan.full_clean()

    def test_approved_to_draft(self):
        plan = self._make_plan(SplicePlanStatusChoices.APPROVED)
        plan.status = SplicePlanStatusChoices.DRAFT
        plan.full_clean()

    def test_draft_to_archived(self):
        plan = self._make_plan()
        plan.status = SplicePlanStatusChoices.ARCHIVED
        plan.full_clean()

    def test_pending_to_archived(self):
        plan = self._make_plan(SplicePlanStatusChoices.PENDING_APPROVAL)
        plan.status = SplicePlanStatusChoices.ARCHIVED
        plan.full_clean()

    # Invalid transitions
    def test_invalid_draft_to_approved(self):
        plan = self._make_plan()
        plan.status = SplicePlanStatusChoices.APPROVED
        with self.assertRaises(ValidationError):
            plan.full_clean()

    def test_invalid_archived_to_draft(self):
        plan = self._make_plan(SplicePlanStatusChoices.ARCHIVED)
        plan.status = SplicePlanStatusChoices.DRAFT
        with self.assertRaises(ValidationError):
            plan.full_clean()

    def test_invalid_archived_to_approved(self):
        plan = self._make_plan(SplicePlanStatusChoices.ARCHIVED)
        plan.status = SplicePlanStatusChoices.APPROVED
        with self.assertRaises(ValidationError):
            plan.full_clean()

    def test_invalid_archived_to_pending(self):
        plan = self._make_plan(SplicePlanStatusChoices.ARCHIVED)
        plan.status = SplicePlanStatusChoices.PENDING_APPROVAL
        with self.assertRaises(ValidationError):
            plan.full_clean()

    # Validation rules
    def test_pending_requires_submitted_by(self):
        plan = self._make_plan()
        plan.status = SplicePlanStatusChoices.PENDING_APPROVAL
        plan.submitted_by = None
        with self.assertRaises(ValidationError):
            plan.full_clean()

    def test_new_plan_always_draft(self):
        plan = SplicePlan(closure=self.closure, name="New", status=SplicePlanStatusChoices.DRAFT)
        plan.full_clean()


class TestBulkUpdateStatusEnforcement(TransactionTestCase):
    """Test that bulk_update_entries rejects changes on non-draft plans."""

    def setUp(self):
        site = Site.objects.create(name="API Site", slug="api-site")
        mfr = Manufacturer.objects.create(name="API Mfr", slug="api-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="API Closure", slug="api-closure")
        role = DeviceRole.objects.create(name="API Role", slug="api-role")
        self.closure = Device.objects.create(name="API-Closure", site=site, device_type=dt, role=role)
        self.user = User.objects.create_superuser(username="api-user", password="test")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_bulk_update_blocked_on_pending_approval(self):
        plan = SplicePlan.objects.create(
            closure=self.closure,
            name="Locked Plan",
            status=SplicePlanStatusChoices.PENDING_APPROVAL,
            submitted_by=self.user,
        )
        url = f"/api/plugins/fms/splice-plans/{plan.pk}/bulk-update/"
        resp = self.client.post(url, {"add": [], "remove": []}, format="json")
        assert resp.status_code == 403

    def test_bulk_update_blocked_on_approved(self):
        plan = SplicePlan.objects.create(
            closure=self.closure,
            name="Approved Plan",
            status=SplicePlanStatusChoices.APPROVED,
        )
        url = f"/api/plugins/fms/splice-plans/{plan.pk}/bulk-update/"
        resp = self.client.post(url, {"add": [], "remove": []}, format="json")
        assert resp.status_code == 403

    def test_bulk_update_blocked_on_archived(self):
        plan = SplicePlan.objects.create(
            closure=self.closure,
            name="Archived Plan",
            status=SplicePlanStatusChoices.ARCHIVED,
        )
        url = f"/api/plugins/fms/splice-plans/{plan.pk}/bulk-update/"
        resp = self.client.post(url, {"add": [], "remove": []}, format="json")
        assert resp.status_code == 403

    def test_bulk_update_allowed_on_draft(self):
        plan = SplicePlan.objects.create(
            closure=self.closure,
            name="Draft Plan",
            status=SplicePlanStatusChoices.DRAFT,
        )
        url = f"/api/plugins/fms/splice-plans/{plan.pk}/bulk-update/"
        resp = self.client.post(url, {"add": [], "remove": []}, format="json")
        assert resp.status_code == 200


class TestSplicePlanDeletion(TransactionTestCase):
    """Test deletion permission rules based on plan status."""

    def setUp(self):
        site = Site.objects.create(name="Del Site", slug="del-site")
        mfr = Manufacturer.objects.create(name="Del Mfr", slug="del-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Del Closure", slug="del-closure")
        role = DeviceRole.objects.create(name="Del Role", slug="del-role")
        self.closure = Device.objects.create(name="Del-Closure", site=site, device_type=dt, role=role)

        # User with change+delete+view+add but NOT approve
        self.user = User.objects.create_user(username="del-user", password="test")
        ct = ContentType.objects.get_for_model(SplicePlan)
        obj_perm = ObjectPermission.objects.create(
            name="SplicePlan CRUD",
            actions=["view", "add", "change", "delete"],
        )
        obj_perm.object_types.add(ct)
        obj_perm.users.add(self.user)

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_delete_draft_allowed(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Draft", status=SplicePlanStatusChoices.DRAFT)
        resp = self.client.delete(f"/api/plugins/fms/splice-plans/{plan.pk}/")
        assert resp.status_code == 204

    def test_delete_pending_blocked_without_approve(self):
        plan = SplicePlan.objects.create(
            closure=self.closure,
            name="Pending",
            status=SplicePlanStatusChoices.PENDING_APPROVAL,
            submitted_by=self.user,
        )
        resp = self.client.delete(f"/api/plugins/fms/splice-plans/{plan.pk}/")
        assert resp.status_code == 403

    def test_delete_approved_blocked_without_approve(self):
        plan = SplicePlan.objects.create(
            closure=self.closure,
            name="Approved",
            status=SplicePlanStatusChoices.APPROVED,
        )
        resp = self.client.delete(f"/api/plugins/fms/splice-plans/{plan.pk}/")
        assert resp.status_code == 403

    def test_delete_archived_allowed(self):
        plan = SplicePlan.objects.create(
            closure=self.closure, name="Archived", status=SplicePlanStatusChoices.ARCHIVED
        )
        resp = self.client.delete(f"/api/plugins/fms/splice-plans/{plan.pk}/")
        assert resp.status_code == 204
