"""Unit tests for the naming template engine."""

import pytest
from dcim.models import Cable, FrontPort, Manufacturer, RearPort
from django.core.exceptions import ValidationError
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

    Uses ``link_cable_topology`` rather than ``create_closure_cable``: the latter's
    final ``cable.save()`` triggers ``signals._rename_ports_for_cable``, which still
    rebuilds names with its own pre-template, tube-local formula (that rebuild is
    Task 5's job). ``link_cable_topology``'s greenfield path never re-saves the
    cable after provisioning, so its port names are exactly what
    ``_provision_device_ports`` -- the unit under test here -- produced.
    """

    @classmethod
    def setUpTestData(cls):
        from dcim.models import Device, DeviceRole, DeviceType, Site

        cls.mfr = Manufacturer.objects.create(name="PN Mfr", slug="pn-mfr")
        site = Site.objects.create(name="PN Site", slug="pn-site")
        dt = DeviceType.objects.create(manufacturer=cls.mfr, model="PN Closure", slug="pn-closure")
        role = DeviceRole.objects.create(name="PN Role", slug="pn-role")
        cls.dev_a = Device.objects.create(name="PN-A", site=site, device_type=dt, role=role)

    def _tubed_type(self, **kwargs):
        fct = FiberCableType.objects.create(
            manufacturer=self.mfr, model=f"PN-{len(kwargs)}", construction="loose_tube", strand_count=4, **kwargs
        )
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=2)
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T2", position=2, fiber_count=2)
        return fct

    def test_default_port_names(self):
        fct = self._tubed_type()
        cable = Cable.objects.create(type="smf-os2", label="NST")
        link_cable_topology(cable, fct, self.dev_a)
        fp_names = sorted(FrontPort.objects.filter(device=self.dev_a).values_list("name", flat=True))
        assert fp_names == ["NST:T1:F1", "NST:T1:F2", "NST:T2:F3", "NST:T2:F4"]
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
