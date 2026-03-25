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
