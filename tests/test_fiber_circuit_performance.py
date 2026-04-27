import time

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

from netbox_fms.models import FiberCircuit, FiberCircuitNode, FiberCircuitPath


class TestTracePerformance(TestCase):
    """Performance tests for the trace engine."""

    @classmethod
    def setUpTestData(cls):
        """Create a long linear chain with splices for performance testing."""
        site = Site.objects.create(name="Perf Site", slug="perf-site")
        mfr = Manufacturer.objects.create(name="Perf Mfr", slug="perf-mfr")
        rp_ct = ContentType.objects.get_for_model(RearPort)
        fp_ct = ContentType.objects.get_for_model(FrontPort)

        # Build a 20-hop chain (21 closures connected by cables with splices at each intermediate)
        num_closures = 21
        closures = []
        for i in range(num_closures):
            dt, _ = DeviceType.objects.get_or_create(manufacturer=mfr, model=f"Perf-C-{i}", slug=f"perf-c-{i}")
            role, _ = DeviceRole.objects.get_or_create(name="Perf-Role", slug="perf-role")
            device = Device.objects.create(name=f"Perf-Closure-{i}", site=site, device_type=dt, role=role)
            mt, _ = ModuleType.objects.get_or_create(manufacturer=mfr, model=f"Perf-Tray-{i}")
            bay = ModuleBay.objects.create(device=device, name="Bay1")
            tray = Module.objects.create(device=device, module_bay=bay, module_type=mt)
            closures.append((device, tray))

        prev_egress_fp = None
        for i in range(num_closures - 1):
            dev_a, tray_a = closures[i]
            dev_b, tray_b = closures[i + 1]

            rp_a = RearPort.objects.create(device=dev_a, module=tray_a, name=f"RP-out-{i}", type="lc", positions=1)
            fp_a = FrontPort.objects.create(device=dev_a, module=tray_a, name=f"FP-out-{i}", type="lc")
            PortMapping.objects.create(
                device=dev_a, front_port=fp_a, rear_port=rp_a, front_port_position=1, rear_port_position=1
            )

            rp_b = RearPort.objects.create(device=dev_b, module=tray_b, name=f"RP-in-{i + 1}", type="lc", positions=1)
            fp_b = FrontPort.objects.create(device=dev_b, module=tray_b, name=f"FP-in-{i + 1}", type="lc")
            PortMapping.objects.create(
                device=dev_b, front_port=fp_b, rear_port=rp_b, front_port_position=1, rear_port_position=1
            )

            cable = Cable.objects.create()
            CableTermination.objects.create(cable=cable, cable_end="A", termination_type=rp_ct, termination_id=rp_a.pk)
            CableTermination.objects.create(cable=cable, cable_end="B", termination_type=rp_ct, termination_id=rp_b.pk)

            # Create splice at intermediate closures (connect previous ingress to this egress)
            if prev_egress_fp is not None and i > 0:
                # At closure i: prev_egress_fp is the ingress FP, fp_a is the egress FP
                # Both are on device closures[i] — splice them via a zero-length cable
                splice_cable = Cable.objects.create(length=0, length_unit="m")
                CableTermination.objects.create(
                    cable=splice_cable, cable_end="A", termination_type=fp_ct, termination_id=prev_egress_fp.pk
                )
                CableTermination.objects.create(
                    cable=splice_cable, cable_end="B", termination_type=fp_ct, termination_id=fp_a.pk
                )

            prev_egress_fp = fp_b

        cls.origin_fp = FrontPort.objects.filter(device=closures[0][0], name__startswith="FP-out").first()

    def test_trace_20_hops_under_2s(self):
        """20-hop trace should complete quickly."""
        start = time.monotonic()
        result = FiberCircuitPath.from_origin(self.origin_fp)
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"20-hop trace took {elapsed:.3f}s (target < 2.0s)"
        assert result.is_complete is True


class TestNodeRebuildPerformance(TestCase):
    def test_rebuild_from_large_path(self):
        """Rebuilding nodes from a path with 50 entries should be fast."""
        site = Site.objects.create(name="Rebuild Site", slug="rebuild-site")
        mfr = Manufacturer.objects.create(name="Rebuild Mfr", slug="rebuild-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="RebuildDev", slug="rebuilddev")
        role = DeviceRole.objects.create(name="Rebuild Role", slug="rebuild-role")
        device = Device.objects.create(name="RebuildDev-1", site=site, device_type=dt, role=role)
        fp = FrontPort.objects.create(device=device, name="RebuildFP", type="lc")

        # Create path with 50 cable entries
        cables = [Cable.objects.create() for _ in range(50)]
        path_json = [{"type": "cable", "id": c.pk} for c in cables]

        circuit = FiberCircuit.objects.create(name="Rebuild-Perf", strand_count=1)
        path = FiberCircuitPath.objects.create(
            circuit=circuit,
            position=1,
            origin=fp,
            path=path_json,
            is_complete=False,
        )

        start = time.monotonic()
        path.rebuild_nodes()
        elapsed = time.monotonic() - start

        assert elapsed < 1.0, f"50-entry rebuild took {elapsed:.3f}s (target < 1.0s)"
        assert FiberCircuitNode.objects.filter(path=path).count() == 50


class TestProtectionQueryPerformance(TestCase):
    def test_cable_lookup_with_many_nodes(self):
        """Protection query should be fast even with many nodes."""
        site = Site.objects.create(name="PQ Site", slug="pq-site")
        mfr = Manufacturer.objects.create(name="PQ Mfr", slug="pq-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="PQDev", slug="pqdev")
        role = DeviceRole.objects.create(name="PQ Role", slug="pq-role")
        device = Device.objects.create(name="PQDev-1", site=site, device_type=dt, role=role)
        fp = FrontPort.objects.create(device=device, name="PQFP", type="lc")

        # Create 100 circuits each with 1 cable node
        target_cable = Cable.objects.create()
        for i in range(100):
            circuit = FiberCircuit.objects.create(name=f"PQ-{i}", strand_count=1)
            path = FiberCircuitPath.objects.create(
                circuit=circuit,
                position=1,
                origin=fp,
                path=[],
                is_complete=False,
            )
            cable = target_cable if i == 0 else Cable.objects.create()
            FiberCircuitNode.objects.create(path=path, position=1, cable=cable)

        start = time.monotonic()
        result = FiberCircuitNode.objects.filter(cable=target_cable).select_related("path__circuit").first()
        elapsed = time.monotonic() - start

        assert result is not None
        assert elapsed < 0.1, f"Protection lookup took {elapsed:.3f}s (target < 0.1s)"
