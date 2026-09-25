"""Tests for the port label template engine.

Covers the label slice of the naming-template design (regression surface for
issue #69): the pure Jinja2 engine, plugin-config resolution, context
builders, and the built-in non-blank defaults.
"""

from unittest import mock

import pytest
from django.test import SimpleTestCase, TestCase, override_settings

from netbox_fms import naming
from tests.conftest import NAME_TEMPLATES, ClosurePairMixin, call_command_capture, port_labels, port_names


class Stub:
    """Attribute bag standing in for a model instance."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class TestNameGrammar(SimpleTestCase):
    """Write-once port names: cable pk plus absolute fiber number.

    The grammar has exactly one home; every producer of generated port
    names (provisioning, conversion, sample data) must call these helpers.
    """

    def test_front_port_name_is_pk_and_absolute_position(self):
        assert naming.front_port_name(1043, 25) == "1043:F25"

    def test_rear_port_name_for_buffer_tube(self):
        assert naming.rear_port_name(1043, tube=3) == "1043:T3"

    def test_rear_port_name_for_ribbon(self):
        assert naming.rear_port_name(1043, ribbon=2) == "1043:R2"

    def test_rear_port_name_bare_for_containerless_cable(self):
        assert naming.rear_port_name(1043) == "1043"

    def test_ribbon_wins_over_tube(self):
        """A ribbon inside a tube is the splice unit; its rear port is R, not T."""
        assert naming.rear_port_name(7, tube=1, ribbon=4) == "7:R4"


class TestDefaults(SimpleTestCase):
    """The built-in defaults must carry the readable port identity."""

    def setUp(self):
        self.compiled = naming.compile_labels()

    def test_front_label_tubed(self):
        ctx = {
            "cable": "CL-01 -- CL-02",
            "tube_name": "T1",
            "tube_color": "Blue",
            "ribbon_name": None,
            "strand_color": "Slate",
            "strand": 25,
        }
        rendered = naming.render(naming.FRONT_PORT_LABEL, self.compiled, ctx)
        assert rendered == "CL-01 -- CL-02 / T1 (Blue) / Slate / F25"

    def test_front_label_tubeless(self):
        ctx = {
            "cable": "TB",
            "tube_name": None,
            "tube_color": None,
            "ribbon_name": None,
            "strand_color": "Orange",
            "strand": 2,
        }
        assert naming.render(naming.FRONT_PORT_LABEL, self.compiled, ctx) == "TB / Orange / F2"

    def test_front_label_ribbon(self):
        ctx = {
            "cable": "CR",
            "tube_name": None,
            "tube_color": None,
            "ribbon_name": "R1",
            "strand_color": "Blue",
            "strand": 5,
        }
        assert naming.render(naming.FRONT_PORT_LABEL, self.compiled, ctx) == "CR / R1 / Blue / F5"

    def test_front_label_tube_without_color(self):
        ctx = {
            "cable": "NC",
            "tube_name": "T2",
            "tube_color": None,
            "ribbon_name": None,
            "strand_color": None,
            "strand": 13,
        }
        assert naming.render(naming.FRONT_PORT_LABEL, self.compiled, ctx) == "NC / T2 / F13"

    def test_rear_label_tubed(self):
        ctx = {"cable": "CL", "tube_name": "T3", "tube_color": "Green", "ribbon_name": None}
        assert naming.render(naming.REAR_PORT_LABEL, self.compiled, ctx) == "CL / T3 (Green)"

    def test_rear_label_tubeless(self):
        ctx = {"cable": "CL", "tube_name": None, "tube_color": None, "ribbon_name": None}
        assert naming.render(naming.REAR_PORT_LABEL, self.compiled, ctx) == "CL"

    def test_rear_label_ribbon(self):
        """A rear port can now cover a ribbon; its label must say which one."""
        ctx = {"cable": "CL", "tube_name": None, "tube_color": None, "ribbon_name": "R2"}
        assert naming.render(naming.REAR_PORT_LABEL, self.compiled, ctx) == "CL / R2"

    def test_rear_label_ribbon_in_tube(self):
        ctx = {"cable": "CL", "tube_name": "T1", "tube_color": "Blue", "ribbon_name": "R1"}
        assert naming.render(naming.REAR_PORT_LABEL, self.compiled, ctx) == "CL / T1 (Blue) / R1"

    def test_defaults_pass_their_own_validation(self):
        """The shipped defaults must survive the validator they are checked by."""
        assert naming.validate(naming.FRONT_PORT_LABEL, naming.DEFAULT_FRONT_PORT_LABEL) is None
        assert naming.validate(naming.REAR_PORT_LABEL, naming.DEFAULT_REAR_PORT_LABEL) is None


class TestResolution(SimpleTestCase):
    """Plugin config beats the built-in default; empty string opts out."""

    def test_builtin_when_nothing_set(self):
        assert naming.resolve_source(naming.FRONT_PORT_LABEL) == naming.DEFAULT_FRONT_PORT_LABEL
        assert naming.resolve_source(naming.REAR_PORT_LABEL) == naming.DEFAULT_REAR_PORT_LABEL

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": "CFG-{{ strand }}"}})
    def test_plugin_config_beats_builtin(self):
        assert naming.resolve_source(naming.FRONT_PORT_LABEL) == "CFG-{{ strand }}"
        # The other target still falls through to its default.
        assert naming.resolve_source(naming.REAR_PORT_LABEL) == naming.DEFAULT_REAR_PORT_LABEL

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": "", "rear_port_label_template": ""}})
    def test_empty_config_disables_label_management(self):
        """An explicit empty template compiles to None: leave stored labels alone."""
        compiled = naming.compile_labels()
        assert naming.render(naming.FRONT_PORT_LABEL, compiled, {}) is None
        assert naming.render(naming.REAR_PORT_LABEL, compiled, {}) is None

    def test_configured_template_rendering_empty_is_not_none(self):
        """An empty render from a real template is a deliberate blank, not "unset"."""
        with override_settings(
            PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": "{% if tube %}T{{ tube }}{% endif %}"}}
        ):
            compiled = naming.compile_labels()
            assert naming.render(naming.FRONT_PORT_LABEL, compiled, {"tube": None}) == ""


MALFORMED = "{{ cable "


class TestPluginConfigSyntaxGuard(SimpleTestCase):
    """A malformed PLUGINS_CONFIG template must surface as a NamingError.

    A template set plugin-wide never passes through a form or serializer, so
    it reaches ``compile_labels`` unvalidated -- and a raw
    ``jinja2.TemplateSyntaxError`` is not a ``NamingError``, so the callers'
    ``except NamingError`` guards would miss it and every FMS cable save and
    provisioning call would raise.
    """

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": MALFORMED}})
    def test_compile_labels_raises_naming_error(self):
        with pytest.raises(naming.NamingError, match="syntax"):
            naming.compile_labels()

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"rear_port_label_template": MALFORMED}})
    def test_validate_plugin_config_names_the_setting(self):
        problems = naming.validate_plugin_config()
        assert [key for key, _msg in problems] == ["rear_port_label_template"]
        assert "syntax" in problems[0][1]

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": "{{ cable }}:F{{ strand }}"}})
    def test_validate_plugin_config_clean_config(self):
        assert naming.validate_plugin_config() == []

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"rear_port_label_template": MALFORMED}})
    def test_startup_check_logs_without_raising(self):
        """A bad setting must be reported at startup, never block NetBox booting."""
        from netbox_fms import NetBoxFMSConfig

        with self.assertLogs("netbox_fms", level="ERROR") as captured:
            NetBoxFMSConfig._check_port_templates()
        joined = "\n".join(captured.output)
        assert "rear_port_label_template" in joined
        assert "syntax" in joined


class TestValidation(SimpleTestCase):
    def test_syntax_error_rejected(self):
        with pytest.raises(naming.NamingError, match="syntax"):
            naming.validate(naming.FRONT_PORT_LABEL, MALFORMED)

    def test_strand_token_rejected_on_rear_label(self):
        """A rear port covers a whole tube; strand tokens are front-only."""
        with pytest.raises(naming.NamingError, match="render"):
            naming.validate(naming.REAR_PORT_LABEL, "{{ cable }}:{{ strand }}")

    def test_unknown_token_rejected(self):
        with pytest.raises(naming.NamingError, match="render"):
            naming.validate(naming.FRONT_PORT_LABEL, "{{ tubes }}")

    def test_overlong_dummy_render_rejected(self):
        with pytest.raises(naming.NamingError, match="maximum"):
            naming.validate(naming.FRONT_PORT_LABEL, "X" * 65)

    def test_blank_is_valid(self):
        assert naming.validate(naming.FRONT_PORT_LABEL, "") is None

    def test_sandbox_blocks_attribute_escape(self):
        """The sandboxed environment must refuse dunder attribute traversal."""
        with pytest.raises(naming.NamingError):
            naming.validate(naming.FRONT_PORT_LABEL, "{{ cable.__class__.__mro__ }}")


class TestRender(SimpleTestCase):
    def test_truncates_to_max_length(self):
        """dcim port label columns are 64 characters; the render must fit them."""
        with override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": "{{ cable }}"}}):
            compiled = naming.compile_labels()
            rendered = naming.render(naming.FRONT_PORT_LABEL, compiled, {"cable": "L" * 100})
        assert len(rendered) == 64

    def test_context_scoped_to_target_tokens(self):
        """A rear template cannot see strand tokens even if the caller passes them."""
        with override_settings(PLUGINS_CONFIG={"netbox_fms": {"rear_port_label_template": "{{ strand }}"}}):
            compiled = naming.compile_labels()
            with pytest.raises(naming.NamingError):
                naming.render(naming.REAR_PORT_LABEL, compiled, {"cable": "NST", "strand": 7})


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


class TestPortContext(SimpleTestCase):
    """The context builder maps model attributes to template tokens."""

    def _strand(self):
        ribbon = Stub(position=2, name="R2", color="ff8000")
        return Stub(position=25, color="708090", ribbon=ribbon)

    def test_front_context(self):
        class _Cable:
            pk = 17

            def __str__(self):
                return "CL-01"

        tube = Stub(position=3, name="T3", color="0000ff")
        ctx = naming.port_context(
            cable=_Cable(),
            cable_type="ACME 144F",
            device=Stub(name="FOSC-1"),
            end="A",
            color_scheme="eia_598",
            tube=tube,
            strand=self._strand(),
        )
        assert ctx == {
            "cable": "CL-01",
            "cable_id": 17,
            "cable_type": "ACME 144F",
            "device": "FOSC-1",
            "end": "A",
            "tray": None,
            "tray_position": None,
            "tube": 3,
            "tube_name": "T3",
            "tube_color": "Blue",
            "tube_color_hex": "0000ff",
            "ribbon": 2,
            "ribbon_name": "R2",
            "ribbon_color": "Orange",
            "ribbon_color_hex": "ff8000",
            "strand": 25,
            "strand_color": "Slate",
            "strand_color_hex": "708090",
        }

    def test_rear_context_has_no_strand_or_ribbon_values(self):
        ctx = naming.port_context(
            cable=None,
            cable_type="ACME 144F",
            device=Stub(name="FOSC-1"),
            end="B",
            color_scheme="eia_598",
            tube=None,
        )
        assert ctx["cable"] == ""
        assert ctx["cable_id"] is None
        assert ctx["end"] == "B"
        assert ctx["tube"] is None
        assert ctx["ribbon"] is None
        assert ctx["strand"] is None

    def test_explicit_ribbon_feeds_rear_context(self):
        """Rear-port callers have a ribbon but no strand to derive it from."""
        ctx = naming.port_context(
            cable=None,
            cable_type="ACME 144F",
            device=Stub(name="FOSC-1"),
            end="A",
            color_scheme="eia_598",
            ribbon=Stub(position=2, name="R2", color="ff8000"),
        )
        assert ctx["ribbon_name"] == "R2"
        assert ctx["ribbon_color"] == "Orange"
        assert ctx["strand"] is None


class LabelFixtureMixin(ClosurePairMixin):
    """Closure pair plus a builder for provisioned FiberCables."""

    prefix = "LBL"

    def _build(self, label, **kwargs):
        return self._provision(label, **kwargs)[:2]

    def _provision(self, label, *, construction="loose_tube", tube=True, ribbon=False, strand_count=2):
        """Provision a two-strand cable; returns (type, fiber cable, provisioning warnings)."""
        from netbox_fms.models import BufferTubeTemplate, FiberCableType, RibbonTemplate
        from netbox_fms.services import create_closure_cable

        fct = FiberCableType.objects.create(
            manufacturer=self.mfr,
            model=f"FCT-{label}",
            construction=construction,
            strand_count=strand_count,
        )
        if tube:
            BufferTubeTemplate.objects.create(
                fiber_cable_type=fct, name="T1", position=1, fiber_count=strand_count, color="0000ff"
            )
        if ribbon:
            RibbonTemplate.objects.create(fiber_cable_type=fct, name="R1", position=1, fiber_count=strand_count)
        fc, warnings = create_closure_cable(
            device_a=self.dev_a,
            device_b=self.dev_b,
            fiber_cable_type=fct,
            cable_attrs={"type": "smf-os2", "label": label},
        )
        return fct, fc, warnings


class TestProvisionedLabels(LabelFixtureMixin, TestCase):
    """_provision_device_ports must stamp default labels onto new ports."""

    def test_loose_tube_labels(self):
        from dcim.models import FrontPort, RearPort

        self._build("LT")
        expected_front = ["LT / T1 (Blue) / Blue / F1", "LT / T1 (Blue) / Orange / F2"]
        assert port_labels(self.dev_a, FrontPort) == expected_front
        assert port_labels(self.dev_b, FrontPort) == expected_front
        assert port_labels(self.dev_a, RearPort) == ["LT / T1 (Blue)"]
        assert port_labels(self.dev_b, RearPort) == ["LT / T1 (Blue)"]

    def test_tight_buffer_labels(self):
        from dcim.models import FrontPort, RearPort

        self._build("TB", construction="tight_buffer", tube=False)
        assert port_labels(self.dev_a, FrontPort) == ["TB / Blue / F1", "TB / Orange / F2"]
        assert port_labels(self.dev_a, RearPort) == ["TB"]

    def test_central_ribbon_labels(self):
        from dcim.models import FrontPort

        self._build("CRB", construction="ribbon", tube=False, ribbon=True)
        assert port_labels(self.dev_a, FrontPort) == ["CRB / R1 / Blue / F1", "CRB / R1 / Orange / F2"]

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": "", "rear_port_label_template": ""}})
    def test_opted_out_provisioning_leaves_labels_blank(self):
        from dcim.models import FrontPort, RearPort

        self._build("OPT")
        assert port_labels(self.dev_a, FrontPort) == ["", ""]
        assert port_labels(self.dev_a, RearPort) == [""]

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": MALFORMED}})
    def test_malformed_config_degrades_to_blank_labels(self):
        """Provisioning must survive a broken plugin-config template."""
        from dcim.models import FrontPort

        self._build("BAD")
        assert port_labels(self.dev_a, FrontPort) == ["", ""]


class TestRelabelSignal(LabelFixtureMixin, TestCase):
    """A cable save must re-render labels on the cable's FMS-provisioned ports."""

    def test_cable_relabel_rerenders_labels(self):
        from dcim.models import FrontPort, RearPort

        _fct, fc = self._build("OLD")

        fc.cable.label = "NEW"
        fc.cable.save()

        assert port_labels(self.dev_a, FrontPort) == [
            "NEW / T1 (Blue) / Blue / F1",
            "NEW / T1 (Blue) / Orange / F2",
        ]
        assert port_labels(self.dev_a, RearPort) == ["NEW / T1 (Blue)"]

    def test_device_and_end_tokens_differ_per_side(self):
        """The relabel path must resolve device and cable end per port."""
        from dcim.models import FrontPort

        _fct, fc = self._build("END")
        with override_settings(
            PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": "{{ device }}:{{ end }}:F{{ strand }}"}}
        ):
            fc.cable.save()

        assert port_labels(self.dev_a, FrontPort) == ["LBL-A:A:F1", "LBL-A:A:F2"]
        assert port_labels(self.dev_b, FrontPort) == ["LBL-B:B:F1", "LBL-B:B:F2"]

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": "", "rear_port_label_template": ""}})
    def test_operator_labels_survive_when_opted_out(self):
        """The None protocol: no configured template means no label write."""
        from dcim.models import FrontPort, RearPort

        _fct, fc = self._build("KEEP")
        fp = FrontPort.objects.filter(device=self.dev_a).order_by("name").first()
        rp = RearPort.objects.filter(device=self.dev_a).order_by("name").first()
        # Bypass save() so the operator labels are planted without side effects.
        FrontPort.objects.filter(pk=fp.pk).update(label="Rack-A-01")
        RearPort.objects.filter(pk=rp.pk).update(label="Rack-A-RP")

        fc.cable.label = "KEEP2"
        fc.cable.save()

        fp.refresh_from_db()
        rp.refresh_from_db()
        assert fp.label == "Rack-A-01"
        assert rp.label == "Rack-A-RP"

    def test_malformed_config_degrades_and_leaves_labels_alone(self):
        from dcim.models import FrontPort

        _fct, fc = self._build("SAFE")
        before = port_labels(self.dev_a, FrontPort)

        with override_settings(PLUGINS_CONFIG={"netbox_fms": {"rear_port_label_template": MALFORMED}}):
            fc.cable.description = "touched"
            fc.cable.save()  # must not raise

        assert port_labels(self.dev_a, FrontPort) == before


class TestRerenderPortLabelsCommand(LabelFixtureMixin, TestCase):
    """rerender_port_labels backfills labels on brownfield data."""

    def _blank_labels(self):
        from dcim.models import FrontPort, RearPort

        FrontPort.objects.update(label="")
        RearPort.objects.update(label="")

    def test_backfills_default_labels(self):
        from dcim.models import FrontPort, RearPort

        self._build("BF")
        self._blank_labels()

        out, err = call_command_capture("rerender_port_labels")

        assert err == ""
        assert "->" in out
        assert port_labels(self.dev_a, FrontPort) == [
            "BF / T1 (Blue) / Blue / F1",
            "BF / T1 (Blue) / Orange / F2",
        ]
        assert port_labels(self.dev_a, RearPort) == ["BF / T1 (Blue)"]

    def test_dry_run_writes_nothing(self):
        from dcim.models import FrontPort

        self._build("DRY")
        self._blank_labels()

        out, _err = call_command_capture("rerender_port_labels", "--dry-run")

        assert "->" in out, "the dry run must still report the changes it would make"
        assert port_labels(self.dev_a, FrontPort) == ["", ""]

    def test_cable_type_restricts_the_walk(self):
        from dcim.models import FrontPort

        self._build("ONE")
        self._build("TWO")
        self._blank_labels()

        call_command_capture("rerender_port_labels", "--cable-type", "FCT-ONE")

        labels = port_labels(self.dev_a, FrontPort)
        assert "ONE / T1 (Blue) / Blue / F1" in labels
        assert labels.count("") == 2, "the other cable type's ports must stay untouched"

    def test_limit_stops_after_n_cables(self):
        from dcim.models import FrontPort

        _fct1, fc1 = self._build("LIM1")
        self._build("LIM2")
        self._blank_labels()

        call_command_capture("rerender_port_labels", "--limit", "1")

        relabeled = FrontPort.objects.exclude(label="")
        assert relabeled.count() == 4, "exactly one cable (two devices x two strands) must be processed"
        strand_fp_ids = {fp_id for s in fc1.fiber_strands.all() for fp_id in (s.front_port_a_id, s.front_port_b_id)}
        assert {fp.pk for fp in relabeled} == strand_fp_ids

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": "", "rear_port_label_template": ""}})
    def test_opted_out_run_leaves_operator_labels_alone(self):
        from dcim.models import FrontPort

        self._build("OPTC")
        FrontPort.objects.update(label="Rack-7")

        out, err = call_command_capture("rerender_port_labels")

        assert out == "" and err == ""
        assert set(FrontPort.objects.values_list("label", flat=True)) == {"Rack-7"}

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": MALFORMED}})
    def test_broken_template_is_reported_not_raised(self):
        from dcim.models import FrontPort

        self._build("BRK")
        self._blank_labels()

        _out, err = call_command_capture("rerender_port_labels")

        assert "syntax" in err
        assert port_labels(self.dev_a, FrontPort) == ["", ""]


class TestProvisioningRenderFailure(LabelFixtureMixin, TestCase):
    """A template that compiles but fails at render must not break provisioning."""

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": "{{ bogus }}"}})
    def test_undefined_token_degrades_to_blank_front_labels(self):
        from dcim.models import FrontPort, RearPort

        self._build("RF")
        assert port_labels(self.dev_a, FrontPort) == ["", ""]
        # The rear template is untouched and still renders.
        assert port_labels(self.dev_a, RearPort) == ["RF / T1 (Blue)"]


_TRAY_TEMPLATE = "{% if tray %}{{ tray }}:{{ tray_position }}/{% endif %}F{{ strand }}"


class TestTrayLabelToken(LabelFixtureMixin, TestCase):
    """Front labels can reference the tube's tray via TubeAssignment (#154 follow-up).

    The tray tokens are front-only and driven by assignment changes: a tube
    assignment save or delete re-renders the cable's labels, but only when a
    configured template actually uses a tray token.
    """

    def _assigned_tray(self, fc):
        from netbox_fms.models import TubeAssignment
        from tests.conftest import make_tray_module, make_tray_type

        tray = make_tray_module(self.dev_a, make_tray_type(self.mfr, "TRK Tray"), "TRK Bay")
        assignment = TubeAssignment.objects.create(
            closure=self.dev_a, tray=tray, buffer_tube=fc.buffer_tubes.first(), position=1
        )
        return tray, assignment

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": _TRAY_TEMPLATE}})
    def test_assignment_save_renders_tray_into_labels(self):
        from dcim.models import FrontPort

        _fct, fc = self._build("TRK")
        tray, _assignment = self._assigned_tray(fc)
        assert port_labels(self.dev_a, FrontPort) == [f"{tray}:1/F1", f"{tray}:1/F2"]
        # The far device has no assignment; its labels stay tray-less.
        assert port_labels(self.dev_b, FrontPort) == ["F1", "F2"]

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": _TRAY_TEMPLATE}})
    def test_assignment_delete_clears_tray_from_labels(self):
        from dcim.models import FrontPort

        _fct, fc = self._build("TRD")
        _tray, assignment = self._assigned_tray(fc)
        assignment.delete()
        assert port_labels(self.dev_a, FrontPort) == ["F1", "F2"]

    def test_labels_use_tray_false_for_defaults(self):
        from netbox_fms import naming

        assert naming.labels_use_tray() is False

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": _TRAY_TEMPLATE}})
    def test_labels_use_tray_detects_the_token(self):
        from netbox_fms import naming

        assert naming.labels_use_tray() is True

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": ""}})
    def test_labels_use_tray_skips_opted_out_target(self):
        from netbox_fms import naming

        assert naming.labels_use_tray() is False

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": "{% if tray %}{{ tray "}})
    def test_labels_use_tray_tolerates_malformed_template(self):
        """The gate must never raise: a malformed template is someone else's
        problem (startup check, render guards); the gate just answers False.
        """
        from netbox_fms import naming

        assert naming.labels_use_tray() is False

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": _TRAY_TEMPLATE}})
    def test_relabel_guard_tolerates_cascading_tube_delete(self):
        """A cascade that already removed the tube must not break the handler."""
        from netbox_fms.models import BufferTube
        from netbox_fms.signals import _relabel_for_tube_assignment

        _fct, fc = self._build("TRC")
        _tray, assignment = self._assigned_tray(fc)
        BufferTube.objects.filter(pk=assignment.buffer_tube_id).delete()
        # The handler receives an uncached instance whose tube is already
        # gone, exactly what a cascading delete hands the post_delete signal.
        from netbox_fms.models import TubeAssignment

        stale = TubeAssignment(
            pk=assignment.pk,
            closure_id=assignment.closure_id,
            tray_id=assignment.tray_id,
            buffer_tube_id=assignment.buffer_tube_id,
        )
        _relabel_for_tube_assignment(stale)  # must not raise

    def test_tray_token_rejected_for_rear_target(self):
        from netbox_fms import naming

        with pytest.raises(naming.NamingError):
            naming.validate(naming.REAR_PORT_LABEL, "{{ tray }}")


class TestNameTargets(SimpleTestCase):
    """Port NAME templates: unset means the pk grammar, never a blank name."""

    def test_settings_keys(self):
        assert naming.TARGETS[naming.FRONT_PORT_NAME].setting == "front_port_name_template"
        assert naming.TARGETS[naming.REAR_PORT_NAME].setting == "rear_port_name_template"

    def test_unset_name_templates_compile_to_none(self):
        assert naming.compile_names() == {naming.FRONT_PORT_NAME: None, naming.REAR_PORT_NAME: None}

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_name_template": "{{ cable }}-F{{ strand }}"}})
    def test_name_render_is_not_truncated(self):
        """Names are pre-checked for length, so an overflow must stay visible, not be silently cut."""
        compiled = naming.compile_names()
        rendered = naming.render(naming.FRONT_PORT_NAME, compiled, {"cable": "N" * 100, "strand": 3}, truncate=False)
        assert rendered == "N" * 100 + "-F3"

    def test_tray_tokens_are_not_name_tokens(self):
        """Ports are named before any tray assignment exists; a tray token could only render None."""
        with pytest.raises(naming.NamingError, match="render"):
            naming.validate(naming.FRONT_PORT_NAME, "{{ tray }}")

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"rear_port_name_template": MALFORMED}})
    def test_startup_validation_covers_name_templates(self):
        assert [key for key, _msg in naming.validate_plugin_config()] == ["rear_port_name_template"]


class TestMaxLength(SimpleTestCase):
    """Length limits are read from the dcim columns, so they follow NetBox if it widens them."""

    def test_validation_limit_tracks_the_dcim_name_column(self):
        from dcim.models import FrontPort

        with mock.patch.object(FrontPort._meta.get_field("name"), "max_length", 10):
            with pytest.raises(naming.NamingError, match="maximum is 10"):
                naming.validate(naming.FRONT_PORT_NAME, "X" * 11)
        assert naming.validate(naming.FRONT_PORT_NAME, "X" * 11) is None

    def test_label_truncation_tracks_the_dcim_label_column(self):
        from dcim.models import RearPort

        with override_settings(PLUGINS_CONFIG={"netbox_fms": {"rear_port_label_template": "{{ cable }}"}}):
            compiled = naming.compile_labels()
            with mock.patch.object(RearPort._meta.get_field("label"), "max_length", 5):
                rendered = naming.render(naming.REAR_PORT_LABEL, compiled, {"cable": "L" * 100})
        assert rendered == "LLLLL"


class TestProvisionedNames(LabelFixtureMixin, TestCase):
    """Configured name templates name new ports.

    Anything that would break the per-device uniqueness or length rules
    drops every port of that device end to the pk grammar (never a mix) and
    reports why through the provisioning warnings.
    """

    @staticmethod
    def _fallbacks(warnings):
        return [w for w in warnings if "fell back" in w]

    @override_settings(PLUGINS_CONFIG={"netbox_fms": NAME_TEMPLATES})
    def test_templates_name_new_ports(self):
        from dcim.models import FrontPort, RearPort

        _fct, _fc, warnings = self._provision("NM")
        assert self._fallbacks(warnings) == []
        assert port_names(self.dev_a, FrontPort) == ["NM-A-F1", "NM-A-F2"]
        assert port_names(self.dev_b, FrontPort) == ["NM-B-F1", "NM-B-F2"]
        assert port_names(self.dev_a, RearPort) == ["NM-A-T1"]

    @override_settings(
        PLUGINS_CONFIG={"netbox_fms": {"front_port_name_template": NAME_TEMPLATES["front_port_name_template"]}}
    )
    def test_unset_rear_template_keeps_the_pk_grammar(self):
        from dcim.models import FrontPort, RearPort

        _fct, fc, _warnings = self._provision("HALF")
        assert port_names(self.dev_a, FrontPort) == ["HALF-A-F1", "HALF-A-F2"]
        assert port_names(self.dev_a, RearPort) == [f"{fc.cable_id}:T1"]

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_name_template": "{{ cable }}"}})
    def test_duplicate_names_fall_back_to_pk_on_both_ends(self):
        from dcim.models import FrontPort

        _fct, fc, warnings = self._provision("DUP")
        pk = fc.cable_id
        fallbacks = self._fallbacks(warnings)
        assert port_names(self.dev_a, FrontPort) == [f"{pk}:F1", f"{pk}:F2"]
        assert port_names(self.dev_b, FrontPort) == [f"{pk}:F1", f"{pk}:F2"]
        assert len(fallbacks) == 2
        assert "duplicate" in fallbacks[0]
        assert "front_port_name_template" in fallbacks[0]
        assert "DUP" in fallbacks[0]

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"rear_port_name_template": "{{ 'x' * 70 }}"}})
    def test_overlong_name_falls_back_to_pk(self):
        from dcim.models import RearPort

        _fct, fc, warnings = self._provision("LONG")
        fallbacks = self._fallbacks(warnings)
        assert port_names(self.dev_a, RearPort) == [f"{fc.cable_id}:T1"]
        assert "70 characters" in fallbacks[0]
        assert "rear_port_name_template" in fallbacks[0]

    @override_settings(PLUGINS_CONFIG={"netbox_fms": NAME_TEMPLATES})
    def test_collision_with_an_existing_port_falls_back_on_that_device_only(self):
        from dcim.models import FrontPort, RearPort

        FrontPort.objects.create(device=self.dev_a, name="COL-A-F1", type="splice")
        _fct, fc, warnings = self._provision("COL")
        pk = fc.cable_id
        fallbacks = self._fallbacks(warnings)
        assert port_names(self.dev_a, FrontPort) == [f"{pk}:F1", f"{pk}:F2", "COL-A-F1"]
        assert port_names(self.dev_a, RearPort) == [f"{pk}:T1"]
        assert port_names(self.dev_b, FrontPort) == ["COL-B-F1", "COL-B-F2"]
        assert len(fallbacks) == 1
        assert "COL-A-F1" in fallbacks[0]

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_name_template": MALFORMED}})
    def test_malformed_name_template_falls_back_to_pk(self):
        from dcim.models import FrontPort

        _fct, fc, warnings = self._provision("BAD")
        assert port_names(self.dev_a, FrontPort) == [f"{fc.cable_id}:F1", f"{fc.cable_id}:F2"]
        assert "syntax" in self._fallbacks(warnings)[0]
