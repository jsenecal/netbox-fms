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
        from netbox_fms.wdm_constants import CWDM_CHANNELS, DWDM_100GHZ_CHANNELS, DWDM_50GHZ_CHANNELS, WDM_GRIDS

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
