"""Writing analysis results (#196 spec section 2): one test per row of the outcome table."""

from datetime import timedelta

from dcim.models import Cable, RearPort
from django.test import TestCase
from django.utils import timezone

from netbox_fms.choices import PathAnomalyKindChoices, PathEndKindChoices, PathEndReasonChoices
from netbox_fms.models import FiberCable, FiberCableType, FiberStrand, FiberStrandPath, PathAnomaly
from netbox_fms.path_analysis import (
    device_ids_on_paths,
    path_ids_through_devices,
    replace_anomalies,
    try_analysis_lock,
    write_results,
)
from netbox_fms.path_graph import Anomaly, Chain, ChainEnd, route_key_for
from netbox_fms.services import create_closure_cable
from tests.conftest import make_closure_pair, make_infra

TERMINATED = ChainEnd(None, PathEndKindChoices.TERMINATED, "")
OPEN = ChainEnd(None, PathEndKindChoices.OPEN, PathEndReasonChoices.CABLE_END)


def strand_chain(*strands, end_a=OPEN, end_b=OPEN):
    return Chain([("strand", s.pk) for s in strands], end_a, end_b, [s.fiber_cable.cable_id for s in strands])


class WriterCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        _site, mfr, _dt, _role = make_infra("WR")
        fct = FiberCableType.objects.create(manufacturer=mfr, model="WR-3", strand_count=3, construction="tight_buffer")
        cls.cable = Cable.objects.create()
        cls.fc = FiberCable.objects.create(cable=cls.cable, fiber_cable_type=fct)
        cls.s1, cls.s2, cls.s3 = list(cls.fc.fiber_strands.order_by("position"))
        cls.other_cable = Cable.objects.create()
        cls.other_fc = FiberCable.objects.create(cable=cls.other_cable, fiber_cable_type=fct)
        cls.t1, cls.t2, cls.t3 = list(cls.other_fc.fiber_strands.order_by("position"))
        cls.now = timezone.now()

    def store(self, chain):
        stats = write_results([chain], FiberStrandPath.objects.none(), computed_at=self.now - timedelta(hours=1))
        assert stats.paths_created == 1
        return FiberStrandPath.objects.latest("pk")

    @staticmethod
    def stored():
        return FiberStrandPath.objects.prefetch_related("hops")


class TestWriteOutcomes(WriterCase):
    def test_new_chain_creates_a_path_with_its_hops_and_derived_fields(self):
        chain = strand_chain(self.s1, self.t1, end_a=TERMINATED, end_b=OPEN)
        stats = write_results([chain], self.stored(), computed_at=self.now)
        path = FiberStrandPath.objects.get()
        assert stats.paths_created == 1
        assert path.hop_refs() == [("strand", self.s1.pk), ("strand", self.t1.pk)]
        assert path.completeness == "terminated_open"
        assert path.route_key == route_key_for([self.cable.pk, self.other_cable.pk])
        assert (path.end_a_kind, path.end_b_kind, path.end_b_reason) == ("terminated", "open", "cable_end")
        assert path.computed_at == self.now

    def test_identical_hops_only_bump_computed_at(self):
        path = self.store(strand_chain(self.s1, self.s2))
        hop_pks = list(path.hops.values_list("pk", flat=True))
        stats = write_results([strand_chain(self.s1, self.s2)], self.stored(), computed_at=self.now)
        path.refresh_from_db()
        assert (stats.paths_updated, stats.paths_created, stats.paths_deleted) == (0, 0, 0)
        assert path.computed_at == self.now
        assert list(path.hops.values_list("pk", flat=True)) == hop_pks

    def test_reversed_chain_is_oriented_to_the_stored_path_and_not_rewritten(self):
        path = self.store(strand_chain(self.s1, self.s2, self.s3))
        hop_pks = list(path.hops.values_list("pk", flat=True))
        stats = write_results([strand_chain(self.s3, self.s2, self.s1)], self.stored(), computed_at=self.now)
        assert stats.paths_updated == 0
        assert list(path.hops.values_list("pk", flat=True)) == hop_pks

    def test_changed_hops_are_rewritten_in_place(self):
        path = self.store(strand_chain(self.s1, self.s2))
        old_hop_pks = set(path.hops.values_list("pk", flat=True))
        stats = write_results(
            [strand_chain(self.s1, self.s2, self.t1, end_b=TERMINATED)], self.stored(), computed_at=self.now
        )
        path.refresh_from_db()
        assert stats.paths_updated == 1
        assert path.hop_refs() == [("strand", self.s1.pk), ("strand", self.s2.pk), ("strand", self.t1.pk)]
        assert set(path.hops.values_list("pk", flat=True)).isdisjoint(old_hop_pks)
        assert path.completeness == "terminated_open"
        assert path.end_b_kind == "terminated"

    def test_extension_at_the_a_end_rewrites_the_existing_path(self):
        path = self.store(strand_chain(self.s2, self.s3))
        stats = write_results([strand_chain(self.s1, self.s2, self.s3)], self.stored(), computed_at=self.now)
        assert (stats.paths_updated, stats.paths_created, stats.paths_deleted) == (1, 0, 0)
        assert FiberStrandPath.objects.get().pk == path.pk

    def test_cut_keeps_the_chain_holding_the_old_first_strand(self):
        path = self.store(strand_chain(self.s1, self.s2, self.s3))
        stats = write_results(
            [strand_chain(self.s3), strand_chain(self.s1, self.s2)], self.stored(), computed_at=self.now
        )
        assert (stats.paths_updated, stats.paths_created) == (1, 1)
        path.refresh_from_db()
        assert path.hop_refs() == [("strand", self.s1.pk), ("strand", self.s2.pk)]
        new_path = FiberStrandPath.objects.exclude(pk=path.pk).get()
        assert new_path.hop_refs() == [("strand", self.s3.pk)]

    def test_cut_whose_old_first_strand_is_in_no_chain_keeps_the_first_chain(self):
        path = self.store(strand_chain(self.s1, self.s2, self.s3))
        write_results([strand_chain(self.s2), strand_chain(self.s3)], self.stored(), computed_at=self.now)
        path.refresh_from_db()
        assert path.hop_refs() == [("strand", self.s2.pk)]
        assert FiberStrandPath.objects.count() == 2

    def test_stored_path_without_hops_is_lost(self):
        path = self.store(strand_chain(self.s1))
        FiberStrand.objects.filter(pk=self.s1.pk).delete()  # cascades the hop away
        stats = write_results([], self.stored(), computed_at=self.now)
        assert stats.paths_deleted == 1
        assert not FiberStrandPath.objects.filter(pk=path.pk).exists()

    def test_path_with_every_strand_gone_is_deleted(self):
        self.store(strand_chain(self.s1))
        stats = write_results([], self.stored(), computed_at=self.now)
        assert stats.paths_deleted == 1
        assert not FiberStrandPath.objects.exists()

    def test_strandless_chain_matches_on_first_or_last_hop(self):
        plain = Chain(
            [("cable", self.cable.pk), ("cable", self.other_cable.pk)],
            TERMINATED,
            TERMINATED,
            [self.cable.pk, self.other_cable.pk],
        )
        path = self.store(plain)
        stats = write_results([plain.reversed()], self.stored(), computed_at=self.now)
        assert (stats.paths_updated, stats.paths_created, stats.paths_deleted) == (0, 0, 0)
        assert FiberStrandPath.objects.get().pk == path.pk

    def test_identical_chains_for_one_path_are_stored_once(self):
        path = self.store(strand_chain(self.s1, self.s2))
        stats = write_results(
            [strand_chain(self.s1, self.s2), strand_chain(self.s1, self.s2)], self.stored(), computed_at=self.now
        )
        assert (stats.paths_updated, stats.paths_created, stats.paths_deleted) == (0, 0, 0)
        assert FiberStrandPath.objects.get().pk == path.pk

    def test_summary_names_every_counter(self):
        stats = write_results([strand_chain(self.s1)], self.stored(), computed_at=self.now)
        assert stats.summary() == (
            "devices=0 paths_created=1 paths_updated=0 paths_deleted=0 assignments_broken=0 assignments_authorized=0"
        )


class TestAnomalyRows(WriterCase):
    def test_rows_of_the_analyzed_area_are_replaced_and_others_kept(self):
        pair = make_closure_pair("WRA")
        fct = self.fc.fiber_cable_type
        fc, _ = create_closure_cable(device_a=pair.dev_a, device_b=pair.dev_b, fiber_cable_type=fct)
        landed = fc.fiber_strands.order_by("position").first()
        replace_anomalies(
            [
                Anomaly(PathAnomalyKindChoices.LOOP, strand_id=landed.pk),
                Anomaly(PathAnomalyKindChoices.LOOP, strand_id=self.s1.pk),
            ]
        )
        assert PathAnomaly.objects.count() == 2
        replace_anomalies(
            [Anomaly(PathAnomalyKindChoices.DANGLING_REFERENCE, front_port_id=landed.front_port_a_id)],
            device_ids=[pair.dev_a.pk],
        )
        assert sorted(PathAnomaly.objects.values_list("kind", "strand_id", "front_port_id"), key=repr) == sorted(
            [("loop", self.s1.pk, None), ("dangling_reference", None, landed.front_port_a_id)], key=repr
        )
        replace_anomalies([])
        assert not PathAnomaly.objects.exists()


class TestPathDeviceLookups(WriterCase):
    def test_paths_are_found_through_strand_ports_cable_terminations_and_end_ports(self):
        pair = make_closure_pair("WRL")
        fct = self.fc.fiber_cable_type
        fc, _ = create_closure_cable(device_a=pair.dev_a, device_b=pair.dev_b, fiber_cable_type=fct)
        landed = fc.fiber_strands.order_by("position").first()
        by_strand = self.store(strand_chain(landed))
        plain_cable = Cable.objects.create(
            a_terminations=[RearPort.objects.create(device=pair.dev_a, name="WRL-RP", type="splice", positions=2)]
        )
        by_cable = self.store(Chain([("cable", plain_cable.pk)], OPEN, OPEN, [plain_cable.pk]))
        by_end = self.store(
            Chain([("strand", self.s1.pk)], ChainEnd(landed.front_port_b_id, "terminated"), OPEN, [self.cable.pk])
        )
        assert path_ids_through_devices([pair.dev_a.pk]) == {by_strand.pk, by_cable.pk}
        assert path_ids_through_devices([pair.dev_b.pk]) == {by_strand.pk, by_end.pk}
        assert path_ids_through_devices([]) == set()
        assert device_ids_on_paths() == {pair.dev_a.pk, pair.dev_b.pk}
        assert device_ids_on_paths([pair.dev_b.pk, 999_999]) == {pair.dev_b.pk}


class TestAnalysisLock(WriterCase):
    def test_lock_is_granted_and_reentrant_within_one_transaction(self):
        assert try_analysis_lock() is True
        assert try_analysis_lock() is True
