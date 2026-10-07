"""find_assignable_path_groups (#196 spec section 3): filters and contiguity-first ranking."""

import pytest
from dcim.choices import DeviceStatusChoices
from dcim.models import Cable, Device, Site
from django.test import TestCase
from tenancy.models import Tenant

from netbox_fms.assignment import _device_sequence, _group_is_contiguous, find_assignable_path_groups, is_contiguous
from netbox_fms.choices import FiberCircuitStatusChoices
from netbox_fms.models import FiberCableType, FiberCircuit, FiberStrandPath
from netbox_fms.path_analysis import run_reconcile
from netbox_fms.services import create_closure_cable
from tests.conftest import assign_strand_path, connect_front_ports, make_closure_pair, make_strand_path

ACTIVE, PLANNED = FiberCircuitStatusChoices.ACTIVE, FiberCircuitStatusChoices.PLANNED


@pytest.mark.parametrize(
    ("mappings", "expected"),
    [
        ([(11, 1), (11, 2)], True),
        ([(11, 1), (11, 3)], False),
        # Tube 1 position 2 next to tube 2 position 1: consecutive numbers, different rear ports (#197).
        ([(11, 2), (12, 1)], False),
    ],
)
def test_contiguity_is_adjacent_positions_of_one_rear_port(mappings, expected):
    assert is_contiguous(mappings) is expected


class PickerCase(TestCase):
    """A -- AB (4 lc strands, two tubes of 2) -- B -- BC (4 lc strands) -- C, strand 1 spliced through at B."""

    @classmethod
    def setUpTestData(cls):
        pair = make_closure_pair("PK")
        cls.dev_a, cls.dev_b = pair.dev_a, pair.dev_b
        cls.dev_c = Device.objects.create(name="PK-C", site=pair.site, device_type=pair.device_type, role=pair.role)
        cls.fct = FiberCableType.objects.create(
            manufacturer=pair.mfr, model="PK-4", strand_count=4, construction="loose_tube"
        )
        from netbox_fms.models import BufferTubeTemplate

        BufferTubeTemplate.objects.create(fiber_cable_type=cls.fct, name="T1", position=1, fiber_count=2)
        BufferTubeTemplate.objects.create(fiber_cable_type=cls.fct, name="T2", position=2, fiber_count=2)
        cls.fc_ab, _ = create_closure_cable(
            device_a=cls.dev_a, device_b=cls.dev_b, fiber_cable_type=cls.fct, port_type="lc"
        )
        cls.fc_bc, _ = create_closure_cable(
            device_a=cls.dev_b, device_b=cls.dev_c, fiber_cable_type=cls.fct, port_type="lc"
        )
        cls.ab = list(cls.fc_ab.fiber_strands.order_by("position"))
        cls.bc = list(cls.fc_bc.fiber_strands.order_by("position"))
        connect_front_ports(cls.ab[0].front_port_b, cls.bc[0].front_port_a)
        run_reconcile()

    @staticmethod
    def groups(strand_count=1, **kwargs):
        kwargs.setdefault("circuit_status", ACTIVE)
        return find_assignable_path_groups(strand_count, **kwargs)

    def path_of(self, strand):
        return FiberStrandPath.objects.get(hops__strand=strand)


class TestPickerFilters(PickerCase):
    def test_every_complete_unassigned_path_is_offered_grouped_by_route(self):
        groups = self.groups()
        assert {g.route_key for g in groups} == {self.path_of(s).route_key for s in self.ab + self.bc}
        assert all(len(g.paths) == 1 for g in groups)
        assert sum(len(g.paths) for g in groups) == 7  # 8 strands, strand 1 of each cable spliced into one path

    def test_assigned_and_defective_paths_are_skipped(self):
        circuit = FiberCircuit.objects.create(name="PK-C1", strand_count=1, status=ACTIVE)
        assign_strand_path(circuit, self.path_of(self.ab[1]))
        FiberStrandPath.objects.filter(pk=self.path_of(self.ab[2]).pk).update(is_defective=True)
        offered = {p.pk for g in self.groups() for p in g.paths}
        assert self.path_of(self.ab[1]).pk not in offered
        assert self.path_of(self.ab[2]).pk not in offered

    def test_a_path_with_only_an_inactive_assignment_is_still_offered(self):
        circuit = FiberCircuit.objects.create(name="PK-C2", strand_count=1, status=ACTIVE)
        path = self.path_of(self.ab[1])
        assign_strand_path(circuit, path, active=False)
        assert path.pk in {p.pk for g in self.groups() for p in g.paths}

    def test_incomplete_paths_only_when_allowed(self):
        from dcim.models import PortMapping

        from netbox_fms.signals import fms_portmapping_bypass

        with fms_portmapping_bypass():  # unmapping the far landing leaves strand 4 open at C
            PortMapping.objects.filter(front_port=self.bc[3].front_port_b).delete()
        run_reconcile()
        incomplete = self.path_of(self.bc[3])
        assert incomplete.completeness == "terminated_open"
        assert incomplete.pk not in {p.pk for g in self.groups() for p in g.paths}
        assert incomplete.pk in {p.pk for g in self.groups(allow_incomplete=True) for p in g.paths}

    def test_proposed_paths_only_for_planned_circuits(self):
        self.dev_c.status = DeviceStatusChoices.STATUS_PLANNED
        self.dev_c.save()
        run_reconcile()
        proposed = {self.path_of(s).pk for s in self.bc[1:]}
        assert proposed.isdisjoint(p.pk for g in self.groups() for p in g.paths)
        assert proposed <= {p.pk for g in self.groups(circuit_status=PLANNED) for p in g.paths}

    def test_must_pass_through_is_an_ordered_device_list(self):
        through = self.path_of(self.ab[0])
        assert through.pk in {p.pk for g in self.groups(must_pass_through=[self.dev_b]) for p in g.paths}
        assert [g.paths[0].pk for g in self.groups(must_pass_through=[self.dev_a, self.dev_b, self.dev_c])] == [
            through.pk
        ]
        assert self.groups(must_pass_through=[self.dev_c, self.dev_a]) == []

    def test_avoid_devices_cables_sites_and_tenants(self):
        through = self.path_of(self.ab[0])
        remaining = {p.pk for g in self.groups(avoid_devices=[self.dev_c]) for p in g.paths}
        assert remaining == {self.path_of(s).pk for s in self.ab[1:]}
        assert through.pk not in {p.pk for g in self.groups(avoid_cables=[self.fc_bc.cable]) for p in g.paths}
        far_site = Site.objects.create(name="PK far", slug="pk-far")
        Device.objects.filter(pk=self.dev_c.pk).update(site=far_site)
        assert through.pk not in {p.pk for g in self.groups(avoid_sites=[far_site]) for p in g.paths}
        tenant = Tenant.objects.create(name="PK tenant", slug="pk-tenant")
        Cable.objects.filter(pk=self.fc_ab.cable_id).update(tenant=tenant)
        assert {p.pk for g in self.groups(avoid_tenants=[tenant]) for p in g.paths} == {
            self.path_of(s).pk for s in self.bc[1:]
        }

    def test_ends_at_requires_each_device_to_hold_an_end(self):
        at_a = {p.pk for g in self.groups(ends_at=self.dev_a) for p in g.paths}
        assert at_a == {self.path_of(s).pk for s in self.ab}
        assert [g.paths[0].pk for g in self.groups(ends_at=(self.dev_a, self.dev_c))] == [self.path_of(self.ab[0]).pk]


class TestPickerRanking(PickerCase):
    def test_contiguous_same_tube_pairs_rank_first_then_hop_count_then_position(self):
        groups = self.groups(strand_count=2)
        keys = [(g.is_contiguous, g.hop_count, g.lowest_position, g.path_ids) for g in groups]
        # AB strands 3+4 (tube 2) and BC strands 3+4 are contiguous one-hop pairs; AB/BC strands 2+3 straddle tubes.
        assert keys[0][:3] == (True, 1, 3)
        assert keys[1][:3] == (True, 1, 3)
        assert all(k[0] is False for k in keys[2:])
        assert all(len(g.paths) == 2 and g.route_key for g in groups)

    def test_groups_smaller_than_the_strand_count_are_dropped(self):
        assert self.groups(strand_count=5) == []
        two_hop = self.groups(strand_count=1, must_pass_through=[self.dev_a, self.dev_c])
        assert [g.hop_count for g in two_hop] == [2]

    def test_a_strand_whose_port_lost_its_mapping_is_never_contiguous(self):
        from dcim.models import PortMapping

        from netbox_fms.signals import fms_portmapping_bypass

        with fms_portmapping_bypass():
            PortMapping.objects.filter(front_port=self.ab[2].front_port_a).delete()
        run_reconcile()  # strand 3 is now open at A, so it is offered only with allow_incomplete
        groups = self.groups(strand_count=2, allow_incomplete=True)
        pair = next(g for g in groups if self.path_of(self.ab[2]).pk in g.path_ids)
        assert pair.is_contiguous is False

    def test_a_path_stored_b_first_is_oriented_by_its_end_devices(self):
        strand = self.ab[3]
        flipped = make_strand_path(strand, end_a=strand.front_port_b, end_b=strand.front_port_a)
        assert _device_sequence(flipped) == [self.dev_b.pk, self.dev_a.pk]
        found = self.groups(must_pass_through=[self.dev_b, self.dev_a])
        assert [p.pk for g in found for p in g.paths] == [flipped.pk]


class TestPickerPlainAndProviderHops(TestCase):
    """Strandless paths rank by hop count only and count their devices through cable terminations."""

    @classmethod
    def setUpTestData(cls):
        from dcim.models import FrontPort, RearPort

        from tests.conftest import make_provider_circuit, make_strand_path

        pair = make_closure_pair("PKP")
        cls.dev_a, cls.dev_c = pair.dev_a, pair.dev_b
        rp_a = RearPort.objects.create(device=cls.dev_a, name="PKP-RP", type="lc", positions=1)
        fp_a = FrontPort.objects.create(device=cls.dev_a, name="PKP-FA", type="lc")
        fp_c = FrontPort.objects.create(device=cls.dev_c, name="PKP-FC", type="lc")
        span = make_provider_circuit("PKP")
        plain = Cable.objects.create(a_terminations=[rp_a], b_terminations=[span.term_a])
        cls.path = make_strand_path(plain, span.circuit, end_a=fp_a, end_b=fp_c)

    def test_devices_come_from_terminations_and_the_group_is_not_contiguous(self):
        (group,) = find_assignable_path_groups(1, circuit_status=ACTIVE, must_pass_through=[self.dev_a])
        assert group.path_ids == [self.path.pk]
        assert (group.is_contiguous, group.hop_count, group.lowest_position) == (False, 2, 0)
        assert find_assignable_path_groups(1, circuit_status=ACTIVE, avoid_devices=[self.dev_c]) == []


class TestContiguityHoldsOnEveryCable(PickerCase):
    """Contiguity is judged on every cable of the route, not just the first."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        connect_front_ports(cls.ab[1].front_port_b, cls.bc[2].front_port_a)
        run_reconcile()

    def test_a_group_split_on_the_second_cable_ranks_below_a_contiguous_group(self):
        groups = self.groups(strand_count=2)
        spliced = self.path_of(self.ab[1]).route_key
        split = next(g for g in groups if g.route_key == spliced)
        assert split.hop_count == 2
        assert split.is_contiguous is False  # AB 1+2 share tube 1, BC 1+3 straddle tubes
        contiguous = next(g for g in groups if g.is_contiguous)
        assert groups.index(contiguous) < groups.index(split)

    def test_paths_that_cross_a_cable_differently_are_never_contiguous(self):
        strand_path = self.path_of(self.ab[2])
        plain = make_strand_path(self.fc_ab.cable, end_a=self.ab[2].front_port_a, end_b=self.ab[2].front_port_b)
        assert plain.route_key == strand_path.route_key
        mapping_of = {self.ab[2].front_port_a_id: (1, 1)}
        assert _group_is_contiguous([strand_path, plain], mapping_of) is False
