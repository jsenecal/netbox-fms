from django.test import TestCase

from netbox_fms.choices import SplicePlanStatusChoices
from netbox_fms.models import SpliceProject


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
