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

from netbox_fms.choices import SplicePlanStatusChoices
from netbox_fms.models import FiberCableType, FiberStrand, SplicePlan, SplicePlanEntry
from netbox_fms.services import create_closure_cable
from netbox_fms.trace_hops import build_hops, flat_entries
from tests.conftest import (
    connect_front_ports,
    make_closure_pair,
    make_provider_circuit,
    make_strand_path,
    make_tray_module,
    make_tray_type,
)


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


class TestProviderCircuitHop(TestCase):
    """build_hops renders provider circuits as opaque edge hops (issue #135)."""

    @classmethod
    def setUpTestData(cls):
        from tests.conftest import make_provider_circuit

        cls.span = make_provider_circuit("Hop")

    def test_provider_circuit_hop_shape(self):
        hops = build_hops([{"type": "provider_circuit", "id": self.span.circuit.pk}])
        assert hops == [
            {
                "type": "provider_circuit",
                "id": self.span.circuit.pk,
                "cid": self.span.circuit.cid,
                "provider": self.span.provider.name,
                "url": self.span.circuit.get_absolute_url(),
            }
        ]

    def test_missing_circuit_degrades(self):
        hops = build_hops([{"type": "provider_circuit", "id": 999999}])
        assert hops[0]["cid"] == "Circuit #999999"
        assert hops[0]["provider"] is None


class TestFlatEntries(TestCase):
    """flat_entries rebuilds the port-level trace the renderer consumes from a stored path."""

    @classmethod
    def setUpTestData(cls):
        pair = make_closure_pair("FE")
        cls.dev_a, cls.dev_b = pair.dev_a, pair.dev_b
        pair2 = make_closure_pair("FE2")
        dev_c, dev_d = pair2.dev_b, pair2.dev_a
        fct = FiberCableType.objects.create(
            manufacturer=pair.mfr, model="FE-2", strand_count=2, construction="tight_buffer"
        )
        fc_ab, _ = create_closure_cable(device_a=cls.dev_a, device_b=cls.dev_b, fiber_cable_type=fct)
        fc_bc, _ = create_closure_cable(device_a=cls.dev_b, device_b=dev_c, fiber_cable_type=fct)
        fc_cd, _ = create_closure_cable(device_a=dev_c, device_b=dev_d, fiber_cable_type=fct)
        cls.s1 = fc_ab.fiber_strands.order_by("position").first()
        cls.t1 = fc_bc.fiber_strands.order_by("position").first()
        # u1 lands A-side on C and B-side on D: read from A, B, a plain cable
        # and then D, its B landing is the entry.
        cls.u1 = fc_cd.fiber_strands.order_by("position").first()
        connect_front_ports(cls.s1.front_port_b, cls.t1.front_port_a)
        plan = SplicePlan.objects.create(closure=cls.dev_b, name="FE plan", status=SplicePlanStatusChoices.ARCHIVED)
        tray = make_tray_module(cls.dev_b, make_tray_type(pair.mfr, "FE Tray"), "Bay 1")
        cls.entry = SplicePlanEntry.objects.create(
            plan=plan, tray=tray, fiber_a=cls.s1.front_port_b, fiber_b=cls.t1.front_port_a
        )

    def _rear(self, fp_id):
        return PortMapping.objects.get(front_port_id=fp_id).rear_port_id

    def test_strand_hops_expand_to_ports_cables_and_splice_entries(self):
        path = make_strand_path(self.s1, self.t1, end_a=self.s1.front_port_a, end_b=self.t1.front_port_b)
        types_and_ids = [(e["type"], e["id"]) for e in flat_entries(path)]
        assert types_and_ids == [
            ("front_port", self.s1.front_port_a_id),
            ("rear_port", self._rear(self.s1.front_port_a_id)),
            ("cable", self.s1.fiber_cable.cable_id),
            ("rear_port", self._rear(self.s1.front_port_b_id)),
            ("front_port", self.s1.front_port_b_id),
            ("splice_entry", self.entry.pk),
            ("front_port", self.t1.front_port_a_id),
            ("rear_port", self._rear(self.t1.front_port_a_id)),
            ("cable", self.t1.fiber_cable.cable_id),
            ("rear_port", self._rear(self.t1.front_port_b_id)),
            ("front_port", self.t1.front_port_b_id),
        ]
        assert [h["type"] for h in build_hops(flat_entries(path))] == ["device", "cable", "device", "cable", "device"]

    def test_a_path_read_from_its_b_end_orients_each_strand(self):
        path = make_strand_path(self.t1, self.s1, end_a=self.t1.front_port_b, end_b=self.s1.front_port_a)
        fps = [e["id"] for e in flat_entries(path) if e["type"] == "front_port"]
        assert fps == [
            self.t1.front_port_b_id,
            self.t1.front_port_a_id,
            self.s1.front_port_b_id,
            self.s1.front_port_a_id,
        ]

    def test_plain_cable_and_provider_hops_stay_single_entries(self):
        span = make_provider_circuit("FE")
        plain = Cable.objects.create()
        path = make_strand_path(self.s1, plain, span.circuit, end_a=self.s1.front_port_a)
        tail = [(e["type"], e["id"]) for e in flat_entries(path)][-2:]
        assert tail == [("cable", plain.pk), ("provider_circuit", span.circuit.pk)]

    def _front_ports(self, path):
        return [e["id"] for e in flat_entries(path) if e["type"] == "front_port"]

    def test_a_strand_after_a_plain_cable_is_oriented_by_the_b_end(self):
        """Strand -> plain cable -> strand landed B-first: the exit is the landing on the B end's device."""
        path = make_strand_path(
            self.s1, Cable.objects.create(), self.u1, end_a=self.s1.front_port_a, end_b=self.u1.front_port_a
        )
        assert self._front_ports(path) == [
            self.s1.front_port_a_id,
            self.s1.front_port_b_id,
            self.u1.front_port_b_id,
            self.u1.front_port_a_id,
        ]

    def test_a_strand_after_a_plain_cable_is_oriented_by_the_next_strand(self):
        path = make_strand_path(
            self.s1, Cable.objects.create(), self.u1, self.t1, end_a=self.s1.front_port_a, end_b=self.t1.front_port_a
        )
        assert self._front_ports(path) == [
            self.s1.front_port_a_id,
            self.s1.front_port_b_id,
            self.u1.front_port_b_id,
            self.u1.front_port_a_id,
            self.t1.front_port_b_id,
            self.t1.front_port_a_id,
        ]

    def test_a_path_without_ends_reads_each_strand_a_to_b(self):
        assert self._front_ports(make_strand_path(self.s1)) == [self.s1.front_port_a_id, self.s1.front_port_b_id]

    def test_half_landed_strand_and_unmapped_port(self):
        from netbox_fms.signals import fms_portmapping_bypass

        FiberStrand.objects.filter(pk=self.s1.pk).update(front_port_b=None)
        with fms_portmapping_bypass():
            PortMapping.objects.filter(front_port_id=self.s1.front_port_a_id).delete()
        self.s1.refresh_from_db()
        path = make_strand_path(self.s1, end_a=self.s1.front_port_a)
        assert [(e["type"], e["id"]) for e in flat_entries(path)] == [
            ("front_port", self.s1.front_port_a_id),
            ("cable", self.s1.fiber_cable.cable_id),
        ]
