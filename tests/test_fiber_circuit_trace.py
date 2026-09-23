"""Tests for the fiber circuit trace engine.

Uses PortMapping model (NOT FrontPort.rear_port FK which doesn't exist in NetBox 4.5+).
"""

from dcim.models import Cable, CableTermination, FrontPort, PortMapping, RearPort
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from netbox_fms.choices import SplicePlanStatusChoices
from netbox_fms.models import FiberCircuitPath, SplicePlan, SplicePlanEntry
from tests.conftest import connect_front_ports, make_closure_with_tray


def _make_closure(name):
    """Bare closure Device + tray Module, no pre-made ports."""
    ns = make_closure_with_tray(name, port_count=0)
    return ns.closure, ns.tray


def _connect_cable(cable, rear_port_a, rear_port_b):
    rp_ct = ContentType.objects.get_for_model(RearPort)
    CableTermination.objects.create(cable=cable, cable_end="A", termination_type=rp_ct, termination_id=rear_port_a.pk)
    CableTermination.objects.create(cable=cable, cable_end="B", termination_type=rp_ct, termination_id=rear_port_b.pk)


class TestTraceSingleCable(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dev_a, cls.tray_a = _make_closure("ClosureA")
        cls.dev_b, cls.tray_b = _make_closure("ClosureB")

        cls.rp_a = RearPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="RP-A1", type="lc", positions=1)
        cls.fp_a = FrontPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="FP-A1", type="lc")
        PortMapping.objects.create(
            device=cls.dev_a, front_port=cls.fp_a, rear_port=cls.rp_a, front_port_position=1, rear_port_position=1
        )

        cls.rp_b = RearPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="RP-B1", type="lc", positions=1)
        cls.fp_b = FrontPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="FP-B1", type="lc")
        PortMapping.objects.create(
            device=cls.dev_b, front_port=cls.fp_b, rear_port=cls.rp_b, front_port_position=1, rear_port_position=1
        )

        cls.cable = Cable.objects.create()
        _connect_cable(cls.cable, cls.rp_a, cls.rp_b)

    def test_single_cable_trace(self):
        result = FiberCircuitPath.from_origin(self.fp_a)
        assert result.origin == self.fp_a
        assert result.destination == self.fp_b
        assert result.is_complete is True
        assert len(result.path) == 5  # FP, RP, Cable, RP, FP

    def test_path_json_format(self):
        result = FiberCircuitPath.from_origin(self.fp_a)
        assert result.path[0] == {"type": "front_port", "id": self.fp_a.pk}
        assert result.path[1] == {"type": "rear_port", "id": self.rp_a.pk}
        assert result.path[2] == {"type": "cable", "id": self.cable.pk}
        assert result.path[3] == {"type": "rear_port", "id": self.rp_b.pk}
        assert result.path[4] == {"type": "front_port", "id": self.fp_b.pk}


class TestTraceMultiHop(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dev_a, cls.tray_a = _make_closure("MH-ClosA")
        cls.dev_b, cls.tray_b = _make_closure("MH-ClosB")
        cls.dev_c, cls.tray_c = _make_closure("MH-ClosC")

        cls.rp_a = RearPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="RP-A", type="lc", positions=1)
        cls.fp_a = FrontPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="FP-A", type="lc")
        PortMapping.objects.create(
            device=cls.dev_a, front_port=cls.fp_a, rear_port=cls.rp_a, front_port_position=1, rear_port_position=1
        )

        cls.rp_b1 = RearPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="RP-B1", type="lc", positions=1)
        cls.fp_b1 = FrontPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="FP-B1", type="lc")
        PortMapping.objects.create(
            device=cls.dev_b, front_port=cls.fp_b1, rear_port=cls.rp_b1, front_port_position=1, rear_port_position=1
        )
        cls.rp_b2 = RearPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="RP-B2", type="lc", positions=1)
        cls.fp_b2 = FrontPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="FP-B2", type="lc")
        PortMapping.objects.create(
            device=cls.dev_b, front_port=cls.fp_b2, rear_port=cls.rp_b2, front_port_position=1, rear_port_position=1
        )

        cls.rp_c = RearPort.objects.create(device=cls.dev_c, module=cls.tray_c, name="RP-C", type="lc", positions=1)
        cls.fp_c = FrontPort.objects.create(device=cls.dev_c, module=cls.tray_c, name="FP-C", type="lc")
        PortMapping.objects.create(
            device=cls.dev_c, front_port=cls.fp_c, rear_port=cls.rp_c, front_port_position=1, rear_port_position=1
        )

        cls.cable1 = Cable.objects.create()
        _connect_cable(cls.cable1, cls.rp_a, cls.rp_b1)

        connect_front_ports(cls.fp_b1, cls.fp_b2)
        cls.plan_b = SplicePlan.objects.create(
            closure=cls.dev_b, name="Plan-B", status=SplicePlanStatusChoices.ARCHIVED
        )
        cls.splice_entry = SplicePlanEntry.objects.create(
            plan=cls.plan_b,
            tray=cls.tray_b,
            fiber_a=cls.fp_b1,
            fiber_b=cls.fp_b2,
        )

        cls.cable2 = Cable.objects.create()
        _connect_cable(cls.cable2, cls.rp_b2, cls.rp_c)

    def test_multi_hop_trace(self):
        result = FiberCircuitPath.from_origin(self.fp_a)
        assert result.origin == self.fp_a
        assert result.destination == self.fp_c
        assert result.is_complete is True

    def test_multi_hop_path_length(self):
        result = FiberCircuitPath.from_origin(self.fp_a)
        assert len(result.path) == 11  # FP,RP,Cable,RP,FP,Splice,FP,RP,Cable,RP,FP

    def test_splice_in_path(self):
        result = FiberCircuitPath.from_origin(self.fp_a)
        splice_entries = [e for e in result.path if e["type"] == "splice_entry"]
        assert len(splice_entries) == 1
        assert splice_entries[0]["id"] == self.splice_entry.pk


class TestTraceIncomplete(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dev_a, cls.tray_a = _make_closure("IC-ClosA")
        cls.dev_b, cls.tray_b = _make_closure("IC-ClosB")

        cls.rp_a = RearPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="RP-A", type="lc", positions=1)
        cls.fp_a = FrontPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="FP-A", type="lc")
        PortMapping.objects.create(
            device=cls.dev_a, front_port=cls.fp_a, rear_port=cls.rp_a, front_port_position=1, rear_port_position=1
        )

        cls.rp_b = RearPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="RP-B", type="lc", positions=1)
        cls.fp_b = FrontPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="FP-B", type="lc")
        PortMapping.objects.create(
            device=cls.dev_b, front_port=cls.fp_b, rear_port=cls.rp_b, front_port_position=1, rear_port_position=1
        )

        cls.cable = Cable.objects.create()
        _connect_cable(cls.cable, cls.rp_a, cls.rp_b)

    def test_trace_terminates_with_no_splice(self):
        result = FiberCircuitPath.from_origin(self.fp_a)
        assert result.destination == self.fp_b
        assert result.is_complete is True

    def test_no_port_mapping_incomplete(self):
        dev, tray = _make_closure("NoMap")
        fp = FrontPort.objects.create(device=dev, module=tray, name="OrphanFP", type="lc")
        result = FiberCircuitPath.from_origin(fp)
        assert result.is_complete is False
        assert len(result.path) == 1


class TestTraceProviderCircuit(TestCase):
    """Mid-span provider circuits are crossed as opaque segments (issue #135)."""

    @classmethod
    def setUpTestData(cls):
        from tests.conftest import connect_rp_to_ct, make_provider_circuit

        cls.dev_a, cls.tray_a = _make_closure("PC-ClosA")
        cls.dev_b, cls.tray_b = _make_closure("PC-ClosB")

        cls.rp_a = RearPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="RP-A", type="lc", positions=1)
        cls.fp_a = FrontPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="FP-A", type="lc")
        PortMapping.objects.create(
            device=cls.dev_a, front_port=cls.fp_a, rear_port=cls.rp_a, front_port_position=1, rear_port_position=1
        )
        cls.rp_b = RearPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="RP-B", type="lc", positions=1)
        cls.fp_b = FrontPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="FP-B", type="lc")
        PortMapping.objects.create(
            device=cls.dev_b, front_port=cls.fp_b, rear_port=cls.rp_b, front_port_position=1, rear_port_position=1
        )

        cls.span = make_provider_circuit("PC1")
        cls.cable_a = connect_rp_to_ct(cls.rp_a, cls.span.term_a)
        cls.cable_z = connect_rp_to_ct(cls.rp_b, cls.span.term_z)

    def test_trace_across_provider_circuit(self):
        result = FiberCircuitPath.from_origin(self.fp_a)
        assert result.destination == self.fp_b
        assert result.is_complete is True
        types = [e["type"] for e in result.path]
        assert types == ["front_port", "rear_port", "cable", "provider_circuit", "cable", "rear_port", "front_port"]
        assert {"type": "provider_circuit", "id": self.span.circuit.pk} in result.path

    def test_incomplete_when_far_termination_uncabled(self):
        self.cable_z.delete()
        result = FiberCircuitPath.from_origin(self.fp_a)
        assert result.is_complete is False
        assert result.destination is None
        assert result.path[-1] == {"type": "provider_circuit", "id": self.span.circuit.pk}

    def test_incomplete_when_egress_cable_dangles(self):
        from circuits.models import CircuitTermination

        self.cable_z.delete()
        dangling = Cable.objects.create()
        ct_ct = ContentType.objects.get_for_model(CircuitTermination)
        CableTermination.objects.create(
            cable=dangling, cable_end="A", termination_type=ct_ct, termination_id=self.span.term_z.pk
        )
        result = FiberCircuitPath.from_origin(self.fp_a)
        assert result.is_complete is False
        assert result.path[-1] == {"type": "cable", "id": dangling.pk}

    def test_incomplete_when_no_far_termination(self):
        self.cable_z.delete()
        self.span.term_z.delete()
        result = FiberCircuitPath.from_origin(self.fp_a)
        assert result.is_complete is False
        assert result.path[-1] == {"type": "provider_circuit", "id": self.span.circuit.pk}


class TestTraceChainedProviderCircuits(TestCase):
    """Back-to-back provider circuits and the revisit guard (issue #135)."""

    @classmethod
    def setUpTestData(cls):
        from tests.conftest import connect_ct_to_ct, connect_rp_to_ct, make_provider_circuit

        cls.dev_a, cls.tray_a = _make_closure("CH-ClosA")
        cls.dev_b, cls.tray_b = _make_closure("CH-ClosB")

        cls.rp_a = RearPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="RP-A", type="lc", positions=1)
        cls.fp_a = FrontPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="FP-A", type="lc")
        PortMapping.objects.create(
            device=cls.dev_a, front_port=cls.fp_a, rear_port=cls.rp_a, front_port_position=1, rear_port_position=1
        )
        cls.rp_b = RearPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="RP-B", type="lc", positions=1)
        cls.fp_b = FrontPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="FP-B", type="lc")
        PortMapping.objects.create(
            device=cls.dev_b, front_port=cls.fp_b, rear_port=cls.rp_b, front_port_position=1, rear_port_position=1
        )

        cls.span1 = make_provider_circuit("CH1")
        cls.span2 = make_provider_circuit("CH2")
        cls.cable1 = connect_rp_to_ct(cls.rp_a, cls.span1.term_a)
        connect_ct_to_ct(cls.span1.term_z, cls.span2.term_a)
        connect_rp_to_ct(cls.rp_b, cls.span2.term_z)

    def test_trace_across_chained_circuits(self):
        result = FiberCircuitPath.from_origin(self.fp_a)
        assert result.destination == self.fp_b
        assert result.is_complete is True
        pc_ids = [e["id"] for e in result.path if e["type"] == "provider_circuit"]
        assert pc_ids == [self.span1.circuit.pk, self.span2.circuit.pk]

    def test_revisit_guard_stops_the_walk(self):
        # A circuit cannot legitimately appear twice in one walk (one cable
        # per termination), so exercise the guard directly on the helper.
        from netbox_fms.trace import _hop_provider_circuits

        entry_term = CableTermination.objects.get(cable=self.cable1, cable_end="B")
        path = []
        assert _hop_provider_circuits(entry_term, path, {self.span1.circuit.pk}) is None
