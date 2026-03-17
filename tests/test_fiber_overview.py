from dcim.models import Cable, Device, DeviceRole, DeviceType, Manufacturer, Module, ModuleBay, ModuleType, Site
from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()

from netbox_fms.models import ClosureCableEntry, FiberCable, FiberCableType
from netbox_fms.views import _device_has_modules_or_fiber_cables


class TestFiberOverviewTabVisibility(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="FO Vis Site", slug="fo-vis-site")
        manufacturer = Manufacturer.objects.create(name="FO Mfr", slug="fo-mfr")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="FO Model", slug="fo-model")
        role = DeviceRole.objects.create(name="FO Role", slug="fo-role")
        cls.device = Device.objects.create(name="FO-Device", site=site, device_type=device_type, role=role)
        cls.manufacturer = manufacturer

    def test_hidden_for_plain_device(self):
        assert _device_has_modules_or_fiber_cables(self.device) is False

    def test_visible_when_device_has_module(self):
        module_type = ModuleType.objects.create(manufacturer=self.manufacturer, model="FO Tray")
        bay = ModuleBay.objects.create(device=self.device, name="FO Bay 1")
        Module.objects.create(device=self.device, module_bay=bay, module_type=module_type)
        assert _device_has_modules_or_fiber_cables(self.device) is True


class TestFiberOverviewView(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="FOV Site", slug="fov-site")
        manufacturer = Manufacturer.objects.create(name="FOV Mfr", slug="fov-mfr")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="FOV Closure", slug="fov-closure")
        role = DeviceRole.objects.create(name="FOV Role", slug="fov-role")
        cls.device = Device.objects.create(name="FOV-Closure", site=site, device_type=device_type, role=role)
        cls.user = User.objects.create_user(username="fov_testuser", password="testpass", is_superuser=True)

    def test_fiber_overview_returns_200(self):
        self.client.force_login(self.user)
        url = f"/dcim/devices/{self.device.pk}/fiber-overview/"
        response = self.client.get(url)
        assert response.status_code == 200

    def test_fiber_overview_context_has_stats(self):
        self.client.force_login(self.user)
        url = f"/dcim/devices/{self.device.pk}/fiber-overview/"
        response = self.client.get(url)
        assert "stats" in response.context
        assert "cable_rows" in response.context


class TestUpdateGlandLabelAction(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="GL Site", slug="gl-site")
        manufacturer = Manufacturer.objects.create(name="GL Mfr", slug="gl-mfr")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="GL Closure", slug="gl-closure")
        role = DeviceRole.objects.create(name="GL Role", slug="gl-role")
        cls.device = Device.objects.create(name="GL-Closure", site=site, device_type=device_type, role=role)

        fct = FiberCableType.objects.create(
            manufacturer=manufacturer,
            model="GL-FCT",
            construction="loose_tube",
            fiber_type="smf_os2",
            strand_count=4,
        )
        cable = Cable.objects.create()
        cls.fiber_cable = FiberCable.objects.create(cable=cable, fiber_cable_type=fct)

        cls.user = User.objects.create_user(username="gl_testuser", password="testpass", is_superuser=True)

    def test_get_returns_modal_form(self):
        self.client.force_login(self.user)
        url = f"/plugins/fms/fiber-overview/{self.device.pk}/update-gland/?fiber_cable_id={self.fiber_cable.pk}"
        response = self.client.get(url)
        assert response.status_code == 200
        assert b"modal" in response.content

    def test_post_creates_closure_cable_entry(self):
        self.client.force_login(self.user)
        url = f"/plugins/fms/fiber-overview/{self.device.pk}/update-gland/"
        response = self.client.post(
            url,
            {
                "fiber_cable_id": self.fiber_cable.pk,
                "entrance_label": "Gland X",
            },
        )
        assert response.status_code == 200
        assert response.has_header("HX-Redirect")

        entry = ClosureCableEntry.objects.get(closure=self.device, fiber_cable=self.fiber_cable)
        assert entry.entrance_label == "Gland X"

    def test_post_updates_existing_entry(self):
        ClosureCableEntry.objects.create(
            closure=self.device,
            fiber_cable=self.fiber_cable,
            entrance_label="Old Label",
        )

        self.client.force_login(self.user)
        url = f"/plugins/fms/fiber-overview/{self.device.pk}/update-gland/"
        response = self.client.post(
            url,
            {
                "fiber_cable_id": self.fiber_cable.pk,
                "entrance_label": "New Label",
            },
        )
        assert response.status_code == 200
        assert response.has_header("HX-Redirect")

        entry = ClosureCableEntry.objects.get(closure=self.device, fiber_cable=self.fiber_cable)
        assert entry.entrance_label == "New Label"


class TestNavigationCleanup(TestCase):
    def _get_link_texts(self):
        from netbox_fms.navigation import menu

        link_texts = []
        for group in menu.groups:
            for item in group.items:
                link_texts.append(item.link_text)
        return link_texts

    def test_removed_items_not_in_menu(self):
        link_texts = self._get_link_texts()

        assert "Splice Entries" not in link_texts
        assert "Cable Entries" not in link_texts
        assert "Provision Ports" not in link_texts

    def test_kept_items_in_menu(self):
        link_texts = self._get_link_texts()

        assert "Fiber Cable Types" in link_texts
        assert "Fiber Cables" in link_texts
        assert "Splice Projects" in link_texts
        assert "Splice Plans" in link_texts
        assert "Fiber Path Losses" in link_texts
