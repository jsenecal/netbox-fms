"""Unit tests for the naming template engine."""

from io import StringIO

import pytest
from dcim.models import Cable, FrontPort, Manufacturer, RearPort
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from netbox_fms import naming
from netbox_fms.models import BufferTubeTemplate, FiberCable, FiberCableType, RibbonTemplate
from netbox_fms.services import create_closure_cable, link_cable_topology


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
        # strand (global) deliberately differs from strand_local: the default
        # numbers front ports per tube, matching the pre-template steady state.
        ctx = {"cable": "NST", "tube": 3, "strand": 19, "strand_local": 7}
        assert naming.render(naming.FRONT_PORT_NAME, self.compiled, ctx) == "NST:T3:F7"

    def test_front_port_name_tubeless(self):
        ctx = {"cable": "NST", "tube": None, "strand": 7, "strand_local": 7}
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

    def test_labels_default_to_no_template(self):
        """Blank default -> None, the signal to leave any stored label alone."""
        assert naming.render(naming.FRONT_PORT_LABEL, self.compiled, {}) is None
        assert naming.render(naming.REAR_PORT_LABEL, self.compiled, {}) is None

    def test_configured_template_rendering_empty_is_not_none(self):
        """An empty render from a real template is a deliberate blank, not "unset"."""
        fct = blank_type()
        fct.front_port_label_template = "{% if tube %}T{{ tube }}{% endif %}"
        compiled = naming.compile_for(fct)
        assert naming.render(naming.FRONT_PORT_LABEL, compiled, {"tube": None}) == ""


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


class TestCableTypeValidation(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mfr = Manufacturer.objects.create(name="Naming Mfr", slug="naming-mfr")

    def _cable_type(self, **kwargs):
        return FiberCableType(
            manufacturer=self.mfr,
            model="NT-12",
            construction="loose_tube",
            strand_count=12,
            **kwargs,
        )

    def test_syntax_error_raises_on_the_right_field(self):
        fct = self._cable_type(front_port_name_template="{{ cable ")
        with self.assertRaises(ValidationError) as ctx:
            fct.full_clean()
        assert "front_port_name_template" in ctx.exception.message_dict

    def test_strand_token_rejected_on_rear_template(self):
        fct = self._cable_type(rear_port_name_template="{{ strand }}")
        with self.assertRaises(ValidationError) as ctx:
            fct.full_clean()
        assert "rear_port_name_template" in ctx.exception.message_dict

    def test_blank_templates_are_valid(self):
        self._cable_type().full_clean()

    def test_resolve_methods_use_the_override(self):
        fct = self._cable_type(front_port_name_template="X-{{ strand }}")
        assert fct.resolve_front_port_name(strand=9) == "X-9"

    def test_unconfigured_label_resolves_to_none(self):
        """None, not "", is what tells a caller to leave the stored label alone."""
        fct = self._cable_type()
        assert fct.resolve_front_port_label(strand=9) is None
        assert fct.resolve_rear_port_label() is None

    def test_deepcopy_survives_a_populated_naming_cache(self):
        """``__getstate__`` must keep dropping the uncopyable Jinja cache.

        Django's ``TestData`` deep-copies ``setUpTestData`` attributes before
        every test method, so a FiberCableType whose ``_compiled_naming`` has
        been populated must stay deep-copyable. Renaming that attribute without
        updating ``__getstate__`` otherwise fails far away from this class,
        with Jinja2's opaque ``Template.__new__()`` TypeError.
        """
        import copy

        fct = self._cable_type(front_port_name_template="D-{{ strand }}")
        assert fct.resolve_front_port_name(strand=4) == "D-4"
        assert "_compiled_naming" in fct.__dict__, "cache must be populated for this test to mean anything"

        clone = copy.deepcopy(fct)

        assert "_compiled_naming" not in clone.__dict__
        assert clone.resolve_front_port_name(strand=5) == "D-5"


class TestStrandNameBackCompat(TestCase):
    """Default templates must reproduce the pre-template strand names exactly."""

    @classmethod
    def setUpTestData(cls):
        cls.mfr = Manufacturer.objects.create(name="BC Mfr", slug="bc-mfr")

    def _cable_for(self, fct):
        cable = Cable.objects.create(type="smf-os2", label="BC")
        return FiberCable.objects.create(cable=cable, fiber_cable_type=fct)

    def test_loose_tube_names(self):
        fct = FiberCableType.objects.create(
            manufacturer=self.mfr, model="BC-LT", construction="loose_tube", strand_count=4
        )
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=2)
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T2", position=2, fiber_count=2)
        fc = self._cable_for(fct)
        names = list(fc.fiber_strands.order_by("position").values_list("name", flat=True))
        assert names == ["T1-F1", "T1-F2", "T2-F1", "T2-F2"]

    def test_tight_buffer_names(self):
        fct = FiberCableType.objects.create(
            manufacturer=self.mfr, model="BC-TB", construction="tight_buffer", strand_count=3
        )
        fc = self._cable_for(fct)
        names = list(fc.fiber_strands.order_by("position").values_list("name", flat=True))
        assert names == ["F1", "F2", "F3"]

    def test_ribbon_names(self):
        """Ribbon-in-tube strand names take the R<n>-F<n> form."""
        fct = FiberCableType.objects.create(
            manufacturer=self.mfr, model="BC-RIB", construction="ribbon_in_tube", strand_count=4
        )
        tt = BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1)
        RibbonTemplate.objects.create(
            fiber_cable_type=fct, buffer_tube_template=tt, name="R1", position=1, fiber_count=4
        )
        fc = self._cable_for(fct)
        names = list(fc.fiber_strands.order_by("position").values_list("name", flat=True))
        assert names == ["R1-F1", "R1-F2", "R1-F3", "R1-F4"]

    def test_strand_local_differs_from_strand(self):
        """Second tube restarts local numbering but not global position."""
        fct = FiberCableType.objects.create(
            manufacturer=self.mfr,
            model="BC-LOCAL",
            construction="loose_tube",
            strand_count=4,
            strand_name_template="{{ strand }}/{{ strand_local }}",
        )
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=2)
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T2", position=2, fiber_count=2)
        fc = self._cable_for(fct)
        names = list(fc.fiber_strands.order_by("position").values_list("name", flat=True))
        assert names == ["1/1", "2/2", "3/1", "4/2"]


class TestPortNameBackCompat(TestCase):
    """Default templates must reproduce the pre-template port names exactly.

    The load-bearing guard is ``test_steady_state_names_match_pre_template``.
    It pins the names that exist in the database AFTER the cable post_save
    signal has run, because that -- not the provisioning output -- is what
    every pre-existing install actually holds.

    Before naming templates the two writers disagreed with each other. Old
    ``_provision_device_ports`` named a front port with the strand's
    cable-wide position; old ``_rename_ports_for_cable`` renamed it with the
    tube-local ``PortMapping.rear_port_position``. The signal always ran last
    (``create_closure_cable`` ends with ``cable.save()``, and every later
    cable save fires it again), so the tube-local form is the steady state:
    tube 2 strand 1 is stored as "X:T2:F1", never "X:T2:F3".

    An earlier version of this class routed through ``link_cable_topology``
    specifically to avoid the signal, which pinned the provisioning form and
    left the steady state -- the exact side of the divergence that matters on
    upgrade -- untested. The multi-tube ``create_closure_cable`` test below
    exists to close that gap; keep it going through ``create_closure_cable``.

    Expected strings are derived BY HAND from the pre-branch formula
    (``git show 2ba4ef0:netbox_fms/signals.py``), not from the current
    templates::

        rear:  f"{label}:T{tube_pos}"                            (tubed)
        front: f"{label}:T{tube_pos}:F{pm.rear_port_position}"    (tubed)

    Deriving them from the new code instead would make the guard tautological.
    """

    @classmethod
    def setUpTestData(cls):
        from dcim.models import Device, DeviceRole, DeviceType, Site

        cls.mfr = Manufacturer.objects.create(name="PN Mfr", slug="pn-mfr")
        site = Site.objects.create(name="PN Site", slug="pn-site")
        dt = DeviceType.objects.create(manufacturer=cls.mfr, model="PN Closure", slug="pn-closure")
        role = DeviceRole.objects.create(name="PN Role", slug="pn-role")
        cls.dev_a = Device.objects.create(name="PN-A", site=site, device_type=dt, role=role)
        cls.dev_b = Device.objects.create(name="PN-B", site=site, device_type=dt, role=role)

    _model_seq = 0

    def _tubed_type(self, **kwargs):
        type(self)._model_seq += 1
        fct = FiberCableType.objects.create(
            manufacturer=self.mfr,
            model=f"PN-{self._model_seq}",
            construction="loose_tube",
            strand_count=4,
            **kwargs,
        )
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=2)
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T2", position=2, fiber_count=2)
        return fct

    def _tubeless_type(self, **kwargs):
        type(self)._model_seq += 1
        return FiberCableType.objects.create(
            manufacturer=self.mfr,
            model=f"PN-{self._model_seq}",
            construction="tight_buffer",
            strand_count=4,
            **kwargs,
        )

    def test_steady_state_names_match_pre_template(self):
        """Post-signal names on a MULTI-TUBE cable must equal the pre-branch ones.

        ``create_closure_cable`` finishes with ``cable.save()``, so the cable
        post_save signal renames the ports here exactly as it does in
        production. The strings asserted are what the pre-branch signal
        formula wrote, so any template default that renumbers tube 2 and
        beyond fails this test.
        """
        fct = self._tubed_type()
        fc, _ = create_closure_cable(
            device_a=self.dev_a,
            device_b=self.dev_b,
            fiber_cable_type=fct,
            cable_attrs={"type": "smf-os2", "label": "NSS"},
        )
        # Pre-branch signal: f"{label}:T{tube_pos}:F{pm.rear_port_position}",
        # with rear_port_position running 1..N *within each tube*.
        expected_fp = ["NSS:T1:F1", "NSS:T1:F2", "NSS:T2:F1", "NSS:T2:F2"]
        expected_rp = ["NSS:T1", "NSS:T2"]
        for device in (self.dev_a, self.dev_b):
            fp_names = sorted(FrontPort.objects.filter(device=device).values_list("name", flat=True))
            assert fp_names == expected_fp, f"{device}: {fp_names}"
            rp_names = sorted(RearPort.objects.filter(device=device).values_list("name", flat=True))
            assert rp_names == expected_rp, f"{device}: {rp_names}"

        # A later, unrelated cable save must be a no-op on the names.
        fc.cable.description = "touched"
        fc.cable.save()
        fp_names = sorted(FrontPort.objects.filter(device=self.dev_a).values_list("name", flat=True))
        assert fp_names == expected_fp

    def test_steady_state_names_match_pre_template_tubeless(self):
        """Tubeless: pre-branch local and global indices coincide, so both agree.

        One RearPort spans every strand and ``rear_port_position`` runs 1..N
        over the whole cable, which is also the strands' cable-wide position.
        """
        fct = self._tubeless_type()
        create_closure_cable(
            device_a=self.dev_a,
            device_b=self.dev_b,
            fiber_cable_type=fct,
            cable_attrs={"type": "smf-os2", "label": "NSW"},
        )
        # Pre-branch signal, untubed branch: f"{label}:F{pm.rear_port_position}".
        fp_names = sorted(FrontPort.objects.filter(device=self.dev_a).values_list("name", flat=True))
        assert fp_names == ["NSW:F1", "NSW:F2", "NSW:F3", "NSW:F4"]
        rp_names = sorted(RearPort.objects.filter(device=self.dev_a).values_list("name", flat=True))
        assert rp_names == ["NSW"]

    def test_provisioning_names_match_steady_state(self):
        """The provisioning path must land on the same names the signal would.

        ``link_cable_topology``'s greenfield path never re-saves the cable, so
        these names are ``_provision_device_ports``' own output. They have to
        equal the steady-state strings above, or the two writers have diverged
        again and a port's name depends on which path last touched it.
        """
        fct = self._tubed_type()
        cable = Cable.objects.create(type="smf-os2", label="NST")
        link_cable_topology(cable, fct, self.dev_a)
        fp_names = sorted(FrontPort.objects.filter(device=self.dev_a).values_list("name", flat=True))
        assert fp_names == ["NST:T1:F1", "NST:T1:F2", "NST:T2:F1", "NST:T2:F2"]
        rp_names = sorted(RearPort.objects.filter(device=self.dev_a).values_list("name", flat=True))
        assert rp_names == ["NST:T1", "NST:T2"]

    def test_labels_stay_blank_by_default(self):
        fct = self._tubed_type()
        cable = Cable.objects.create(type="smf-os2", label="NSU")
        link_cable_topology(cable, fct, self.dev_a)
        labels = set(FrontPort.objects.filter(device=self.dev_a).values_list("label", flat=True))
        assert labels == {""}

    def test_custom_name_and_label_templates(self):
        fct = self._tubed_type(
            front_port_name_template="{{ cable }}:B{{ tube }}F{{ strand }}",
            front_port_label_template="{{ tube_color }} F{{ strand_local }}",
        )
        cable = Cable.objects.create(type="smf-os2", label="NSV")
        link_cable_topology(cable, fct, self.dev_a)
        fp = FrontPort.objects.filter(device=self.dev_a).order_by("name").first()
        assert fp.name == "NSV:B1F1"
        assert fp.label.endswith("F1")


class TestRenameSignal(TestCase):
    """Relabelling a cable re-renders port names through the template."""

    @classmethod
    def setUpTestData(cls):
        from dcim.models import Device, DeviceRole, DeviceType, Site

        cls.mfr = Manufacturer.objects.create(name="RS Mfr", slug="rs-mfr")
        site = Site.objects.create(name="RS Site", slug="rs-site")
        dt = DeviceType.objects.create(manufacturer=cls.mfr, model="RS Closure", slug="rs-closure")
        role = DeviceRole.objects.create(name="RS Role", slug="rs-role")
        cls.dev_a = Device.objects.create(name="RS-A", site=site, device_type=dt, role=role)
        cls.dev_b = Device.objects.create(name="RS-B", site=site, device_type=dt, role=role)

    def test_relabel_uses_custom_template(self):
        fct = FiberCableType.objects.create(
            manufacturer=self.mfr,
            model="RS-1",
            construction="loose_tube",
            strand_count=2,
            front_port_name_template="{{ cable }}#{{ strand }}",
        )
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=2)
        fc, _ = create_closure_cable(
            device_a=self.dev_a,
            device_b=self.dev_b,
            fiber_cable_type=fct,
            cable_attrs={"type": "smf-os2", "label": "OLD"},
        )
        fc.cable.label = "NEW"
        fc.cable.save()
        names = sorted(FrontPort.objects.filter(device=self.dev_a).values_list("name", flat=True))
        assert names == ["NEW#1", "NEW#2"]

    def test_render_failure_does_not_break_cable_save(self):
        """A broken template must not propagate out of a Cable save."""
        fct = FiberCableType.objects.create(
            manufacturer=self.mfr, model="RS-2", construction="loose_tube", strand_count=2
        )
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=2)
        fc, _ = create_closure_cable(
            device_a=self.dev_a,
            device_b=self.dev_b,
            fiber_cable_type=fct,
            cable_attrs={"type": "smf-os2", "label": "SAFE"},
        )
        # Bypass clean() to plant a template that only fails at render time.
        FiberCableType.objects.filter(pk=fct.pk).update(front_port_name_template="{{ strand.no_such }}")

        rp_names_before = dict(RearPort.objects.filter(device__in=[self.dev_a, self.dev_b]).values_list("pk", "name"))
        fp_names_before = dict(FrontPort.objects.filter(device__in=[self.dev_a, self.dev_b]).values_list("pk", "name"))

        fc.cable.label = "SAFE2"
        fc.cable.save()  # must not raise
        assert fc.cable.label == "SAFE2"

        rp_names_after = dict(RearPort.objects.filter(device__in=[self.dev_a, self.dev_b]).values_list("pk", "name"))
        fp_names_after = dict(FrontPort.objects.filter(device__in=[self.dev_a, self.dev_b]).values_list("pk", "name"))
        assert rp_names_after == rp_names_before, "RearPort names must be untouched when the render guard fires"
        assert fp_names_after == fp_names_before, "FrontPort names must be untouched when the render guard fires"

    def test_end_token_differs_between_cable_sides(self):
        """The {{ end }} token must render 'A' on device_a's ports and 'B' on device_b's.

        create_closure_cable itself hardcodes front_port_a/front_port_b by which
        device it is provisioning, without ever computing a cable end -- that
        computation now happens inside _rename_ports_for_cable via
        _determine_cable_end, triggered by the final cable.save() in
        create_closure_cable. This is the only test in the suite that exercises
        the {{ end }} token or the "B"/both-ends path at all.
        """
        fct = FiberCableType.objects.create(
            manufacturer=self.mfr,
            model="RS-3",
            construction="tight_buffer",
            strand_count=2,
            front_port_name_template="{{ cable }}-{{ end }}{{ strand }}",
        )
        create_closure_cable(
            device_a=self.dev_a,
            device_b=self.dev_b,
            fiber_cable_type=fct,
            cable_attrs={"type": "smf-os2", "label": "END"},
        )
        names_a = sorted(FrontPort.objects.filter(device=self.dev_a).values_list("name", flat=True))
        names_b = sorted(FrontPort.objects.filter(device=self.dev_b).values_list("name", flat=True))
        assert names_a == ["END-A1", "END-A2"]
        assert names_b == ["END-B1", "END-B2"]


class TestTrayToken(TestCase):
    """{{ tray }} is blank at provisioning and fills in on tube assignment."""

    @classmethod
    def setUpTestData(cls):
        from dcim.models import Device, DeviceRole, DeviceType, Module, ModuleBay, ModuleType, Site

        cls.mfr = Manufacturer.objects.create(name="TT Mfr", slug="tt-mfr")
        site = Site.objects.create(name="TT Site", slug="tt-site")
        dt = DeviceType.objects.create(manufacturer=cls.mfr, model="TT Closure", slug="tt-closure")
        role = DeviceRole.objects.create(name="TT Role", slug="tt-role")
        cls.dev_a = Device.objects.create(name="TT-A", site=site, device_type=dt, role=role)
        cls.dev_b = Device.objects.create(name="TT-B", site=site, device_type=dt, role=role)
        mt = ModuleType.objects.create(manufacturer=cls.mfr, model="TT Tray")
        bay = ModuleBay.objects.create(device=cls.dev_a, name="Tray 1")
        cls.tray = Module.objects.create(device=cls.dev_a, module_bay=bay, module_type=mt)

    def test_tray_lifecycle(self):
        from netbox_fms.models import TubeAssignment

        fct = FiberCableType.objects.create(
            manufacturer=self.mfr,
            model="TT-1",
            construction="loose_tube",
            strand_count=2,
            front_port_name_template="{% if tray %}{{ tray }}:{% endif %}F{{ strand }}",
        )
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=2)
        fc, _ = create_closure_cable(
            device_a=self.dev_a,
            device_b=self.dev_b,
            fiber_cable_type=fct,
            cable_attrs={"type": "smf-os2", "label": "TT"},
        )
        # Provisioned before any assignment exists: tray is blank.
        assert sorted(FrontPort.objects.filter(device=self.dev_a).values_list("name", flat=True)) == ["F1", "F2"]

        tube = fc.buffer_tubes.get(position=1)
        assignment = TubeAssignment.objects.create(closure=self.dev_a, tray=self.tray, buffer_tube=tube)
        names = sorted(FrontPort.objects.filter(device=self.dev_a).values_list("name", flat=True))
        assert names == ["Tray 1:F1", "Tray 1:F2"]

        assignment.delete()
        names = sorted(FrontPort.objects.filter(device=self.dev_a).values_list("name", flat=True))
        assert names == ["F1", "F2"]


class TestTrayGuardSkipsRename(TestCase):
    """Cable types with no tray token must not have FMS rename ports on tube assignment.

    Models the adopt path PR #90's own suite exercises: FrontPorts that came from a
    DeviceType template or were named by hand, never provisioned by FMS. Regression
    test for the behaviour caught by tests/test_tube_assignment_port_sync.py -- an
    unconditional re-render would silently overwrite an operator's port name the
    moment a tube is assigned to a tray, even though they configured no template
    that references one.
    """

    @classmethod
    def setUpTestData(cls):
        from dcim.models import Device, DeviceRole, DeviceType, Module, ModuleBay, ModuleType, Site

        cls.mfr = Manufacturer.objects.create(name="TG Mfr", slug="tg-mfr")
        site = Site.objects.create(name="TG Site", slug="tg-site")
        dt = DeviceType.objects.create(manufacturer=cls.mfr, model="TG Closure", slug="tg-closure")
        role = DeviceRole.objects.create(name="TG Role", slug="tg-role")
        cls.closure = Device.objects.create(name="TG-Closure", site=site, device_type=dt, role=role)
        mt = ModuleType.objects.create(manufacturer=cls.mfr, model="TG Tray")
        bay = ModuleBay.objects.create(device=cls.closure, name="Tray 1")
        cls.tray = Module.objects.create(device=cls.closure, module_bay=bay, module_type=mt)

    def test_no_tray_token_leaves_names_untouched(self):
        from netbox_fms.models import BufferTube, TubeAssignment
        from tests.conftest import make_front_port

        fct = FiberCableType.objects.create(
            manufacturer=self.mfr, model="TG-1", construction="loose_tube", strand_count=2
        )
        assert not fct.naming_uses_tray

        fc = FiberCable.objects.create(cable=Cable.objects.create(), fiber_cable_type=fct)
        tube = BufferTube.objects.create(fiber_cable=fc, name="TG-T1", position=1)

        hand_named_ports = {}
        for strand in fc.fiber_strands.all().order_by("position"):
            port = make_front_port(device=self.closure, name=f"HAND-{strand.position}")
            strand.buffer_tube = tube
            strand.front_port_a = port
            strand.save()
            hand_named_ports[strand.position] = port

        TubeAssignment.objects.create(closure=self.closure, tray=self.tray, buffer_tube=tube)

        for position, port in hand_named_ports.items():
            port.refresh_from_db()
            assert port.name == f"HAND-{position}", "port name must be untouched with no tray token in the template"
            assert port.module_id == self.tray.pk, "module_id must still move to the assigned tray"


class TestTrayPositionPerTube(TestCase):
    """``{{ tray_position }}`` must render the port's OWN tube's assignment position.

    ``TubeAssignment``'s unique constraint is (closure, buffer_tube), so several
    tubes routinely share one tray at different positions. Resolving the token
    by (closure, tray) alone returns an arbitrary sibling -- the lowest, under
    ``Meta.ordering = ("closure", "tray", "position")`` -- while
    ``sync_tube_assignment_ports`` uses the real ``assignment.position``. The
    two paths then disagree and a port's name flip-flops on every cable save.
    """

    @classmethod
    def setUpTestData(cls):
        from dcim.models import Device, DeviceRole, DeviceType, Module, ModuleBay, ModuleType, Site

        cls.mfr = Manufacturer.objects.create(name="TP Mfr", slug="tp-mfr")
        site = Site.objects.create(name="TP Site", slug="tp-site")
        dt = DeviceType.objects.create(manufacturer=cls.mfr, model="TP Closure", slug="tp-closure")
        role = DeviceRole.objects.create(name="TP Role", slug="tp-role")
        cls.closure = Device.objects.create(name="TP-Closure", site=site, device_type=dt, role=role)
        cls.far_end = Device.objects.create(name="TP-Far", site=site, device_type=dt, role=role)
        mt = ModuleType.objects.create(manufacturer=cls.mfr, model="TP Tray")
        bay = ModuleBay.objects.create(device=cls.closure, name="Tray 1")
        cls.tray = Module.objects.create(device=cls.closure, module_bay=bay, module_type=mt)

    def test_two_tubes_on_one_tray_keep_their_own_positions(self):
        from netbox_fms.models import TubeAssignment

        fct = FiberCableType.objects.create(
            manufacturer=self.mfr,
            model="TP-1",
            construction="loose_tube",
            strand_count=4,
            # {{ tube }} keeps the far-end names (tray_position None there)
            # unique; the assertions below only read the closure's ports.
            front_port_name_template="{{ cable }}:T{{ tube }}:P{{ tray_position }}:F{{ strand_local }}",
        )
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=2)
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T2", position=2, fiber_count=2)
        fc, _ = create_closure_cable(
            device_a=self.closure,
            device_b=self.far_end,
            fiber_cable_type=fct,
            cable_attrs={"type": "smf-os2", "label": "TPC"},
        )

        tube1, tube2 = fc.buffer_tubes.order_by("position")
        TubeAssignment.objects.create(closure=self.closure, tray=self.tray, buffer_tube=tube1, position=1)
        TubeAssignment.objects.create(closure=self.closure, tray=self.tray, buffer_tube=tube2, position=2)

        expected = ["TPC:T1:P1:F1", "TPC:T1:P1:F2", "TPC:T2:P2:F1", "TPC:T2:P2:F2"]
        synced = sorted(FrontPort.objects.filter(device=self.closure).values_list("name", flat=True))
        assert synced == expected, f"sync path: {synced}"

        # The cable-save path must land on the same names, not on tube 1's
        # position for every tube sharing the tray.
        fc.cable.description = "touched"
        fc.cable.save()
        after_save = sorted(FrontPort.objects.filter(device=self.closure).values_list("name", flat=True))
        assert after_save == expected, f"cable-save path disagrees with the sync path: {after_save}"


class TestSnapshotOrdering(TestCase):
    """Regression tests for change-logging ordering (review finding 1).

    ``port.snapshot()`` must run before any field on that port is mutated,
    or NetBox's changelog "before" state ends up equal to the "after" state
    and the actual change is silently dropped from history. Asserting only
    final field values (as the rest of this file and PR #90's suite do)
    cannot catch that class of bug -- these tests inspect the captured
    ``_prechange_snapshot`` itself, via a transient ``post_save`` receiver,
    since the ``FrontPort`` instance that calls ``snapshot()`` lives inside
    ``services.py`` and is not otherwise reachable from the test.
    """

    @classmethod
    def setUpTestData(cls):
        from dcim.models import Device, DeviceRole, DeviceType, Module, ModuleBay, ModuleType, Site

        cls.mfr = Manufacturer.objects.create(name="SO Mfr", slug="so-mfr")
        site = Site.objects.create(name="SO Site", slug="so-site")
        dt = DeviceType.objects.create(manufacturer=cls.mfr, model="SO Closure", slug="so-closure")
        role = DeviceRole.objects.create(name="SO Role", slug="so-role")
        cls.closure = Device.objects.create(name="SO-Closure", site=site, device_type=dt, role=role)
        mt = ModuleType.objects.create(manufacturer=cls.mfr, model="SO Tray")
        bay1 = ModuleBay.objects.create(device=cls.closure, name="Tray 1")
        bay2 = ModuleBay.objects.create(device=cls.closure, name="Tray 2")
        cls.tray1 = Module.objects.create(device=cls.closure, module_bay=bay1, module_type=mt)
        cls.tray2 = Module.objects.create(device=cls.closure, module_bay=bay2, module_type=mt)

    def _make_assignment_fixture(self, front_port_name_template=""):
        from netbox_fms.models import BufferTube
        from tests.conftest import make_front_port

        fct = FiberCableType.objects.create(
            manufacturer=self.mfr,
            model=f"SO-{front_port_name_template!r}",
            construction="loose_tube",
            strand_count=1,
            front_port_name_template=front_port_name_template,
        )
        fc = FiberCable.objects.create(cable=Cable.objects.create(), fiber_cable_type=fct)
        tube = BufferTube.objects.create(fiber_cable=fc, name="SO-T1", position=1)
        port = make_front_port(device=self.closure, name="SO-N1")
        strand = fc.fiber_strands.get(position=1)
        strand.buffer_tube = tube
        strand.front_port_a = port
        strand.save()
        return tube, port

    def _capture_front_port_saves(self, port_pk):
        """Connect a transient post_save receiver; returns (captures list, disconnect callback)."""
        from django.db.models.signals import post_save

        captures = []

        def _capture(sender, instance, **kwargs):
            if instance.pk == port_pk:
                captures.append(
                    {
                        "prechange": dict(getattr(instance, "_prechange_snapshot", {}) or {}),
                        "module_id": instance.module_id,
                        "name": instance.name,
                    }
                )

        post_save.connect(_capture, sender=FrontPort, dispatch_uid="test-capture-frontport-save", weak=False)
        return captures, lambda: post_save.disconnect(sender=FrontPort, dispatch_uid="test-capture-frontport-save")

    def test_sync_prechange_snapshot_holds_old_module_not_new(self):
        """Assigning a tube to a tray must snapshot the port's OLD module/name, not the post-sync values.

        Uses the initial (device-level -> tray) assignment rather than a
        retarget between two trays, because retargeting runs both
        ``clear_tube_assignment_ports`` (old tray -> device level, via
        ``_tube_assignment_pre_save``) and ``sync_tube_assignment_ports``
        (device level -> new tray) as two separate saves; checking only the
        first save keeps this test's cause and effect direct.
        """
        from netbox_fms.models import TubeAssignment

        tube, port = self._make_assignment_fixture(
            front_port_name_template="{% if tray %}{{ tray }}:{% endif %}F{{ strand }}"
        )
        assert port.module_id is None
        assert port.name == "SO-N1"

        captures, disconnect = self._capture_front_port_saves(port.pk)
        try:
            TubeAssignment.objects.create(closure=self.closure, tray=self.tray1, buffer_tube=tube)
        finally:
            disconnect()

        assert captures, "sync_tube_assignment_ports should have saved the port"
        prechange = captures[-1]["prechange"]
        assert prechange["module"] is None, "prechange snapshot must record the OLD module (None), not the new tray"
        assert prechange["name"] == "SO-N1", "prechange snapshot must record the OLD name, not the rendered one"
        assert captures[-1]["module_id"] == self.tray1.pk
        assert captures[-1]["name"] == "Tray 1:F1"

    def test_clear_prechange_snapshot_holds_old_module_not_none(self):
        """Deleting a TubeAssignment must snapshot the tray it was on, not the cleared value."""
        from netbox_fms.models import TubeAssignment

        tube, port = self._make_assignment_fixture(
            front_port_name_template="{% if tray %}{{ tray }}:{% endif %}F{{ strand }}"
        )
        assignment = TubeAssignment.objects.create(closure=self.closure, tray=self.tray1, buffer_tube=tube)
        port.refresh_from_db()
        assert port.module_id == self.tray1.pk

        captures, disconnect = self._capture_front_port_saves(port.pk)
        try:
            assignment.delete()
        finally:
            disconnect()

        assert captures, "clear_tube_assignment_ports should have saved the port"
        prechange = captures[-1]["prechange"]
        assert prechange["module"] == self.tray1.pk, "prechange snapshot must record the OLD (assigned) module"
        assert prechange["name"] == "Tray 1:F1", "prechange snapshot must record the OLD name, not the cleared one"
        assert captures[-1]["module_id"] is None
        assert captures[-1]["name"] == "F1"

    def test_sync_no_tray_token_still_snapshots_old_module(self):
        """The guard-off path (no tray token) must still preserve changelog ordering."""
        from netbox_fms.models import TubeAssignment

        tube, port = self._make_assignment_fixture(front_port_name_template="")
        assert port.module_id is None
        original_name = port.name

        captures, disconnect = self._capture_front_port_saves(port.pk)
        try:
            TubeAssignment.objects.create(closure=self.closure, tray=self.tray1, buffer_tube=tube)
        finally:
            disconnect()

        assert captures, "sync_tube_assignment_ports should have saved the port"
        prechange = captures[-1]["prechange"]
        assert prechange["module"] is None, "prechange snapshot must record the OLD module (None), not the new tray"
        assert captures[-1]["module_id"] == self.tray1.pk
        assert captures[-1]["name"] == original_name, "no tray token means the name must never be touched"


class TestLabelPreservation(TestCase):
    """With no label template configured, FMS must never write a port label.

    ``TestPortNameBackCompat.test_labels_stay_blank_by_default`` only covers
    greenfield ports, whose labels are blank anyway; it cannot catch a
    re-render path that blanks a label an operator already set. These do:
    the ports here carry non-blank labels (the shape of ports adopted from a
    DeviceType template) before the write path under test runs.
    """

    @classmethod
    def setUpTestData(cls):
        from dcim.models import Device, DeviceRole, DeviceType, Site

        cls.mfr = Manufacturer.objects.create(name="LP Mfr", slug="lp-mfr")
        site = Site.objects.create(name="LP Site", slug="lp-site")
        dt = DeviceType.objects.create(manufacturer=cls.mfr, model="LP Closure", slug="lp-closure")
        role = DeviceRole.objects.create(name="LP Role", slug="lp-role")
        cls.dev_a = Device.objects.create(name="LP-A", site=site, device_type=dt, role=role)
        cls.dev_b = Device.objects.create(name="LP-B", site=site, device_type=dt, role=role)

    def _build(self, label, **kwargs):
        fct = FiberCableType.objects.create(
            manufacturer=self.mfr,
            model=f"LP-{label}",
            construction="loose_tube",
            strand_count=2,
            **kwargs,
        )
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=2)
        fc, _ = create_closure_cable(
            device_a=self.dev_a,
            device_b=self.dev_b,
            fiber_cable_type=fct,
            cable_attrs={"type": "smf-os2", "label": label},
        )
        return fct, fc

    def test_existing_labels_survive_cable_save(self):
        _fct, fc = self._build("KEEP")
        fp = FrontPort.objects.filter(device=self.dev_a).order_by("name").first()
        rp = RearPort.objects.filter(device=self.dev_a).order_by("name").first()
        # Bypass save() so the pre-existing labels are planted without touching names.
        FrontPort.objects.filter(pk=fp.pk).update(label="Rack-A-01")
        RearPort.objects.filter(pk=rp.pk).update(label="Rack-A-RP")

        fc.cable.label = "KEEP2"
        fc.cable.save()

        fp.refresh_from_db()
        rp.refresh_from_db()
        assert fp.label == "Rack-A-01", "FrontPort label must survive a cable save with no label template"
        assert rp.label == "Rack-A-RP", "RearPort label must survive a cable save with no label template"

    def test_configured_label_template_still_writes(self):
        """The no-op guard must not stop a configured label template from applying."""
        fct, fc = self._build("SET")
        FiberCableType.objects.filter(pk=fct.pk).update(front_port_label_template="L{{ strand }}")

        fc.cable.label = "SET2"
        fc.cable.save()

        labels = sorted(FrontPort.objects.filter(device=self.dev_a).values_list("label", flat=True))
        assert labels == ["L1", "L2"]


class TestUsesTokens(SimpleTestCase):
    """``naming.uses_tokens`` is the static detector both re-render guards read."""

    def _fct(self, **templates):
        fct = blank_type()
        fct.__dict__.update(templates)
        return fct

    def test_detects_a_referenced_token(self):
        fct = self._fct(front_port_name_template="{{ strand_name }}-x")
        assert naming.uses_tokens(fct, (naming.FRONT_PORT_NAME,), {naming.STRAND_NAME})

    def test_literal_text_is_not_a_reference(self):
        """Static parsing, not substring matching: the word alone must not count."""
        fct = self._fct(front_port_name_template="strand_name is not a token here")
        assert not naming.uses_tokens(fct, (naming.FRONT_PORT_NAME,), {naming.STRAND_NAME})

    def test_only_the_named_targets_are_checked(self):
        fct = self._fct(front_port_label_template="{{ strand_name }}")
        assert not naming.uses_tokens(fct, (naming.FRONT_PORT_NAME,), {naming.STRAND_NAME})
        assert naming.uses_tokens(fct, (naming.FRONT_PORT_LABEL,), {naming.STRAND_NAME})


class TestRerenderCommands(TestCase):
    """The ``rerender_strand_names`` / ``rerender_port_names`` command pair."""

    @classmethod
    def setUpTestData(cls):
        from dcim.models import Device, DeviceRole, DeviceType, Site

        cls.mfr = Manufacturer.objects.create(name="RR Mfr", slug="rr-mfr")
        site = Site.objects.create(name="RR Site", slug="rr-site")
        dt = DeviceType.objects.create(manufacturer=cls.mfr, model="RR Closure", slug="rr-closure")
        role = DeviceRole.objects.create(name="RR Role", slug="rr-role")
        cls.dev_a = Device.objects.create(name="RR-A", site=site, device_type=dt, role=role)
        cls.dev_b = Device.objects.create(name="RR-B", site=site, device_type=dt, role=role)

    def _build(self, label, strand_count=2):
        fct = FiberCableType.objects.create(
            manufacturer=self.mfr, model=f"RR-{label}", construction="loose_tube", strand_count=strand_count
        )
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=strand_count)
        fc, _ = create_closure_cable(
            device_a=self.dev_a,
            device_b=self.dev_b,
            fiber_cable_type=fct,
            cable_attrs={"type": "smf-os2", "label": label},
        )
        return fct, fc

    def _port_state(self, *devices):
        """Every FrontPort/RearPort name and label on the given devices, from the DB."""
        return {
            "front": dict(FrontPort.objects.filter(device__in=devices).values_list("pk", "name")),
            "front_labels": dict(FrontPort.objects.filter(device__in=devices).values_list("pk", "label")),
            "rear": dict(RearPort.objects.filter(device__in=devices).values_list("pk", "name")),
            "rear_labels": dict(RearPort.objects.filter(device__in=devices).values_list("pk", "label")),
        }

    # -- rerender_strand_names -------------------------------------------

    def test_strand_dry_run_writes_nothing(self):
        fct, fc = self._build("DRY")
        FiberCableType.objects.filter(pk=fct.pk).update(strand_name_template="S{{ strand }}")
        before = list(fc.fiber_strands.order_by("position").values_list("name", flat=True))
        out = StringIO()
        call_command("rerender_strand_names", "--dry-run", stdout=out)
        after = list(fc.fiber_strands.order_by("position").values_list("name", flat=True))
        assert after == before
        assert "->" in out.getvalue()

    def test_applies_strand_template(self):
        fct, fc = self._build("APP")
        FiberCableType.objects.filter(pk=fct.pk).update(strand_name_template="S{{ strand }}")
        call_command("rerender_strand_names", stdout=StringIO())
        after = list(fc.fiber_strands.order_by("position").values_list("name", flat=True))
        assert after == ["S1", "S2"]

    def test_strand_command_never_touches_ports(self):
        """The split's contract: strand names are the strand command's business alone."""
        fct, fc = self._build("TGT")
        FiberCableType.objects.filter(pk=fct.pk).update(
            strand_name_template="S{{ strand }}",
            front_port_name_template="P{{ strand }}",
            front_port_label_template="L{{ strand }}",
            rear_port_name_template="RP{{ tube }}",
        )
        before = self._port_state(self.dev_a, self.dev_b)

        call_command("rerender_strand_names", stdout=StringIO(), stderr=StringIO())

        assert list(fc.fiber_strands.order_by("position").values_list("name", flat=True)) == ["S1", "S2"]
        assert self._port_state(self.dev_a, self.dev_b) == before

    def test_cable_type_restricts_to_one_type(self):
        """--cable-type must leave every other cable type's objects untouched."""
        fct_one, fc_one = self._build("CT1")
        fct_two, fc_two = self._build("CT2")
        for fct in (fct_one, fct_two):
            FiberCableType.objects.filter(pk=fct.pk).update(strand_name_template="S{{ strand }}")
        untouched = list(fc_two.fiber_strands.order_by("position").values_list("name", flat=True))

        call_command("rerender_strand_names", "--cable-type", fct_one.model, stdout=StringIO(), stderr=StringIO())

        assert list(fc_one.fiber_strands.order_by("position").values_list("name", flat=True)) == ["S1", "S2"]
        assert list(fc_two.fiber_strands.order_by("position").values_list("name", flat=True)) == untouched

    # -- rerender_port_names ---------------------------------------------

    def test_port_dry_run_writes_nothing(self):
        """--dry-run must leave every name AND label column exactly as it was."""
        fct, _fc = self._build("PDRY")
        FiberCableType.objects.filter(pk=fct.pk).update(
            front_port_name_template="P{{ strand }}",
            front_port_label_template="L{{ strand }}",
            rear_port_name_template="RP{{ tube }}",
            rear_port_label_template="RL{{ tube }}",
        )
        before = self._port_state(self.dev_a, self.dev_b)
        out = StringIO()

        call_command("rerender_port_names", "--dry-run", stdout=out, stderr=StringIO())

        assert self._port_state(self.dev_a, self.dev_b) == before
        assert "->" in out.getvalue()

    def test_rerenders_rear_port_names(self):
        """The gap this pair closes: the old single command never reached RearPorts."""
        fct, _fc = self._build("RP")
        FiberCableType.objects.filter(pk=fct.pk).update(rear_port_name_template="RP-{{ device }}-T{{ tube }}")

        call_command("rerender_port_names", stdout=StringIO(), stderr=StringIO())

        assert list(RearPort.objects.filter(device=self.dev_a).values_list("name", flat=True)) == ["RP-RR-A-T1"]
        assert list(RearPort.objects.filter(device=self.dev_b).values_list("name", flat=True)) == ["RP-RR-B-T1"]

    def test_rear_port_label_survives_with_no_label_template(self):
        """The None protocol, for rear ports: no rear label template means no label write.

        The run must still rewrite the rear port's NAME, so the port is in the
        bulk_update batch -- that is what makes a label leak possible at all.
        """
        fct, _fc = self._build("RPL")
        rp = RearPort.objects.filter(device=self.dev_a).first()
        RearPort.objects.filter(pk=rp.pk).update(label="Rack-A-RP")
        FiberCableType.objects.filter(pk=fct.pk).update(rear_port_name_template="RP{{ tube }}")

        call_command("rerender_port_names", stdout=StringIO(), stderr=StringIO())

        rp.refresh_from_db()
        assert rp.name == "RP1", "the rear port name must have been re-rendered"
        assert rp.label == "Rack-A-RP", "an operator-set rear port label must survive a run with no label template"

    def test_no_template_change_writes_nothing(self):
        """The no-op promise: a run with no template edits must change nothing.

        Includes ports carrying non-blank labels, the state adopted
        DeviceType-template ports arrive in. A run that blanks them is exactly
        the regression this pins.
        """
        _fct, fc = self._build("NOOP")
        fp = FrontPort.objects.filter(device=self.dev_a).order_by("name").first()
        rp = RearPort.objects.filter(device=self.dev_a).order_by("name").first()
        FrontPort.objects.filter(pk=fp.pk).update(label="Bay-7")
        RearPort.objects.filter(pk=rp.pk).update(label="Bay-7-RP")

        before = self._port_state(self.dev_a, self.dev_b)
        strands_before = list(fc.fiber_strands.order_by("position").values_list("name", flat=True))

        call_command("rerender_port_names", stdout=StringIO(), stderr=StringIO())
        call_command("rerender_strand_names", stdout=StringIO(), stderr=StringIO())

        assert self._port_state(self.dev_a, self.dev_b) == before
        assert list(fc.fiber_strands.order_by("position").values_list("name", flat=True)) == strands_before

    def test_targets_labels_only_leaves_names_alone(self):
        """--targets labels re-renders labels without touching names."""
        fct, _fc = self._build("LBL")
        FiberCableType.objects.filter(pk=fct.pk).update(
            front_port_name_template="P{{ strand }}",
            front_port_label_template="L{{ strand }}",
            rear_port_name_template="RP{{ tube }}",
            rear_port_label_template="RL{{ tube }}",
        )
        names_before = self._port_state(self.dev_a, self.dev_b)

        call_command("rerender_port_names", "--targets", "labels", stdout=StringIO(), stderr=StringIO())

        after = self._port_state(self.dev_a, self.dev_b)
        assert after["front"] == names_before["front"]
        assert after["rear"] == names_before["rear"]
        assert sorted(after["front_labels"].values()) == ["L1", "L1", "L2", "L2"]
        assert sorted(after["rear_labels"].values()) == ["RL1", "RL1"]

    def test_strand_local_agrees_with_the_cable_save_path(self):
        """The command must recover the real local index, not render "None".

        The command and the cable-save signal write the same ports; if they
        disagree on ``strand_local`` a port's name flip-flops depending on
        which path last ran.
        """
        fct, fc = self._build("LOC")
        FiberCableType.objects.filter(pk=fct.pk).update(front_port_name_template="{{ cable }}:F{{ strand_local }}")

        call_command("rerender_port_names", "--targets", "names", stdout=StringIO(), stderr=StringIO())
        after_command = sorted(FrontPort.objects.filter(device=self.dev_a).values_list("name", flat=True))
        assert after_command == ["LOC:F1", "LOC:F2"]

        fc.cable.save()
        after_save = sorted(FrontPort.objects.filter(device=self.dev_a).values_list("name", flat=True))
        assert after_save == after_command

    def test_collision_refused(self):
        """A template that renders the same name for every front port is refused."""
        fct, _fc = self._build("COL")
        FiberCableType.objects.filter(pk=fct.pk).update(front_port_name_template="SAME")
        before = sorted(FrontPort.objects.filter(device=self.dev_a).values_list("name", flat=True))
        err = StringIO()

        call_command("rerender_port_names", stdout=StringIO(), stderr=err)

        after = sorted(FrontPort.objects.filter(device=self.dev_a).values_list("name", flat=True))
        assert after == before
        assert "collision" in err.getvalue().lower()

    def test_front_and_rear_may_share_a_name(self):
        """FrontPort and RearPort are separate tables with separate unique constraints.

        Each declares its own ``(device, name)`` constraint, so one device can
        legitimately hold a FrontPort and a RearPort of the same name. Merging
        the two into one collision group would refuse a write the database
        accepts.
        """
        fct, _fc = self._build("SHARE", strand_count=1)
        FiberCableType.objects.filter(pk=fct.pk).update(
            front_port_name_template="{{ cable }}-X",
            rear_port_name_template="{{ cable }}-X",
        )
        err = StringIO()

        call_command("rerender_port_names", stdout=StringIO(), stderr=err)

        assert "collision" not in err.getvalue().lower()
        assert list(FrontPort.objects.filter(device=self.dev_a).values_list("name", flat=True)) == ["SHARE-X"]
        assert list(RearPort.objects.filter(device=self.dev_a).values_list("name", flat=True)) == ["SHARE-X"]

    def test_rear_port_tray_render_agrees_with_the_cable_save_path(self):
        """The command and the cable-save signal must render a tray-placed RearPort alike.

        FMS never assigns ``RearPort.module`` itself, but ``tray`` and
        ``tray_position`` are in ``naming._REAR_TOKENS``, so a rear-port
        template may reference them, and a RearPort inherits ``module`` from
        NetBox's ``ModularComponentModel`` -- an operator can place one on a
        tray through the UI. If the command rendered ``tray`` as ``None``
        while ``_rename_ports_for_cable`` rendered the real tray name, that
        port's name would flip-flop depending on which path last wrote it,
        the same bug class already caught on this branch with
        ``strand_local``.

        Asserting only that the command renders the tray would pass even if
        the signal diverged, so this pins the two against each other.
        """
        from dcim.models import Module, ModuleBay, ModuleType

        fct, fc = self._build("RTRAY", strand_count=1)
        mt = ModuleType.objects.create(manufacturer=self.mfr, model="RR Tray")
        bay = ModuleBay.objects.create(device=self.dev_a, name="Tray 3")
        tray = Module.objects.create(device=self.dev_a, module_bay=bay, module_type=mt)

        rp = RearPort.objects.get(device=self.dev_a)
        RearPort.objects.filter(pk=rp.pk).update(module=tray)
        FiberCableType.objects.filter(pk=fct.pk).update(
            rear_port_name_template="{% if tray %}{{ tray }}:{% endif %}RP{{ tube }}"
        )

        fc.cable.save()
        after_save = RearPort.objects.get(pk=rp.pk).name

        call_command("rerender_port_names", "--cable-type", fct.model, stdout=StringIO(), stderr=StringIO())
        after_command = RearPort.objects.get(pk=rp.pk).name

        assert after_save == "Tray 3:RP1", "the cable-save path must render the real tray name"
        assert after_command == after_save, "rerender_port_names must agree with the cable-save path"

    # -- the ordering warning --------------------------------------------

    def test_warns_when_a_port_template_reads_strand_name(self):
        """Splitting the command made strand-before-port ordering the operator's job."""
        fct, _fc = self._build("ORD")
        FiberCableType.objects.filter(pk=fct.pk).update(front_port_name_template="{{ strand_name }}-p")
        err = StringIO()

        call_command("rerender_port_names", "--cable-type", fct.model, stdout=StringIO(), stderr=err)

        message = err.getvalue()
        assert "rerender_strand_names" in message
        assert str(fct) in message

    def test_no_warning_without_a_strand_name_reference(self):
        fct, _fc = self._build("NOORD")
        FiberCableType.objects.filter(pk=fct.pk).update(front_port_name_template="P{{ strand }}")
        err = StringIO()

        call_command("rerender_port_names", "--cable-type", fct.model, stdout=StringIO(), stderr=err)

        assert "rerender_strand_names" not in err.getvalue()


class TestSelfLoopingCableEnd(TestCase):
    """{{ end }} on a front port must read the same on all three paths that write it.

    ``_determine_cable_end`` returns "AB" when a cable has both its A and B
    terminations on RearPorts of one device -- a self-looping cable. That
    device-level value is right for a RearPort, which spans a whole tube and
    has no strand, but a FrontPort belongs to exactly one strand end:
    ``_provision_device_ports`` and ``services.render_port_strings`` both
    derive "A"/"B" from the strand and never produce "AB". Left alone, the
    cable-save signal would rewrite a provisioned "...A" to "...AB" and the
    next ``rerender_port_names`` run would put it back, the same flip-flop
    bug class already caught on this branch with ``strand_local`` and the
    rear-port tray tokens.
    """

    @classmethod
    def setUpTestData(cls):
        from dcim.models import Device, DeviceRole, DeviceType, Site

        cls.mfr = Manufacturer.objects.create(name="SL Mfr", slug="sl-mfr")
        site = Site.objects.create(name="SL Site", slug="sl-site")
        dt = DeviceType.objects.create(manufacturer=cls.mfr, model="SL Closure", slug="sl-closure")
        role = DeviceRole.objects.create(name="SL Role", slug="sl-role")
        cls.dev = Device.objects.create(name="SL-A", site=site, device_type=dt, role=role)

    def _self_loop(self, label):
        """Build a cable with both of its ends on RearPorts of a single device.

        ``create_closure_cable`` refuses ``device_a == device_b``, so the
        cable is assembled here: FMS provisions the A side normally, and the
        B side is terminated on a plain loop-back RearPort of the same
        device. Only one side is FMS-provisioned on purpose -- provisioning
        both would render two RearPorts of one device down to the same "AB"
        name and trip the ``(device, name)`` unique constraint, which is a
        separate limitation, not what this test is about.

        Returns ``(fct, fc)``.
        """
        from dcim.models import CableTermination
        from django.contrib.contenttypes.models import ContentType

        from netbox_fms.services import _provision_device_ports

        fct = FiberCableType.objects.create(
            manufacturer=self.mfr,
            model=f"SL-{label}",
            construction="loose_tube",
            strand_count=2,
            front_port_name_template="{{ cable }}-{{ end }}{{ strand }}",
            rear_port_name_template="RP-{{ end }}-T{{ tube }}",
        )
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=2)

        cable = Cable.objects.create(type="smf-os2", label=label)
        loop_back = RearPort.objects.create(device=self.dev, name=f"{label}-LOOPBACK", type="splice", positions=2)
        fc = FiberCable.objects.create(cable=cable, fiber_cable_type=fct)

        rp_ct = ContentType.objects.get_for_model(RearPort)
        for tube, rp, fiber_count in _provision_device_ports(fc, self.dev, "splice", "front_port_a"):
            CableTermination.objects.create(
                cable=cable,
                cable_end="A",
                termination_type=rp_ct,
                termination_id=rp.pk,
                connector=tube.position,
                positions=list(range(1, fiber_count + 1)),
            )
        CableTermination.objects.create(
            cable=cable,
            cable_end="B",
            termination_type=rp_ct,
            termination_id=loop_back.pk,
            connector=1,
            positions=[1, 2],
        )
        return fct, FiberCable.objects.get(pk=fc.pk)

    def _front_names(self):
        return sorted(FrontPort.objects.filter(device=self.dev).values_list("name", flat=True))

    def test_front_port_end_agrees_across_every_write_path(self):
        from netbox_fms.services import _determine_cable_end

        fct, fc = self._self_loop("LOOP")

        # Guard the fixture: without this the test could pass while never
        # reaching the "AB" branch it exists to pin.
        assert _determine_cable_end(fc.cable, self.dev) == "AB", "fixture must be a self-looping cable"

        after_provision = self._front_names()

        fc.cable.save()
        after_save = self._front_names()

        call_command("rerender_port_names", "--cable-type", fct.model, stdout=StringIO(), stderr=StringIO())
        after_command = self._front_names()

        assert after_provision == ["LOOP-A1", "LOOP-A2"]
        assert after_save == after_provision, "the cable-save path must agree with provisioning on {{ end }}"
        assert after_command == after_provision, "rerender_port_names must agree with provisioning on {{ end }}"

    def test_rear_port_end_still_renders_both_ends(self):
        """The device-level "AB" is correct for a RearPort and must survive.

        A RearPort has no strand, so ``_determine_cable_end`` is the only
        thing that can supply its ``{{ end }}``; both paths that write rear
        port names already agree on it.
        """
        fct, fc = self._self_loop("BOTH")

        fc.cable.save()
        after_save = sorted(RearPort.objects.filter(device=self.dev).values_list("name", flat=True))

        call_command("rerender_port_names", "--cable-type", fct.model, stdout=StringIO(), stderr=StringIO())
        after_command = sorted(RearPort.objects.filter(device=self.dev).values_list("name", flat=True))

        assert "RP-AB-T1" in after_save, "a self-looping cable's rear port must still render end as AB"
        assert after_command == after_save, "rerender_port_names must agree with the cable-save path on rear ports"
