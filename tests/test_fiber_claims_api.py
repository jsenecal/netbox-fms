"""Tests for the fiber-claims API endpoint."""

from dcim.models import Device, DeviceRole, DeviceType, FrontPort, Manufacturer, Module, ModuleBay, ModuleType, Site
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from netbox_fms.choices import SplicePlanStatusChoices
from netbox_fms.models import SplicePlan, SplicePlanEntry, SpliceProject

User = get_user_model()


class TestFiberClaimsAPIView(TransactionTestCase):
    """Test GET /api/plugins/fms/closures/{device_id}/fiber-claims/"""

    def setUp(self):
        site = Site.objects.create(name="Claims Site", slug="claims-site")
        mfr = Manufacturer.objects.create(name="Claims Mfr", slug="claims-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Claims Closure", slug="claims-closure")
        role = DeviceRole.objects.create(name="Claims Role", slug="claims-role")
        self.closure = Device.objects.create(name="Claims-Closure", site=site, device_type=dt, role=role)

        # Create a module type and module bay to host front ports
        mt = ModuleType.objects.create(manufacturer=mfr, model="Claims Tray")
        mb = ModuleBay.objects.create(device=self.closure, name="Bay 1", position="1")
        self.tray = Module.objects.create(device=self.closure, module_bay=mb, module_type=mt)

        # Create 4 front ports on the tray
        self.ports = []
        for i in range(1, 5):
            fp = FrontPort.objects.create(
                device=self.closure,
                module=self.tray,
                name=f"Port {i}",
                type="lc",
            )
            self.ports.append(fp)

        self.user = User.objects.create_superuser(username="claims-user", password="test")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _url(self, device_id=None, exclude_plan=None):
        did = device_id if device_id is not None else self.closure.pk
        url = f"/api/plugins/fms/closures/{did}/fiber-claims/"
        if exclude_plan is not None:
            url += f"?exclude_plan={exclude_plan}"
        return url

    def _make_plan(self, name, status=SplicePlanStatusChoices.DRAFT, project=None):
        return SplicePlan.objects.create(
            closure=self.closure,
            name=name,
            status=status,
            project=project,
        )

    def _make_entry(self, plan, fiber_a, fiber_b):
        return SplicePlanEntry.objects.create(
            plan=plan,
            tray=self.tray,
            fiber_a=fiber_a,
            fiber_b=fiber_b,
        )

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_empty_when_no_plans(self):
        """GET returns empty list when there are no plans for the closure."""
        resp = self.client.get(self._url())
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_other_plans_claims(self):
        """With exclude_plan set, only entries from other plans are returned."""
        plan_a = self._make_plan("Plan A")
        plan_b = self._make_plan("Plan B")
        entry_a = self._make_entry(plan_a, self.ports[0], self.ports[1])
        _entry_b = self._make_entry(plan_b, self.ports[2], self.ports[3])

        resp = self.client.get(self._url(exclude_plan=plan_b.pk))
        assert resp.status_code == 200
        data = resp.json()

        # Only plan_a's entry should appear (plan_b is excluded)
        assert len(data) == 1
        item = data[0]
        assert item["fiber_a"] == self.ports[0].pk
        assert item["fiber_b"] == self.ports[1].pk
        assert item["plan_id"] == plan_a.pk
        assert item["plan_name"] == "Plan A"
        assert item["status"] == SplicePlanStatusChoices.DRAFT

    def test_excludes_archived_plans(self):
        """Entries from archived plans are never returned."""
        archived_plan = self._make_plan("Archived Plan", status=SplicePlanStatusChoices.ARCHIVED)
        self._make_entry(archived_plan, self.ports[0], self.ports[1])

        resp = self.client.get(self._url())
        assert resp.status_code == 200
        assert resp.json() == []

    def test_includes_project_name(self):
        """When a plan belongs to a project, project_name is populated."""
        project = SpliceProject.objects.create(name="Downtown Ring")
        plan = self._make_plan("Phase 2 Upgrade", project=project)
        self._make_entry(plan, self.ports[0], self.ports[1])

        resp = self.client.get(self._url())
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["project_name"] == "Downtown Ring"
        assert data[0]["plan_name"] == "Phase 2 Upgrade"

    def test_project_name_none_when_no_project(self):
        """When a plan has no project, project_name is None."""
        plan = self._make_plan("No Project Plan")
        self._make_entry(plan, self.ports[0], self.ports[1])

        resp = self.client.get(self._url())
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["project_name"] is None

    def test_no_exclude_param_returns_all_non_archived(self):
        """Without exclude_plan param, all non-archived plans' entries are returned."""
        plan_a = self._make_plan("Plan A")
        plan_b = self._make_plan("Plan B")
        archived = self._make_plan("Archived", status=SplicePlanStatusChoices.ARCHIVED)

        self._make_entry(plan_a, self.ports[0], self.ports[1])
        self._make_entry(plan_b, self.ports[2], self.ports[3])
        self._make_entry(archived, self.ports[0], self.ports[2])  # should not appear

        resp = self.client.get(self._url())
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        plan_ids = {item["plan_id"] for item in data}
        assert plan_ids == {plan_a.pk, plan_b.pk}

    def test_requires_authentication(self):
        """Unauthenticated requests receive 403."""
        unauthenticated_client = APIClient()
        resp = unauthenticated_client.get(self._url())
        assert resp.status_code in (401, 403)

    def test_response_contains_all_required_fields(self):
        """Each result item contains all required fields."""
        plan = self._make_plan("Full Fields Plan")
        self._make_entry(plan, self.ports[0], self.ports[1])

        resp = self.client.get(self._url())
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        item = data[0]
        required_fields = {"fiber_a", "fiber_b", "plan_id", "plan_name", "project_name", "status"}
        assert required_fields.issubset(set(item.keys()))
