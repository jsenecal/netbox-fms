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
