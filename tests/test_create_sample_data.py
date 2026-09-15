"""Regression tests for the create_sample_data management command.

Issue #56: the command drifted from the models after SlackLoop.length_unit
was replaced by FiberCableType.mark_unit (migration 0033) and crashed with
``TypeError: SlackLoop() got unexpected keyword arguments: 'length_unit'``.
A single smoke run of the command catches any constructor drift against the
current models.
"""

from io import StringIO

import pytest
from dcim.models import Cable, Device, FrontPort, RearPort
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import OutputWrapper

from netbox_fms.management.commands.create_sample_data import Command
from netbox_fms.models import (
    BufferTubeTemplate,
    FiberCable,
    FiberCableType,
    FiberCircuit,
    FiberCircuitPath,
    FiberStrand,
    SlackLoop,
    SplicePlan,
    SplicePlanEntry,
)
from tests.conftest import make_closure_with_tray, make_front_port


@pytest.mark.django_db
class TestCreateSampleData:
    def test_simple_mode_completes_and_slack_loops_are_valid(self):
        call_command("create_sample_data", "--simple")

        loops = SlackLoop.objects.all()
        assert loops.exists()
        # Slack loops are bulk_create'd (no clean()); they must still validate
        # against the current model, which requires the cable type to declare
        # a mark_unit.
        for loop in loops:
            loop.full_clean()

    def test_simple_mode_creates_splice_plans_with_entries(self):
        """Issue #96: the command grouped front ports by parsing '#<cable_pk>'
        prefixes out of port names, but the port-rename signal names ports
        from the cable label, so no port ever matched and every closure was
        skipped after its (empty) plan row had already been created.
        """
        call_command("create_sample_data", "--simple")

        plans = SplicePlan.objects.all()
        assert plans.exists()
        assert SplicePlanEntry.objects.exists()

        empty_plans = [plan.name for plan in plans if not plan.entries.exists()]
        assert empty_plans == []


def _make_tubed_cable(rig, closure, far_device, label, fp_offset):
    """Create a labeled 3-tube/6-strand cable entering the closure, with the
    closure-side strand ports mapped onto the rig's tray front ports."""
    fct = FiberCableType.objects.create(
        manufacturer=rig.mfr,
        model=f"{label}-FCT",
        construction="loose_tube",
        strand_count=6,
    )
    for pos in range(1, 4):
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name=f"T{pos}", position=pos, fiber_count=2)
    rp = RearPort.objects.create(device=closure, name=f"{label}-RP", type="splice", positions=6)
    far_fp = make_front_port(far_device, f"{label}-FarFP")
    cable = Cable.objects.create(a_terminations=[rp], b_terminations=[far_fp], label=label)
    fc = FiberCable.objects.create(cable=cable, fiber_cable_type=fct)
    for strand, fp in zip(fc.fiber_strands.order_by("position"), rig.ports[fp_offset : fp_offset + 6], strict=True):
        strand.front_port_a = fp
        strand.save()
    return fc


@pytest.mark.django_db
class TestFullModeSplicePlanBuilder:
    def test_backbone_closure_splices_tube_for_tube_with_express(self):
        """Issue #96: the full-mode builder grouped ports by parsing a
        '#<cable_pk>' name prefix (which never matches label-derived port
        names) and derived the backbone express flag from a string
        comparison on a name fragment ('T1' > 'T02' is True, so every tube
        of a labeled cable would have counted as express). Exercise the
        builder directly on a backbone closure with two 3-tube cables.
        """
        rig = make_closure_with_tray("FMSP", port_count=12)
        far = Device.objects.create(name="FMSP-Far", site=rig.site, device_type=rig.device_type, role=rig.role)
        _make_tubed_cable(rig, rig.closure, far, "FMSP-A", 0)
        _make_tubed_cable(rig, rig.closure, far, "FMSP-B", 6)
        # A closure reached by a single cable must be skipped without leaving
        # an empty plan row behind.
        lone_rig = make_closure_with_tray("FMSL", port_count=6)
        _make_tubed_cable(lone_rig, lone_rig.closure, far, "FMSL-A", 0)

        cmd = Command()
        cmd.stdout = OutputWrapper(StringIO())
        cmd.devices = {"BB-FMSP-01": rig.closure, "BB-FMSL-01": lone_rig.closure}
        cmd.fp_ct = ContentType.objects.get_for_model(FrontPort)
        cmd._create_splice_plans()

        assert not SplicePlan.objects.filter(closure=lone_rig.closure).exists()
        plan = SplicePlan.objects.get(closure=rig.closure)
        entries = list(plan.entries.all())
        assert len(entries) == 6
        # First two tubes are cut/spliced; tube 3 passes through express.
        for entry in entries:
            strand = FiberStrand.objects.get(front_port_a=entry.fiber_a)
            assert entry.is_express is (strand.buffer_tube.position > 2)


@pytest.mark.django_db
class TestFullModeFiberCircuitOrigins:
    def test_origin_ports_found_via_strand_linkage(self):
        """Issue #96: the circuit origin lookup parsed a '#<cable_pk>' name
        prefix that label-derived port names never carry, so it always fell
        back to "first two ports by name". Resolve through strands instead:
        the decoy port (which sorts first by name) must not be picked.
        """
        rig = make_closure_with_tray("FMCO", port_count=2)
        co = Device.objects.create(name="CO-Downtown", site=rig.site, device_type=rig.device_type, role=rig.role)
        make_front_port(co, "AAA-Decoy")
        fp1 = make_front_port(co, "FMCO-F1")
        fp2 = make_front_port(co, "FMCO-F2")

        fct = FiberCableType.objects.create(
            manufacturer=rig.mfr, model="FMCO-FCT", construction="tight_buffer", strand_count=2
        )
        cable = Cable.objects.create(
            a_terminations=[fp1, fp2], b_terminations=rig.ports, label="CO-Downtown → BB-DO-NO-A-01"
        )
        fc = FiberCable.objects.create(cable=cable, fiber_cable_type=fct)
        for strand, fp in zip(fc.fiber_strands.order_by("position"), [fp1, fp2], strict=True):
            strand.front_port_a = fp
            strand.save()

        cmd = Command()
        cmd.stdout = OutputWrapper(StringIO())
        cmd.devices = {"CO-Downtown": co}
        cmd._create_fiber_circuits()

        circuit = FiberCircuit.objects.get(cid="BB-DT-NO-001")
        origins = {path.origin_id for path in FiberCircuitPath.objects.filter(circuit=circuit)}
        assert origins == {fp1.pk, fp2.pk}
