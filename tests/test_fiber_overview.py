import pytest
from dcim.models import (
    Cable,
    CableTermination,
    Device,
    DeviceRole,
    DeviceType,
    Manufacturer,
    Module,
    ModuleBay,
    ModuleType,
    RearPort,
    Site,
)
from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import TestCase

User = get_user_model()

from netbox_fms.choices import SplicePlanStatusChoices
from netbox_fms.models import ClosureCableEntry, FiberCable, FiberCableType, SplicePlan, SplicePlanEntry
from netbox_fms.services import apply_diff, create_closure_cable
from netbox_fms.views import _build_cable_rows, _device_has_modules_or_fiber_cables, _get_closure_cable_or_404
from tests.conftest import make_closure_with_tray


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

    def test_kept_items_in_menu(self):
        link_texts = self._get_link_texts()

        assert "Fiber Cable Types" in link_texts
        assert "Fiber Cables" in link_texts
        assert "Splice Projects" in link_texts
        assert "Splice Plans" in link_texts


class TestFiberOverviewCableRows(TestCase):
    """Fiber Overview lists only closure topology cables, not splice jumpers (issue #93)."""

    @classmethod
    def setUpTestData(cls):
        rig = make_closure_with_tray("FO93", port_count=3)
        cls.closure = rig.closure
        cls.tray = rig.tray
        cls.fp1, cls.fp2, cls.fp3 = rig.ports
        far_end = Device.objects.create(name="FO93-Far", site=rig.site, device_type=rig.device_type, role=rig.role)
        cls.fct = FiberCableType.objects.create(
            manufacturer=rig.mfr,
            model="FO93-TB6",
            construction="tight_buffer",
            strand_count=6,
        )
        cls.fiber_cable, _ = create_closure_cable(
            device_a=cls.closure,
            device_b=far_end,
            fiber_cable_type=cls.fct,
        )
        cls.trunk = cls.fiber_cable.cable

        # Rear-port cable with no FiberCable yet: the row that must keep its
        # "Link Topology" button.
        rear_port = RearPort.objects.create(device=cls.closure, name="FO93-RP-Bare", type="splice", positions=12)
        cls.bare = Cable.objects.create()
        CableTermination.objects.create(cable=cls.bare, cable_end="A", termination=rear_port)

        # FiberCable attached to a cable that reaches the closure only through a
        # front port -- the shape the form, import, and API paths allow.
        cls.fp_cable = Cable.objects.create()
        CableTermination.objects.create(cable=cls.fp_cable, cable_end="A", termination=cls.fp3)
        cls.fp_fiber_cable = FiberCable.objects.create(cable=cls.fp_cable, fiber_cable_type=cls.fct)

        # apply_diff only runs on approved plans, so the jumper this fixture
        # needs can only be created from one.
        plan = SplicePlan.objects.create(
            closure=cls.closure,
            name="FO93 Plan",
            status=SplicePlanStatusChoices.APPROVED,
        )
        SplicePlanEntry.objects.create(plan=plan, tray=cls.tray, fiber_a=cls.fp1, fiber_b=cls.fp2)
        assert apply_diff(plan)["added"] == 1
        cls.jumper = Cable.objects.exclude(pk__in=[cls.trunk.pk, cls.bare.pk, cls.fp_cable.pk]).get()

    def _rows_by_cable_pk(self):
        return {row["cable"].pk: row for row in _build_cable_rows(self.closure)}

    def test_front_port_jumper_excluded(self):
        assert self.jumper.pk not in self._rows_by_cable_pk()

    def test_rear_port_cables_still_listed(self):
        rows = self._rows_by_cable_pk()
        assert rows[self.trunk.pk]["fiber_cable"] == self.fiber_cable
        assert rows[self.bare.pk]["fiber_cable"] is None

    def test_fiber_cable_on_non_rear_port_listed(self):
        rows = self._rows_by_cable_pk()
        assert rows[self.fp_cable.pk]["fiber_cable"] == self.fp_fiber_cable

    def test_link_topology_guard_rejects_cable_outside_topology(self):
        assert _get_closure_cable_or_404(self.closure, self.bare.pk) == self.bare
        with pytest.raises(Http404):
            _get_closure_cable_or_404(self.closure, self.jumper.pk)
