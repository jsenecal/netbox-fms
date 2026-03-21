"""Tests for WDM wavelength service stitching: path assembly, API action, and trace annotations."""

import pytest

from netbox_fms.models import (
    FiberCircuit,
    WavelengthChannel,
    WavelengthService,
    WavelengthServiceChannelAssignment,
    WavelengthServiceCircuit,
    WdmNode,
)


@pytest.fixture
def stitching_fixtures():
    """Create a MUX-A -> circuit -> MUX-B topology for stitching tests."""
    from dcim.models import Device, DeviceRole, DeviceType, FrontPort, Manufacturer, Site

    site = Site.objects.create(name="Stitch-Site", slug="stitch-site")
    mfr = Manufacturer.objects.create(name="Stitch-Mfr", slug="stitch-mfr")
    role = DeviceRole.objects.create(name="Stitch-Role", slug="stitch-role")
    dt = DeviceType.objects.create(manufacturer=mfr, model="Stitch-DT", slug="stitch-dt")

    dev_a = Device.objects.create(name="MUX-A", site=site, device_type=dt, role=role)
    dev_b = Device.objects.create(name="MUX-B", site=site, device_type=dt, role=role)

    fp_a = FrontPort.objects.create(device=dev_a, name="Ch-1", type="lc", positions=1)
    fp_b = FrontPort.objects.create(device=dev_b, name="Ch-1", type="lc", positions=1)

    node_a = WdmNode.objects.create(device=dev_a, node_type="terminal_mux", grid="dwdm_100ghz")
    node_b = WdmNode.objects.create(device=dev_b, node_type="terminal_mux", grid="dwdm_100ghz")

    ch_a = WavelengthChannel.objects.create(
        wdm_node=node_a, grid_position=1, wavelength_nm=1560.61, label="C21", front_port=fp_a, status="lit"
    )
    ch_b = WavelengthChannel.objects.create(
        wdm_node=node_b, grid_position=1, wavelength_nm=1560.61, label="C21", front_port=fp_b, status="lit"
    )

    circuit = FiberCircuit.objects.create(name="Trunk-AB", status="active", strand_count=1)

    return {
        "dev_a": dev_a,
        "dev_b": dev_b,
        "node_a": node_a,
        "node_b": node_b,
        "ch_a": ch_a,
        "ch_b": ch_b,
        "circuit": circuit,
    }


# ---------------------------------------------------------------------------
# Task 1: get_stitched_path() model method tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGetStitchedPath:
    def test_simple_two_node_path(self, stitching_fixtures):
        """MUX-A (ch) -> circuit -> MUX-B (ch) returns 3 hops in correct order."""
        svc = WavelengthService.objects.create(name="Stitch-1", status="active", wavelength_nm=1560.61)
        WavelengthServiceChannelAssignment.objects.create(
            service=svc, channel=stitching_fixtures["ch_a"], sequence=1
        )
        WavelengthServiceCircuit.objects.create(
            service=svc, fiber_circuit=stitching_fixtures["circuit"], sequence=2
        )
        WavelengthServiceChannelAssignment.objects.create(
            service=svc, channel=stitching_fixtures["ch_b"], sequence=3
        )

        path = svc.get_stitched_path()
        assert len(path) == 3

        # First hop: wdm_node (MUX-A)
        assert path[0]["type"] == "wdm_node"
        assert path[0]["node_name"] == "MUX-A"
        assert path[0]["channel_label"] == "C21"
        assert path[0]["wavelength_nm"] == pytest.approx(1560.61)

        # Second hop: fiber_circuit
        assert path[1]["type"] == "fiber_circuit"
        assert path[1]["circuit_name"] == "Trunk-AB"

        # Third hop: wdm_node (MUX-B)
        assert path[2]["type"] == "wdm_node"
        assert path[2]["node_name"] == "MUX-B"

    def test_empty_service_returns_empty_path(self):
        """A service with no assignments returns an empty path."""
        svc = WavelengthService.objects.create(name="Empty-Svc", status="planned", wavelength_nm=1550.0)
        path = svc.get_stitched_path()
        assert path == []

    def test_path_ordering_follows_sequence(self, stitching_fixtures):
        """Items added in reverse order are still returned sorted by sequence."""
        svc = WavelengthService.objects.create(name="Reverse-Order", status="active", wavelength_nm=1560.61)

        # Add in reverse sequence order
        WavelengthServiceChannelAssignment.objects.create(
            service=svc, channel=stitching_fixtures["ch_b"], sequence=3
        )
        WavelengthServiceCircuit.objects.create(
            service=svc, fiber_circuit=stitching_fixtures["circuit"], sequence=2
        )
        WavelengthServiceChannelAssignment.objects.create(
            service=svc, channel=stitching_fixtures["ch_a"], sequence=1
        )

        path = svc.get_stitched_path()
        assert len(path) == 3
        assert path[0]["type"] == "wdm_node"
        assert path[0]["node_name"] == "MUX-A"
        assert path[1]["type"] == "fiber_circuit"
        assert path[2]["type"] == "wdm_node"
        assert path[2]["node_name"] == "MUX-B"


# ---------------------------------------------------------------------------
# Task 4: Trace annotations tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWavelengthServiceAnnotations:
    def test_annotations_for_circuit_with_service(self, stitching_fixtures):
        """A fiber circuit assigned to a service should return annotation data."""
        from netbox_fms.trace_hops import get_wavelength_service_annotations

        svc = WavelengthService.objects.create(name="Annotated-Svc", status="active", wavelength_nm=1560.61)
        WavelengthServiceCircuit.objects.create(
            service=svc, fiber_circuit=stitching_fixtures["circuit"], sequence=2
        )

        annotations = get_wavelength_service_annotations(stitching_fixtures["circuit"])
        assert len(annotations) == 1
        assert annotations[0]["service_name"] == "Annotated-Svc"
        assert annotations[0]["wavelength_nm"] == pytest.approx(1560.61)
        assert annotations[0]["status"] == "active"

    def test_annotations_for_circuit_without_service(self, stitching_fixtures):
        """A fiber circuit with no service assignments returns empty annotations."""
        from netbox_fms.trace_hops import get_wavelength_service_annotations

        # Create a separate circuit with no service assignments
        circuit2 = FiberCircuit.objects.create(name="Unassigned", status="active", strand_count=1)
        annotations = get_wavelength_service_annotations(circuit2)
        assert annotations == []

    def test_multiple_services_on_same_circuit(self, stitching_fixtures):
        """Multiple services on the same circuit should all appear in annotations."""
        from netbox_fms.trace_hops import get_wavelength_service_annotations

        svc1 = WavelengthService.objects.create(name="Svc-1", status="active", wavelength_nm=1560.61)
        svc2 = WavelengthService.objects.create(name="Svc-2", status="planned", wavelength_nm=1560.61)
        WavelengthServiceCircuit.objects.create(
            service=svc1, fiber_circuit=stitching_fixtures["circuit"], sequence=1
        )
        WavelengthServiceCircuit.objects.create(
            service=svc2, fiber_circuit=stitching_fixtures["circuit"], sequence=1
        )

        annotations = get_wavelength_service_annotations(stitching_fixtures["circuit"])
        assert len(annotations) == 2
        names = {a["service_name"] for a in annotations}
        assert names == {"Svc-1", "Svc-2"}
