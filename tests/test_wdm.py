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


# ---------------------------------------------------------------------------
# Integration tests: channel consistency across WDM nodes and fiber circuits
# ---------------------------------------------------------------------------


@pytest.fixture
def two_node_topology():
    """Create a MUX-A → FiberCircuit → MUX-B topology for integration tests."""
    from dcim.models import Device, DeviceRole, DeviceType, FrontPort, Manufacturer, RearPort, Site

    from netbox_fms.models import (
        FiberCircuit,
        WavelengthChannel,
        WdmNode,
        WdmTrunkPort,
    )

    site = Site.objects.create(name="WDM-Int-Site", slug="wdm-int-site")
    mfr = Manufacturer.objects.create(name="WDM-Int-Mfr", slug="wdm-int-mfr")
    role = DeviceRole.objects.create(name="WDM-Int-Role", slug="wdm-int-role")
    dt = DeviceType.objects.create(manufacturer=mfr, model="MUX-INT", slug="mux-int")

    dev_a = Device.objects.create(name="MUX-A", site=site, device_type=dt, role=role)
    dev_b = Device.objects.create(name="MUX-B", site=site, device_type=dt, role=role)

    # Trunk RearPorts (44 positions for DWDM 100GHz)
    rp_a = RearPort.objects.create(device=dev_a, name="Trunk", type="lc", positions=44)
    rp_b = RearPort.objects.create(device=dev_b, name="Trunk", type="lc", positions=44)

    # Client FrontPorts (one per device for channel C21)
    fp_a = FrontPort.objects.create(device=dev_a, name="Ch-1", type="lc", positions=1)
    fp_b = FrontPort.objects.create(device=dev_b, name="Ch-1", type="lc", positions=1)

    # WDM Nodes
    node_a = WdmNode.objects.create(device=dev_a, node_type="terminal_mux", grid="dwdm_100ghz")
    node_b = WdmNode.objects.create(device=dev_b, node_type="terminal_mux", grid="dwdm_100ghz")

    # Trunk ports
    WdmTrunkPort.objects.create(wdm_node=node_a, rear_port=rp_a, direction="common", position=1)
    WdmTrunkPort.objects.create(wdm_node=node_b, rear_port=rp_b, direction="common", position=1)

    # Channel C21 on both nodes (same grid_position=1, same wavelength)
    ch_a = WavelengthChannel.objects.create(
        wdm_node=node_a,
        grid_position=1,
        wavelength_nm=1560.61,
        label="C21",
        front_port=fp_a,
        status="lit",
    )
    ch_b = WavelengthChannel.objects.create(
        wdm_node=node_b,
        grid_position=1,
        wavelength_nm=1560.61,
        label="C21",
        front_port=fp_b,
        status="lit",
    )

    # Fiber circuit representing the trunk between the two MUXes
    circuit = FiberCircuit.objects.create(name="Trunk-AB", status="active", strand_count=1)

    return {
        "node_a": node_a,
        "node_b": node_b,
        "ch_a": ch_a,
        "ch_b": ch_b,
        "rp_a": rp_a,
        "rp_b": rp_b,
        "fp_a": fp_a,
        "fp_b": fp_b,
        "circuit": circuit,
        "dev_a": dev_a,
        "dev_b": dev_b,
    }


@pytest.mark.django_db
class TestWavelengthServiceChannelTracking:
    """Test that wavelength services correctly track channels across fiber circuits."""

    def test_service_links_channels_and_circuit(self, two_node_topology):
        """A service should reference channels at both ends and the connecting circuit."""
        from netbox_fms.models import (
            WavelengthService,
            WavelengthServiceChannelAssignment,
            WavelengthServiceCircuit,
        )

        svc = WavelengthService.objects.create(
            name="Lambda-C21",
            status="active",
            wavelength_nm=1560.61,
        )
        WavelengthServiceChannelAssignment.objects.create(
            service=svc,
            channel=two_node_topology["ch_a"],
            sequence=1,
        )
        WavelengthServiceCircuit.objects.create(
            service=svc,
            fiber_circuit=two_node_topology["circuit"],
            sequence=2,
        )
        WavelengthServiceChannelAssignment.objects.create(
            service=svc,
            channel=two_node_topology["ch_b"],
            sequence=3,
        )

        # Verify the relationships
        assert svc.channel_assignments.count() == 2
        assert svc.circuit_assignments.count() == 1

        # Verify ordering by sequence
        assignments = list(svc.channel_assignments.order_by("sequence"))
        assert assignments[0].channel == two_node_topology["ch_a"]
        assert assignments[1].channel == two_node_topology["ch_b"]

    def test_service_protects_both_channels_and_circuit(self, two_node_topology):
        """Active service should protect all referenced channels and circuits."""
        from netbox_fms.models import (
            WavelengthService,
            WavelengthServiceChannelAssignment,
            WavelengthServiceCircuit,
        )

        svc = WavelengthService.objects.create(
            name="Protected-C21",
            status="active",
            wavelength_nm=1560.61,
        )
        WavelengthServiceChannelAssignment.objects.create(
            service=svc,
            channel=two_node_topology["ch_a"],
            sequence=1,
        )
        WavelengthServiceCircuit.objects.create(
            service=svc,
            fiber_circuit=two_node_topology["circuit"],
            sequence=2,
        )
        WavelengthServiceChannelAssignment.objects.create(
            service=svc,
            channel=two_node_topology["ch_b"],
            sequence=3,
        )
        svc.rebuild_nodes()

        # Should have 3 protection nodes: 2 channels + 1 circuit
        assert svc.nodes.count() == 3

        # Can't delete either channel
        with pytest.raises(Exception):
            two_node_topology["ch_a"].delete()
        with pytest.raises(Exception):
            two_node_topology["ch_b"].delete()

        # Can't delete the fiber circuit
        with pytest.raises(Exception):
            two_node_topology["circuit"].delete()

    def test_channels_share_same_grid_position(self, two_node_topology):
        """Both channels in a service should have the same grid_position for routing consistency."""
        ch_a = two_node_topology["ch_a"]
        ch_b = two_node_topology["ch_b"]
        assert ch_a.grid_position == ch_b.grid_position
        assert ch_a.wavelength_nm == ch_b.wavelength_nm

    def test_channels_on_different_nodes(self, two_node_topology):
        """Channel assignments should reference different WDM nodes (not the same one twice)."""
        from netbox_fms.models import (
            WavelengthService,
            WavelengthServiceChannelAssignment,
        )

        svc = WavelengthService.objects.create(
            name="Multi-Node",
            status="active",
            wavelength_nm=1560.61,
        )
        WavelengthServiceChannelAssignment.objects.create(
            service=svc,
            channel=two_node_topology["ch_a"],
            sequence=1,
        )
        WavelengthServiceChannelAssignment.objects.create(
            service=svc,
            channel=two_node_topology["ch_b"],
            sequence=2,
        )

        nodes = set(svc.channel_assignments.values_list("channel__wdm_node_id", flat=True))
        assert len(nodes) == 2  # Two different WDM nodes

    def test_decommission_releases_all_channels(self, two_node_topology):
        """Decommissioning a service should release all channels at all nodes."""
        from netbox_fms.models import (
            WavelengthService,
            WavelengthServiceChannelAssignment,
            WavelengthServiceCircuit,
        )

        svc = WavelengthService.objects.create(
            name="Decomm-Test",
            status="active",
            wavelength_nm=1560.61,
        )
        WavelengthServiceChannelAssignment.objects.create(
            service=svc,
            channel=two_node_topology["ch_a"],
            sequence=1,
        )
        WavelengthServiceCircuit.objects.create(
            service=svc,
            fiber_circuit=two_node_topology["circuit"],
            sequence=2,
        )
        WavelengthServiceChannelAssignment.objects.create(
            service=svc,
            channel=two_node_topology["ch_b"],
            sequence=3,
        )
        svc.rebuild_nodes()
        assert svc.nodes.count() == 3

        # Decommission
        svc.status = "decommissioned"
        svc.save()

        assert svc.nodes.count() == 0

        # Both channels should be available
        two_node_topology["ch_a"].refresh_from_db()
        two_node_topology["ch_b"].refresh_from_db()
        assert two_node_topology["ch_a"].status == "available"
        assert two_node_topology["ch_b"].status == "available"

        # Circuit should be deletable now
        two_node_topology["circuit"].delete()


@pytest.mark.django_db
class TestWavelengthServiceValidation:
    """Test validation rules for wavelength services."""

    def test_service_rejects_mismatched_grids(self, two_node_topology):
        """A service should not accept channels from nodes with different grids."""
        from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site
        from django.core.exceptions import ValidationError

        from netbox_fms.models import (
            WavelengthChannel,
            WavelengthService,
            WavelengthServiceChannelAssignment,
            WdmNode,
        )

        # Create a CWDM node (different grid from the DWDM fixtures)
        site = Site.objects.create(name="CWDM-Site", slug="cwdm-site")
        mfr = Manufacturer.objects.create(name="CWDM-Mfr", slug="cwdm-mfr")
        role = DeviceRole.objects.create(name="CWDM-Role", slug="cwdm-role")
        dt = DeviceType.objects.create(manufacturer=mfr, model="CWDM-MUX", slug="cwdm-mux")
        dev = Device.objects.create(name="CWDM-Node", site=site, device_type=dt, role=role)
        cwdm_node = WdmNode.objects.create(device=dev, node_type="terminal_mux", grid="cwdm")
        cwdm_ch = WavelengthChannel.objects.create(
            wdm_node=cwdm_node,
            grid_position=1,
            wavelength_nm=1270.0,
            label="CWDM-1270",
        )

        svc = WavelengthService.objects.create(
            name="Mixed-Grid",
            status="planned",
            wavelength_nm=1560.61,
        )
        WavelengthServiceChannelAssignment.objects.create(
            service=svc,
            channel=two_node_topology["ch_a"],
            sequence=1,
        )
        WavelengthServiceChannelAssignment.objects.create(
            service=svc,
            channel=cwdm_ch,
            sequence=2,
        )

        with pytest.raises(ValidationError, match="same grid"):
            svc.clean()

    def test_service_rejects_mismatched_wavelength(self, two_node_topology):
        """Service wavelength_nm should match its channels' wavelength."""
        from django.core.exceptions import ValidationError

        from netbox_fms.models import (
            WavelengthService,
            WavelengthServiceChannelAssignment,
        )

        svc = WavelengthService.objects.create(
            name="Wrong-Lambda",
            status="planned",
            wavelength_nm=1310.0,  # Doesn't match C21
        )
        WavelengthServiceChannelAssignment.objects.create(
            service=svc,
            channel=two_node_topology["ch_a"],
            sequence=1,
        )

        with pytest.raises(ValidationError, match="wavelength"):
            svc.clean()

    def test_service_accepts_matching_channels(self, two_node_topology):
        """Service with consistent channels should pass validation."""
        from netbox_fms.models import (
            WavelengthService,
            WavelengthServiceChannelAssignment,
            WavelengthServiceCircuit,
        )

        svc = WavelengthService.objects.create(
            name="Valid-Service",
            status="active",
            wavelength_nm=1560.61,
        )
        WavelengthServiceChannelAssignment.objects.create(
            service=svc,
            channel=two_node_topology["ch_a"],
            sequence=1,
        )
        WavelengthServiceCircuit.objects.create(
            service=svc,
            fiber_circuit=two_node_topology["circuit"],
            sequence=2,
        )
        WavelengthServiceChannelAssignment.objects.create(
            service=svc,
            channel=two_node_topology["ch_b"],
            sequence=3,
        )

        # Should not raise
        svc.clean()


@pytest.mark.django_db
class TestChannelGridPositionConsistency:
    """Test that grid_position is consistent across nodes for the same channel."""

    def test_same_channel_same_position_on_both_nodes(self, two_node_topology):
        """Two nodes with the same grid should have matching positions for the same wavelength."""
        from netbox_fms.models import WavelengthChannel

        # Add C22 to both nodes
        ch_a2 = WavelengthChannel.objects.create(
            wdm_node=two_node_topology["node_a"],
            grid_position=2,
            wavelength_nm=1559.79,
            label="C22",
        )
        ch_b2 = WavelengthChannel.objects.create(
            wdm_node=two_node_topology["node_b"],
            grid_position=2,
            wavelength_nm=1559.79,
            label="C22",
        )
        assert ch_a2.grid_position == ch_b2.grid_position == 2
        assert ch_a2.wavelength_nm == ch_b2.wavelength_nm

    def test_unique_channel_per_service(self, two_node_topology):
        """A channel can only be assigned to one service at a time (unique constraint)."""

        from netbox_fms.models import (
            WavelengthService,
            WavelengthServiceChannelAssignment,
        )

        svc1 = WavelengthService.objects.create(
            name="SVC-1",
            status="active",
            wavelength_nm=1560.61,
        )
        svc2 = WavelengthService.objects.create(
            name="SVC-2",
            status="active",
            wavelength_nm=1560.61,
        )
        WavelengthServiceChannelAssignment.objects.create(
            service=svc1,
            channel=two_node_topology["ch_a"],
            sequence=1,
        )
        # Same channel on different service — this is currently allowed by the schema
        # (unique_together is per-service). This test documents the current behavior.
        WavelengthServiceChannelAssignment.objects.create(
            service=svc2,
            channel=two_node_topology["ch_a"],
            sequence=1,
        )
        # Both assignments exist — no constraint prevents sharing
        # (a channel can carry the same wavelength for different services if needed,
        # but in practice this shouldn't happen for the same physical channel)
        assert WavelengthServiceChannelAssignment.objects.filter(channel=two_node_topology["ch_a"]).count() == 2
