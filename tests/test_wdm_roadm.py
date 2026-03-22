"""Tests for ROADM apply-mapping API endpoint."""

import pytest
from dcim.models import Device, DeviceRole, DeviceType, FrontPort, Manufacturer, PortMapping, RearPort, Site
from django.test import TestCase
from rest_framework.test import APIClient

from netbox_fms.choices import WavelengthChannelStatusChoices, WdmGridChoices, WdmNodeTypeChoices
from netbox_fms.models import WavelengthChannel, WdmNode, WdmTrunkPort


@pytest.fixture
def roadm_fixtures(db):
    """Create a ROADM device with trunk ports, channels, and front ports."""
    site = Site.objects.create(name="ROADM Site", slug="roadm-site")
    mfr = Manufacturer.objects.create(name="ROADM Mfr", slug="roadm-mfr")
    role = DeviceRole.objects.create(name="ROADM Role", slug="roadm-role")
    dt = DeviceType.objects.create(manufacturer=mfr, model="ROADM-8", slug="roadm-8")
    device = Device.objects.create(name="ROADM-1", site=site, device_type=dt, role=role)

    # Trunk RearPort with 8 positions
    trunk_rp = RearPort.objects.create(device=device, name="Trunk-East", type="lc", positions=8)

    # 4 client FrontPorts
    fps = []
    for i in range(1, 5):
        fp = FrontPort.objects.create(device=device, name=f"Client-{i}", type="lc")
        fps.append(fp)

    # WdmNode (roadm, cwdm) — bypass auto-populate by creating manually
    wdm_node = WdmNode(device=device, node_type=WdmNodeTypeChoices.ROADM, grid=WdmGridChoices.CWDM)
    # Save without triggering _auto_populate_channels (no profile exists, so it's fine)
    wdm_node.save()

    # WdmTrunkPort (common direction)
    trunk_port = WdmTrunkPort.objects.create(wdm_node=wdm_node, rear_port=trunk_rp, direction="common", position=1)

    # 4 WavelengthChannels (available, no front_port)
    channels = []
    for i in range(1, 5):
        ch = WavelengthChannel.objects.create(
            wdm_node=wdm_node,
            grid_position=i,
            wavelength_nm=1270 + (i - 1) * 20,
            label=f"CWDM-{1270 + (i - 1) * 20}",
            status=WavelengthChannelStatusChoices.AVAILABLE,
        )
        channels.append(ch)

    return {
        "device": device,
        "wdm_node": wdm_node,
        "trunk_rp": trunk_rp,
        "trunk_port": trunk_port,
        "front_ports": fps,
        "channels": channels,
    }


class TestApplyMappingValidation(TestCase):
    """Test WdmNode.validate_channel_mapping() helper."""

    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="ValSite", slug="val-site")
        mfr = Manufacturer.objects.create(name="ValMfr", slug="val-mfr")
        role = DeviceRole.objects.create(name="ValRole", slug="val-role")
        dt = DeviceType.objects.create(manufacturer=mfr, model="ValDev", slug="valdev")
        cls.device = Device.objects.create(name="ValDev-1", site=site, device_type=dt, role=role)

        cls.trunk_rp = RearPort.objects.create(device=cls.device, name="Trunk-Val", type="lc", positions=8)

        cls.fps = []
        for i in range(1, 5):
            fp = FrontPort.objects.create(device=cls.device, name=f"ValClient-{i}", type="lc")
            cls.fps.append(fp)

        cls.wdm_node = WdmNode(device=cls.device, node_type=WdmNodeTypeChoices.ROADM, grid=WdmGridChoices.CWDM)
        cls.wdm_node.save()

        cls.trunk_port = WdmTrunkPort.objects.create(
            wdm_node=cls.wdm_node, rear_port=cls.trunk_rp, direction="common", position=1
        )

        cls.channels = []
        for i in range(1, 5):
            ch = WavelengthChannel.objects.create(
                wdm_node=cls.wdm_node,
                grid_position=i,
                wavelength_nm=1270 + (i - 1) * 20,
                label=f"CWDM-{1270 + (i - 1) * 20}",
                status=WavelengthChannelStatusChoices.AVAILABLE,
            )
            cls.channels.append(ch)

    def test_rejects_protected_channel_remap(self):
        """Protected channels (lit/reserved) cannot be remapped."""

        ch = self.channels[0]
        ch.status = WavelengthChannelStatusChoices.LIT
        ch.front_port = self.fps[0]
        ch.save()

        # Try to remap a lit channel to a different port
        desired = {ch.pk: self.fps[1].pk}
        errors = WdmNode.validate_channel_mapping(self.wdm_node, desired)
        assert len(errors) > 0
        assert "protected" in errors[0].lower() or "lit" in errors[0].lower() or "reserved" in errors[0].lower()

        # Cleanup
        ch.status = WavelengthChannelStatusChoices.AVAILABLE
        ch.front_port = None
        ch.save()

    def test_rejects_port_conflict(self):
        """Two channels cannot map to the same FrontPort."""

        desired = {
            self.channels[0].pk: self.fps[0].pk,
            self.channels[1].pk: self.fps[0].pk,  # conflict!
        }
        errors = WdmNode.validate_channel_mapping(self.wdm_node, desired)
        assert len(errors) > 0
        assert "conflict" in errors[0].lower() or "same" in errors[0].lower()

    def test_allows_available_channel_remap(self):
        """Available channels can be freely remapped."""

        desired = {
            self.channels[0].pk: self.fps[0].pk,
            self.channels[1].pk: self.fps[1].pk,
        }
        errors = WdmNode.validate_channel_mapping(self.wdm_node, desired)
        assert errors == []


class TestApplyMappingPortMappings(TestCase):
    """Test _apply_mapping helper creates/removes PortMappings correctly."""

    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="PMSite", slug="pm-site")
        mfr = Manufacturer.objects.create(name="PMMfr", slug="pm-mfr")
        role = DeviceRole.objects.create(name="PMRole", slug="pm-role")
        dt = DeviceType.objects.create(manufacturer=mfr, model="PMDev", slug="pmdev")
        cls.device = Device.objects.create(name="PMDev-1", site=site, device_type=dt, role=role)

        cls.trunk_rp = RearPort.objects.create(device=cls.device, name="Trunk-PM", type="lc", positions=8)

        cls.fps = []
        for i in range(1, 5):
            fp = FrontPort.objects.create(device=cls.device, name=f"PMClient-{i}", type="lc")
            cls.fps.append(fp)

        cls.wdm_node = WdmNode(device=cls.device, node_type=WdmNodeTypeChoices.ROADM, grid=WdmGridChoices.CWDM)
        cls.wdm_node.save()

        cls.trunk_port = WdmTrunkPort.objects.create(
            wdm_node=cls.wdm_node, rear_port=cls.trunk_rp, direction="common", position=1
        )

        cls.channels = []
        for i in range(1, 5):
            ch = WavelengthChannel.objects.create(
                wdm_node=cls.wdm_node,
                grid_position=i,
                wavelength_nm=1270 + (i - 1) * 20,
                label=f"CWDM-{1270 + (i - 1) * 20}",
                status=WavelengthChannelStatusChoices.AVAILABLE,
            )
            cls.channels.append(ch)

    def test_creates_port_mappings(self):
        """Assigning a channel to a front_port creates a PortMapping with correct rear_port_position."""
        from netbox_fms.api.views import _apply_mapping

        ch = self.channels[0]
        desired = {ch.pk: self.fps[0].pk}
        result = _apply_mapping(self.wdm_node, desired)

        assert result["added"] >= 1

        # Verify PortMapping created
        pm = PortMapping.objects.filter(
            front_port=self.fps[0],
            rear_port=self.trunk_rp,
            rear_port_position=ch.grid_position,
        )
        assert pm.exists()

        # Verify channel updated
        ch.refresh_from_db()
        assert ch.front_port_id == self.fps[0].pk

    def test_removes_port_mappings_on_unassign(self):
        """Unassigning a channel (front_port=None) removes its PortMapping."""
        from netbox_fms.api.views import _apply_mapping

        ch = self.channels[1]

        # First assign
        _apply_mapping(self.wdm_node, {ch.pk: self.fps[1].pk})
        assert PortMapping.objects.filter(front_port=self.fps[1], rear_port=self.trunk_rp).exists()

        # Now unassign
        result = _apply_mapping(self.wdm_node, {ch.pk: None})
        assert result["removed"] >= 1

        # Verify PortMapping gone
        assert not PortMapping.objects.filter(front_port=self.fps[1], rear_port=self.trunk_rp).exists()

        # Verify channel updated
        ch.refresh_from_db()
        assert ch.front_port is None


class TestApplyMappingIntegration(TestCase):
    """Test the apply-mapping API endpoint end-to-end."""

    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="IntSite", slug="int-site")
        mfr = Manufacturer.objects.create(name="IntMfr", slug="int-mfr")
        role = DeviceRole.objects.create(name="IntRole", slug="int-role")
        dt = DeviceType.objects.create(manufacturer=mfr, model="IntDev", slug="intdev")
        cls.device = Device.objects.create(name="IntDev-1", site=site, device_type=dt, role=role)

        cls.trunk_rp = RearPort.objects.create(device=cls.device, name="Trunk-Int", type="lc", positions=8)

        cls.fps = []
        for i in range(1, 5):
            fp = FrontPort.objects.create(device=cls.device, name=f"IntClient-{i}", type="lc")
            cls.fps.append(fp)

        cls.wdm_node = WdmNode(device=cls.device, node_type=WdmNodeTypeChoices.ROADM, grid=WdmGridChoices.CWDM)
        cls.wdm_node.save()

        cls.trunk_port = WdmTrunkPort.objects.create(
            wdm_node=cls.wdm_node, rear_port=cls.trunk_rp, direction="common", position=1
        )

        cls.channels = []
        for i in range(1, 5):
            ch = WavelengthChannel.objects.create(
                wdm_node=cls.wdm_node,
                grid_position=i,
                wavelength_nm=1270 + (i - 1) * 20,
                label=f"CWDM-{1270 + (i - 1) * 20}",
                status=WavelengthChannelStatusChoices.AVAILABLE,
            )
            cls.channels.append(ch)

    def setUp(self):
        from django.contrib.auth import get_user_model

        user_model = get_user_model()
        self.user = user_model.objects.create_superuser("roadmtest", "roadm@test.com", "password")
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.user)

    def test_full_assign_save_cycle(self):
        """POST apply-mapping assigns channels and creates PortMappings."""
        url = f"/api/plugins/fms/wdm-nodes/{self.wdm_node.pk}/apply-mapping/"
        mapping = {
            str(self.channels[0].pk): self.fps[0].pk,
            str(self.channels[1].pk): self.fps[1].pk,
        }
        response = self.client_api.post(
            url,
            {"mapping": mapping, "last_updated": str(self.wdm_node.last_updated)},
            format="json",
        )
        assert response.status_code == 200, response.data
        assert response.data["added"] >= 2

        # Verify channels updated
        self.channels[0].refresh_from_db()
        assert self.channels[0].front_port_id == self.fps[0].pk

    def test_remap_updates_port_mappings(self):
        """Remapping a channel removes old PortMapping and creates new one."""
        from netbox_fms.api.views import _apply_mapping

        ch = self.channels[2]
        # Assign to fps[2]
        _apply_mapping(self.wdm_node, {ch.pk: self.fps[2].pk})
        assert PortMapping.objects.filter(front_port=self.fps[2], rear_port=self.trunk_rp).exists()

        # Remap to fps[3]
        _apply_mapping(self.wdm_node, {ch.pk: self.fps[3].pk})

        # Old mapping gone
        assert not PortMapping.objects.filter(front_port=self.fps[2], rear_port=self.trunk_rp).exists()
        # New mapping exists
        assert PortMapping.objects.filter(
            front_port=self.fps[3], rear_port=self.trunk_rp, rear_port_position=ch.grid_position
        ).exists()

    def test_concurrent_edit_returns_409(self):
        """Stale last_updated returns 409 Conflict."""
        url = f"/api/plugins/fms/wdm-nodes/{self.wdm_node.pk}/apply-mapping/"
        response = self.client_api.post(
            url,
            {"mapping": {}, "last_updated": "1999-01-01 00:00:00+00:00"},
            format="json",
        )
        assert response.status_code == 409
