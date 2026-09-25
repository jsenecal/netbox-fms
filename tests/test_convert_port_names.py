"""Tests for the convert_port_names management command.

The write-once pk-based names (issue #153) never self-convert: legacy
label-derived names stay until this command rewrites them. The command must
rename within the EXISTING rear-port structure and skip a cable entirely on
any name collision rather than half-renaming it.
"""

from functools import partial

from dcim.models import FrontPort, PortMapping, RearPort
from django.test import TestCase, override_settings

from netbox_fms.models import BufferTubeTemplate, FiberCable, FiberCableType
from netbox_fms.services import create_closure_cable, plan_port_names
from tests.conftest import (
    NAME_TEMPLATES,
    ClosurePairMixin,
    call_command_capture,
    land_strands,
    make_central_core_type,
    make_ribbon_in_tube_type,
    make_tray_module,
    make_tray_type,
    port_names,
)

_call = partial(call_command_capture, "convert_port_names")


class ConvertFixtureMixin(ClosurePairMixin):
    prefix = "CVT"

    def _build_legacy(self, label, *, model=None, strand_count=2):
        """Provision a loose-tube cable, then plant legacy label-derived names."""
        fct = FiberCableType.objects.create(
            manufacturer=self.mfr,
            model=model or f"CVT-{label}",
            construction="loose_tube",
            strand_count=strand_count,
        )
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=strand_count)
        fc, _ = create_closure_cable(
            device_a=self.dev_a,
            device_b=self.dev_b,
            fiber_cable_type=fct,
            cable_attrs={"type": "smf-os2", "label": label},
        )
        for strand in fc.fiber_strands.all():
            FrontPort.objects.filter(pk__in=(strand.front_port_a_id, strand.front_port_b_id)).update(
                name=f"{label}:T1:F{strand.position}"
            )
        rp_ids = PortMapping.objects.filter(front_port_id__in=self._front_port_ids(fc)).values("rear_port_id")
        RearPort.objects.filter(pk__in=rp_ids).update(name=f"{label}:T1")
        return fc

    @staticmethod
    def _front_port_ids(fc):
        return [
            fp_id
            for strand in fc.fiber_strands.all()
            for fp_id in (strand.front_port_a_id, strand.front_port_b_id)
            if fp_id is not None
        ]

    def _park_fronts(self, fc, device, module):
        """Move a cable's front ports on one device onto a module, as tube assignment would."""
        FrontPort.objects.filter(pk__in=self._front_port_ids(fc), device=device).update(module=module)


class TestConvertPortNames(ConvertFixtureMixin, TestCase):
    def test_converts_legacy_names_on_both_devices(self):
        fc = self._build_legacy("LEG")
        pk = fc.cable_id

        out, err = _call()

        assert err == ""
        assert "->" in out
        for device in (self.dev_a, self.dev_b):
            assert port_names(device, FrontPort) == sorted([f"{pk}:F1", f"{pk}:F2"])
            assert port_names(device, RearPort) == [f"{pk}:T1"]

    def test_second_run_is_a_no_op(self):
        self._build_legacy("IDEM")
        _call()

        out, err = _call()

        assert out == "" and err == ""

    def test_dry_run_writes_nothing(self):
        fc = self._build_legacy("DRY")

        out, _err = _call("--dry-run")

        assert "->" in out, "the dry run must still report the renames it would make"
        assert port_names(self.dev_a, FrontPort) == sorted([f"DRY:T1:F{n}" for n in (1, 2)])
        assert port_names(self.dev_a, RearPort) == ["DRY:T1"]
        assert fc.pk  # fixture used

    def test_cable_type_restricts_the_walk(self):
        fc_one = self._build_legacy("ONE", model="CVT-ONE")
        self._build_legacy("TWO", model="CVT-TWO")

        _call("--cable-type", "CVT-ONE")

        names = port_names(self.dev_a, FrontPort)
        assert f"{fc_one.cable_id}:F1" in names
        assert "TWO:T1:F1" in names, "the other cable type's ports must stay untouched"

    def test_collision_skips_the_whole_cable(self):
        fc = self._build_legacy("COL")
        pk = fc.cable_id
        FrontPort.objects.create(device=self.dev_a, name=f"{pk}:F1", type="splice")

        out, err = _call()

        assert "skipped" in err and str(fc) in err
        # Nothing was half-renamed, on either device.
        assert "COL:T1:F1" in port_names(self.dev_a, FrontPort)
        assert port_names(self.dev_b, FrontPort) == sorted([f"COL:T1:F{n}" for n in (1, 2)])
        assert port_names(self.dev_a, RearPort) == ["COL:T1"]
        assert out == ""

    def test_per_ribbon_rear_ports_recover_their_r_names(self):
        """A cable already structured per ribbon converts back to R names."""
        fct = make_central_core_type(self.mfr, "CVT-CC", ribbons=2, fibers=2)
        fc, _ = create_closure_cable(
            device_a=self.dev_a,
            device_b=self.dev_b,
            fiber_cable_type=fct,
            cable_attrs={"label": "RCC"},
        )
        pk = fc.cable_id
        for port in FrontPort.objects.all():
            FrontPort.objects.filter(pk=port.pk).update(name=f"RCC-F-{port.pk}")
        for port in RearPort.objects.all():
            RearPort.objects.filter(pk=port.pk).update(name=f"RCC-R-{port.pk}")

        _out, err = _call()

        assert err == ""
        for device in (self.dev_a, self.dev_b):
            assert port_names(device, RearPort) == [f"{pk}:R1", f"{pk}:R2"]
            assert port_names(device, FrontPort) == sorted(f"{pk}:F{n}" for n in range(1, 5))

    def test_swap_shaped_rename_is_refused(self):
        """A target name still held by another port in the same plan is a problem.

        The end state would be consistent, but the non-deferrable unique
        constraint can reject the swap mid-update, so the plan must refuse it.
        """
        fc = self._build_legacy("SWP")
        pk = fc.cable_id
        first, second = fc.fiber_strands.order_by("position")
        FrontPort.objects.filter(pk=first.front_port_a_id).update(name=f"{pk}:F2")

        _renames, problems, _warnings = plan_port_names(fc)

        assert any("still held" in p for p in problems)

    def test_tube_grouped_ribbon_cable_keeps_its_structure(self):
        """Rear-port STRUCTURE is not migrated: a legacy tube-grouped ribbon
        cable keeps one rear port per tube and gets {cable.id}:T{n} names.
        """
        from dcim.models import Cable

        fct = make_ribbon_in_tube_type(self.mfr, "CVT-RIT", tubes=1, ribbons_per_tube=2, fibers=2)
        cable = Cable.objects.create(label="RIB")
        fc = FiberCable.objects.create(cable=cable, fiber_cable_type=fct)

        # Legacy structure: ONE rear port for the whole tube, ribbons flattened.
        rp = RearPort.objects.create(device=self.dev_a, name="RIB:T1", type="splice", positions=4)
        fps = [FrontPort.objects.create(device=self.dev_a, name=f"RIB:T1:F{i}", type="splice") for i in range(1, 5)]
        land_strands(fc, fps, rear_port=rp)

        _out, err = _call()

        assert err == ""
        rp.refresh_from_db()
        assert rp.name == f"{cable.pk}:T1", "the tube-grouped rear port keeps a T name, not R"
        assert RearPort.objects.filter(device=self.dev_a).count() == 1, "no rear-port re-homing"
        assert port_names(self.dev_a, FrontPort) == sorted(f"{cable.pk}:F{n}" for n in range(1, 5))


class TestConvertPortNamesOwnership(ConvertFixtureMixin, TestCase):
    """Only ports FMS created are converted (issue #180); adopted ports keep their names."""

    def test_ports_parked_on_a_splice_tray_convert(self):
        fc = self._build_legacy("TRY")
        tray = make_tray_module(self.dev_a, make_tray_type(self.mfr, "CVT-Tray"), "Tray 1")
        self._park_fronts(fc, self.dev_a, tray)
        pk = fc.cable_id

        _out, err = _call()

        assert err == ""
        assert port_names(self.dev_a, FrontPort) == sorted([f"{pk}:F1", f"{pk}:F2"])
        assert port_names(self.dev_a, RearPort) == [f"{pk}:T1"]

    def test_ports_on_a_non_tray_module_are_left_alone(self):
        """A cassette's ports were designed with the module type; FMS never places ports there.

        The device-level rear port stays too: its mapped fronts are not ours.
        """
        fc = self._build_legacy("CAS")
        cassette = make_tray_module(self.dev_a, make_tray_type(self.mfr, "CVT-Cassette", role=None), "Slot 1")
        self._park_fronts(fc, self.dev_a, cassette)
        pk = fc.cable_id

        _out, err = _call()

        assert err == ""
        assert port_names(self.dev_a, FrontPort) == ["CAS:T1:F1", "CAS:T1:F2"]
        assert port_names(self.dev_a, RearPort) == ["CAS:T1"]
        # The other end sits at device level with no templates, so it still converts.
        assert port_names(self.dev_b, FrontPort) == sorted([f"{pk}:F1", f"{pk}:F2"])

    def test_template_born_device_level_ports_are_left_alone(self):
        """Device-level ports instantiated from the DeviceType's templates keep the operator's names."""
        from dcim.models import Cable, Device, DeviceType, FrontPortTemplate, RearPortTemplate

        dt = DeviceType.objects.create(manufacturer=self.mfr, model="CVT-Panel", slug="cvt-panel")
        RearPortTemplate.objects.create(device_type=dt, name="MPO", type="mpo", positions=2)
        for n in (1, 2):
            FrontPortTemplate.objects.create(device_type=dt, name=f"LC{n}", type="lc")
        panel = Device.objects.create(name="CVT-Panel", site=self.dev_a.site, device_type=dt, role=self.dev_a.role)
        rp = RearPort.objects.get(device=panel)
        fct = FiberCableType.objects.create(
            manufacturer=self.mfr, model="CVT-TPL", construction="tight_buffer", strand_count=2
        )
        fc = FiberCable.objects.create(cable=Cable.objects.create(label="TPL"), fiber_cable_type=fct)
        land_strands(fc, [FrontPort.objects.get(device=panel, name=f"LC{i}") for i in (1, 2)], rear_port=rp)

        out, err = _call()

        assert out == "" and err == ""
        assert port_names(panel, FrontPort) == ["LC1", "LC2"]
        assert port_names(panel, RearPort) == ["MPO"]


class TestConvertPortNamesTemplates(ConvertFixtureMixin, TestCase):
    """A configured name template is the scheme the command converges on."""

    @override_settings(PLUGINS_CONFIG={"netbox_fms": NAME_TEMPLATES})
    def test_configured_template_converges_existing_names(self):
        self._build_legacy("TPL")

        _call()

        assert port_names(self.dev_a, FrontPort) == ["TPL-A-F1", "TPL-A-F2"]
        assert port_names(self.dev_b, FrontPort) == ["TPL-B-F1", "TPL-B-F2"]
        assert port_names(self.dev_b, RearPort) == ["TPL-B-T1"]

    @override_settings(PLUGINS_CONFIG={"netbox_fms": NAME_TEMPLATES})
    def test_second_run_on_template_names_is_a_no_op(self):
        """A port's own current name must not count as a collision against itself."""
        self._build_legacy("AGAIN")
        _call()

        out, err = _call()

        assert out == ""
        assert err == ""

    @override_settings(PLUGINS_CONFIG={"netbox_fms": {"front_port_name_template": "{{ cable }}"}})
    def test_template_fallback_is_reported_and_pk_names_applied(self):
        fc = self._build_legacy("FB")

        _out, err = _call()

        assert "fell back" in err
        assert "FB" in err
        assert port_names(self.dev_a, FrontPort) == [f"{fc.cable_id}:F1", f"{fc.cable_id}:F2"]
