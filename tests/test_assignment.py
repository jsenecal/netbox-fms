"""assign_paths / acknowledge_route / authorize_route_change (#196 spec section 3)."""

from dcim.models import Cable, Device
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from netbox_fms.assignment import acknowledge_route, assign_paths, authorize_route_change
from netbox_fms.choices import AssignmentBrokenReasonChoices, FiberCircuitStatusChoices
from netbox_fms.models import FiberCable, FiberCableType, FiberCircuit, FiberCircuitPath, RouteChangeAuthorization
from tests.conftest import assign_strand_path, make_front_port, make_infra, make_provider_circuit, make_strand_path


class AssignCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = make_infra("ASG")
        device = Device.objects.create(name="ASG-Dev", site=site, device_type=dt, role=role)
        cls.fp_a, cls.fp_b = make_front_port(device, "ASG-A"), make_front_port(device, "ASG-B")
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="ASG-4", strand_count=4, construction="tight_buffer"
        )
        fc = FiberCable.objects.create(cable=Cable.objects.create(), fiber_cable_type=fct)
        cls.s1, cls.s2, cls.s3, cls.s4 = list(fc.fiber_strands.order_by("position"))
        cls.complete = [make_strand_path(s, end_a=cls.fp_a, end_b=cls.fp_b) for s in (cls.s1, cls.s2, cls.s3)]
        cls.incomplete = make_strand_path(cls.s4, end_a=cls.fp_a)
        cls.circuit = FiberCircuit.objects.create(name="ASG-C", strand_count=2, status=FiberCircuitStatusChoices.ACTIVE)


class TestAssignPaths(AssignCase):
    def test_assigns_with_positions_snapshots_and_projection(self):
        span = make_provider_circuit("ASG")
        riding = make_strand_path(
            self.s1, Cable.objects.create(), span.circuit, Cable.objects.create(), end_a=self.fp_a, end_b=self.fp_b
        )
        first, second = assign_paths(self.circuit, [riding, self.complete[1]])
        assert (first.position, second.position) == (1, 2)
        assert first.assigned_hops == [{"type": h[0], "id": h[1]} for h in riding.hop_refs()]
        assert (first.delivered_incomplete, first.is_broken, first.active) == (False, False, True)
        assert list(self.circuit.provider_circuits.all()) == [span.circuit]

    def test_positions_continue_after_existing_assignments(self):
        assign_strand_path(self.circuit, self.complete[0], position=5)
        (assignment,) = assign_paths(self.circuit, [self.complete[1]])
        assert assignment.position == 6

    def test_strand_count_limit_rejects_the_whole_call(self):
        with self.assertRaises(ValidationError) as ctx:
            assign_paths(self.circuit, self.complete)
        assert "strand count (2)" in str(ctx.exception)
        assert not FiberCircuitPath.objects.exists()

    def test_a_path_with_an_active_assignment_elsewhere_is_refused(self):
        other = FiberCircuit.objects.create(name="ASG-O", strand_count=1)
        assign_strand_path(other, self.complete[0])
        with self.assertRaises(ValidationError) as ctx:
            assign_paths(self.circuit, [self.complete[0]])
        assert "already assigned" in str(ctx.exception)

    def test_incomplete_paths_need_explicit_permission(self):
        with self.assertRaises(ValidationError) as ctx:
            assign_paths(self.circuit, [self.incomplete])
        assert "not terminated at both ends" in str(ctx.exception)
        (assignment,) = assign_paths(self.circuit, [self.incomplete], allow_incomplete=True)
        assert assignment.delivered_incomplete is True

    def test_a_path_whose_other_assignment_is_inactive_can_be_assigned(self):
        gone = FiberCircuit.objects.create(
            name="ASG-G", strand_count=1, status=FiberCircuitStatusChoices.DECOMMISSIONED
        )
        assign_strand_path(gone, self.complete[0], active=False)
        (assignment,) = assign_paths(self.circuit, [self.complete[0]])
        assert assignment.active is True

    def test_duplicate_path_in_one_call_is_refused(self):
        with self.assertRaises(ValidationError) as ctx:
            assign_paths(self.circuit, [self.complete[0], self.complete[0]])
        assert "more than once" in str(ctx.exception)

    def test_candidate_paths_are_locked_before_the_exclusivity_check(self):
        """Two circuits racing for one path must queue on its row instead of colliding on the unique index."""
        with CaptureQueriesContext(connection) as queries:
            assign_paths(self.circuit, self.complete[:1])
        sql = [q["sql"] for q in queries]
        lock = next((i for i, q in enumerate(sql) if "FOR UPDATE" in q and '"netbox_fms_fiberstrandpath"' in q), None)
        exclusivity = next(
            i for i, q in enumerate(sql) if q.startswith("SELECT") and '"netbox_fms_fibercircuitpath"' in q
        )
        assert lock is not None and lock < exclusivity, sql

    def test_decommissioned_circuit_takes_no_assignment(self):
        self.circuit.status = FiberCircuitStatusChoices.DECOMMISSIONED
        self.circuit.save()
        with self.assertRaises(ValidationError) as ctx:
            assign_paths(self.circuit, [self.complete[0]])
        assert "decommissioned" in str(ctx.exception)


class TestAcknowledgeAndAuthorize(AssignCase):
    def test_acknowledge_accepts_the_current_hops_and_clears_the_flags(self):
        assignment = assign_strand_path(
            self.circuit,
            self.complete[0],
            assigned_hops=[],
            is_broken=True,
            broken_reason=AssignmentBrokenReasonChoices.HOPS_CHANGED,
        )
        FiberCircuit.objects.filter(pk=self.circuit.pk).update(is_broken=True)
        self.circuit.refresh_from_db()
        assert acknowledge_route(self.circuit) == 1
        assignment.refresh_from_db()
        self.circuit.refresh_from_db()
        assert assignment.assigned_hops == [{"type": "strand", "id": self.s1.pk}]
        assert (assignment.is_broken, assignment.broken_reason, self.circuit.is_broken) == (False, "", False)

    def test_acknowledge_leaves_a_path_lost_assignment_broken(self):
        """A hop-less path has nothing to accept; healing it would leave a circuit with no fiber under it."""
        assign_strand_path(
            self.circuit, self.complete[0], assigned_hops=[], is_broken=True, broken_reason="hops_changed"
        )
        lost_hops = [{"type": "strand", "id": self.s4.pk}]
        lost = assign_strand_path(
            self.circuit,
            make_strand_path(),
            assigned_hops=lost_hops,
            is_broken=True,
            broken_reason=AssignmentBrokenReasonChoices.PATH_LOST,
        )
        FiberCircuit.objects.filter(pk=self.circuit.pk).update(is_broken=True)
        self.circuit.refresh_from_db()
        assert acknowledge_route(self.circuit) == 1
        lost.refresh_from_db()
        self.circuit.refresh_from_db()
        assert (lost.is_broken, lost.broken_reason, lost.assigned_hops) == (True, "path_lost", lost_hops)
        assert self.circuit.is_broken is True

    def test_acknowledge_is_a_no_op_without_broken_assignments(self):
        assign_strand_path(self.circuit, self.complete[0])
        assert acknowledge_route(self.circuit) == 0

    def test_authorize_records_the_source(self):
        authorization = authorize_route_change(self.circuit, self.fp_a)
        assert RouteChangeAuthorization.objects.get(pk=authorization.pk).source == self.fp_a
        assert authorization.circuit == self.circuit
