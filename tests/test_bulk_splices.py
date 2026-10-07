"""Bulk splice creation: same stored rows as the per-object path, in two modes."""

from unittest.mock import patch

from dcim.models import Cable, CableTermination, Device, FrontPort
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase

from netbox_fms.bulk import SpliceSpec, create_splices
from netbox_fms.jobs import PathAnalysisJob
from netbox_fms.models import BufferTubeTemplate, FiberCableType, PathAnalysisQueue, SplicePlan
from netbox_fms.services import create_closure_cable, front_port_splice_pairs
from tests.conftest import (
    changes_logged,
    is_indexed,
    make_infra,
    place_in_rack,
    rolled_back,
    saves_seen,
    stored_columns,
)
from tests.test_path_walker import chain_from


def reference_splices(pairs):
    """The per-object path the bulk writer replaces (the additions loop of apply_diff)."""
    fp_ct = ContentType.objects.get_for_model(FrontPort)
    for port_a_id, port_b_id in pairs:
        cable = Cable(status="connected")
        cable.save()
        CableTermination.objects.create(cable=cable, cable_end="A", termination_type=fp_ct, termination_id=port_a_id)
        CableTermination.objects.create(cable=cable, cable_end="B", termination_type=fp_ct, termination_id=port_b_id)


def dump_splices(closure):
    """Every stored column of the closure's jumpers, keyed by the names of the two spliced ports."""
    fp_ct = ContentType.objects.get_for_model(FrontPort)
    ports = {p.pk: p for p in FrontPort.objects.filter(device=closure)}
    by_cable = {}
    for term in CableTermination.objects.filter(termination_type=fp_ct, termination_id__in=ports).order_by("cable_end"):
        by_cable.setdefault(term.cable_id, []).append(term)
    out = {}
    for cable in Cable.objects.filter(pk__in=by_cable):
        terms = by_cable[cable.pk]
        out[tuple(ports[t.termination_id].name for t in terms)] = {
            "cable": stored_columns(cable),
            "terminations": [stored_columns(t, drop=("cable_id", "termination_id")) for t in terms],
            "ports": [
                {"on_this_cable": ports[t.termination_id].cable_id == cable.pk}
                | stored_columns(ports[t.termination_id], drop=("cable_id",))
                for t in terms
            ],
        }
    return out


class BulkSpliceCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = make_infra("BSP")
        cls.far1 = Device.objects.create(name="BSP-FAR1", site=site, device_type=dt, role=role)
        cls.closure = place_in_rack(
            Device.objects.create(name="BSP-CLOSURE", site=site, device_type=dt, role=role), "BSP"
        )
        cls.far2 = Device.objects.create(name="BSP-FAR2", site=site, device_type=dt, role=role)
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="BSP-LT12", strand_count=12, construction="loose_tube"
        )
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=12)
        cls.cable_a, _ = create_closure_cable(device_a=cls.far1, device_b=cls.closure, fiber_cable_type=fct)
        cls.cable_b, _ = create_closure_cable(device_a=cls.closure, device_b=cls.far2, fiber_cable_type=fct)
        a = {s.position: s for s in cls.cable_a.fiber_strands.all()}
        b = {s.position: s for s in cls.cable_b.fiber_strands.all()}
        cls.strands_a, cls.strands_b = a, b
        # Fibre k of cable A spliced to fibre k of cable B, on the closure's own ports.
        cls.pairs = [(a[k].front_port_b_id, b[k].front_port_a_id) for k in range(1, 13)]

    def specs(self, pairs=None, **attrs):
        return [SpliceSpec(a, b, dict(attrs) or None) for a, b in (pairs or self.pairs)]


class TestEquivalence(BulkSpliceCase):
    def test_quiet_mode_stores_what_the_per_object_path_stores(self):
        _, expected = rolled_back(lambda: reference_splices(self.pairs), lambda: dump_splices(self.closure))
        create_splices(self.closure, self.specs(), notify=False)
        assert len(expected) == 12
        assert dump_splices(self.closure) == expected

    def test_interactive_mode_stores_the_same_and_announces_each_object(self):
        _, expected = rolled_back(lambda: reference_splices(self.pairs), lambda: dump_splices(self.closure))
        with saves_seen(Cable, CableTermination) as seen:
            cables = create_splices(self.closure, self.specs())
        assert dump_splices(self.closure) == expected
        assert sorted(pk for model, pk, created in seen if model is Cable and created) == sorted(c.pk for c in cables)
        assert sum(1 for model, _pk, created in seen if model is CableTermination and created) == 24

    def test_quiet_mode_fires_no_post_save(self):
        with saves_seen(Cable, CableTermination, FrontPort) as seen:
            create_splices(self.closure, self.specs(), notify=False)
        assert seen == []

    def test_returns_the_cables_in_input_order(self):
        cables = create_splices(self.closure, self.specs(self.pairs[:3]), notify=False)
        fp_ct = ContentType.objects.get_for_model(FrontPort)
        for cable, (port_a, port_b) in zip(cables, self.pairs[:3], strict=True):
            ends = dict(
                CableTermination.objects.filter(cable=cable, termination_type=fp_ct).values_list(
                    "cable_end", "termination_id"
                )
            )
            assert ends == {"A": port_a, "B": port_b}


class TestReadBack(BulkSpliceCase):
    def test_fms_reads_the_splices_back_and_traces_across_them(self):
        create_splices(self.closure, self.specs(), notify=False)
        port_ids = [p for pair in self.pairs for p in pair]
        assert {frozenset(p) for p in front_port_splice_pairs(port_ids)} == {frozenset(p) for p in self.pairs}
        chain = chain_from(self.strands_a[5].front_port_a)
        assert chain.end_b.port_id == self.strands_b[5].front_port_b_id
        assert chain.hops == [("strand", self.strands_a[5].pk), ("strand", self.strands_b[5].pk)]


class TestAttributes(BulkSpliceCase):
    def test_attrs_are_stored_on_the_jumper(self):
        (cable,) = create_splices(
            self.closure,
            self.specs(self.pairs[:1], description="ARCFM splice (Fusion)", comments="note", label="J1"),
            notify=False,
        )
        cable.refresh_from_db()
        assert (cable.description, cable.comments, cable.label, cable.status) == (
            "ARCFM splice (Fusion)",
            "note",
            "J1",
            "connected",
        )

    def test_custom_field_data_is_merged_over_the_defaults(self):
        from core.models import ObjectType
        from extras.models import CustomField

        field = CustomField.objects.create(name="bsp_origin", type="text", default="unset")
        other = CustomField.objects.create(name="bsp_other", type="text", default="kept")
        for cf in (field, other):
            cf.object_types.set([ObjectType.objects.get_for_model(Cable)])
        (cable,) = create_splices(
            self.closure,
            self.specs(self.pairs[:1], custom_field_data={"bsp_origin": "import"}),
            notify=False,
        )
        cable.refresh_from_db()
        assert cable.custom_field_data["bsp_origin"] == "import"
        assert cable.custom_field_data["bsp_other"] == "kept"


class TestValidation(BulkSpliceCase):
    def assert_rejected(self, pairs, fragment):
        before = Cable.objects.count()
        with self.assertRaises(ValidationError) as raised:
            create_splices(self.closure, self.specs(pairs), notify=False)
        assert fragment in " ".join(raised.exception.messages)
        assert Cable.objects.count() == before

    def test_a_port_of_another_device_is_rejected(self):
        foreign = self.strands_a[1].front_port_a_id  # on far1
        self.assert_rejected([(foreign, self.pairs[0][1])], str(foreign))

    def test_a_port_that_already_carries_a_cable_is_rejected(self):
        create_splices(self.closure, self.specs(self.pairs[:1]), notify=False)
        taken = self.pairs[0][0]
        self.assert_rejected([(taken, self.pairs[1][1])], str(taken))

    def test_a_port_used_twice_in_one_batch_is_rejected(self):
        shared = self.pairs[0][0]
        self.assert_rejected([self.pairs[0], (shared, self.pairs[1][1])], str(shared))

    def test_a_splice_of_a_port_to_itself_is_rejected(self):
        port = self.pairs[0][0]
        self.assert_rejected([(port, port)], str(port))


class TestQuietReplacements(BulkSpliceCase):
    def test_marks_the_closure_plans_stale_and_indexes_the_cables(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="BSP plan", diff_stale=False)
        (cable,) = create_splices(self.closure, self.specs(self.pairs[:1], label="BSP-JUMPER"), notify=False)
        plan.refresh_from_db()
        assert plan.diff_stale is True
        assert is_indexed(cable, "BSP-JUMPER")

    def test_quiet_mode_queues_the_closure_for_analysis(self):
        with patch.object(PathAnalysisJob, "enqueue"), self.captureOnCommitCallbacks(execute=True):
            create_splices(self.closure, self.specs(self.pairs[:1]), notify=False)
        queued = set(PathAnalysisQueue.objects.values_list("device_id", "reason"))
        assert queued == {(self.closure.pk, "bulk_operation")}


class TestChangeLog(BulkSpliceCase):
    def test_interactive_mode_logs_the_changes_the_per_object_path_logs(self):
        expected = changes_logged(lambda: reference_splices(self.pairs[:3]))
        assert expected[("cable", "create")] == 3
        # Cable.save() writes a new cable twice (insert, then update), which logs an empty update
        # next to the create; one bulk insert has no such second write.
        assert expected.pop(("cable", "update")) == 3
        assert changes_logged(lambda: create_splices(self.closure, self.specs(self.pairs[:3]))) == expected

    def test_quiet_mode_logs_nothing(self):
        assert not changes_logged(lambda: create_splices(self.closure, self.specs(self.pairs[:3]), notify=False))
