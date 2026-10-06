"""Tests for the fiber circuit provisioning engine."""

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

from netbox_fms.choices import FiberCircuitStatusChoices, SplicePlanStatusChoices
from netbox_fms.models import FiberCircuit, SplicePlan, SpliceProject
from netbox_fms.provisioning import _generate_single_hop_candidates, create_circuit_from_proposal, find_fiber_paths
from tests.conftest import connect_tube_cable, make_closure_pair, make_mapped_rear_ports


def _setup_linear_network(site, mfr, num_closures, strands_per_cable=4):
    """Create a linear chain of closures connected by cables with properly mapped ports."""
    closures = []
    cables = []
    rp_ct = ContentType.objects.get_for_model(RearPort)

    for i in range(num_closures):
        dt, _ = DeviceType.objects.get_or_create(manufacturer=mfr, model=f"Net-Closure-{i}", slug=f"net-closure-{i}")
        role, _ = DeviceRole.objects.get_or_create(name="Net-Role", slug="net-role")
        device = Device.objects.create(name=f"Closure-{i}", site=site, device_type=dt, role=role)
        mt, _ = ModuleType.objects.get_or_create(manufacturer=mfr, model=f"Net-Tray-{i}")
        bay = ModuleBay.objects.create(device=device, name="Bay1")
        tray = Module.objects.create(device=device, module_bay=bay, module_type=mt)
        closures.append((device, tray))

    for i in range(num_closures - 1):
        dev_a, tray_a = closures[i]
        dev_b, tray_b = closures[i + 1]

        rp_a = RearPort.objects.create(
            device=dev_a, module=tray_a, name=f"RP-out-{i}", type="lc", positions=strands_per_cable
        )
        rp_b = RearPort.objects.create(
            device=dev_b, module=tray_b, name=f"RP-in-{i + 1}", type="lc", positions=strands_per_cable
        )

        for s in range(1, strands_per_cable + 1):
            fp_a = FrontPort.objects.create(device=dev_a, module=tray_a, name=f"FP-out-{i}-{s}", type="lc")
            PortMapping.objects.create(
                device=dev_a,
                front_port=fp_a,
                rear_port=rp_a,
                front_port_position=s,
                rear_port_position=s,
            )
            fp_b = FrontPort.objects.create(device=dev_b, module=tray_b, name=f"FP-in-{i + 1}-{s}", type="lc")
            PortMapping.objects.create(
                device=dev_b,
                front_port=fp_b,
                rear_port=rp_b,
                front_port_position=s,
                rear_port_position=s,
            )

        cable = Cable.objects.create()
        CableTermination.objects.create(cable=cable, cable_end="A", termination_type=rp_ct, termination_id=rp_a.pk)
        CableTermination.objects.create(cable=cable, cable_end="B", termination_type=rp_ct, termination_id=rp_b.pk)
        cables.append(cable)

    return closures, cables


class TestFindPaths(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name="FindPath Site", slug="findpath-site")
        cls.mfr = Manufacturer.objects.create(name="FindPath Mfr", slug="findpath-mfr")
        cls.closures, cls.cables = _setup_linear_network(cls.site, cls.mfr, num_closures=3, strands_per_cable=4)

    def test_find_single_path(self):
        origin_dev = self.closures[0][0]
        dest_dev = self.closures[-1][0]
        results = FiberCircuit.find_paths(
            origin_device=origin_dev,
            destination_device=dest_dev,
            strand_count=1,
            priorities=["hop_count"],
        )
        assert len(results) > 0

    def test_find_multi_strand_path(self):
        origin_dev = self.closures[0][0]
        dest_dev = self.closures[-1][0]
        results = FiberCircuit.find_paths(
            origin_device=origin_dev,
            destination_device=dest_dev,
            strand_count=2,
            priorities=["hop_count", "strand_adjacency"],
        )
        assert len(results) > 0
        assert all(len(r["strands"]) == 2 for r in results)

    def test_no_path_between_unconnected_devices(self):
        """Devices with no cable between them should return empty results."""
        # Create an isolated device
        dt, _ = DeviceType.objects.get_or_create(manufacturer=self.mfr, model="Isolated-Type", slug="isolated-type")
        role, _ = DeviceRole.objects.get_or_create(name="Net-Role", slug="net-role")
        isolated = Device.objects.create(name="Isolated", site=self.site, device_type=dt, role=role)

        results = FiberCircuit.find_paths(
            origin_device=self.closures[0][0],
            destination_device=isolated,
            strand_count=1,
            priorities=["hop_count"],
        )
        assert len(results) == 0

    def test_scoring_lowest_strand(self):
        """Results with lowest_strand priority should prefer lower positions."""
        origin_dev = self.closures[0][0]
        dest_dev = self.closures[-1][0]
        results = FiberCircuit.find_paths(
            origin_device=origin_dev,
            destination_device=dest_dev,
            strand_count=1,
            priorities=["lowest_strand"],
        )
        if len(results) >= 2:
            assert results[0]["lowest_position"] <= results[1]["lowest_position"]

    def test_proposal_contains_route(self):
        """Each proposal should contain the route as a list of device IDs."""
        origin_dev = self.closures[0][0]
        dest_dev = self.closures[-1][0]
        results = FiberCircuit.find_paths(
            origin_device=origin_dev,
            destination_device=dest_dev,
            strand_count=1,
            priorities=["hop_count"],
        )
        assert len(results) > 0
        route = results[0]["route"]
        assert route[0] == origin_dev.pk
        assert route[-1] == dest_dev.pk


class TestCreateFromProposal(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name="Create Site", slug="create-site")
        cls.mfr = Manufacturer.objects.create(name="Create Mfr", slug="create-mfr")
        cls.closures, cls.cables = _setup_linear_network(cls.site, cls.mfr, num_closures=2, strands_per_cable=4)

    def test_create_circuit_from_proposal(self):
        origin_dev = self.closures[0][0]
        dest_dev = self.closures[-1][0]
        results = FiberCircuit.find_paths(
            origin_device=origin_dev,
            destination_device=dest_dev,
            strand_count=1,
            priorities=["hop_count"],
        )
        assert len(results) > 0
        circuit = FiberCircuit.create_from_proposal(results[0], name_template="Test-{n}")
        assert circuit.pk is not None
        assert circuit.name == "Test-1"
        assert circuit.paths.count() == 1

    def test_auto_increment_name(self):
        origin_dev = self.closures[0][0]
        dest_dev = self.closures[-1][0]
        results = FiberCircuit.find_paths(
            origin_device=origin_dev,
            destination_device=dest_dev,
            strand_count=1,
            priorities=["hop_count"],
        )
        FiberCircuit.create_from_proposal(results[0], name_template="Inc-{n}")
        # Need fresh results for second circuit (strands may be taken)
        results2 = FiberCircuit.find_paths(
            origin_device=origin_dev,
            destination_device=dest_dev,
            strand_count=1,
            priorities=["hop_count"],
        )
        if results2:
            circuit2 = FiberCircuit.create_from_proposal(results2[0], name_template="Inc-{n}")
            assert circuit2.name == "Inc-2"

    def test_circuit_has_correct_status(self):
        origin_dev = self.closures[0][0]
        dest_dev = self.closures[-1][0]
        results = FiberCircuit.find_paths(
            origin_device=origin_dev,
            destination_device=dest_dev,
            strand_count=1,
            priorities=["hop_count"],
        )
        circuit = FiberCircuit.create_from_proposal(results[0], name_template="Status-{n}")
        assert circuit.status == FiberCircuitStatusChoices.PLANNED

    def test_circuit_path_has_nodes(self):
        origin_dev = self.closures[0][0]
        dest_dev = self.closures[-1][0]
        results = FiberCircuit.find_paths(
            origin_device=origin_dev,
            destination_device=dest_dev,
            strand_count=1,
            priorities=["hop_count"],
        )
        circuit = FiberCircuit.create_from_proposal(results[0], name_template="Nodes-{n}")
        path = circuit.paths.first()
        assert path is not None
        assert path.nodes.count() > 0

    def test_multi_strand_circuit(self):
        origin_dev = self.closures[0][0]
        dest_dev = self.closures[-1][0]
        results = FiberCircuit.find_paths(
            origin_device=origin_dev,
            destination_device=dest_dev,
            strand_count=2,
            priorities=["hop_count"],
        )
        assert len(results) > 0
        circuit = FiberCircuit.create_from_proposal(results[0], name_template="Multi-{n}")
        assert circuit.strand_count == 2
        assert circuit.paths.count() == 2


class TestCreateFromProposalWithSpliceProject(TestCase):
    """Tests for the splice_project and name parameters on create_circuit_from_proposal."""

    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name="SplProj Site", slug="splproj-site")
        cls.mfr = Manufacturer.objects.create(name="SplProj Mfr", slug="splproj-mfr")
        # 3 closures → 2 hops → intermediate closure needs splices
        cls.closures, cls.cables = _setup_linear_network(cls.site, cls.mfr, num_closures=3, strands_per_cable=4)

    def test_splice_project_creates_linked_plans(self):
        """When splice_project is provided, SplicePlans are created linked to the project."""
        project = SpliceProject.objects.create(name="Test Project")
        origin_dev = self.closures[0][0]
        dest_dev = self.closures[-1][0]
        results = FiberCircuit.find_paths(
            origin_device=origin_dev,
            destination_device=dest_dev,
            strand_count=1,
            priorities=["hop_count"],
        )
        assert len(results) > 0
        proposal = results[0]
        # Multi-hop proposals should have splices_needed at intermediate closure
        assert len(proposal["splices_needed"]) > 0

        circuit = FiberCircuit.create_from_proposal(proposal, name_template="SP-{n}", splice_project=project)
        assert circuit.pk is not None

        # A SplicePlan should now exist for the intermediate closure, linked to the project
        intermediate_dev = self.closures[1][0]
        plan = SplicePlan.objects.filter(closure=intermediate_dev, project=project).first()
        assert plan is not None
        assert plan.status == SplicePlanStatusChoices.DRAFT
        assert project.name in plan.name
        assert plan.entries.count() > 0

    def test_no_splice_project_preserves_existing_behavior(self):
        """When splice_project is None, existing SplicePlan lookup behavior is used."""
        origin_dev = self.closures[0][0]
        dest_dev = self.closures[-1][0]
        results = FiberCircuit.find_paths(
            origin_device=origin_dev,
            destination_device=dest_dev,
            strand_count=1,
            priorities=["hop_count"],
        )
        assert len(results) > 0
        proposal = results[0]
        assert len(proposal["splices_needed"]) > 0

        # No splice_project → no new SplicePlan created (none pre-exists)
        circuit = FiberCircuit.create_from_proposal(proposal, name_template="NoSP-{n}")
        assert circuit.pk is not None

        intermediate_dev = self.closures[1][0]
        # No plan should have been auto-created without a project
        assert SplicePlan.objects.filter(closure=intermediate_dev).count() == 0

    def test_literal_name_parameter(self):
        """The name parameter should be used as a literal circuit name."""
        origin_dev = self.closures[0][0]
        dest_dev = self.closures[-1][0]
        results = FiberCircuit.find_paths(
            origin_device=origin_dev,
            destination_device=dest_dev,
            strand_count=1,
            priorities=["hop_count"],
        )
        assert len(results) > 0
        circuit = FiberCircuit.create_from_proposal(
            results[0], name_template="Should-Not-Use-{n}", name="My Literal Name"
        )
        assert circuit.name == "My Literal Name"

    def test_splice_project_reuses_existing_plan(self):
        """If a plan already exists for (closure, project), it is reused via get_or_create."""
        project = SpliceProject.objects.create(name="Reuse Project")
        intermediate_dev = self.closures[1][0]
        existing_plan = SplicePlan.objects.create(
            closure=intermediate_dev,
            project=project,
            name="Pre-existing Plan",
            status=SplicePlanStatusChoices.DRAFT,
        )

        origin_dev = self.closures[0][0]
        dest_dev = self.closures[-1][0]
        results = FiberCircuit.find_paths(
            origin_device=origin_dev,
            destination_device=dest_dev,
            strand_count=1,
            priorities=["hop_count"],
        )
        assert len(results) > 0

        FiberCircuit.create_from_proposal(results[0], name_template="Reuse-{n}", splice_project=project)

        # Should still be only one plan for this (closure, project)
        plans = SplicePlan.objects.filter(closure=intermediate_dev, project=project)
        assert plans.count() == 1
        assert plans.first().pk == existing_plan.pk


def _tube_pairs(proposal):
    """The (entry_rp_id, exit_rp_id) pair of every strand's first hop in a proposal."""
    return {(s["hops"][0]["entry_rp_id"], s["hops"][0]["exit_rp_id"]) for s in proposal["strands"]}


class TestMultiTubeCablePairing(TestCase):
    """Regression tests for issue #197: the wizard crossed buffer tubes mid-cable.

    Two closures joined by a two-tube trunk (RP1/RP2 at each end, connectors
    1 and 2 on both ends). A strand entering on tube 1 must leave on tube 1.
    """

    @classmethod
    def setUpTestData(cls):
        pair = make_closure_pair("MTP")
        cls.dev_a, cls.dev_b = pair.dev_a, pair.dev_b
        (cls.rp_a1, cls.rp_a2), cls.fps_a = make_mapped_rear_ports(cls.dev_a, ["RP1", "RP2"], "A-{rp}-{i}", 2)
        (cls.rp_b1, cls.rp_b2), cls.fps_b = make_mapped_rear_ports(cls.dev_b, ["RP1", "RP2"], "B-{rp}-{i}", 2)
        cls.cable = Cable.objects.create()
        connect_tube_cable(cls.cable, [(cls.rp_a1, cls.rp_b1), (cls.rp_a2, cls.rp_b2)])

    def test_strands_never_cross_tubes(self):
        """Every proposed strand pairs a rear port with its same-connector far end."""
        results = find_fiber_paths(self.dev_a, self.dev_b, strand_count=1, priorities=["lowest_strand"])

        assert results
        same_tube = {(self.rp_a1.pk, self.rp_b1.pk), (self.rp_a2.pk, self.rp_b2.pk)}
        for proposal in results:
            assert _tube_pairs(proposal) <= same_tube, _tube_pairs(proposal)

    def test_ambiguous_connectorless_cable_yields_no_route(self):
        """Two connector-less rear ports per end cannot be paired, so no fiber is proposed."""
        CableTermination.objects.filter(cable=self.cable).update(connector=None)

        assert find_fiber_paths(self.dev_a, self.dev_b, strand_count=1) == []

    def test_asymmetric_connectorless_cable_yields_no_route(self):
        """One connector-less rear port on A facing two on B: no pair holds from both ends.

        Each B tube resolves to the single A rear port, but a trace entering
        from A sees two far candidates and refuses to cross. The wizard must
        not offer edges the trace cannot reproduce (issue #197).
        """
        CableTermination.objects.filter(cable=self.cable).update(connector=None)
        CableTermination.objects.filter(cable=self.cable, cable_end="A", termination_id=self.rp_a2.pk).delete()

        assert find_fiber_paths(self.dev_a, self.dev_b, strand_count=1) == []

    def test_default_ranking_prefers_contiguous_pair_over_fewer_hops(self):
        """A same-tube pair two hops away outranks a scattered direct pair by default.

        Strands of one circuit (a Tx/Rx pair) must share route and specs, so
        strand adjacency ranks ahead of hop count.
        """
        # Occupy RP1 position 1 and RP2 position 2, leaving the direct cable
        # only a cross-tube pair (RP1 position 2 + RP2 position 1).
        for rp, position in ((self.rp_a1, 1), (self.rp_a2, 2)):
            proposal = next(
                p
                for p in find_fiber_paths(self.dev_a, self.dev_b, strand_count=1)
                if p["strands"][0]["hops"][0]["entry_rp_id"] == rp.pk and p["strands"][0]["position"] == position
            )
            create_circuit_from_proposal(proposal, name=f"occupy {rp.name} {position}")

        # Detour A -- C -- B over single-tube cables with two free positions each.
        dev_c = Device.objects.create(
            name="MTP-C", site=self.dev_a.site, device_type=self.dev_a.device_type, role=self.dev_a.role
        )
        (rp_a3,), _ = make_mapped_rear_ports(self.dev_a, ["RP3"], "A-{rp}-{i}", 2)
        (rp_b3,), _ = make_mapped_rear_ports(self.dev_b, ["RP3"], "B-{rp}-{i}", 2)
        (rp_c_in, rp_c_out), _ = make_mapped_rear_ports(dev_c, ["IN", "OUT"], "C-{rp}-{i}", 2)
        connect_tube_cable(Cable.objects.create(), [(rp_a3, rp_c_in)])
        connect_tube_cable(Cable.objects.create(), [(rp_c_out, rp_b3)])

        results = find_fiber_paths(self.dev_a, self.dev_b, strand_count=2)

        assert {(c["hop_count"], c["is_contiguous"]) for c in results} == {(1, False), (2, True)}
        assert results[0]["hop_count"] == 2


def _avail(rp, position, cable_id=1):
    """One available position on a hop, as _find_available_strand_groups builds it.

    Rear port ``rp`` (1 or 2) is tube ``rp`` of the cable; front-port ids are
    derived so each position gets its own pair.
    """
    return {
        "cable_info": {"cable_id": cable_id},
        "position": position,
        "fp_entry_id": 100 * rp + position,
        "fp_exit_id": 200 * rp + position,
        "entry_rp_id": 10 + rp,
        "exit_rp_id": 20 + rp,
    }


class TestContiguityStaysWithinTube:
    """Regression tests for issue #197: adjacency never crosses a tube boundary.

    The last free fiber of tube 1 and the first free fiber of tube 2 carry
    consecutive position numbers but sit in different buffer tubes, so a
    strand group spanning them is not contiguous.
    """

    def test_cross_tube_group_is_not_contiguous(self):
        """Tube 1 position 2 next to tube 2 position 1: consecutive numbers, different rear ports."""
        candidates = _generate_single_hop_candidates([_avail(1, 2), _avail(2, 1)], 2, [1, 2])

        assert len(candidates) == 1
        assert candidates[0]["is_contiguous"] is False
        assert candidates[0]["lowest_position"] == 1
