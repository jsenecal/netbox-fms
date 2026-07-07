import pytest
from dcim.models import Cable, Manufacturer

from netbox_fms.choices import FiberColorSchemeChoices
from netbox_fms.constants import (
    COLOR_SCHEME_PALETTES,
    EIA_598_COLORS,
    NBR_14771_COLORS,
    get_strand_color,
)
from netbox_fms.models import (
    BufferTubeTemplate,
    FiberCable,
    FiberCableType,
    FiberStrand,
    RibbonTemplate,
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


def _make_type(model, construction, strand_count, scheme=None):
    mfr, _ = Manufacturer.objects.get_or_create(name="NBR Mfr", slug="nbr-mfr")
    kwargs = {"color_scheme": scheme} if scheme else {}
    return FiberCableType.objects.create(
        manufacturer=mfr,
        model=model,
        construction=construction,
        strand_count=strand_count,
        **kwargs,
    )


def _strand_colors(fiber_cable):
    return list(
        FiberStrand.objects.filter(fiber_cable=fiber_cable).order_by("position").values_list("color", flat=True)
    )


@pytest.mark.django_db
class TestColorSchemeInstantiation:
    def test_default_scheme_is_eia_598(self):
        fct = _make_type("DEF-4F", "tight_buffer", 4)
        assert fct.color_scheme == FiberColorSchemeChoices.EIA_598
        fc = FiberCable.objects.create(fiber_cable_type=fct, cable=Cable.objects.create())
        assert _strand_colors(fc) == ["0000ff", "ff8000", "00ff00", "8b4513"]

    def test_tight_buffer_nbr(self):
        fct = _make_type("NBR-4F-TB", "tight_buffer", 4, FiberColorSchemeChoices.NBR_14771)
        fc = FiberCable.objects.create(fiber_cable_type=fct, cable=Cable.objects.create())
        assert _strand_colors(fc) == ["00ff00", "ffff00", "ffffff", "0000ff"]

    def test_loose_tube_nbr(self):
        fct = _make_type("NBR-12F-LT", "loose_tube", 12, FiberColorSchemeChoices.NBR_14771)
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, color="00ff00", fiber_count=12)
        fc = FiberCable.objects.create(fiber_cable_type=fct, cable=Cable.objects.create())
        assert _strand_colors(fc) == [hex_color for hex_color, _name in NBR_14771_COLORS]

    def test_ribbon_nbr(self):
        fct = _make_type("NBR-12F-RB", "ribbon", 12, FiberColorSchemeChoices.NBR_14771)
        RibbonTemplate.objects.create(fiber_cable_type=fct, name="R1", position=1, fiber_count=12)
        fc = FiberCable.objects.create(fiber_cable_type=fct, cable=Cable.objects.create())
        assert _strand_colors(fc) == [hex_color for hex_color, _name in NBR_14771_COLORS]

    def test_clone_fields_include_scheme(self):
        assert "color_scheme" in FiberCableType.clone_fields
