"""Regression tests for the create_sample_data management command.

Issue #56: the command drifted from the models after SlackLoop.length_unit
was replaced by FiberCableType.mark_unit (migration 0033) and crashed with
``TypeError: SlackLoop() got unexpected keyword arguments: 'length_unit'``.
A single smoke run of the command catches any constructor drift against the
current models.
"""

import re

import pytest
from django.core.management import call_command

from netbox_fms.models import FiberStrand, SlackLoop, SplicePlanEntry


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

        # Sample ports must use the shared write-once name grammar
        # ({cable.id}:F{absolute fiber number}), not a private copy of it.
        strand = FiberStrand.objects.select_related("fiber_cable", "front_port_a").first()
        fp = strand.front_port_a
        assert fp.name == f"{strand.fiber_cable.cable_id}:F{strand.position}"
        assert re.fullmatch(r"\d+:F\d+", fp.name)

        # The splice-plan builder groups tray ports via strand linkage, so
        # the demo plans actually carry entries under the pk-based names.
        assert SplicePlanEntry.objects.exists()


@pytest.mark.django_db
class TestSampleDataRetracesSplicedCorePaths:
    def test_simple_mode_core_path_reaches_far_end_after_splicing(self):
        """Issue #96 follow-up: _create_splice_cables bulk-creates the
        FP-to-FP splice jumpers with hand-built CableTerminations, bypassing
        Cable.save() and NetBox's automatic CablePath recalculation. Every
        core CablePath computed from a patch cable created before its
        splice jumpers existed is left dead-ending at the first closure it
        reached, even though the plugin's own live trace walks the full
        spliced path.
        """
        from dcim.models import CablePath, Device, FrontPort, Interface

        call_command("create_sample_data", "--simple")

        co = Device.objects.get(name="CO-Main")
        router = Device.objects.get(name="CO-Main-Router")
        hub_switch = Device.objects.get(name="Hub-East-Switch")

        # The core-router interface patched to the CO ODF's lowest-named
        # FrontPort -- found from the data via its patch cable, not
        # hard-coded, since the interface/port naming is an implementation
        # detail of the sample-data build.
        candidates = []
        for intf in Interface.objects.filter(device=router).exclude(cable=None):
            fp_term = intf.cable.terminations.exclude(cable_end=intf.cable_end).first()
            if fp_term is None or not isinstance(fp_term.termination, FrontPort):
                continue
            fp = fp_term.termination
            if fp.device_id != co.pk:
                continue
            candidates.append((fp.name, intf))
        assert candidates, "expected a core-router interface patched to the CO ODF"
        _, origin_intf = min(candidates, key=lambda pair: pair[0])

        origin_intf.refresh_from_db()
        assert origin_intf._path_id, "origin interface has no stored CablePath"
        path = CablePath.objects.get(pk=origin_intf._path_id)

        # On unfixed code this path is stale: it was computed when the patch
        # cable was created, before the splice jumpers existed, so it dead-
        # ends at the first closure (is_complete=False).
        assert path.is_complete, "core CablePath is stale and dead-ends before reaching the far end"
        destinations = path.destinations
        assert len(destinations) == 1
        assert isinstance(destinations[0], Interface)
        assert destinations[0].device_id == hub_switch.pk


@pytest.mark.django_db
class TestSplicePlanRowLeak:
    def test_lone_cable_closure_leaves_no_empty_plan(self):
        """Issue #96: a closure reached by fewer than two cables must be
        skipped without leaving an applied SplicePlan row with zero entries
        behind (the plan row used to be created before the check).
        """
        from io import StringIO

        from dcim.models import Cable, Device, FrontPort, RearPort
        from django.contrib.contenttypes.models import ContentType
        from django.core.management.base import OutputWrapper

        from netbox_fms.management.commands.create_sample_data import Command
        from netbox_fms.models import FiberCable, FiberCableType, SplicePlan
        from tests.conftest import make_closure_with_tray, make_front_port

        rig = make_closure_with_tray("LONE", port_count=2)
        far = Device.objects.create(name="LONE-Far", site=rig.site, device_type=rig.device_type, role=rig.role)
        fct = FiberCableType.objects.create(
            manufacturer=rig.mfr, model="LONE-FCT", construction="tight_buffer", strand_count=2
        )
        rp = RearPort.objects.create(device=rig.closure, name="LONE-RP", type="splice", positions=2)
        cable = Cable.objects.create(a_terminations=[rp], b_terminations=[make_front_port(far, "LONE-Far-FP")])
        fc = FiberCable.objects.create(cable=cable, fiber_cable_type=fct)
        for strand, fp in zip(fc.fiber_strands.order_by("position"), rig.ports, strict=True):
            strand.front_port_a = fp
            strand.save()

        cmd = Command()
        cmd.stdout = OutputWrapper(StringIO())
        cmd.devices = {"BB-LONE-01": rig.closure}
        cmd.fp_ct = ContentType.objects.get_for_model(FrontPort)
        cmd._create_splice_plans()

        assert not SplicePlan.objects.filter(closure=rig.closure).exists()
