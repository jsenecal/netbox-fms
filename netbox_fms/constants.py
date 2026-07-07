from django.utils.translation import gettext_lazy as _

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


def get_grouped_color_choices(scheme=None):
    """
    Build optgrouped color choices for component color pickers.

    When ``scheme`` is a known color scheme, its palette is the primary
    optgroup (options labelled "position - name"); otherwise every known
    scheme gets a group. A trailing "Other" group carries the NetBox
    generic colors not already present in a scheme group, so off-palette
    values stay selectable.
    """
    from netbox.choices import ColorChoices

    scheme_labels = dict(FiberColorSchemeChoices.CHOICES)
    schemes = [scheme] if scheme in COLOR_SCHEME_PALETTES else list(COLOR_SCHEME_PALETTES)
    groups = []
    used = set()
    for s in schemes:
        options = [
            (hex_color, f"{position} - {name}")
            for position, (hex_color, name) in enumerate(COLOR_SCHEME_PALETTES[s], start=1)
        ]
        groups.append((scheme_labels[s], options))
        used.update(hex_color for hex_color, _label in options)
    other = [(value, label) for value, label in ColorChoices.CHOICES if value not in used]
    groups.append((_("Other"), other))
    return groups
