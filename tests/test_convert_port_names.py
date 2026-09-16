"""Tests for the convert_port_names management command.

The write-once pk-based names (issue #153) never self-convert: legacy
label-derived names stay until this command rewrites them. The command must
rename within the EXISTING rear-port structure and skip a cable entirely on
any name collision rather than half-renaming it.
"""

from io import StringIO

from dcim.models import Device, FrontPort, PortMapping, RearPort
from django.core.management import call_command
from django.test import TestCase

from netbox_fms.models import BufferTubeTemplate, FiberCable, FiberCableType, RibbonTemplate
from netbox_fms.services import create_closure_cable
from netbox_fms.signals import fms_portmapping_bypass
from tests.conftest import make_infra


def _call(*args):
    out, err = StringIO(), StringIO()
    call_command("convert_port_names", *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


class ConvertFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        site, cls.mfr, dt, role = make_infra("CVT")
        cls.dev_a = Device.objects.create(name="CVT-A", site=site, device_type=dt, role=role)
        cls.dev_b = Device.objects.create(name="CVT-B", site=site, device_type=dt, role=role)

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
        fp_ids = []
        for strand in fc.fiber_strands.all():
            for fp_id in (strand.front_port_a_id, strand.front_port_b_id):
                FrontPort.objects.filter(pk=fp_id).update(name=f"{label}:T1:F{strand.position}")
                fp_ids.append(fp_id)
        rp_ids = PortMapping.objects.filter(front_port_id__in=fp_ids).values("rear_port_id")
        RearPort.objects.filter(pk__in=rp_ids).update(name=f"{label}:T1")
        return fc

    def _names(self, device, model):
        return sorted(model.objects.filter(device=device).values_list("name", flat=True))


class TestConvertPortNames(ConvertFixtureMixin, TestCase):
    def test_converts_legacy_names_on_both_devices(self):
        fc = self._build_legacy("LEG")
        pk = fc.cable_id

        out, err = _call()

        assert err == ""
        assert "->" in out
        for device in (self.dev_a, self.dev_b):
            assert self._names(device, FrontPort) == sorted([f"{pk}:F1", f"{pk}:F2"])
            assert self._names(device, RearPort) == [f"{pk}:T1"]

    def test_second_run_is_a_no_op(self):
        self._build_legacy("IDEM")
        _call()

        out, err = _call()

        assert out == "" and err == ""

    def test_dry_run_writes_nothing(self):
        fc = self._build_legacy("DRY")

        out, _err = _call("--dry-run")

        assert "->" in out, "the dry run must still report the renames it would make"
        assert self._names(self.dev_a, FrontPort) == sorted([f"DRY:T1:F{n}" for n in (1, 2)])
        assert self._names(self.dev_a, RearPort) == ["DRY:T1"]
        assert fc.pk  # fixture used

    def test_cable_type_restricts_the_walk(self):
        fc_one = self._build_legacy("ONE", model="CVT-ONE")
        self._build_legacy("TWO", model="CVT-TWO")

        _call("--cable-type", "CVT-ONE")

        names = self._names(self.dev_a, FrontPort)
        assert f"{fc_one.cable_id}:F1" in names
        assert "TWO:T1:F1" in names, "the other cable type's ports must stay untouched"

    def test_collision_skips_the_whole_cable(self):
        fc = self._build_legacy("COL")
        pk = fc.cable_id
        FrontPort.objects.create(device=self.dev_a, name=f"{pk}:F1", type="splice")

        out, err = _call()

        assert "skipped" in err and str(fc) in err
        # Nothing was half-renamed, on either device.
        assert "COL:T1:F1" in self._names(self.dev_a, FrontPort)
        assert self._names(self.dev_b, FrontPort) == sorted([f"COL:T1:F{n}" for n in (1, 2)])
        assert self._names(self.dev_a, RearPort) == ["COL:T1"]
        assert out == ""

    def test_tube_grouped_ribbon_cable_keeps_its_structure(self):
        """Rear-port STRUCTURE is not migrated: a legacy tube-grouped ribbon
        cable keeps one rear port per tube and gets {cable.id}:T{n} names.
        """
        from dcim.models import Cable

        fct = FiberCableType.objects.create(
            manufacturer=self.mfr,
            model="CVT-RIT",
            construction="ribbon_in_tube",
            strand_count=4,
        )
        btt = BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=None)
        for r in (1, 2):
            RibbonTemplate.objects.create(
                fiber_cable_type=fct, buffer_tube_template=btt, name=f"T1-R{r}", position=r, fiber_count=2
            )
        cable = Cable.objects.create(label="RIB")
        fc = FiberCable.objects.create(cable=cable, fiber_cable_type=fct)

        # Legacy structure: ONE rear port for the whole tube, ribbons flattened.
        with fms_portmapping_bypass():
            rp = RearPort.objects.create(device=self.dev_a, name="RIB:T1", type="splice", positions=4)
            for i, strand in enumerate(fc.fiber_strands.order_by("position"), start=1):
                fp = FrontPort.objects.create(device=self.dev_a, name=f"RIB:T1:F{i}", type="splice")
                PortMapping.objects.create(
                    device=self.dev_a, front_port=fp, rear_port=rp, front_port_position=1, rear_port_position=i
                )
                strand.front_port_a = fp
                strand.save(update_fields=["front_port_a"])

        _out, err = _call()

        assert err == ""
        rp.refresh_from_db()
        assert rp.name == f"{cable.pk}:T1", "the tube-grouped rear port keeps a T name, not R"
        assert RearPort.objects.filter(device=self.dev_a).count() == 1, "no rear-port re-homing"
        assert self._names(self.dev_a, FrontPort) == sorted(f"{cable.pk}:F{n}" for n in range(1, 5))
