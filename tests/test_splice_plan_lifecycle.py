from dcim.models import Device, DeviceRole, DeviceType, FrontPort, Manufacturer, Module, ModuleBay, ModuleType, Site
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
        resp = self.client.post(url, {"add": [], "remove": []}, format="json", HTTP_X_CHANGELOG_MESSAGE="test draft")
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


class TestFiberExclusivity(TransactionTestCase):
    """Test that fibers can't be claimed by multiple non-archived plans."""

    def setUp(self):
        site = Site.objects.create(name="FE Site", slug="fe-site")
        mfr = Manufacturer.objects.create(name="FE Mfr", slug="fe-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="FE Closure", slug="fe-closure")
        role = DeviceRole.objects.create(name="FE Role", slug="fe-role")
        self.closure = Device.objects.create(name="FE-Closure", site=site, device_type=dt, role=role)

        mt = ModuleType.objects.create(manufacturer=mfr, model="FE Tray")
        bay = ModuleBay.objects.create(device=self.closure, name="Bay 1")
        self.tray = Module.objects.create(device=self.closure, module_bay=bay, module_type=mt)

        # Create FrontPorts on the closure, assigned to the tray module
        self.fp1 = FrontPort.objects.create(device=self.closure, module=self.tray, name="F1", type="splice")
        self.fp2 = FrontPort.objects.create(device=self.closure, module=self.tray, name="F2", type="splice")
        self.fp3 = FrontPort.objects.create(device=self.closure, module=self.tray, name="F3", type="splice")
        self.fp4 = FrontPort.objects.create(device=self.closure, module=self.tray, name="F4", type="splice")

    def test_same_plan_allows_same_closure(self):
        """Entries within the same plan don't conflict with each other."""
        plan = SplicePlan.objects.create(closure=self.closure, name="Plan A")
        from netbox_fms.models import SplicePlanEntry

        entry = SplicePlanEntry(plan=plan, tray=self.tray, fiber_a=self.fp1, fiber_b=self.fp2)
        entry.full_clean()  # Should not raise

    def test_different_plans_conflict_on_fiber_a(self):
        """Two plans on same closure can't both claim the same fiber."""
        plan_a = SplicePlan.objects.create(closure=self.closure, name="Plan A")
        plan_b = SplicePlan.objects.create(closure=self.closure, name="Plan B")

        from netbox_fms.models import SplicePlanEntry

        SplicePlanEntry.objects.create(plan=plan_a, tray=self.tray, fiber_a=self.fp1, fiber_b=self.fp2)

        # Plan B tries to use fp1 (claimed by Plan A)
        entry_b = SplicePlanEntry(plan=plan_b, tray=self.tray, fiber_a=self.fp1, fiber_b=self.fp3)
        with self.assertRaises(ValidationError):
            entry_b.full_clean()

    def test_different_plans_conflict_on_fiber_b(self):
        """Conflict also detected on fiber_b side."""
        plan_a = SplicePlan.objects.create(closure=self.closure, name="Plan A")
        plan_b = SplicePlan.objects.create(closure=self.closure, name="Plan B")

        from netbox_fms.models import SplicePlanEntry

        SplicePlanEntry.objects.create(plan=plan_a, tray=self.tray, fiber_a=self.fp1, fiber_b=self.fp2)

        # Plan B tries to use fp2 as fiber_a (claimed as fiber_b in Plan A)
        entry_b = SplicePlanEntry(plan=plan_b, tray=self.tray, fiber_a=self.fp2, fiber_b=self.fp3)
        with self.assertRaises(ValidationError):
            entry_b.full_clean()

    def test_archived_plan_does_not_block(self):
        """Archived plans release their fiber claims."""
        plan_a = SplicePlan.objects.create(
            closure=self.closure, name="Plan A", status=SplicePlanStatusChoices.ARCHIVED
        )
        plan_b = SplicePlan.objects.create(closure=self.closure, name="Plan B")

        from netbox_fms.models import SplicePlanEntry

        SplicePlanEntry.objects.create(plan=plan_a, tray=self.tray, fiber_a=self.fp1, fiber_b=self.fp2)

        # Plan B can use fp1 since Plan A is archived
        entry_b = SplicePlanEntry(plan=plan_b, tray=self.tray, fiber_a=self.fp1, fiber_b=self.fp3)
        entry_b.full_clean()  # Should not raise

    def test_different_closures_no_conflict(self):
        """Same fiber on different closures doesn't conflict."""
        site = Site.objects.create(name="FE2 Site", slug="fe2-site")
        mfr = Manufacturer.objects.get(slug="fe-mfr")
        dt = DeviceType.objects.get(slug="fe-closure")
        role = DeviceRole.objects.get(slug="fe-role")
        closure2 = Device.objects.create(name="FE-Closure2", site=site, device_type=dt, role=role)

        plan_a = SplicePlan.objects.create(closure=self.closure, name="Plan A")
        plan_b = SplicePlan.objects.create(closure=closure2, name="Plan B")

        from netbox_fms.models import SplicePlanEntry

        SplicePlanEntry.objects.create(plan=plan_a, tray=self.tray, fiber_a=self.fp1, fiber_b=self.fp2)

        mt = ModuleType.objects.get(model="FE Tray")
        bay2 = ModuleBay.objects.create(device=closure2, name="Bay 1")
        tray2 = Module.objects.create(device=closure2, module_bay=bay2, module_type=mt)

        # Create FrontPorts on closure2's tray
        fp1_c2 = FrontPort.objects.create(device=closure2, module=tray2, name="F1", type="splice")
        fp3_c2 = FrontPort.objects.create(device=closure2, module=tray2, name="F3", type="splice")

        # Different closure's plan — no conflict
        entry_b = SplicePlanEntry(plan=plan_b, tray=tray2, fiber_a=fp1_c2, fiber_b=fp3_c2)
        entry_b.full_clean()  # Should not raise

    def test_api_bulk_update_blocks_conflicting_fibers(self):
        """bulk_update_entries returns 409 when adding fibers claimed by another plan."""
        user = User.objects.create_superuser(username="fe-api-user", password="test")
        client = APIClient()
        client.force_authenticate(user=user)

        plan_a = SplicePlan.objects.create(closure=self.closure, name="Plan A")
        plan_b = SplicePlan.objects.create(closure=self.closure, name="Plan B")

        from netbox_fms.models import SplicePlanEntry

        SplicePlanEntry.objects.create(plan=plan_a, tray=self.tray, fiber_a=self.fp1, fiber_b=self.fp2)

        # Plan B tries to add splice using fp1 via API
        url = f"/api/plugins/fms/splice-plans/{plan_b.pk}/bulk-update/"
        resp = client.post(
            url,
            {
                "add": [{"fiber_a": self.fp1.pk, "fiber_b": self.fp3.pk}],
                "remove": [],
            },
            format="json",
            HTTP_X_CHANGELOG_MESSAGE="test",
        )
        assert resp.status_code == 409, f"Expected 409, got {resp.status_code}: {resp.data}"
