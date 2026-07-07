from .choices import FiberColorSchemeChoices

# EIA/TIA-598 standard fiber color code.
# Used for buffer tube and fiber strand identification.
# Index 0 = position 1, etc.
EIA_598_COLORS = (
    ("0000ff", "Blue"),
    ("ff8000", "Orange"),
    ("00ff00", "Green"),
    ("8b4513", "Brown"),
    ("708090", "Slate"),
    ("ffffff", "White"),
    ("ff0000", "Red"),
    ("000000", "Black"),
    ("ffff00", "Yellow"),
    ("ee82ee", "Violet"),
    ("ff69b4", "Rose"),
    ("00ffff", "Aqua"),
)


def get_eia598_color(position):
    """
    Return the (hex_color, name) tuple for a 1-indexed fiber/tube position.
    Cycles through the 12-color palette for positions > 12.
    """
    idx = (position - 1) % len(EIA_598_COLORS)
    return EIA_598_COLORS[idx]


# ABNT NBR 14771 fiber color code (Brazilian standard).
# Same 12 colors as EIA-598, different position order; position 10 is
# named "Gray" (NBR "Cinza") but shares the EIA Slate hex.
NBR_14771_COLORS = (
    ("00ff00", "Green"),
    ("ffff00", "Yellow"),
    ("ffffff", "White"),
    ("0000ff", "Blue"),
    ("ff0000", "Red"),
    ("ee82ee", "Violet"),
    ("8b4513", "Brown"),
    ("ff69b4", "Rose"),
    ("000000", "Black"),
    ("708090", "Gray"),
    ("ff8000", "Orange"),
    ("00ffff", "Aqua"),
)

COLOR_SCHEME_PALETTES = {
    FiberColorSchemeChoices.EIA_598: EIA_598_COLORS,
    FiberColorSchemeChoices.NBR_14771: NBR_14771_COLORS,
}


def get_strand_color(position, scheme):
    """
    Return the (hex_color, name) tuple for a 1-indexed fiber position under
    the given color scheme. Cycles through the palette for positions > 12.
    """
    palette = COLOR_SCHEME_PALETTES[scheme]
    return palette[(position - 1) % len(palette)]


# Subset of dcim.choices.CableTypeChoices values that this plugin treats as
# fibre. A FiberCable can only be linked to a dcim.Cable whose ``type`` is
# in this set. AOC (active optical cable) is intentionally excluded -- it is
# transceiver-bonded and not managed as outside plant.
FIBER_CABLE_TYPES = frozenset(
    {
        "smf",
        "smf-os1",
        "smf-os2",
        "mmf",
        "mmf-om1",
        "mmf-om2",
        "mmf-om3",
        "mmf-om4",
        "mmf-om5",
    }
)
