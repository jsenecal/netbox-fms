from dcim.models import Cable, Device, DeviceRole, DeviceType, Manufacturer, Site
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from netbox_fms.models import FiberCable, FiberCableType, SplicePlan

User = get_user_model()


class TestUnauthenticatedAccess(TestCase):
    """Verify all custom views reject unauthenticated requests."""

    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Auth Site", slug="auth-site")
        manufacturer = Manufacturer.objects.create(name="Auth Mfr", slug="auth-mfr")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="Auth Closure", slug="auth-closure")
        role = DeviceRole.objects.create(name="Auth Role", slug="auth-role")
        cls.device = Device.objects.create(name="Auth-Device", site=site, device_type=device_type, role=role)
        fct = FiberCableType.objects.create(
            manufacturer=manufacturer,
            model="Auth-FCT",
            construction="loose_tube",
            fiber_type="smf_os2",
            strand_count=12,
        )
        cable = Cable.objects.create()
        cls.fiber_cable = FiberCable.objects.create(cable=cable, fiber_cable_type=fct)
        cls.plan = SplicePlan.objects.create(
            closure=cls.device,
            name="Auth Plan",
            status="draft",
        )

    def test_quick_add_form_requires_login(self):
        response = self.client.get("/plugins/fms/splice-plans/quick-add-form/")
        assert response.status_code == 302
        assert "/login/" in response.url

    def test_import_from_device_requires_login(self):
        response = self.client.post(f"/plugins/fms/splice-plans/{self.plan.pk}/import/")
        assert response.status_code == 302
        assert "/login/" in response.url

    def test_apply_view_requires_login(self):
        response = self.client.get(f"/plugins/fms/splice-plans/{self.plan.pk}/apply/")
        assert response.status_code == 302
        assert "/login/" in response.url

    def test_export_drawio_requires_login(self):
        response = self.client.get(f"/plugins/fms/splice-plans/{self.plan.pk}/export/")
        assert response.status_code == 302
        assert "/login/" in response.url

    def test_provision_ports_requires_login(self):
        response = self.client.get("/plugins/fms/provision-ports/")
        assert response.status_code == 302
        assert "/login/" in response.url

    def test_splice_editor_requires_login(self):
        response = self.client.get(f"/plugins/fms/splice-plans/{self.plan.pk}/editor/")
        assert response.status_code == 302
        assert "/login/" in response.url


class TestAPIActionPermissions(TestCase):
    """Verify custom API actions check permissions beyond just authentication."""

    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="APIPerm Site", slug="apiperm-site")
        manufacturer = Manufacturer.objects.create(name="APIPerm Mfr", slug="apiperm-mfr")
        device_type = DeviceType.objects.create(
            manufacturer=manufacturer, model="APIPerm Closure", slug="apiperm-closure"
        )
        role = DeviceRole.objects.create(name="APIPerm Role", slug="apiperm-role")
        cls.device = Device.objects.create(name="APIPerm-Device", site=site, device_type=device_type, role=role)
        cls.plan = SplicePlan.objects.create(
            closure=cls.device,
            name="APIPerm Plan",
            status="draft",
        )
        cls.readonly_user = User.objects.create_user(username="apiperm_readonly", password="testpass")
        cls.super_user = User.objects.create_user(username="apiperm_super", password="testpass", is_superuser=True)

    def test_import_from_device_requires_change_permission(self):
        client = APIClient()
        client.force_authenticate(user=self.readonly_user)
        url = f"/api/plugins/fms/splice-plans/{self.plan.pk}/import-from-device/"
        response = client.post(url)
        assert response.status_code == 403

    def test_apply_plan_requires_change_permission(self):
        client = APIClient()
        client.force_authenticate(user=self.readonly_user)
        url = f"/api/plugins/fms/splice-plans/{self.plan.pk}/apply/"
        response = client.post(url)
        assert response.status_code == 403

    def test_bulk_update_requires_change_permission(self):
        client = APIClient()
        client.force_authenticate(user=self.readonly_user)
        url = f"/api/plugins/fms/splice-plans/{self.plan.pk}/bulk-update/"
        response = client.post(url, {"add": [], "remove": []}, format="json")
        assert response.status_code == 403

    def test_diff_requires_view_permission(self):
        client = APIClient()
        client.force_authenticate(user=self.readonly_user)
        url = f"/api/plugins/fms/splice-plans/{self.plan.pk}/diff/"
        response = client.get(url)
        assert response.status_code == 403

    def test_quick_add_requires_add_permission(self):
        client = APIClient()
        client.force_authenticate(user=self.readonly_user)
        url = "/api/plugins/fms/splice-plans/quick-add/"
        response = client.post(
            url,
            {
                "closure": self.device.pk,
                "name": "Test Plan",
                "status": "draft",
            },
            format="json",
        )
        assert response.status_code == 403


class TestHiddenFieldTampering(TestCase):
    """Verify HTMX views reject tampered hidden field values."""

    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Tamper Site", slug="tamper-site")
        manufacturer = Manufacturer.objects.create(name="Tamper Mfr", slug="tamper-mfr")
        device_type = DeviceType.objects.create(
            manufacturer=manufacturer, model="Tamper Closure", slug="tamper-closure"
        )
        role = DeviceRole.objects.create(name="Tamper Role", slug="tamper-role")
        cls.device = Device.objects.create(name="Tamper-Device", site=site, device_type=device_type, role=role)
        cls.other_device = Device.objects.create(name="Other-Device", site=site, device_type=device_type, role=role)

        fct = FiberCableType.objects.create(
            manufacturer=manufacturer,
            model="Tamper-FCT",
            construction="loose_tube",
            fiber_type="smf_os2",
            strand_count=4,
        )

        cls.cable_on_device = Cable.objects.create()
        cls.fc_on_device = FiberCable.objects.create(cable=cls.cable_on_device, fiber_cable_type=fct)

        cls.cable_on_other = Cable.objects.create()
        cls.fc_on_other = FiberCable.objects.create(cable=cls.cable_on_other, fiber_cable_type=fct)

        cls.user = User.objects.create_user(username="tamper_user", password="testpass", is_superuser=True)

    def test_link_topology_requires_permission(self):
        """Link topology view requires add_fibercable permission."""

        unprivileged = User.objects.create_user(username="unpriv_user", password="testpass")
        self.client.force_login(unprivileged)
        url = f"/plugins/fms/fiber-overview/{self.device.pk}/link-topology/"
        response = self.client.get(url + f"?cable_id={self.cable_on_device.pk}")
        assert response.status_code == 403

    def test_update_gland_requires_permission(self):
        """Update gland view requires closurecableentry permissions."""
        unprivileged = User.objects.create_user(username="unpriv_gland", password="testpass")
        self.client.force_login(unprivileged)
        url = f"/plugins/fms/fiber-overview/{self.device.pk}/update-gland/"
        response = self.client.get(url + f"?fiber_cable_id={self.fc_on_device.pk}")
        assert response.status_code == 403
