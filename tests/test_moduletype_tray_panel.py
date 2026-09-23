"""ModuleType detail pages must surface FMS tray profile details (or offer to add one)."""

from dcim.models import Manufacturer
from django.test import RequestFactory, TestCase

from tests.conftest import make_tray_type


class TestModuleTypeTrayProfilePanel(TestCase):
    @classmethod
    def setUpTestData(cls):
        mfr = Manufacturer.objects.create(name="MTP Mfr", slug="mtp-mfr")
        cls.profiled = make_tray_type(mfr, "MTP Profiled Tray")
        cls.unprofiled = make_tray_type(mfr, "MTP Plain Module", role=None)

    def _render_panel(self, module_type):
        from netbox_fms.template_content import ModuleTypeTrayProfilePanel

        request = RequestFactory().get(f"/dcim/module-types/{module_type.pk}/")
        panel = ModuleTypeTrayProfilePanel(context={"object": module_type, "request": request, "config": {}})
        return panel.left_page()

    def test_profiled_type_shows_tray_profile_details(self):
        html = self._render_panel(self.profiled)
        profile = self.profiled.tray_profile
        assert "Splice Tray" in html
        assert str(profile.max_fibers) in html
        assert profile.get_absolute_url() in html

    def test_unprofiled_type_offers_add_action(self):
        html = self._render_panel(self.unprofiled)
        assert "Add Tray Profile" in html
        assert f"module_type={self.unprofiled.pk}" in html

    def test_unprofiled_type_shows_no_profile_details(self):
        html = self._render_panel(self.unprofiled)
        assert "Splice Tray" not in html
