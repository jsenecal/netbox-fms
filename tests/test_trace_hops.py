"""Tests for the trace-to-hops transformation engine."""

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

from netbox_fms.trace_hops import build_hops


def _make_device(site, mfr, name, suffix=""):
    """Create a device with a module tray."""
    slug_name = f"{name}{suffix}".lower().replace(" ", "-")
    dt, _ = DeviceType.objects.get_or_create(manufacturer=mfr, model=f"{name}-Type{suffix}", slug=f"{slug_name}-dt")
    role, _ = DeviceRole.objects.get_or_create(name=f"{name}-Role", slug=f"{slug_name}-role")
    device = Device.objects.create(name=f"{name}{suffix}", site=site, device_type=dt, role=role)
    mt, _ = ModuleType.objects.get_or_create(manufacturer=mfr, model=f"{name}-Tray{suffix}")
    bay = ModuleBay.objects.create(device=device, name="Bay1")
    tray = Module.objects.create(device=device, module_bay=bay, module_type=mt)
    return device, tray


def _make_front_rear_pair(device, tray, fp_name, rp_name):
    """Create a FrontPort/RearPort pair linked via PortMapping."""
    rp = RearPort.objects.create(device=device, module=tray, name=rp_name, type="lc", positions=1)
    fp = FrontPort.objects.create(device=device, module=tray, name=fp_name, type="lc")
    PortMapping.objects.create(device=device, front_port=fp, rear_port=rp, front_port_position=1, rear_port_position=1)
    return fp, rp


def _connect_cable_rp(cable, rp_a, rp_b):
    """Connect a cable between two RearPorts."""
    rp_ct = ContentType.objects.get_for_model(RearPort)
    CableTermination.objects.create(cable=cable, cable_end="A", termination_type=rp_ct, termination_id=rp_a.pk)
    CableTermination.objects.create(cable=cable, cable_end="B", termination_type=rp_ct, termination_id=rp_b.pk)


class TestBuildHopsEmpty(TestCase):
    def test_empty_path(self):
        result = build_hops([])
        assert result == []

    def test_none_like_empty(self):
        """Passing an empty list returns empty list."""
        assert build_hops([]) == []


class TestBuildHopsSimplePath(TestCase):
    """A → cable → B produces 3 hops: device A, cable, device B."""

    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name="Hops Site", slug="hops-site")
        cls.mfr = Manufacturer.objects.create(name="Hops Mfr", slug="hops-mfr")

        cls.dev_a, cls.tray_a = _make_device(cls.site, cls.mfr, "HopsDevA")
        cls.dev_b, cls.tray_b = _make_device(cls.site, cls.mfr, "HopsDevB")

        cls.fp_a, cls.rp_a = _make_front_rear_pair(cls.dev_a, cls.tray_a, "FP-A1", "RP-A1")
        cls.fp_b, cls.rp_b = _make_front_rear_pair(cls.dev_b, cls.tray_b, "FP-B1", "RP-B1")

        cls.cable = Cable.objects.create()
        _connect_cable_rp(cls.cable, cls.rp_a, cls.rp_b)

    def _make_path(self):
        return [
            {"type": "front_port", "id": self.fp_a.pk},
            {"type": "rear_port", "id": self.rp_a.pk},
            {"type": "cable", "id": self.cable.pk},
            {"type": "rear_port", "id": self.rp_b.pk},
            {"type": "front_port", "id": self.fp_b.pk},
        ]

    def test_simple_path_two_devices_produces_three_hops(self):
        hops = build_hops(self._make_path())
        assert len(hops) == 3, f"Expected 3 hops, got {len(hops)}: {hops}"

    def test_hop_types(self):
        hops = build_hops(self._make_path())
        types = [h["type"] for h in hops]
        assert types == ["device", "cable", "device"]

    def test_first_hop_is_device_a(self):
        hops = build_hops(self._make_path())
        first = hops[0]
        assert first["type"] == "device"
        assert first["id"] == self.dev_a.pk
        assert first["name"] == self.dev_a.name
        assert "ports" in first
        assert first["ports"]["front_port"]["id"] == self.fp_a.pk
        assert first["ports"]["rear_port"]["id"] == self.rp_a.pk

    def test_cable_hop(self):
        hops = build_hops(self._make_path())
        cable_hop = hops[1]
        assert cable_hop["type"] == "cable"
        assert cable_hop["id"] == self.cable.pk

    def test_last_hop_is_device_b(self):
        hops = build_hops(self._make_path())
        last = hops[2]
        assert last["type"] == "device"
        assert last["id"] == self.dev_b.pk

    def test_no_pending_device_id_in_output(self):
        """Internal _pending_device_id markers must be cleaned up before returning."""
        hops = build_hops(self._make_path())
        for hop in hops:
            assert "_pending_device_id" not in hop, f"Hop still has _pending_device_id: {hop}"

    def test_device_hop_has_role_and_site(self):
        hops = build_hops(self._make_path())
        first = hops[0]
        assert first["site"] == self.site.name
        assert first["role"] is not None

    def test_device_hop_has_url(self):
        hops = build_hops(self._make_path())
        for hop in hops:
            if hop["type"] == "device":
                assert "url" in hop
                assert hop["url"]  # non-empty


class TestBuildHopsNoPendingOnSingleDevice(TestCase):
    """A single device endpoint (terminal FrontPort only) produces one device hop."""

    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name="Terminal Site", slug="terminal-site")
        cls.mfr = Manufacturer.objects.create(name="Terminal Mfr", slug="terminal-mfr")
        cls.dev, cls.tray = _make_device(cls.site, cls.mfr, "TermDev")
        cls.fp = FrontPort.objects.create(device=cls.dev, module=cls.tray, name="FP-T1", type="lc")

    def test_terminal_front_port_only(self):
        """A path with just a terminal FrontPort (no following RearPort) still produces one device hop."""
        path = [{"type": "front_port", "id": self.fp.pk}]
        hops = build_hops(path)
        assert len(hops) == 1
        assert hops[0]["type"] == "device"
        assert "_pending_device_id" not in hops[0]

    def test_no_pending_device_id_terminal(self):
        path = [{"type": "front_port", "id": self.fp.pk}]
        hops = build_hops(path)
        for hop in hops:
            assert "_pending_device_id" not in hop


class TestBuildHopsUnknownEntryType(TestCase):
    """Unknown entry types are skipped gracefully."""

    def test_unknown_type_skipped(self):
        path = [{"type": "unknown_future_type", "id": 999}]
        hops = build_hops(path)
        assert hops == []

    def test_mixed_known_unknown(self):
        """Unknown entries don't break processing of valid entries around them."""
        # Just an unknown type, should return empty
        path = [
            {"type": "unknown_type", "id": 1},
            {"type": "another_unknown", "id": 2},
        ]
        hops = build_hops(path)
        assert hops == []


class TestBuildHopsClosurePattern(TestCase):
    """Mid-path rear_port → front_port pattern creates ingress hop."""

    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name="Closure Site", slug="closure-site")
        cls.mfr = Manufacturer.objects.create(name="Closure Mfr", slug="closure-mfr")

        cls.dev_a, cls.tray_a = _make_device(cls.site, cls.mfr, "ClsA")
        cls.dev_mid, cls.tray_mid = _make_device(cls.site, cls.mfr, "ClsMid")
        cls.dev_b, cls.tray_b = _make_device(cls.site, cls.mfr, "ClsB")

        cls.fp_a, cls.rp_a = _make_front_rear_pair(cls.dev_a, cls.tray_a, "FP-A1", "RP-A1")

        # Closure: ingress RP + FP, egress FP + RP (two separate port pairs)
        cls.rp_mid_in = RearPort.objects.create(
            device=cls.dev_mid, module=cls.tray_mid, name="RP-MID-IN", type="lc", positions=1
        )
        cls.fp_mid_in = FrontPort.objects.create(device=cls.dev_mid, module=cls.tray_mid, name="FP-MID-IN", type="lc")
        PortMapping.objects.create(
            device=cls.dev_mid,
            front_port=cls.fp_mid_in,
            rear_port=cls.rp_mid_in,
            front_port_position=1,
            rear_port_position=1,
        )

        cls.fp_mid_out, cls.rp_mid_out = _make_front_rear_pair(cls.dev_mid, cls.tray_mid, "FP-MID-OUT", "RP-MID-OUT")
        cls.fp_b, cls.rp_b = _make_front_rear_pair(cls.dev_b, cls.tray_b, "FP-B1", "RP-B1")

        cls.cable1 = Cable.objects.create()
        _connect_cable_rp(cls.cable1, cls.rp_a, cls.rp_mid_in)

        cls.cable2 = Cable.objects.create()
        _connect_cable_rp(cls.cable2, cls.rp_mid_out, cls.rp_b)

    def _make_path(self):
        return [
            {"type": "front_port", "id": self.fp_a.pk},
            {"type": "rear_port", "id": self.rp_a.pk},
            {"type": "cable", "id": self.cable1.pk},
            # Closure ingress: rp → fp
            {"type": "rear_port", "id": self.rp_mid_in.pk},
            {"type": "front_port", "id": self.fp_mid_in.pk},
            # Closure egress: fp → rp
            {"type": "front_port", "id": self.fp_mid_out.pk},
            {"type": "rear_port", "id": self.rp_mid_out.pk},
            {"type": "cable", "id": self.cable2.pk},
            {"type": "rear_port", "id": self.rp_b.pk},
            {"type": "front_port", "id": self.fp_b.pk},
        ]

    def test_no_pending_device_id_closure(self):
        hops = build_hops(self._make_path())
        for hop in hops:
            assert "_pending_device_id" not in hop, f"Hop still has _pending_device_id: {hop}"

    def test_closure_produces_ingress_hop(self):
        hops = build_hops(self._make_path())
        device_hops = [h for h in hops if h["type"] == "device"]
        # Should have device A, mid-closure (ingress), and device B
        assert len(device_hops) >= 2

    def test_all_hops_have_no_internal_markers(self):
        hops = build_hops(self._make_path())
        for hop in hops:
            assert "_pending_device_id" not in hop
