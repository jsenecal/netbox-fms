"""The analysis walker reproduces the trace engine's hops on its fixtures (#196).

Fixtures are the former tests/test_fiber_circuit_trace.py and
tests/test_trace_multitube.py rigs; the one intended behavior change is the
open/terminated rule: a splice-type port with nothing continuing it is open.
"""

from dcim.models import Cable, CableTermination, FrontPort, PortMapping, RearPort
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from netbox_fms.choices import PathCompletenessChoices, PathEndKindChoices, PathEndReasonChoices
from netbox_fms.models import FiberCableType
from netbox_fms.path_graph import ChainEnd, fp_node, load_plant, rp_node, walk_all, walk_from
from netbox_fms.services import create_closure_cable
from netbox_fms.signals import fms_portmapping_bypass
from tests.conftest import (
    connect_ct_to_ct,
    connect_front_ports,
    connect_rp_to_ct,
    connect_tube_cable,
    make_closure_pair,
    make_closure_with_tray,
    make_mapped_endpoint,
    make_mapped_rear_ports,
    make_provider_circuit,
)

OPEN_NO_PORT = ChainEnd(None, PathEndKindChoices.OPEN, PathEndReasonChoices.CABLE_END)


def _make_closure(name):
    ns = make_closure_with_tray(name, port_count=0)
    return ns.closure, ns.tray


def _pair(device, tray, name):
    rp = RearPort.objects.create(device=device, module=tray, name=f"RP-{name}", type="lc", positions=1)
    fp = FrontPort.objects.create(device=device, module=tray, name=f"FP-{name}", type="lc")
    PortMapping.objects.create(device=device, front_port=fp, rear_port=rp, front_port_position=1, rear_port_position=1)
    return fp, rp


def _connect_cable(cable, rear_port_a, rear_port_b):
    rp_ct = ContentType.objects.get_for_model(RearPort)
    CableTermination.objects.create(cable=cable, cable_end="A", termination_type=rp_ct, termination_id=rear_port_a.pk)
    CableTermination.objects.create(cable=cable, cable_end="B", termination_type=rp_ct, termination_id=rear_port_b.pk)


def chain_from(fp, seeds=None):
    """The one chain through ``fp``, oriented so ``fp`` is end A."""
    chains = walk_from(load_plant(seeds or [fp.device_id]), fp_node(fp.pk))
    assert len(chains) == 1, chains
    chain = chains[0]
    return chain if chain.end_a.port_id == fp.pk else chain.reversed()


class TestWalkSingleCable(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dev_a, tray_a = _make_closure("WClosureA")
        cls.dev_b, tray_b = _make_closure("WClosureB")
        cls.fp_a, cls.rp_a = _pair(cls.dev_a, tray_a, "A1")
        cls.fp_b, cls.rp_b = _pair(cls.dev_b, tray_b, "B1")
        cls.cable = Cable.objects.create()
        _connect_cable(cls.cable, cls.rp_a, cls.rp_b)

    def test_plain_cable_between_lc_ports_is_one_terminated_cable_hop(self):
        chain = chain_from(self.fp_a)
        assert chain.hops == [("cable", self.cable.pk)]
        assert chain.cable_ids == [self.cable.pk]
        assert chain.end_a == ChainEnd(self.fp_a.pk, PathEndKindChoices.TERMINATED, "")
        assert chain.end_b == ChainEnd(self.fp_b.pk, PathEndKindChoices.TERMINATED, "")
        assert chain.completeness == PathCompletenessChoices.TERMINATED_TERMINATED
        assert chain.is_proposed is False

    def test_the_far_device_is_loaded_from_a_one_device_seed(self):
        plant = load_plant([self.dev_a.pk])
        assert plant.device_ids == {self.dev_a.pk, self.dev_b.pk}
        assert plant.device_fps[self.dev_b.pk] == [self.fp_b.pk]

    def test_walk_all_finds_the_same_chain_once(self):
        chains = walk_all(load_plant([self.dev_a.pk]))
        assert [chain.hops for chain in chains] == [[("cable", self.cable.pk)]]


class TestWalkMultiHop(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dev_a, tray_a = _make_closure("WMH-A")
        cls.dev_b, tray_b = _make_closure("WMH-B")
        cls.dev_c, tray_c = _make_closure("WMH-C")
        cls.fp_a, rp_a = _pair(cls.dev_a, tray_a, "A")
        cls.fp_b1, rp_b1 = _pair(cls.dev_b, tray_b, "B1")
        cls.fp_b2, rp_b2 = _pair(cls.dev_b, tray_b, "B2")
        cls.fp_c, rp_c = _pair(cls.dev_c, tray_c, "C")
        cls.cable1 = Cable.objects.create()
        _connect_cable(cls.cable1, rp_a, rp_b1)
        connect_front_ports(cls.fp_b1, cls.fp_b2)
        cls.cable2 = Cable.objects.create()
        _connect_cable(cls.cable2, rp_b2, rp_c)

    def test_splice_joins_two_cable_hops_into_one_chain(self):
        chain = chain_from(self.fp_a)
        assert chain.hops == [("cable", self.cable1.pk), ("cable", self.cable2.pk)]
        assert chain.end_b.port_id == self.fp_c.pk
        assert chain.completeness == PathCompletenessChoices.TERMINATED_TERMINATED

    def test_region_expands_through_the_splicing_device_only(self):
        plant = load_plant([self.dev_a.pk])
        assert plant.device_ids == {self.dev_a.pk, self.dev_b.pk, self.dev_c.pk}

    def test_a_port_with_no_mapping_and_no_strand_has_no_chain(self):
        dev, tray = _make_closure("WNoMap")
        fp = FrontPort.objects.create(device=dev, module=tray, name="OrphanFP", type="lc")
        assert walk_from(load_plant([dev.pk]), fp_node(fp.pk)) == []


class TestWalkProviderCircuit(TestCase):
    @classmethod
    def setUpTestData(cls):
        end_a = make_mapped_endpoint("WPC-A")
        end_b = make_mapped_endpoint("WPC-B")
        cls.fp_a, cls.fp_b = end_a.fp, end_b.fp
        cls.span = make_provider_circuit("WPC1")
        cls.cable_a = connect_rp_to_ct(end_a.rp, cls.span.term_a)
        cls.cable_z = connect_rp_to_ct(end_b.rp, cls.span.term_z)

    def test_provider_span_is_cable_circuit_cable(self):
        chain = chain_from(self.fp_a)
        assert chain.hops == [
            ("cable", self.cable_a.pk),
            ("provider_circuit", self.span.circuit.pk),
            ("cable", self.cable_z.pk),
        ]
        assert chain.cable_ids == [self.cable_a.pk, self.cable_z.pk]
        assert chain.end_b.port_id == self.fp_b.pk

    def test_walking_from_the_z_side_reverses_the_span(self):
        chain = chain_from(self.fp_b)
        assert chain.hops[0] == ("cable", self.cable_z.pk)
        assert chain.cable_ids == [self.cable_z.pk, self.cable_a.pk]

    def test_far_termination_uncabled_leaves_no_fiber(self):
        self.cable_z.delete()
        assert walk_from(load_plant([self.fp_a.device_id]), fp_node(self.fp_a.pk)) == []

    def test_egress_cable_dangling_leaves_no_fiber(self):
        from circuits.models import CircuitTermination

        self.cable_z.delete()
        dangling = Cable.objects.create()
        ct_ct = ContentType.objects.get_for_model(CircuitTermination)
        CableTermination.objects.create(
            cable=dangling, cable_end="A", termination_type=ct_ct, termination_id=self.span.term_z.pk
        )
        assert walk_from(load_plant([self.fp_a.device_id]), fp_node(self.fp_a.pk)) == []

    def test_missing_far_termination_leaves_no_fiber(self):
        self.cable_z.delete()
        self.span.term_z.delete()
        assert walk_from(load_plant([self.fp_a.device_id]), fp_node(self.fp_a.pk)) == []


class TestWalkChainedProviderCircuits(TestCase):
    @classmethod
    def setUpTestData(cls):
        end_a = make_mapped_endpoint("WCH-A")
        end_b = make_mapped_endpoint("WCH-B")
        cls.fp_a, cls.fp_b = end_a.fp, end_b.fp
        cls.span1 = make_provider_circuit("WCH1")
        cls.span2 = make_provider_circuit("WCH2")
        cls.cable1 = connect_rp_to_ct(end_a.rp, cls.span1.term_a)
        cls.cable2 = connect_ct_to_ct(cls.span1.term_z, cls.span2.term_a)
        cls.cable3 = connect_rp_to_ct(end_b.rp, cls.span2.term_z)

    def test_back_to_back_circuits_are_crossed_in_order(self):
        chain = chain_from(self.fp_a)
        assert chain.hops == [
            ("cable", self.cable1.pk),
            ("provider_circuit", self.span1.circuit.pk),
            ("cable", self.cable2.pk),
            ("provider_circuit", self.span2.circuit.pk),
            ("cable", self.cable3.pk),
        ]
        assert chain.end_b.port_id == self.fp_b.pk


class TestWalkMultiTube(TestCase):
    """X -- C1 -- Y -- C2 -- Z, each trunk cable carrying two tubes (issue #168 rig)."""

    @classmethod
    def setUpTestData(cls):
        cls.dev_x, _ = _make_closure("WMT-X")
        cls.dev_y, _ = _make_closure("WMT-Y")
        cls.dev_z, _ = _make_closure("WMT-Z")
        (cls.rp_x1, cls.rp_x2), fps_x = make_mapped_rear_ports(cls.dev_x, ["T1", "T2"], "X-{rp}-{i}", 2)
        (rp_y11, cls.rp_y12), fps_y1 = make_mapped_rear_ports(cls.dev_y, ["C1T1", "C1T2"], "Y1-{rp}-{i}", 2)
        (rp_y21, rp_y22), fps_y2 = make_mapped_rear_ports(cls.dev_y, ["C2T1", "C2T2"], "Y2-{rp}-{i}", 2)
        (rp_z1, rp_z2), fps_z = make_mapped_rear_ports(cls.dev_z, ["T1", "T2"], "Z-{rp}-{i}", 2)
        cls.fp_x2a, cls.fp_z2a = fps_x[2], fps_z[2]
        cls.cable1 = Cable.objects.create()
        connect_tube_cable(cls.cable1, [(cls.rp_x1, rp_y11), (cls.rp_x2, cls.rp_y12)])
        cls.cable2 = Cable.objects.create()
        connect_tube_cable(cls.cable2, [(rp_y21, rp_z1), (rp_y22, rp_z2)])
        for a, b in zip(fps_y1, fps_y2, strict=True):
            connect_front_ports(a, b)

    def test_tube2_fiber_stays_on_tube2(self):
        chain = chain_from(self.fp_x2a)
        assert chain.hops == [("cable", self.cable1.pk), ("cable", self.cable2.pk)]
        assert chain.end_b.port_id == self.fp_z2a.pk
        assert chain.end_a.kind == chain.end_b.kind == PathEndKindChoices.OPEN  # splice-type ports

    def test_missing_egress_mapping_ends_open_at_the_rear_port(self):
        """Review focus: no PortMapping at the entered far position means open/cable_end with no port."""
        PortMapping.objects.filter(rear_port=self.rp_y12, rear_port_position=1).delete()
        chain = chain_from(self.fp_x2a)
        assert chain.hops == [("cable", self.cable1.pk)]
        assert chain.end_b == OPEN_NO_PORT
        assert chain.completeness == PathCompletenessChoices.OPEN_OPEN

    def test_connectorless_two_tube_cable_is_not_crossed(self):
        CableTermination.objects.filter(cable=self.cable1).update(connector=None)
        assert walk_from(load_plant([self.dev_x.pk]), fp_node(self.fp_x2a.pk)) == []


class TestWalkStrandHops(TestCase):
    """FiberCable-backed cables contribute strand hops; splices join them."""

    @classmethod
    def setUpTestData(cls):
        pair = make_closure_pair("WSH")
        cls.dev_a, cls.dev_b = pair.dev_a, pair.dev_b
        cls.dev_c = make_closure_pair("WSH2").dev_b
        cls.fct = FiberCableType.objects.create(
            manufacturer=pair.mfr, model="WSH-2", strand_count=2, construction="tight_buffer"
        )
        cls.fc_ab, _ = create_closure_cable(device_a=cls.dev_a, device_b=cls.dev_b, fiber_cable_type=cls.fct)
        cls.fc_bc, _ = create_closure_cable(device_a=cls.dev_b, device_b=cls.dev_c, fiber_cable_type=cls.fct)
        cls.s1, cls.s2 = list(cls.fc_ab.fiber_strands.order_by("position"))
        cls.t1, cls.t2 = list(cls.fc_bc.fiber_strands.order_by("position"))
        connect_front_ports(cls.s1.front_port_b, cls.t1.front_port_a)

    def test_strand_hop_replaces_the_cable_hop(self):
        chain = chain_from(self.s2.front_port_a)
        assert chain.hops == [("strand", self.s2.pk)]
        assert chain.cable_ids == [self.fc_ab.cable_id]
        assert chain.end_b.port_id == self.s2.front_port_b_id
        assert chain.end_a.reason == PathEndReasonChoices.CABLE_END
        assert chain.end_b.reason == PathEndReasonChoices.UNSPLICED

    def test_spliced_strands_form_one_chain(self):
        chain = chain_from(self.s1.front_port_a)
        assert chain.hops == [("strand", self.s1.pk), ("strand", self.t1.pk)]
        assert chain.cable_ids == [self.fc_ab.cable_id, self.fc_bc.cable_id]
        assert chain.end_b.port_id == self.t1.front_port_b_id

    def test_mapped_position_with_no_landed_strand_keeps_the_cable_hop(self):
        mapping = PortMapping.objects.get(front_port=self.s2.front_port_a)
        with fms_portmapping_bypass():
            PortMapping.objects.filter(front_port__in=[self.s2.front_port_a, self.s2.front_port_b]).delete()
        chains = walk_from(load_plant([self.dev_a.pk]), rp_node(mapping.rear_port_id, mapping.rear_port_position))
        assert [chain.hops for chain in chains] == [[("cable", self.fc_ab.cable_id)]]
        assert chains[0].completeness == PathCompletenessChoices.OPEN_OPEN


class TestRegionBoundary(TestCase):
    @classmethod
    def setUpTestData(cls):
        pair = make_closure_pair("WRB")
        cls.dev_a, cls.dev_b = pair.dev_a, pair.dev_b
        dev_c = make_closure_pair("WRB2").dev_b
        fct = FiberCableType.objects.create(
            manufacturer=pair.mfr, model="WRB-2", strand_count=2, construction="tight_buffer"
        )
        create_closure_cable(device_a=cls.dev_a, device_b=cls.dev_b, fiber_cable_type=fct)
        create_closure_cable(device_a=cls.dev_b, device_b=dev_c, fiber_cable_type=fct)

    def test_a_healthy_cable_beyond_an_unspliced_far_device_is_not_dangling(self):
        """The far device is loaded but not expanded; its other cable's strands are outside the region."""
        plant = load_plant([self.dev_a.pk])
        assert plant.anomalies == []
        assert len(plant.strand_ports) == 2
