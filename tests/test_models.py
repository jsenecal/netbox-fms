from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site
from django.test import TestCase

from netbox_fms.choices import SplicePlanStatusChoices
from netbox_fms.models import SplicePlan, SpliceProject


class TestSplicePlanStatusChoices(TestCase):
    def test_has_draft(self):
        assert SplicePlanStatusChoices.DRAFT == "draft"

    def test_has_pending_review(self):
        assert SplicePlanStatusChoices.PENDING_REVIEW == "pending_review"

    def test_has_ready_to_apply(self):
        assert SplicePlanStatusChoices.READY_TO_APPLY == "ready_to_apply"

    def test_has_applied(self):
        assert SplicePlanStatusChoices.APPLIED == "applied"

    def test_mode_choices_removed(self):
        """SplicePlanModeChoices should no longer exist."""
        import netbox_fms.choices as ch

        assert not hasattr(ch, "SplicePlanModeChoices")


class TestSpliceProject(TestCase):
    def test_create_project(self):
        project = SpliceProject.objects.create(
            name="Main St CO → Elm St Drop",
            description="Route fiber project",
        )
        assert project.pk is not None
        assert str(project) == "Main St CO → Elm St Drop"

    def test_get_absolute_url(self):
        project = SpliceProject.objects.create(name="Test Project")
        assert "/splice-projects/" in project.get_absolute_url()


class TestSplicePlanRework(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Test Site", slug="test-site")
        manufacturer = Manufacturer.objects.create(name="Test Mfr", slug="test-mfr")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="Closure", slug="closure")
        role = DeviceRole.objects.create(name="Splice Closure", slug="splice-closure")
        cls.closure = Device.objects.create(name="Closure-1", site=site, device_type=device_type, role=role)
        cls.project = SpliceProject.objects.create(name="Test Project")

    def test_create_plan_with_new_fields(self):
        from netbox_fms.choices import SplicePlanStatusChoices

        plan = SplicePlan.objects.create(
            closure=self.closure,
            name="Plan 1",
            status=SplicePlanStatusChoices.DRAFT,
        )
        assert plan.pk is not None
        assert plan.cached_diff is None
        assert plan.diff_stale is True
        assert plan.project is None

    def test_plan_with_project(self):
        plan = SplicePlan.objects.create(
            closure=self.closure,
            name="Plan 1",
            project=self.project,
        )
        assert plan.project == self.project
        assert self.project.plans.count() == 1

    def test_unique_closure_constraint(self):
        from django.db import IntegrityError

        SplicePlan.objects.create(closure=self.closure, name="Plan 1")
        with self.assertRaises(IntegrityError):
            SplicePlan.objects.create(closure=self.closure, name="Plan 2")

    def test_no_mode_field(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Plan 1")
        assert not hasattr(plan, "mode")

    def test_no_tray_field(self):
        SplicePlan.objects.create(closure=self.closure, name="Plan 1")
        assert not hasattr(SplicePlan, "tray")

    def test_no_implement_method(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Plan 1")
        assert not hasattr(plan, "implement")

    def test_no_rollback_method(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Plan 1")
        assert not hasattr(plan, "rollback")
