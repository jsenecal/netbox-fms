from dcim.models import Cable, PortMapping
from django.contrib.auth import get_user_model
from django.test import TestCase

from netbox_fms.choices import FiberCircuitStatusChoices, SplicePlanStatusChoices
from netbox_fms.models import FiberCable, FiberCableType, FiberCircuit, SplicePlan, SplicePlanEntry
from netbox_fms.services import create_closure_cable, protecting_assignments, protecting_circuits_by_front_port
from tests.conftest import (
    assign_strand_path,
    make_authed_client,
    make_closure_pair,
    make_infra,
    make_provider_circuit,
    make_strand_path,
    make_tray_module,
    make_tray_type,
)


class TestProviderCircuitProjection(TestCase):
    """provider_circuits mirrors the provider-circuit hops of active assignments (issue #135)."""

    @classmethod
    def setUpTestData(cls):
        span = make_provider_circuit("Proj")
        cls.span = span
        _site, mfr, _dt, _role = make_infra("Proj")
        fct = FiberCableType.objects.create(manufacturer=mfr, model="PJ-1", strand_count=1, construction="tight_buffer")
        fc = FiberCable.objects.create(cable=Cable.objects.create(), fiber_cable_type=fct)
        cls.path = make_strand_path(
            fc.fiber_strands.get(), Cable.objects.create(), span.circuit, Cable.objects.create()
        )
        cls.fc = FiberCircuit.objects.create(name="Proj-FC", status=FiberCircuitStatusChoices.ACTIVE, strand_count=1)

    def test_sync_populates_from_the_hops(self):
        assign_strand_path(self.fc, self.path)
        self.fc.sync_provider_circuits()
        assert list(self.fc.provider_circuits.all()) == [self.span.circuit]

    def test_decommission_empties_and_reactivation_repopulates(self):
        assign_strand_path(self.fc, self.path)
        self.fc.status = FiberCircuitStatusChoices.DECOMMISSIONED
        self.fc.save()
        assert self.fc.provider_circuits.count() == 0
        self.fc.status = FiberCircuitStatusChoices.ACTIVE
        self.fc.save()
        assert list(self.fc.provider_circuits.all()) == [self.span.circuit]

    def test_unassigning_resyncs_the_projection(self):
        assignment = assign_strand_path(self.fc, self.path)
        self.fc.sync_provider_circuits()
        assignment.delete()
        assert self.fc.provider_circuits.count() == 0


class TestProtectionLookups(TestCase):
    """Every reference type the protecting endpoint accepts resolves to the assignment that carries it.

    Rear ports and splice entries are not stored hops; they protect through
    the front ports the assigned strands land on.
    """

    @classmethod
    def setUpTestData(cls):
        pair = make_closure_pair("PL")
        fct = FiberCableType.objects.create(
            manufacturer=pair.mfr, model="PL-2", strand_count=2, construction="tight_buffer"
        )
        fc, _ = create_closure_cable(device_a=pair.dev_a, device_b=pair.dev_b, fiber_cable_type=fct)
        cls.s1, cls.s2 = list(fc.fiber_strands.order_by("position"))
        plan = SplicePlan.objects.create(closure=pair.dev_b, name="PL plan", status=SplicePlanStatusChoices.ARCHIVED)
        tray = make_tray_module(pair.dev_b, make_tray_type(pair.mfr, "PL Tray"), "Bay 1")
        cls.entry = SplicePlanEntry.objects.create(
            plan=plan, tray=tray, fiber_a=cls.s1.front_port_b, fiber_b=cls.s2.front_port_b
        )
        cls.rear_port = PortMapping.objects.get(front_port=cls.s1.front_port_a).rear_port
        cls.circuit = FiberCircuit.objects.create(name="PL-C", status=FiberCircuitStatusChoices.ACTIVE, strand_count=1)
        cls.assignment = assign_strand_path(cls.circuit, make_strand_path(cls.s1, end_a=cls.s1.front_port_a))
        gone = FiberCircuit.objects.create(
            name="PL-gone", status=FiberCircuitStatusChoices.DECOMMISSIONED, strand_count=1
        )
        assign_strand_path(gone, make_strand_path(cls.s2), active=False)

    def test_each_reference_type_resolves_through_the_assignment(self):
        for reference, ref_id in (
            ("fiber_strand", self.s1.pk),
            ("cable", self.s1.fiber_cable.cable_id),
            ("front_port", self.s1.front_port_b_id),
            ("rear_port", self.rear_port.pk),
            ("splice_entry", self.entry.pk),
        ):
            found = list(protecting_assignments(reference, [ref_id]))
            assert found == [self.assignment], reference

    def test_inactive_and_decommissioned_assignments_protect_nothing(self):
        assert list(protecting_assignments("fiber_strand", [self.s2.pk])) == []
        assert protecting_circuits_by_front_port([self.s2.front_port_a_id, self.s2.front_port_b_id]) == {}
        assert protecting_circuits_by_front_port([]) == {}

    def test_applying_a_plan_over_protected_fibers_is_refused(self):
        client = make_authed_client("pl-apply")
        resp = client.post(f"/api/plugins/fms/splice-plans/{self.entry.plan_id}/apply/", format="json")
        assert resp.status_code == 409, resp.content
        assert "PL-C" in resp.json()["error"]

    def test_front_port_lookup_names_the_circuit_and_honours_the_user(self):
        by_port = protecting_circuits_by_front_port([self.s1.front_port_a_id, self.s1.front_port_b_id])
        assert by_port == {self.s1.front_port_a_id: self.circuit, self.s1.front_port_b_id: self.circuit}
        nobody = get_user_model().objects.create_user(username="pl-nobody", password="x")  # noqa: S106
        assert protecting_circuits_by_front_port([self.s1.front_port_a_id], user=nobody) == {}
