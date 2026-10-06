from dcim.models import Cable
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from netbox_fms.choices import AssignmentBrokenReasonChoices, FiberCircuitStatusChoices
from netbox_fms.models import FiberCable, FiberCableType, FiberCircuit, FiberCircuitPath
from netbox_fms.services import create_closure_cable
from netbox_fms.tables import FiberCableTable
from tests.conftest import assign_strand_path, make_closure_pair, make_infra, make_strand_path


class TestFiberCircuitStatusChoices(TestCase):
    def test_has_planned(self):
        assert FiberCircuitStatusChoices.PLANNED == "planned"

    def test_has_staged(self):
        assert FiberCircuitStatusChoices.STAGED == "staged"

    def test_has_active(self):
        assert FiberCircuitStatusChoices.ACTIVE == "active"

    def test_has_decommissioned(self):
        assert FiberCircuitStatusChoices.DECOMMISSIONED == "decommissioned"


class TestFiberCircuit(TestCase):
    def test_create_circuit(self):
        circuit = FiberCircuit.objects.create(
            name="DT-CTR-1",
            status=FiberCircuitStatusChoices.PLANNED,
            strand_count=2,
        )
        assert circuit.pk is not None
        assert str(circuit) == "DT-CTR-1"

    def test_optional_fields(self):
        circuit = FiberCircuit.objects.create(
            name="DT-CTR-2",
            status=FiberCircuitStatusChoices.ACTIVE,
            strand_count=12,
            cid="CARRIER-12345",
            description="Downtown to Central ribbon",
        )
        assert circuit.cid == "CARRIER-12345"
        assert circuit.description == "Downtown to Central ribbon"

    def test_get_absolute_url(self):
        circuit = FiberCircuit.objects.create(
            name="URL-Test",
            status=FiberCircuitStatusChoices.PLANNED,
            strand_count=1,
        )
        assert "/fiber-circuits/" in circuit.get_absolute_url()

    def test_default_status(self):
        circuit = FiberCircuit.objects.create(
            name="Default-Status",
            strand_count=2,
        )
        assert circuit.status == FiberCircuitStatusChoices.PLANNED


class TestFiberCircuitPath(TestCase):
    """The assignment: one circuit, one analyzed path, a hop snapshot."""

    @classmethod
    def setUpTestData(cls):
        cls.circuit = FiberCircuit.objects.create(
            name="Path-Test", status=FiberCircuitStatusChoices.ACTIVE, strand_count=2
        )
        _site, mfr, _dt, _role = make_infra("PathTest")
        fct = FiberCableType.objects.create(manufacturer=mfr, model="PT-3", strand_count=3, construction="tight_buffer")
        fc = FiberCable.objects.create(cable=Cable.objects.create(), fiber_cable_type=fct)
        cls.s1, cls.s2, cls.s3 = list(fc.fiber_strands.order_by("position"))
        cls.p1, cls.p2, cls.p3 = (make_strand_path(s) for s in (cls.s1, cls.s2, cls.s3))

    def test_assignment_snapshots_the_hops_it_was_made_with(self):
        assignment = assign_strand_path(self.circuit, self.p1)
        assert assignment.assigned_hops == [{"type": "strand", "id": self.s1.pk}]
        assert assignment.active is True and assignment.is_broken is False
        assert str(assignment) == f"{self.circuit} path 1"

    def test_unique_position_per_circuit(self):
        assign_strand_path(self.circuit, self.p1, position=1)
        with self.assertRaises(IntegrityError):
            assign_strand_path(self.circuit, self.p2, position=1)

    def test_one_active_assignment_per_path(self):
        assign_strand_path(self.circuit, self.p1)
        other = FiberCircuit.objects.create(name="Other", strand_count=1)
        with self.assertRaises(IntegrityError):
            assign_strand_path(other, self.p1)

    def test_an_inactive_assignment_does_not_hold_the_path(self):
        assign_strand_path(self.circuit, self.p1, active=False)
        other = FiberCircuit.objects.create(name="Other-2", strand_count=1)
        assert assign_strand_path(other, self.p1).pk

    def test_wavelength_required_when_actual_loss_set(self):
        assignment = FiberCircuitPath(circuit=self.circuit, strand_path=self.p1, position=1, actual_loss_db=3.5)
        with self.assertRaises(ValidationError):
            assignment.full_clean()

    def test_strand_count_counts_active_assignments_only(self):
        small = FiberCircuit.objects.create(name="Small", strand_count=1)
        assign_strand_path(small, self.p1, active=False)
        FiberCircuitPath(circuit=small, strand_path=self.p2, position=2).clean()  # inactive one does not count
        assign_strand_path(small, self.p3)
        with self.assertRaises(ValidationError):
            FiberCircuitPath(circuit=small, strand_path=self.p2, position=3).clean()

    def test_get_absolute_url(self):
        assignment = assign_strand_path(self.circuit, self.p1)
        assert assignment.get_absolute_url() == f"/plugins/fms/fiber-circuit-paths/{assignment.pk}/"
        assert self.p1.get_absolute_url() == f"/plugins/fms/fiber-paths/{self.p1.pk}/"


class TestFiberCircuitStatusTransitions(TestCase):
    @classmethod
    def setUpTestData(cls):
        _site, mfr, _dt, _role = make_infra("Trans")
        fct = FiberCableType.objects.create(manufacturer=mfr, model="TR-1", strand_count=1, construction="tight_buffer")
        fc = FiberCable.objects.create(cable=Cable.objects.create(), fiber_cable_type=fct)
        cls.path = make_strand_path(fc.fiber_strands.get())

    def test_decommissioning_deactivates_and_reactivating_restores(self):
        circuit = FiberCircuit.objects.create(name="Trans-C", strand_count=1, status=FiberCircuitStatusChoices.ACTIVE)
        assignment = assign_strand_path(circuit, self.path)
        circuit.status = FiberCircuitStatusChoices.DECOMMISSIONED
        circuit.save()
        assignment.refresh_from_db()
        assert assignment.active is False
        circuit.status = FiberCircuitStatusChoices.ACTIVE
        circuit.save()
        assignment.refresh_from_db()
        assert assignment.active is True

    def test_a_save_without_status_change_touches_no_assignment(self):
        circuit = FiberCircuit.objects.create(name="Trans-D", strand_count=1, status=FiberCircuitStatusChoices.ACTIVE)
        assignment = assign_strand_path(circuit, self.path, active=False)
        circuit.description = "renamed"
        circuit.save()
        assignment.refresh_from_db()
        assert assignment.active is False


class TestAssignmentPages(TestCase):
    """The circuit, assignment, fiber-path and cable pages render the assignment state."""

    @classmethod
    def setUpTestData(cls):
        pair = make_closure_pair("Pages")
        fct = FiberCableType.objects.create(
            manufacturer=pair.mfr, model="PG-2", strand_count=2, construction="tight_buffer"
        )
        cls.fc, _ = create_closure_cable(device_a=pair.dev_a, device_b=pair.dev_b, fiber_cable_type=fct)
        cls.s1, cls.s2 = list(cls.fc.fiber_strands.order_by("position"))
        cls.circuit = FiberCircuit.objects.create(
            name="Pages-C", strand_count=2, status=FiberCircuitStatusChoices.ACTIVE
        )
        cls.healthy = assign_strand_path(
            cls.circuit, make_strand_path(cls.s1, end_a=cls.s1.front_port_a, end_b=cls.s1.front_port_b)
        )
        cls.broken = assign_strand_path(
            cls.circuit,
            make_strand_path(cls.s2),
            is_broken=True,
            broken_reason=AssignmentBrokenReasonChoices.HOPS_CHANGED,
        )
        cls.user = get_user_model().objects.create_superuser(username="pages-admin", password="x")  # noqa: S106

    def setUp(self):
        self.client.force_login(self.user)

    def test_circuit_page_lists_assignments_with_their_status(self):
        html = self.client.get(self.circuit.get_absolute_url()).content.decode()
        assert "Healthy" in html and "Broken" in html
        assert self.healthy.strand_path.get_absolute_url() in html
        assert self.s1.front_port_a.name in html

    def test_assignment_page_shows_the_hop_snapshot_size(self):
        html = self.client.get(self.broken.get_absolute_url()).content.decode()
        assert "Hops changed" in html
        assert "<td>1</td>" in html  # one assigned hop

    def test_fiber_path_pages_render_hops_and_assignments(self):
        detail = self.client.get(self.healthy.strand_path.get_absolute_url()).content.decode()
        assert self.circuit.get_absolute_url() in detail
        assert self.fc.cable.get_absolute_url() in detail
        listing = self.client.get("/plugins/fms/fiber-paths/").content.decode()
        assert self.broken.strand_path.get_absolute_url() in listing

    def test_cable_tab_and_circuit_list_count_assignments(self):
        tab = self.client.get(f"/dcim/cables/{self.fc.cable.pk}/fiber-circuits/").content.decode()
        assert tab.count(self.circuit.get_absolute_url()) >= 2  # both assignments cross the cable
        listing = self.client.get("/plugins/fms/fiber-circuits/").content.decode()
        assert self.circuit.get_absolute_url() in listing

    def test_fiber_cable_strand_utilization_counts_actively_assigned_strands(self):
        self.broken.active = False
        self.broken.save()
        html = self.client.get(self.fc.get_absolute_url()).content.decode()
        assert 'title="1 Active"' in html
        assert FiberCableTable(FiberCable.objects.filter(pk=self.fc.pk)).render_strand_utilization(self.fc) == "1/2"
