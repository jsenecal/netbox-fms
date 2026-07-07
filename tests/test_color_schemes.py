import pytest
from dcim.models import Cable, Manufacturer

from netbox_fms.choices import FiberColorSchemeChoices
from netbox_fms.constants import (
    COLOR_SCHEME_PALETTES,
    EIA_598_COLORS,
    NBR_14771_COLORS,
    get_grouped_color_choices,
    get_strand_color,
)
from netbox_fms.forms import (
    BufferTubeTemplateBulkEditForm,
    BufferTubeTemplateForm,
    RibbonTemplateBulkEditForm,
    RibbonTemplateForm,
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


class TestGroupedColorChoices:
    def test_known_scheme_yields_primary_plus_other(self):
        groups = get_grouped_color_choices(FiberColorSchemeChoices.NBR_14771)
        assert len(groups) == 2
        label, options = groups[0]
        assert str(label) == "ABNT NBR 14771"
        assert options[0] == ("00ff00", "1 - Green")
        assert options[11] == ("00ffff", "12 - Aqua")
        assert len(options) == 12
        assert str(groups[1][0]) == "Other"

    def test_unknown_scheme_yields_both_standards(self):
        groups = get_grouped_color_choices(None)
        assert [str(g[0]) for g in groups] == ["EIA/TIA-598", "ABNT NBR 14771", "Other"]

    def test_other_group_excludes_standard_hexes(self):
        groups = get_grouped_color_choices(FiberColorSchemeChoices.EIA_598)
        other_values = [value for value, _label in groups[-1][1]]
        assert "ffffff" not in other_values  # White is position 6 in EIA group
        assert "00ffff" not in other_values  # Aqua is position 12
        assert "9e9e9e" in other_values  # NetBox Grey is not in the palette


def _picker_groups(form):
    """Return the optgroups of the form's color widget, skipping the blank choice."""
    return [(str(label), options) for label, options in form.fields["color"].widget.choices[1:]]


@pytest.mark.django_db
class TestSchemeAwareColorPicker:
    def test_edit_form_uses_parent_scheme(self):
        fct = _make_type("NBR-PICKER", "loose_tube", 12, FiberColorSchemeChoices.NBR_14771)
        tt = BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=12)
        groups = _picker_groups(BufferTubeTemplateForm(instance=tt))
        assert groups[0][0] == "ABNT NBR 14771"
        assert groups[0][1][0] == ("00ff00", "1 - Green")
        assert [g[0] for g in groups] == ["ABNT NBR 14771", "Other"]

    def test_add_form_with_initial_parent(self):
        fct = _make_type("NBR-PICKER-ADD", "loose_tube", 12, FiberColorSchemeChoices.NBR_14771)
        groups = _picker_groups(BufferTubeTemplateForm(initial={"fiber_cable_type": fct.pk}))
        assert groups[0][0] == "ABNT NBR 14771"

    def test_add_form_without_parent_shows_both_standards(self):
        groups = _picker_groups(BufferTubeTemplateForm())
        assert [g[0] for g in groups] == ["EIA/TIA-598", "ABNT NBR 14771", "Other"]

    def test_off_palette_current_value_stays_selectable(self):
        fct = _make_type("NBR-PICKER-OFF", "loose_tube", 12, FiberColorSchemeChoices.NBR_14771)
        tt = BufferTubeTemplate.objects.create(
            fiber_cable_type=fct, name="T1", position=1, fiber_count=12, color="123456"
        )
        groups = _picker_groups(BufferTubeTemplateForm(instance=tt))
        all_values = {value for _label, options in groups for value, _l in options}
        assert "123456" in all_values

    def test_ribbon_form_uses_parent_scheme(self):
        fct = _make_type("NBR-PICKER-RB", "ribbon", 12, FiberColorSchemeChoices.NBR_14771)
        rt = RibbonTemplate.objects.create(fiber_cable_type=fct, name="R1", position=1, fiber_count=12)
        groups = _picker_groups(RibbonTemplateForm(instance=rt))
        assert groups[0][0] == "ABNT NBR 14771"

    def test_bulk_edit_forms_show_both_standards(self):
        for form_cls in (BufferTubeTemplateBulkEditForm, RibbonTemplateBulkEditForm):
            groups = _picker_groups(form_cls())
            assert [g[0] for g in groups] == ["EIA/TIA-598", "ABNT NBR 14771", "Other"]
