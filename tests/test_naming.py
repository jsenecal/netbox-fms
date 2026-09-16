"""Tests for the port label template engine.

Covers the label slice of the naming-template design (regression surface for
issue #69): the pure Jinja2 engine, plugin-config resolution, context
builders, and the built-in non-blank defaults.
"""

import pytest
from django.test import SimpleTestCase, TestCase, override_settings

from netbox_fms import naming


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
            NetBoxFMSConfig._check_label_templates()
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


class LabelFixtureMixin:
    """Closure pair plus a builder for provisioned FiberCables."""

    @classmethod
    def setUpTestData(cls):
        from dcim.models import Device

        from tests.conftest import make_infra

        site, cls.mfr, dt, role = make_infra("Label")
        cls.dev_a = Device.objects.create(name="LBL-A", site=site, device_type=dt, role=role)
        cls.dev_b = Device.objects.create(name="LBL-B", site=site, device_type=dt, role=role)

    def _build(self, label, *, construction="loose_tube", tube=True, ribbon=False, strand_count=2):
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
        fc, _ = create_closure_cable(
            device_a=self.dev_a,
            device_b=self.dev_b,
            fiber_cable_type=fct,
            cable_attrs={"type": "smf-os2", "label": label},
        )
        return fct, fc

    def _labels(self, device, model):
        return sorted(model.objects.filter(device=device).values_list("label", flat=True))


class TestProvisionedLabels(LabelFixtureMixin, TestCase):
    """_provision_device_ports must stamp default labels onto new ports."""

    def test_loose_tube_labels(self):
        from dcim.models import FrontPort, RearPort

        self._build("LT")
        expected_front = ["LT / T1 (Blue) / Blue / F1", "LT / T1 (Blue) / Orange / F2"]
        assert self._labels(self.dev_a, FrontPort) == expected_front
        assert self._labels(self.dev_b, FrontPort) == expected_front
        assert self._labels(self.dev_a, RearPort) == ["LT / T1 (Blue)"]
        assert self._labels(self.dev_b, RearPort) == ["LT / T1 (Blue)"]

    def test_tight_buffer_labels(self):
        from dcim.models import FrontPort, RearPort

        self._build("TB", construction="tight_buffer", tube=False)
        assert self._labels(self.dev_a, FrontPort) == ["TB / Blue / F1", "TB / Orange / F2"]
        assert self._labels(self.dev_a, RearPort) == ["TB"]

    def test_central_ribbon_labels(self):
        from dcim.models import FrontPort

        self._build("CRB", construction="ribbon", tube=False, ribbon=True)
        assert self._labels(self.dev_a, FrontPort) == ["CRB / R1 / Blue / F1", "CRB / R1 / Orange / F2"]

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": "", "rear_port_label_template": ""}})
    def test_opted_out_provisioning_leaves_labels_blank(self):
        from dcim.models import FrontPort, RearPort

        self._build("OPT")
        assert self._labels(self.dev_a, FrontPort) == ["", ""]
        assert self._labels(self.dev_a, RearPort) == [""]

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": MALFORMED}})
    def test_malformed_config_degrades_to_blank_labels(self):
        """Provisioning must survive a broken plugin-config template."""
        from dcim.models import FrontPort

        self._build("BAD")
        assert self._labels(self.dev_a, FrontPort) == ["", ""]


class TestRelabelSignal(LabelFixtureMixin, TestCase):
    """A cable save must re-render labels on the cable's FMS-provisioned ports."""

    def test_cable_relabel_rerenders_labels(self):
        from dcim.models import FrontPort, RearPort

        _fct, fc = self._build("OLD")

        fc.cable.label = "NEW"
        fc.cable.save()

        assert self._labels(self.dev_a, FrontPort) == [
            "NEW / T1 (Blue) / Blue / F1",
            "NEW / T1 (Blue) / Orange / F2",
        ]
        assert self._labels(self.dev_a, RearPort) == ["NEW / T1 (Blue)"]

    def test_device_and_end_tokens_differ_per_side(self):
        """The relabel path must resolve device and cable end per port."""
        from dcim.models import FrontPort

        _fct, fc = self._build("END")
        with override_settings(
            PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": "{{ device }}:{{ end }}:F{{ strand }}"}}
        ):
            fc.cable.save()

        assert self._labels(self.dev_a, FrontPort) == ["LBL-A:A:F1", "LBL-A:A:F2"]
        assert self._labels(self.dev_b, FrontPort) == ["LBL-B:B:F1", "LBL-B:B:F2"]

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
        before = self._labels(self.dev_a, FrontPort)

        with override_settings(PLUGINS_CONFIG={"netbox_fms": {"rear_port_label_template": MALFORMED}}):
            fc.cable.description = "touched"
            fc.cable.save()  # must not raise

        assert self._labels(self.dev_a, FrontPort) == before


class TestRerenderPortLabelsCommand(LabelFixtureMixin, TestCase):
    """rerender_port_labels backfills labels on brownfield data."""

    def _blank_labels(self):
        from dcim.models import FrontPort, RearPort

        FrontPort.objects.update(label="")
        RearPort.objects.update(label="")

    def _call(self, *args):
        from io import StringIO

        from django.core.management import call_command

        out, err = StringIO(), StringIO()
        call_command("rerender_port_labels", *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def test_backfills_default_labels(self):
        from dcim.models import FrontPort, RearPort

        self._build("BF")
        self._blank_labels()

        out, err = self._call()

        assert err == ""
        assert "->" in out
        assert self._labels(self.dev_a, FrontPort) == [
            "BF / T1 (Blue) / Blue / F1",
            "BF / T1 (Blue) / Orange / F2",
        ]
        assert self._labels(self.dev_a, RearPort) == ["BF / T1 (Blue)"]

    def test_dry_run_writes_nothing(self):
        from dcim.models import FrontPort

        self._build("DRY")
        self._blank_labels()

        out, _err = self._call("--dry-run")

        assert "->" in out, "the dry run must still report the changes it would make"
        assert self._labels(self.dev_a, FrontPort) == ["", ""]

    def test_cable_type_restricts_the_walk(self):
        from dcim.models import FrontPort

        self._build("ONE")
        self._build("TWO")
        self._blank_labels()

        self._call("--cable-type", "FCT-ONE")

        labels = self._labels(self.dev_a, FrontPort)
        assert "ONE / T1 (Blue) / Blue / F1" in labels
        assert labels.count("") == 2, "the other cable type's ports must stay untouched"

    def test_limit_stops_after_n_cables(self):
        from dcim.models import FrontPort

        _fct1, fc1 = self._build("LIM1")
        self._build("LIM2")
        self._blank_labels()

        self._call("--limit", "1")

        relabeled = FrontPort.objects.exclude(label="")
        assert relabeled.count() == 4, "exactly one cable (two devices x two strands) must be processed"
        strand_fp_ids = {fp_id for s in fc1.fiber_strands.all() for fp_id in (s.front_port_a_id, s.front_port_b_id)}
        assert {fp.pk for fp in relabeled} == strand_fp_ids

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": "", "rear_port_label_template": ""}})
    def test_opted_out_run_leaves_operator_labels_alone(self):
        from dcim.models import FrontPort

        self._build("OPTC")
        FrontPort.objects.update(label="Rack-7")

        out, err = self._call()

        assert out == "" and err == ""
        assert set(FrontPort.objects.values_list("label", flat=True)) == {"Rack-7"}

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": MALFORMED}})
    def test_broken_template_is_reported_not_raised(self):
        from dcim.models import FrontPort

        self._build("BRK")
        self._blank_labels()

        _out, err = self._call()

        assert "syntax" in err
        assert self._labels(self.dev_a, FrontPort) == ["", ""]


class TestProvisioningRenderFailure(LabelFixtureMixin, TestCase):
    """A template that compiles but fails at render must not break provisioning."""

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_label_template": "{{ bogus }}"}})
    def test_undefined_token_degrades_to_blank_front_labels(self):
        from dcim.models import FrontPort, RearPort

        self._build("RF")
        assert self._labels(self.dev_a, FrontPort) == ["", ""]
        # The rear template is untouched and still renders.
        assert self._labels(self.dev_a, RearPort) == ["RF / T1 (Blue)"]
