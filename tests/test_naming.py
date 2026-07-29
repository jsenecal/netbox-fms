"""Unit tests for the naming template engine."""

import pytest
from django.test import SimpleTestCase, override_settings

from netbox_fms import naming


class Stub:
    """Attribute bag standing in for a model instance."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def blank_type():
    """A FiberCableType-shaped object with every template left blank."""
    return Stub(**{spec.field: "" for spec in naming.TARGETS.values()})


class TestDefaults(SimpleTestCase):
    """Built-in defaults must reproduce the pre-template output exactly."""

    def setUp(self):
        self.compiled = naming.compile_for(blank_type())

    def test_front_port_name_tubed(self):
        ctx = {"cable": "NST", "tube": 3, "strand": 7}
        assert naming.render(naming.FRONT_PORT_NAME, self.compiled, ctx) == "NST:T3:F7"

    def test_front_port_name_tubeless(self):
        ctx = {"cable": "NST", "tube": None, "strand": 7}
        assert naming.render(naming.FRONT_PORT_NAME, self.compiled, ctx) == "NST:F7"

    def test_rear_port_name_tubed(self):
        ctx = {"cable": "NST", "tube": 3}
        assert naming.render(naming.REAR_PORT_NAME, self.compiled, ctx) == "NST:T3"

    def test_rear_port_name_tubeless(self):
        ctx = {"cable": "NST", "tube": None}
        assert naming.render(naming.REAR_PORT_NAME, self.compiled, ctx) == "NST"

    def test_strand_name_loose_tube(self):
        ctx = {"ribbon_name": None, "tube_name": "T3", "strand_local": 7}
        assert naming.render(naming.STRAND_NAME, self.compiled, ctx) == "T3-F7"

    def test_strand_name_ribbon(self):
        ctx = {"ribbon_name": "R2", "tube_name": "T3", "strand_local": 5}
        assert naming.render(naming.STRAND_NAME, self.compiled, ctx) == "R2-F5"

    def test_strand_name_tight_buffer(self):
        ctx = {"ribbon_name": None, "tube_name": None, "strand_local": 7}
        assert naming.render(naming.STRAND_NAME, self.compiled, ctx) == "F7"

    def test_labels_default_blank(self):
        assert naming.render(naming.FRONT_PORT_LABEL, self.compiled, {}) == ""
        assert naming.render(naming.REAR_PORT_LABEL, self.compiled, {}) == ""


class TestResolution(SimpleTestCase):
    """Cable type beats plugin config beats built-in."""

    def test_builtin_when_nothing_set(self):
        source = naming.resolve_source(naming.FRONT_PORT_NAME, blank_type())
        assert source == naming.DEFAULT_FRONT_PORT_NAME

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_name_template": "CFG-{{ strand }}"}})
    def test_plugin_config_beats_builtin(self):
        source = naming.resolve_source(naming.FRONT_PORT_NAME, blank_type())
        assert source == "CFG-{{ strand }}"

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_name_template": "CFG-{{ strand }}"}})
    def test_cable_type_beats_plugin_config(self):
        fct = blank_type()
        fct.front_port_name_template = "TYPE-{{ strand }}"
        source = naming.resolve_source(naming.FRONT_PORT_NAME, fct)
        assert source == "TYPE-{{ strand }}"


class TestValidation(SimpleTestCase):
    def test_syntax_error_rejected(self):
        with pytest.raises(naming.NamingError, match="syntax"):
            naming.validate(naming.FRONT_PORT_NAME, "{{ cable ")

    def test_strand_token_rejected_on_rear_port(self):
        with pytest.raises(naming.NamingError, match="render"):
            naming.validate(naming.REAR_PORT_NAME, "{{ cable }}:{{ strand }}")

    def test_unknown_token_rejected(self):
        with pytest.raises(naming.NamingError, match="render"):
            naming.validate(naming.FRONT_PORT_NAME, "{{ tubes }}")

    def test_overlong_dummy_render_rejected(self):
        with pytest.raises(naming.NamingError, match="maximum"):
            naming.validate(naming.FRONT_PORT_NAME, "X" * 65)

    def test_blank_is_valid(self):
        assert naming.validate(naming.FRONT_PORT_LABEL, "") is None


class TestRender(SimpleTestCase):
    def test_truncates_to_max_length(self):
        fct = blank_type()
        fct.front_port_name_template = "{{ cable }}"
        compiled = naming.compile_for(fct)
        rendered = naming.render(naming.FRONT_PORT_NAME, compiled, {"cable": "L" * 100})
        assert len(rendered) == 64

    def test_context_scoped_to_target_tokens(self):
        """A rear template cannot see strand tokens even if the caller passes them."""
        fct = blank_type()
        fct.rear_port_name_template = "{{ strand }}"
        compiled = naming.compile_for(fct)
        with pytest.raises(naming.NamingError):
            naming.render(naming.REAR_PORT_NAME, compiled, {"cable": "NST", "strand": 7})


class TestColorName(SimpleTestCase):
    def test_known_hex_returns_palette_name(self):
        assert naming.color_name("0000ff", "eia_598") == "Blue"

    def test_scheme_specific_name(self):
        """708090 is Slate under EIA-598 and Gray under NBR-14771."""
        assert naming.color_name("708090", "eia_598") == "Slate"
        assert naming.color_name("708090", "nbr_14771") == "Gray"

    def test_unknown_hex_falls_back_to_hex(self):
        assert naming.color_name("abcdef", "eia_598") == "abcdef"

    def test_blank_returns_none(self):
        assert naming.color_name("", "eia_598") is None
