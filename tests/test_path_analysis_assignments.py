"""Assignment evaluation inside the writer (#196 spec section 2, "Evaluating assignments")."""

from dcim.models import Cable
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from netbox_fms.assignment import authorize_route_change
from netbox_fms.choices import AssignmentBrokenReasonChoices, FiberCircuitStatusChoices, PathEndKindChoices
from netbox_fms.models import FiberCable, FiberCableType, FiberCircuit, FiberStrandPath, RouteChangeAuthorization
from netbox_fms.path_analysis import write_results
from netbox_fms.path_graph import Chain, ChainEnd
from tests.conftest import assign_strand_path, changes_logged, make_infra, make_strand_path

OPEN = ChainEnd(None, PathEndKindChoices.OPEN, "cable_end")


def chain(*strands):
    return Chain([("strand", s.pk) for s in strands], OPEN, OPEN, [s.fiber_cable.cable_id for s in strands])


class EvaluationCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        _site, mfr, _dt, _role = make_infra("EVA")
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="EVA-4", strand_count=4, construction="tight_buffer"
        )
        fc = FiberCable.objects.create(cable=Cable.objects.create(), fiber_cable_type=fct)
        cls.s1, cls.s2, cls.s3, cls.s4 = list(fc.fiber_strands.order_by("position"))
        cls.circuit = FiberCircuit.objects.create(name="EVA-C", strand_count=2, status=FiberCircuitStatusChoices.ACTIVE)

    def analyze(self, *chains):
        return write_results(list(chains), FiberStrandPath.objects.prefetch_related("hops"), computed_at=timezone.now())

    def assigned(self, *strands, **fields):
        path = make_strand_path(*strands)
        return assign_strand_path(self.circuit, path, **fields), path


class TestBroken(EvaluationCase):
    def test_any_hop_change_breaks_the_assignment_and_flags_the_circuit_once(self):
        assignment, _path = self.assigned(self.s1, self.s2)
        logged = changes_logged(lambda: self.analyze(chain(self.s1, self.s2, self.s3)))
        assert logged[("fibercircuit", "update")] == 1
        assert logged[("fibercircuitpath", "update")] == 1
        stats = self.analyze(
            chain(self.s1, self.s2, self.s3)
        )  # the rollback in changes_logged undid it; do it for real
        assignment.refresh_from_db()
        self.circuit.refresh_from_db()
        assert (assignment.is_broken, assignment.broken_reason) == (True, AssignmentBrokenReasonChoices.HOPS_CHANGED)
        assert self.circuit.is_broken is True
        assert stats.assignments_broken == 1

    def test_an_unchanged_circuit_logs_nothing(self):
        self.assigned(self.s1)
        assert changes_logged(lambda: self.analyze(chain(self.s1))) == {}

    def test_lost_path_is_kept_without_hops_and_marked_path_lost(self):
        assignment, path = self.assigned(self.s1)
        stats = self.analyze()
        assignment.refresh_from_db()
        path.refresh_from_db()
        assert path.hop_refs() == []
        assert (assignment.is_broken, assignment.broken_reason) == (True, AssignmentBrokenReasonChoices.PATH_LOST)
        assert stats.paths_deleted == 0

    def test_lost_path_with_only_an_inactive_assignment_is_kept_silently(self):
        assignment, path = self.assigned(self.s1, active=False)
        self.analyze()
        assignment.refresh_from_db()
        assert FiberStrandPath.objects.filter(pk=path.pk).exists()
        assert assignment.is_broken is False

    def test_a_long_lost_assignment_is_not_reported_broken_again(self):
        self.assigned(self.s1)
        self.analyze()
        seen = []
        logged = changes_logged(lambda: seen.append(self.analyze()))
        assert seen[0].assignments_broken == 0
        assert ("fibercircuitpath", "update") not in logged

    def test_reverted_hops_heal_a_broken_assignment(self):
        assignment, _path = self.assigned(self.s1, self.s2)
        self.analyze(chain(self.s1, self.s2, self.s3))
        self.analyze(chain(self.s1, self.s2))
        assignment.refresh_from_db()
        self.circuit.refresh_from_db()
        assert (assignment.is_broken, self.circuit.is_broken) == (False, False)


class TestAuthorization(EvaluationCase):
    def test_authorized_change_with_the_same_end_strands_stays_healthy(self):
        assignment, _path = self.assigned(self.s1, self.s3)
        authorize_route_change(self.circuit, self.circuit)
        stats = self.analyze(chain(self.s1, self.s2, self.s3))
        assignment.refresh_from_db()
        assert assignment.is_broken is False
        assert assignment.assigned_hops == [{"type": "strand", "id": s.pk} for s in (self.s1, self.s2, self.s3)]
        assert not RouteChangeAuthorization.objects.exists()
        assert stats.assignments_authorized == 1

    def test_authorization_does_not_cover_a_changed_end_strand(self):
        assignment, _path = self.assigned(self.s1, self.s2)
        authorize_route_change(self.circuit, self.circuit)
        self.analyze(chain(self.s1, self.s3))
        assignment.refresh_from_db()
        assert assignment.is_broken is True
        assert RouteChangeAuthorization.objects.filter(circuit=self.circuit).exists()

    def test_another_circuits_authorization_does_not_cover_this_circuit(self):
        assignment, _path = self.assigned(self.s1, self.s3)
        other = FiberCircuit.objects.create(name="EVA-O", strand_count=1)
        authorize_route_change(other, other)
        self.analyze(chain(self.s1, self.s2, self.s3))
        assignment.refresh_from_db()
        assert assignment.is_broken is True
        assert RouteChangeAuthorization.objects.filter(circuit=other).exists()

    def test_an_unused_authorization_survives_a_run_that_changed_nothing_for_the_circuit(self):
        path = make_strand_path(self.s1, self.s2, end_a_kind=PathEndKindChoices.TERMINATED)
        assignment = assign_strand_path(self.circuit, path)
        authorize_route_change(self.circuit, self.circuit)
        stats = self.analyze(chain(self.s1, self.s2))  # the path is rewritten (its end differs), its hops are not
        assignment.refresh_from_db()
        assert (assignment.is_broken, stats.assignments_authorized) == (False, 0)
        assert RouteChangeAuthorization.objects.filter(circuit=self.circuit).exists()

    def test_one_authorization_covers_every_assignment_of_the_circuit(self):
        first, _p1 = self.assigned(self.s1, self.s3)
        second, _p2 = self.assigned(self.s2, self.s4)
        authorize_route_change(self.circuit, self.circuit)
        extra = FiberCable.objects.create(
            cable=Cable.objects.create(), fiber_cable_type=self.s1.fiber_cable.fiber_cable_type
        )
        x1, x2 = list(extra.fiber_strands.order_by("position"))[:2]
        self.analyze(chain(self.s1, x1, self.s3), chain(self.s2, x2, self.s4))
        first.refresh_from_db()
        second.refresh_from_db()
        assert (first.is_broken, second.is_broken) == (False, False)


class TestReactivation(EvaluationCase):
    def test_reactivating_onto_a_path_assigned_elsewhere_is_refused_before_saving(self):
        """Review focus: the status stays decommissioned and both assignments survive."""
        assignment, path = self.assigned(self.s1)
        self.circuit.status = FiberCircuitStatusChoices.DECOMMISSIONED
        self.circuit.save()
        other = FiberCircuit.objects.create(name="EVA-O", strand_count=1, status=FiberCircuitStatusChoices.ACTIVE)
        theirs = assign_strand_path(other, path)
        self.circuit.status = FiberCircuitStatusChoices.ACTIVE
        with self.assertRaises(ValidationError):
            self.circuit.save()
        self.circuit.refresh_from_db()
        assert self.circuit.status == FiberCircuitStatusChoices.DECOMMISSIONED
        assignment.refresh_from_db()
        theirs.refresh_from_db()
        assert (assignment.active, theirs.active) == (False, True)

    def test_reactivation_re_evaluates_against_the_current_hops(self):
        assignment, _path = self.assigned(self.s1)
        self.circuit.status = FiberCircuitStatusChoices.DECOMMISSIONED
        self.circuit.save()
        self.analyze(chain(self.s1, self.s2))  # the inactive assignment is not evaluated now
        assignment.refresh_from_db()
        assert assignment.is_broken is False
        self.circuit.status = FiberCircuitStatusChoices.ACTIVE
        self.circuit.save()
        assignment.refresh_from_db()
        assert (assignment.active, assignment.is_broken) == (True, True)
        assert self.circuit.is_broken is True  # the caller's instance is not left stale
