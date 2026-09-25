"""ModuleType detail pages must surface FMS tray profile details (or offer to add one)."""

from dcim.models import Manufacturer
from django.test import TestCase

from netbox_fms.template_content import ModuleTypeTrayProfilePanel
from tests.conftest import make_tray_type, render_left_page


class TestModuleTypeTrayProfilePanel(TestCase):
    @classmethod
    def setUpTestData(cls):
        mfr = Manufacturer.objects.create(name="MTP Mfr", slug="mtp-mfr")
        cls.profiled = make_tray_type(mfr, "MTP Profiled Tray")
        cls.unprofiled = make_tray_type(mfr, "MTP Plain Module", role=None)

    def test_profiled_type_shows_tray_profile_details(self):
        html = render_left_page(ModuleTypeTrayProfilePanel, self.profiled)
        profile = self.profiled.tray_profile
        assert "Splice Tray" in html
        assert str(profile.max_fibers) in html
        assert profile.get_absolute_url() in html

    def test_unprofiled_type_offers_add_action(self):
        html = render_left_page(ModuleTypeTrayProfilePanel, self.unprofiled)
        assert "Add Tray Profile" in html
        assert f"module_type={self.unprofiled.pk}" in html

    def test_unprofiled_type_shows_no_profile_details(self):
        html = render_left_page(ModuleTypeTrayProfilePanel, self.unprofiled)
        assert "Splice Tray" not in html
