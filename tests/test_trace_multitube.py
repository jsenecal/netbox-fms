"""Regression tests for the multi-tube trunk cable crossing bug (issue #168).

trace_fiber_path picked the far-end rear port of a trunk cable with an
unordered CableTermination lookup, so a fiber entering on tube 2 could exit
on tube 1's rear port instead. These tests build a three-device chain
(X -- C1 -- Y -- C2 -- Z) where each trunk cable carries two tubes (two
RearPorts per end, distinguished by CableTermination.connector), spliced
fiber-for-fiber at Y, and prove the trace stays on its own tube end to end.
"""

from dcim.models import Cable, CableTermination, FrontPort, PortMapping, RearPort
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from netbox_fms.models import FiberCircuitPath
from tests.conftest import connect_front_ports, make_closure_with_tray


def _make_closure(name):
    """Bare closure Device + tray Module, no pre-made ports."""
    ns = make_closure_with_tray(name, port_count=0)
    return ns.closure, ns.tray


def _make_dual_tube(device, tray, prefix):
    """Create two 2-position RearPorts (tube 1, tube 2) with FrontPorts and PortMappings.

    Tube 1 is created before tube 2 so an unordered `.first()` query on
    CableTermination would deterministically return tube 1's row.
    """
    tubes = []
    for n in (1, 2):
        rp = RearPort.objects.create(device=device, module=tray, name=f"RP-{prefix}-T{n}", type="lc", positions=2)
        fp_a = FrontPort.objects.create(device=device, module=tray, name=f"FP-{prefix}-T{n}P1", type="lc")
        fp_b = FrontPort.objects.create(device=device, module=tray, name=f"FP-{prefix}-T{n}P2", type="lc")
        PortMapping.objects.create(
            device=device, front_port=fp_a, rear_port=rp, front_port_position=1, rear_port_position=1
        )
        PortMapping.objects.create(
            device=device, front_port=fp_b, rear_port=rp, front_port_position=1, rear_port_position=2
        )
        tubes.append((rp, fp_a, fp_b))

    (rp1, fp1a, fp1b), (rp2, fp2a, fp2b) = tubes
    return rp1, fp1a, fp1b, rp2, fp2a, fp2b


def _connect_dual_tube_cable(cable, near_rp1, near_rp2, far_rp1, far_rp2):
    """Terminate a two-tube trunk cable, tube 1 first (the ordering trap)."""
    rp_ct = ContentType.objects.get_for_model(RearPort)
    for near_rp, far_rp, connector in [(near_rp1, far_rp1, 1), (near_rp2, far_rp2, 2)]:
        CableTermination.objects.create(
            cable=cable,
            cable_end="A",
            termination_type=rp_ct,
            termination_id=near_rp.pk,
            connector=connector,
            positions=[1, 2],
        )
        CableTermination.objects.create(
            cable=cable,
            cable_end="B",
            termination_type=rp_ct,
            termination_id=far_rp.pk,
            connector=connector,
            positions=[1, 2],
        )


class TestTraceMultiTubeCrossing(TestCase):
    """X -- C1 -- Y -- C2 -- Z, each trunk cable carrying two tubes."""

    @classmethod
    def setUpTestData(cls):
        cls.dev_x, cls.tray_x = _make_closure("MT-ClosureX")
        cls.dev_y, cls.tray_y = _make_closure("MT-ClosureY")
        cls.dev_z, cls.tray_z = _make_closure("MT-ClosureZ")

        cls.rp_x1, cls.fp_x1a, cls.fp_x1b, cls.rp_x2, cls.fp_x2a, cls.fp_x2b = _make_dual_tube(
            cls.dev_x, cls.tray_x, "X"
        )
        cls.rp_y_c1_1, cls.fp_y_c1_1a, cls.fp_y_c1_1b, cls.rp_y_c1_2, cls.fp_y_c1_2a, cls.fp_y_c1_2b = _make_dual_tube(
            cls.dev_y, cls.tray_y, "Y-C1"
        )
        cls.rp_y_c2_1, cls.fp_y_c2_1a, cls.fp_y_c2_1b, cls.rp_y_c2_2, cls.fp_y_c2_2a, cls.fp_y_c2_2b = _make_dual_tube(
            cls.dev_y, cls.tray_y, "Y-C2"
        )
        cls.rp_z1, cls.fp_z1a, cls.fp_z1b, cls.rp_z2, cls.fp_z2a, cls.fp_z2b = _make_dual_tube(
            cls.dev_z, cls.tray_z, "Z"
        )

        cls.cable1 = Cable.objects.create()
        _connect_dual_tube_cable(cls.cable1, cls.rp_x1, cls.rp_x2, cls.rp_y_c1_1, cls.rp_y_c1_2)

        cls.cable2 = Cable.objects.create()
        _connect_dual_tube_cable(cls.cable2, cls.rp_y_c2_1, cls.rp_y_c2_2, cls.rp_z1, cls.rp_z2)

        # Splice jumpers at Y, fiber-for-fiber: tube 1 <-> tube 1, tube 2 <-> tube 2.
        connect_front_ports(cls.fp_y_c1_1a, cls.fp_y_c2_1a)
        connect_front_ports(cls.fp_y_c1_1b, cls.fp_y_c2_1b)
        connect_front_ports(cls.fp_y_c1_2a, cls.fp_y_c2_2a)
        connect_front_ports(cls.fp_y_c1_2b, cls.fp_y_c2_2b)

    def test_tube2_fiber_stays_on_tube2(self):
        """A fiber entered on tube 2 must exit on tube 2's rear port at every hop."""
        result = FiberCircuitPath.from_origin(self.fp_x2a)

        assert result.is_complete is True
        assert result.destination == self.fp_z2a

        front_ports = [entry["id"] for entry in result.path if entry["type"] == "front_port"]
        assert front_ports == [self.fp_x2a.pk, self.fp_y_c1_2a.pk, self.fp_y_c2_2a.pk, self.fp_z2a.pk]

        rear_ports = [entry["id"] for entry in result.path if entry["type"] == "rear_port"]
        assert rear_ports == [self.rp_x2.pk, self.rp_y_c1_2.pk, self.rp_y_c2_2.pk, self.rp_z2.pk]

    def test_missing_egress_mapping_is_incomplete_not_a_fiber_jump(self):
        """No PortMapping at the far rear port's ingress position means stop, not guess."""
        # Tube 2 position 2 keeps its mapping; only position 1 (the position
        # the trace enters on) is removed.
        PortMapping.objects.filter(rear_port=self.rp_y_c1_2, rear_port_position=1).delete()

        result = FiberCircuitPath.from_origin(self.fp_x2a)

        assert result.is_complete is False
        assert result.destination is None
        assert result.path == [
            {"type": "front_port", "id": self.fp_x2a.pk},
            {"type": "rear_port", "id": self.rp_x2.pk},
            {"type": "cable", "id": self.cable1.pk},
            {"type": "rear_port", "id": self.rp_y_c1_2.pk},
        ]

    def test_null_connector_multiple_far_candidates_is_incomplete(self):
        """Both ends connector-less with more than one rear port: refuse to guess."""
        CableTermination.objects.filter(cable=self.cable1).update(connector=None)

        result = FiberCircuitPath.from_origin(self.fp_x2a)

        assert result.is_complete is False
        assert result.destination is None
        assert result.path == [
            {"type": "front_port", "id": self.fp_x2a.pk},
            {"type": "rear_port", "id": self.rp_x2.pk},
            {"type": "cable", "id": self.cable1.pk},
        ]


class TestTraceMixedConnectorSingleRP(TestCase):
    """Near end records a connector, far end doesn't -- still unambiguous for a single-RP cable."""

    @classmethod
    def setUpTestData(cls):
        cls.dev_a, cls.tray_a = _make_closure("MC-ClosureA")
        cls.dev_b, cls.tray_b = _make_closure("MC-ClosureB")

        cls.rp_a = RearPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="RP-MC-A", type="lc", positions=1)
        cls.fp_a = FrontPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="FP-MC-A", type="lc")
        PortMapping.objects.create(
            device=cls.dev_a, front_port=cls.fp_a, rear_port=cls.rp_a, front_port_position=1, rear_port_position=1
        )

        cls.rp_b = RearPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="RP-MC-B", type="lc", positions=1)
        cls.fp_b = FrontPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="FP-MC-B", type="lc")
        PortMapping.objects.create(
            device=cls.dev_b, front_port=cls.fp_b, rear_port=cls.rp_b, front_port_position=1, rear_port_position=1
        )

        cls.cable = Cable.objects.create()
        rp_ct = ContentType.objects.get_for_model(RearPort)
        # Near end (A) records a connector; far end (B) doesn't. Both ends
        # are single-RP, so there is exactly one way to align them.
        CableTermination.objects.create(
            cable=cls.cable, cable_end="A", termination_type=rp_ct, termination_id=cls.rp_a.pk, connector=1
        )
        CableTermination.objects.create(
            cable=cls.cable, cable_end="B", termination_type=rp_ct, termination_id=cls.rp_b.pk
        )

    def test_mixed_connector_single_rp_still_traces(self):
        result = FiberCircuitPath.from_origin(self.fp_a)

        assert result.is_complete is True
        assert result.destination == self.fp_b
