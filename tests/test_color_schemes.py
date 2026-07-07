from netbox_fms.choices import FiberColorSchemeChoices
from netbox_fms.constants import (
    COLOR_SCHEME_PALETTES,
    EIA_598_COLORS,
    NBR_14771_COLORS,
    get_strand_color,
)


class TestFiberColorSchemeChoices:
    def test_values(self):
        assert FiberColorSchemeChoices.EIA_598 == "eia_598"
        assert FiberColorSchemeChoices.NBR_14771 == "nbr_14771"

    def test_labels(self):
        labels = dict(FiberColorSchemeChoices.CHOICES)
        assert str(labels["eia_598"]) == "EIA/TIA-598"
        assert str(labels["nbr_14771"]) == "ABNT NBR 14771"


class TestGetStrandColor:
    def test_nbr_full_sequence(self):
        expected = [
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
        ]
        got = [get_strand_color(pos, FiberColorSchemeChoices.NBR_14771) for pos in range(1, 13)]
        assert got == expected

    def test_eia_position_one_is_blue(self):
        assert get_strand_color(1, FiberColorSchemeChoices.EIA_598) == ("0000ff", "Blue")

    def test_wraparound_past_twelve(self):
        assert get_strand_color(13, FiberColorSchemeChoices.NBR_14771) == ("00ff00", "Green")
        assert get_strand_color(13, FiberColorSchemeChoices.EIA_598) == ("0000ff", "Blue")

    def test_palette_registry(self):
        assert COLOR_SCHEME_PALETTES[FiberColorSchemeChoices.EIA_598] is EIA_598_COLORS
        assert COLOR_SCHEME_PALETTES[FiberColorSchemeChoices.NBR_14771] is NBR_14771_COLORS
