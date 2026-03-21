"""ITU grid constants for WDM channel plans.

Each channel is a tuple of (grid_position, label, wavelength_nm).
Wavelengths for DWDM are computed from the ITU-T frequency grid
using c = 299792.458 km/s (speed of light).
"""

# Speed of light in km/s (for THz → nm conversion: λ = c / f)
_SPEED_OF_LIGHT_KMS = 299792.458

# ---------------------------------------------------------------------------
# CWDM: 18 channels, 1270–1610 nm, 20 nm spacing (ITU-T G.694.2)
# ---------------------------------------------------------------------------
CWDM_CHANNELS: tuple[tuple[int, str, float], ...] = tuple(
    (i + 1, f"CWDM-{1270 + i * 20}", float(1270 + i * 20)) for i in range(18)
)

# ---------------------------------------------------------------------------
# DWDM 100 GHz: 44 channels, C21–C64 (ITU-T G.694.1)
# Start frequency: 192.10 THz (C21), spacing: 0.10 THz
# ---------------------------------------------------------------------------

_DWDM_100GHZ_START_FREQ = 192.10  # THz (C21 = 192.10 THz)
_DWDM_100GHZ_SPACING = 0.10  # THz
_DWDM_100GHZ_COUNT = 44
_DWDM_100GHZ_FIRST_CHANNEL = 21


def _dwdm_100ghz_channels() -> tuple[tuple[int, str, float], ...]:
    channels = []
    for i in range(_DWDM_100GHZ_COUNT):
        freq_thz = _DWDM_100GHZ_START_FREQ + i * _DWDM_100GHZ_SPACING
        wavelength_nm = _SPEED_OF_LIGHT_KMS / freq_thz
        channel_num = _DWDM_100GHZ_FIRST_CHANNEL + i
        label = f"C{channel_num}"
        channels.append((i + 1, label, round(wavelength_nm, 2)))
    return tuple(channels)


DWDM_100GHZ_CHANNELS: tuple[tuple[int, str, float], ...] = _dwdm_100ghz_channels()

# ---------------------------------------------------------------------------
# DWDM 50 GHz: 88 channels, C21–C64.5 with half-channels
# Start freq 192.10 THz, 0.05 THz spacing
# ---------------------------------------------------------------------------

_DWDM_50GHZ_SPACING = 0.05  # THz
_DWDM_50GHZ_COUNT = 88


def _dwdm_50ghz_channels() -> tuple[tuple[int, str, float], ...]:
    channels = []
    for i in range(_DWDM_50GHZ_COUNT):
        freq_thz = _DWDM_100GHZ_START_FREQ + i * _DWDM_50GHZ_SPACING
        wavelength_nm = _SPEED_OF_LIGHT_KMS / freq_thz
        # Even indices are whole channels (C21, C22, ...), odd are half (C21.5, C22.5, ...)
        channel_num = _DWDM_100GHZ_FIRST_CHANNEL + i // 2
        if i % 2 == 0:
            label = f"C{channel_num}"
        else:
            label = f"C{channel_num}.5"
        channels.append((i + 1, label, round(wavelength_nm, 2)))
    return tuple(channels)


DWDM_50GHZ_CHANNELS: tuple[tuple[int, str, float], ...] = _dwdm_50ghz_channels()

# ---------------------------------------------------------------------------
# Lookup dict: grid key → channel list
# ---------------------------------------------------------------------------
WDM_GRIDS: dict[str, tuple[tuple[int, str, float], ...]] = {
    "cwdm": CWDM_CHANNELS,
    "dwdm_100ghz": DWDM_100GHZ_CHANNELS,
    "dwdm_50ghz": DWDM_50GHZ_CHANNELS,
}
