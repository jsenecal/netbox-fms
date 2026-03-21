"""Tests for WDM ITU grid constants and choice sets."""

import pytest


class TestCWDMChannels:
    def test_cwdm_channel_count(self):
        from netbox_fms.wdm_constants import CWDM_CHANNELS

        assert len(CWDM_CHANNELS) == 18

    def test_cwdm_tuple_structure(self):
        from netbox_fms.wdm_constants import CWDM_CHANNELS

        for ch in CWDM_CHANNELS:
            assert len(ch) == 3, f"Channel tuple should have 3 elements: {ch}"
            position, label, wavelength_nm = ch
            assert isinstance(position, int)
            assert isinstance(label, str)
            assert isinstance(wavelength_nm, float)

    def test_cwdm_positions_sequential(self):
        from netbox_fms.wdm_constants import CWDM_CHANNELS

        positions = [ch[0] for ch in CWDM_CHANNELS]
        assert positions == list(range(1, 19))

    def test_cwdm_spacing_20nm(self):
        from netbox_fms.wdm_constants import CWDM_CHANNELS

        wavelengths = [ch[2] for ch in CWDM_CHANNELS]
        for i in range(1, len(wavelengths)):
            assert wavelengths[i] - wavelengths[i - 1] == pytest.approx(20.0)

    def test_cwdm_first_channel(self):
        from netbox_fms.wdm_constants import CWDM_CHANNELS

        pos, label, wl = CWDM_CHANNELS[0]
        assert pos == 1
        assert label == "CWDM-1270"
        assert wl == pytest.approx(1270.0)

    def test_cwdm_last_channel(self):
        from netbox_fms.wdm_constants import CWDM_CHANNELS

        pos, label, wl = CWDM_CHANNELS[-1]
        assert pos == 18
        assert label == "CWDM-1610"
        assert wl == pytest.approx(1610.0)


class TestDWDM100GHzChannels:
    def test_100ghz_channel_count(self):
        from netbox_fms.wdm_constants import DWDM_100GHZ_CHANNELS

        assert len(DWDM_100GHZ_CHANNELS) == 44

    def test_100ghz_tuple_structure(self):
        from netbox_fms.wdm_constants import DWDM_100GHZ_CHANNELS

        for ch in DWDM_100GHZ_CHANNELS:
            assert len(ch) == 3
            position, label, wavelength_nm = ch
            assert isinstance(position, int)
            assert isinstance(label, str)
            assert isinstance(wavelength_nm, float)

    def test_100ghz_positions_sequential(self):
        from netbox_fms.wdm_constants import DWDM_100GHZ_CHANNELS

        positions = [ch[0] for ch in DWDM_100GHZ_CHANNELS]
        assert positions == list(range(1, 45))

    def test_100ghz_first_channel(self):
        from netbox_fms.wdm_constants import DWDM_100GHZ_CHANNELS

        pos, label, wl = DWDM_100GHZ_CHANNELS[0]
        assert pos == 1
        assert label == "C21"
        assert wl == pytest.approx(1560.61, abs=0.01)

    def test_100ghz_no_half_channels(self):
        from netbox_fms.wdm_constants import DWDM_100GHZ_CHANNELS

        for ch in DWDM_100GHZ_CHANNELS:
            assert ".5" not in ch[1], f"100GHz grid should not have half-channels: {ch[1]}"


class TestDWDM50GHzChannels:
    def test_50ghz_channel_count(self):
        from netbox_fms.wdm_constants import DWDM_50GHZ_CHANNELS

        assert len(DWDM_50GHZ_CHANNELS) == 88

    def test_50ghz_tuple_structure(self):
        from netbox_fms.wdm_constants import DWDM_50GHZ_CHANNELS

        for ch in DWDM_50GHZ_CHANNELS:
            assert len(ch) == 3
            position, label, wavelength_nm = ch
            assert isinstance(position, int)
            assert isinstance(label, str)
            assert isinstance(wavelength_nm, float)

    def test_50ghz_positions_sequential(self):
        from netbox_fms.wdm_constants import DWDM_50GHZ_CHANNELS

        positions = [ch[0] for ch in DWDM_50GHZ_CHANNELS]
        assert positions == list(range(1, 89))

    def test_50ghz_includes_half_channels(self):
        from netbox_fms.wdm_constants import DWDM_50GHZ_CHANNELS

        labels = [ch[1] for ch in DWDM_50GHZ_CHANNELS]
        assert "C21.5" in labels, "50GHz grid should include half-channels like C21.5"

    def test_50ghz_includes_whole_channels(self):
        from netbox_fms.wdm_constants import DWDM_50GHZ_CHANNELS

        labels = [ch[1] for ch in DWDM_50GHZ_CHANNELS]
        assert "C21" in labels
        assert "C22" in labels


class TestWDMGridsDict:
    def test_wdm_grids_keys(self):
        from netbox_fms.wdm_constants import WDM_GRIDS

        assert "dwdm_100ghz" in WDM_GRIDS
        assert "dwdm_50ghz" in WDM_GRIDS
        assert "cwdm" in WDM_GRIDS

    def test_wdm_grids_values(self):
        from netbox_fms.wdm_constants import CWDM_CHANNELS, DWDM_50GHZ_CHANNELS, DWDM_100GHZ_CHANNELS, WDM_GRIDS

        assert WDM_GRIDS["cwdm"] is CWDM_CHANNELS
        assert WDM_GRIDS["dwdm_100ghz"] is DWDM_100GHZ_CHANNELS
        assert WDM_GRIDS["dwdm_50ghz"] is DWDM_50GHZ_CHANNELS


class TestWdmChoiceSets:
    def test_wdm_node_type_choices(self):
        from netbox_fms.choices import WdmNodeTypeChoices

        values = [c[0] for c in WdmNodeTypeChoices.CHOICES]
        assert "terminal_mux" in values
        assert "oadm" in values
        assert "roadm" in values
        assert "amplifier" in values

    def test_wdm_grid_choices(self):
        from netbox_fms.choices import WdmGridChoices

        values = [c[0] for c in WdmGridChoices.CHOICES]
        assert "dwdm_100ghz" in values
        assert "dwdm_50ghz" in values
        assert "cwdm" in values

    def test_wavelength_channel_status_choices(self):
        from netbox_fms.choices import WavelengthChannelStatusChoices

        values = [c[0] for c in WavelengthChannelStatusChoices.CHOICES]
        assert "available" in values
        assert "reserved" in values
        assert "lit" in values

    def test_wavelength_service_status_choices(self):
        from netbox_fms.choices import WavelengthServiceStatusChoices

        values = [c[0] for c in WavelengthServiceStatusChoices.CHOICES]
        assert "planned" in values
        assert "staged" in values
        assert "active" in values
        assert "decommissioned" in values


# ---------------------------------------------------------------------------
# Model tests (Task 2)
# ---------------------------------------------------------------------------


@pytest.fixture
def wdm_fixtures():
    """Create base DCIM objects needed by WDM models."""
    from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site

    site = Site.objects.create(name="WDM-Site", slug="wdm-site")
    manufacturer = Manufacturer.objects.create(name="WDM-Mfg", slug="wdm-mfg")
    role = DeviceRole.objects.create(name="WDM-Role", slug="wdm-role")
    device_type = DeviceType.objects.create(manufacturer=manufacturer, model="WDM-DT", slug="wdm-dt")
    device = Device.objects.create(name="WDM-Dev-1", site=site, device_type=device_type, role=role)
    device2 = Device.objects.create(name="WDM-Dev-2", site=site, device_type=device_type, role=role)
    return {
        "site": site,
        "manufacturer": manufacturer,
        "role": role,
        "device_type": device_type,
        "device": device,
        "device2": device2,
    }


@pytest.mark.django_db
class TestWdmDeviceTypeProfile:
    def test_create_profile(self, wdm_fixtures):
        from netbox_fms.choices import WdmGridChoices, WdmNodeTypeChoices
        from netbox_fms.models import WdmDeviceTypeProfile

        profile = WdmDeviceTypeProfile.objects.create(
            device_type=wdm_fixtures["device_type"],
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        assert str(profile) == f"WDM Profile: {wdm_fixtures['device_type']}"
        assert profile.pk is not None

    def test_one_to_one_constraint(self, wdm_fixtures):
        from django.db import IntegrityError

        from netbox_fms.choices import WdmGridChoices, WdmNodeTypeChoices
        from netbox_fms.models import WdmDeviceTypeProfile

        WdmDeviceTypeProfile.objects.create(
            device_type=wdm_fixtures["device_type"],
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        with pytest.raises(IntegrityError):
            WdmDeviceTypeProfile.objects.create(
                device_type=wdm_fixtures["device_type"],
                node_type=WdmNodeTypeChoices.OADM,
                grid=WdmGridChoices.CWDM,
            )


@pytest.mark.django_db
class TestWdmChannelTemplate:
    def test_create_channel_template(self, wdm_fixtures):
        from decimal import Decimal

        from netbox_fms.choices import WdmGridChoices, WdmNodeTypeChoices
        from netbox_fms.models import WdmChannelTemplate, WdmDeviceTypeProfile

        profile = WdmDeviceTypeProfile.objects.create(
            device_type=wdm_fixtures["device_type"],
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ct = WdmChannelTemplate.objects.create(
            profile=profile,
            grid_position=1,
            wavelength_nm=Decimal("1550.12"),
            label="C21",
        )
        assert str(ct) == "C21 (1550.12nm)"
        assert ct.pk is not None

    def test_unique_grid_position(self, wdm_fixtures):
        from decimal import Decimal

        from django.db import IntegrityError

        from netbox_fms.choices import WdmGridChoices, WdmNodeTypeChoices
        from netbox_fms.models import WdmChannelTemplate, WdmDeviceTypeProfile

        profile = WdmDeviceTypeProfile.objects.create(
            device_type=wdm_fixtures["device_type"],
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        WdmChannelTemplate.objects.create(
            profile=profile, grid_position=1, wavelength_nm=Decimal("1550.12"), label="C21"
        )
        with pytest.raises(IntegrityError):
            WdmChannelTemplate.objects.create(
                profile=profile, grid_position=1, wavelength_nm=Decimal("1551.00"), label="C22"
            )


@pytest.mark.django_db
class TestWdmNode:
    def test_create_node(self, wdm_fixtures):
        from netbox_fms.choices import WdmGridChoices, WdmNodeTypeChoices
        from netbox_fms.models import WdmNode

        node = WdmNode.objects.create(
            device=wdm_fixtures["device"],
            node_type=WdmNodeTypeChoices.ROADM,
            grid=WdmGridChoices.DWDM_50GHZ,
        )
        assert str(node) == f"WDM: {wdm_fixtures['device'].name}"
        assert node.pk is not None

    def test_one_to_one_constraint(self, wdm_fixtures):
        from django.db import IntegrityError

        from netbox_fms.choices import WdmGridChoices, WdmNodeTypeChoices
        from netbox_fms.models import WdmNode

        WdmNode.objects.create(
            device=wdm_fixtures["device"],
            node_type=WdmNodeTypeChoices.ROADM,
            grid=WdmGridChoices.DWDM_50GHZ,
        )
        with pytest.raises(IntegrityError):
            WdmNode.objects.create(
                device=wdm_fixtures["device"],
                node_type=WdmNodeTypeChoices.AMPLIFIER,
                grid=WdmGridChoices.CWDM,
            )


@pytest.mark.django_db
class TestWdmTrunkPort:
    def test_create_trunk_port(self, wdm_fixtures):
        from dcim.models import RearPort

        from netbox_fms.choices import WdmGridChoices, WdmNodeTypeChoices
        from netbox_fms.models import WdmNode, WdmTrunkPort

        node = WdmNode.objects.create(
            device=wdm_fixtures["device"],
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        rp = RearPort.objects.create(device=wdm_fixtures["device"], name="RP1", positions=1)
        tp = WdmTrunkPort.objects.create(wdm_node=node, rear_port=rp, direction="east", position=1)
        assert str(tp) == f"east: {rp}"
        assert tp.pk is not None

    def test_unique_rear_port(self, wdm_fixtures):
        from dcim.models import RearPort
        from django.db import IntegrityError

        from netbox_fms.choices import WdmGridChoices, WdmNodeTypeChoices
        from netbox_fms.models import WdmNode, WdmTrunkPort

        node = WdmNode.objects.create(
            device=wdm_fixtures["device"],
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        rp = RearPort.objects.create(device=wdm_fixtures["device"], name="RP1", positions=1)
        WdmTrunkPort.objects.create(wdm_node=node, rear_port=rp, direction="east", position=1)
        with pytest.raises(IntegrityError):
            WdmTrunkPort.objects.create(wdm_node=node, rear_port=rp, direction="west", position=2)

    def test_unique_direction(self, wdm_fixtures):
        from dcim.models import RearPort
        from django.db import IntegrityError

        from netbox_fms.choices import WdmGridChoices, WdmNodeTypeChoices
        from netbox_fms.models import WdmNode, WdmTrunkPort

        node = WdmNode.objects.create(
            device=wdm_fixtures["device"],
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        rp1 = RearPort.objects.create(device=wdm_fixtures["device"], name="RP1", positions=1)
        rp2 = RearPort.objects.create(device=wdm_fixtures["device"], name="RP2", positions=1)
        WdmTrunkPort.objects.create(wdm_node=node, rear_port=rp1, direction="east", position=1)
        with pytest.raises(IntegrityError):
            WdmTrunkPort.objects.create(wdm_node=node, rear_port=rp2, direction="east", position=2)


@pytest.mark.django_db
class TestWavelengthChannel:
    def test_create_channel(self, wdm_fixtures):
        from decimal import Decimal

        from netbox_fms.choices import WdmGridChoices, WdmNodeTypeChoices
        from netbox_fms.models import WavelengthChannel, WdmNode

        node = WdmNode.objects.create(
            device=wdm_fixtures["device"],
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch = WavelengthChannel.objects.create(
            wdm_node=node,
            grid_position=1,
            wavelength_nm=Decimal("1550.12"),
            label="C21",
        )
        assert str(ch) == "C21 (1550.12nm)"
        assert ch.pk is not None

    def test_default_status_is_available(self, wdm_fixtures):
        from decimal import Decimal

        from netbox_fms.choices import WavelengthChannelStatusChoices, WdmGridChoices, WdmNodeTypeChoices
        from netbox_fms.models import WavelengthChannel, WdmNode

        node = WdmNode.objects.create(
            device=wdm_fixtures["device"],
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch = WavelengthChannel.objects.create(
            wdm_node=node,
            grid_position=1,
            wavelength_nm=Decimal("1550.12"),
            label="C21",
        )
        assert ch.status == WavelengthChannelStatusChoices.AVAILABLE


@pytest.mark.django_db
class TestWavelengthService:
    def test_create_service(self, wdm_fixtures):
        from decimal import Decimal

        from netbox_fms.models import WavelengthService

        svc = WavelengthService.objects.create(
            name="Lambda-1",
            wavelength_nm=Decimal("1550.12"),
        )
        assert str(svc) == "Lambda-1"
        assert svc.pk is not None

    def test_service_with_tenant(self, wdm_fixtures):
        from decimal import Decimal

        from tenancy.models import Tenant

        from netbox_fms.models import WavelengthService

        tenant = Tenant.objects.create(name="WDM-Tenant", slug="wdm-tenant")
        svc = WavelengthService.objects.create(
            name="Lambda-2",
            wavelength_nm=Decimal("1550.12"),
            tenant=tenant,
        )
        assert svc.tenant == tenant


# ---------------------------------------------------------------------------
# Task 9: Auto-populate channels from profile
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWdmNodeAutoPopulate:
    def test_auto_populate_from_profile(self, wdm_fixtures):
        from netbox_fms.models import WdmChannelTemplate, WdmDeviceTypeProfile, WdmNode

        dt = wdm_fixtures["device_type"]
        profile = WdmDeviceTypeProfile.objects.create(
            device_type=dt,
            node_type="terminal_mux",
            grid="dwdm_100ghz",
        )
        WdmChannelTemplate.objects.create(
            profile=profile,
            grid_position=1,
            wavelength_nm=1560.61,
            label="C21",
        )
        WdmChannelTemplate.objects.create(
            profile=profile,
            grid_position=2,
            wavelength_nm=1559.79,
            label="C22",
        )

        node = WdmNode.objects.create(
            device=wdm_fixtures["device"],
            node_type="terminal_mux",
            grid="dwdm_100ghz",
        )
        assert node.channels.count() == 2
        ch1 = node.channels.get(grid_position=1)
        assert ch1.label == "C21"
        assert ch1.status == "available"

    def test_no_profile_no_auto_populate(self, wdm_fixtures):
        from netbox_fms.models import WdmNode

        node = WdmNode.objects.create(
            device=wdm_fixtures["device"],
            node_type="terminal_mux",
            grid="dwdm_100ghz",
        )
        assert node.channels.count() == 0

    def test_amplifier_no_channels_even_with_templates(self, wdm_fixtures):
        from netbox_fms.models import WdmChannelTemplate, WdmDeviceTypeProfile, WdmNode

        profile = WdmDeviceTypeProfile.objects.create(
            device_type=wdm_fixtures["device_type"],
            node_type="amplifier",
            grid="dwdm_100ghz",
        )
        WdmChannelTemplate.objects.create(
            profile=profile,
            grid_position=1,
            wavelength_nm=1560.61,
            label="C21",
        )
        WdmChannelTemplate.objects.create(
            profile=profile,
            grid_position=2,
            wavelength_nm=1559.79,
            label="C22",
        )
        node = WdmNode.objects.create(
            device=wdm_fixtures["device"],
            node_type="amplifier",
            grid="dwdm_100ghz",
        )
        assert node.channels.count() == 0


# ---------------------------------------------------------------------------
# Task 10: Protection & Lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWavelengthServiceProtection:
    def test_active_service_protects_channel(self, wdm_fixtures):
        from netbox_fms.models import (
            WavelengthChannel,
            WavelengthService,
            WavelengthServiceChannelAssignment,
            WdmNode,
        )

        node = WdmNode.objects.create(
            device=wdm_fixtures["device"],
            node_type="terminal_mux",
            grid="dwdm_100ghz",
        )
        ch = WavelengthChannel.objects.create(
            wdm_node=node,
            grid_position=1,
            wavelength_nm=1560.61,
            label="C21",
        )
        svc = WavelengthService.objects.create(
            name="SVC-P1",
            status="active",
            wavelength_nm=1560.61,
        )
        WavelengthServiceChannelAssignment.objects.create(
            service=svc,
            channel=ch,
            sequence=1,
        )
        svc.rebuild_nodes()

        with pytest.raises(Exception):  # ProtectedError
            ch.delete()

    def test_decommissioned_service_releases_channel(self, wdm_fixtures):
        from netbox_fms.models import (
            WavelengthChannel,
            WavelengthService,
            WavelengthServiceChannelAssignment,
            WdmNode,
        )

        node = WdmNode.objects.create(
            device=wdm_fixtures["device"],
            node_type="terminal_mux",
            grid="dwdm_100ghz",
        )
        ch = WavelengthChannel.objects.create(
            wdm_node=node,
            grid_position=1,
            wavelength_nm=1560.61,
            label="C21",
            status="lit",
        )
        svc = WavelengthService.objects.create(
            name="SVC-P2",
            status="active",
            wavelength_nm=1560.61,
        )
        WavelengthServiceChannelAssignment.objects.create(
            service=svc,
            channel=ch,
            sequence=1,
        )
        svc.rebuild_nodes()

        svc.status = "decommissioned"
        svc.save()

        assert svc.nodes.count() == 0
        ch.refresh_from_db()
        assert ch.status == "available"
        ch.delete()  # Should succeed now
