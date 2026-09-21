"""Regression tests for the multi-tube trunk cable crossing bug (issue #168).

trace_fiber_path picked the far-end rear port of a trunk cable with an
unordered CableTermination lookup, so a fiber entering on tube 2 could exit
on tube 1's rear port instead. These tests build a three-device chain
(X -- C1 -- Y -- C2 -- Z) where each trunk cable carries two tubes (two
RearPorts per end, distinguished by CableTermination.connector), spliced
fiber-for-fiber at Y, and prove the trace stays on its own tube end to end.
"""

from dcim.models import (
    Cable,
    CableTermination,
    Device,
    DeviceRole,
    DeviceType,
    FrontPort,
    Manufacturer,
    Module,
    ModuleBay,
    ModuleType,
    PortMapping,
    RearPort,
    Site,
)
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from netbox_fms.models import FiberCircuitPath


def _make_closure(site, mfr, name):
    dt, _ = DeviceType.objects.get_or_create(manufacturer=mfr, model=f"{name}-Type", slug=f"{name}-type".lower())
    role, _ = DeviceRole.objects.get_or_create(name=f"{name}-Role", slug=f"{name}-role".lower())
    device = Device.objects.create(name=name, site=site, device_type=dt, role=role)
    mt, _ = ModuleType.objects.get_or_create(manufacturer=mfr, model=f"{name}-Tray")
    bay = ModuleBay.objects.create(device=device, name="Bay1")
    tray = Module.objects.create(device=device, module_bay=bay, module_type=mt)
    return device, tray


def _make_dual_tube(device, tray, prefix):
    """Create two 2-position RearPorts (tube 1, tube 2) with FrontPorts and PortMappings.

    Tube 1 is created before tube 2 so an unordered `.first()` query on
    CableTermination would deterministically return tube 1's row.
    """
    rp1 = RearPort.objects.create(device=device, module=tray, name=f"RP-{prefix}-T1", type="lc", positions=2)
    fp1a = FrontPort.objects.create(device=device, module=tray, name=f"FP-{prefix}-T1P1", type="lc")
    fp1b = FrontPort.objects.create(device=device, module=tray, name=f"FP-{prefix}-T1P2", type="lc")
    PortMapping.objects.create(
        device=device, front_port=fp1a, rear_port=rp1, front_port_position=1, rear_port_position=1
    )
    PortMapping.objects.create(
        device=device, front_port=fp1b, rear_port=rp1, front_port_position=1, rear_port_position=2
    )

    rp2 = RearPort.objects.create(device=device, module=tray, name=f"RP-{prefix}-T2", type="lc", positions=2)
    fp2a = FrontPort.objects.create(device=device, module=tray, name=f"FP-{prefix}-T2P1", type="lc")
    fp2b = FrontPort.objects.create(device=device, module=tray, name=f"FP-{prefix}-T2P2", type="lc")
    PortMapping.objects.create(
        device=device, front_port=fp2a, rear_port=rp2, front_port_position=1, rear_port_position=1
    )
    PortMapping.objects.create(
        device=device, front_port=fp2b, rear_port=rp2, front_port_position=1, rear_port_position=2
    )

    return rp1, fp1a, fp1b, rp2, fp2a, fp2b


def _connect_dual_tube_cable(cable, near_rp1, near_rp2, far_rp1, far_rp2):
    """Terminate a two-tube trunk cable, tube 1 first (the ordering trap)."""
    rp_ct = ContentType.objects.get_for_model(RearPort)
    CableTermination.objects.create(
        cable=cable, cable_end="A", termination_type=rp_ct, termination_id=near_rp1.pk, connector=1, positions=[1, 2]
    )
    CableTermination.objects.create(
        cable=cable, cable_end="B", termination_type=rp_ct, termination_id=far_rp1.pk, connector=1, positions=[1, 2]
    )
    CableTermination.objects.create(
        cable=cable, cable_end="A", termination_type=rp_ct, termination_id=near_rp2.pk, connector=2, positions=[1, 2]
    )
    CableTermination.objects.create(
        cable=cable, cable_end="B", termination_type=rp_ct, termination_id=far_rp2.pk, connector=2, positions=[1, 2]
    )


def _make_jumper(fp_a, fp_b):
    """Splice jumper: an FP-to-FP Cable, mirroring test_fiber_circuit_trace._make_splice."""
    cable = Cable.objects.create(length=0, length_unit="m")
    fp_ct = ContentType.objects.get_for_model(FrontPort)
    CableTermination.objects.create(cable=cable, cable_end="A", termination_type=fp_ct, termination_id=fp_a.pk)
    CableTermination.objects.create(cable=cable, cable_end="B", termination_type=fp_ct, termination_id=fp_b.pk)
    return cable


class TestTraceMultiTubeCrossing(TestCase):
    """X -- C1 -- Y -- C2 -- Z, each trunk cable carrying two tubes."""

    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="MultiTube Site", slug="multitube-site")
        mfr = Manufacturer.objects.create(name="MultiTube Mfr", slug="multitube-mfr")

        cls.dev_x, cls.tray_x = _make_closure(site, mfr, "MT-ClosureX")
        cls.dev_y, cls.tray_y = _make_closure(site, mfr, "MT-ClosureY")
        cls.dev_z, cls.tray_z = _make_closure(site, mfr, "MT-ClosureZ")

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
        _make_jumper(cls.fp_y_c1_1a, cls.fp_y_c2_1a)
        _make_jumper(cls.fp_y_c1_1b, cls.fp_y_c2_1b)
        _make_jumper(cls.fp_y_c1_2a, cls.fp_y_c2_2a)
        _make_jumper(cls.fp_y_c1_2b, cls.fp_y_c2_2b)

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
