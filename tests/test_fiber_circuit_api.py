from dcim.models import Cable, Device
from django.test import TestCase

from netbox_fms.choices import FiberCircuitStatusChoices
from netbox_fms.models import (
    FiberCable,
    FiberCableType,
    FiberCircuit,
    FiberCircuitPath,
    FiberStrandPath,
    PathAnalysisQueue,
    PathAnomaly,
)
from tests.conftest import (
    assign_strand_path,
    client_with,
    make_authed_client,
    make_front_port,
    make_infra,
    make_strand_path,
)


def make_protected_circuit(name, *hops, end_a=None):
    """Active circuit with one assignment over a path of these hops (strands, cables, circuits)."""
    circuit = FiberCircuit.objects.create(name=name, status=FiberCircuitStatusChoices.ACTIVE, strand_count=1)
    assign_strand_path(circuit, make_strand_path(*hops, end_a=end_a))
    return circuit


class TestFiberCircuitAPI(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.circuit = FiberCircuit.objects.create(
            name="API-Test",
            status=FiberCircuitStatusChoices.ACTIVE,
            strand_count=2,
        )

    def setUp(self):
        self.client_api = make_authed_client("apicircuit")

    def test_list_circuits(self):
        response = self.client_api.get("/api/plugins/fms/fiber-circuits/")
        assert response.status_code == 200
        assert response.data["count"] >= 1

    def test_get_circuit(self):
        response = self.client_api.get(f"/api/plugins/fms/fiber-circuits/{self.circuit.pk}/")
        assert response.status_code == 200
        assert response.data["name"] == "API-Test"

    def test_create_circuit(self):
        response = self.client_api.post(
            "/api/plugins/fms/fiber-circuits/",
            {
                "name": "API-Create",
                "status": "planned",
                "strand_count": 4,
            },
        )
        assert response.status_code == 201


class TestProtectionQueryAPI(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cable = Cable.objects.create()
        make_protected_circuit("Prot-Circuit", cls.cable)

    def setUp(self):
        self.client_api = make_authed_client("prottest")

    def test_query_by_cable(self):
        response = self.client_api.get(f"/api/plugins/fms/fiber-circuits/protecting/?cable={self.cable.pk}")
        assert response.status_code == 200
        assert len(response.data) >= 1

    def test_query_no_match(self):
        other_cable = Cable.objects.create()
        response = self.client_api.get(f"/api/plugins/fms/fiber-circuits/protecting/?cable={other_cable.pk}")
        assert response.status_code == 200
        assert len(response.data) == 0


class TestProtectionBulkQueryAPI(TestCase):
    """Bulk impact queries on the protecting endpoint.

    Regression tests for jsenecal/netbox-fms#134: repeated GET params must
    union rather than last-one-wins, malformed IDs must 400 rather than
    crash, and POST must return the deduplicated grouped envelope.
    """

    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = make_infra("Bulk")
        device = Device.objects.create(name="BulkDev-1", site=site, device_type=dt, role=role)
        cls.fp = make_front_port(device, "BulkFP")

        cls.cable1 = Cable.objects.create()
        cls.cable2 = Cable.objects.create()
        cls.cable3 = Cable.objects.create()

        # Circuit A rides cable1 and terminates on cls.fp; circuit B rides
        # cable1 and cable2. Cable3 carries nothing.
        cls.circuit_a = make_protected_circuit("Bulk-A", cls.cable1, end_a=cls.fp)
        cls.circuit_b = make_protected_circuit("Bulk-B", cls.cable1, cls.cable2)

    def setUp(self):
        self.client_api = make_authed_client("bulkprot")

    URL = "/api/plugins/fms/fiber-circuits/protecting/"

    def test_get_repeated_params_return_union(self):
        response = self.client_api.get(f"{self.URL}?cable={self.cable1.pk}&cable={self.cable2.pk}")
        assert response.status_code == 200
        names = {c["name"] for c in response.data}
        assert names == {"Bulk-A", "Bulk-B"}

    def test_get_invalid_id_returns_400(self):
        response = self.client_api.get(f"{self.URL}?cable=abc")
        assert response.status_code == 400

    def test_post_groups_results_by_reference(self):
        response = self.client_api.post(
            self.URL,
            {"cable": [self.cable1.pk, self.cable2.pk, self.cable3.pk]},
            format="json",
        )
        assert response.status_code == 200, response.content
        result_ids = {c["id"] for c in response.data["results"]}
        assert result_ids == {self.circuit_a.pk, self.circuit_b.pk}
        assert response.data["by_reference"] == {
            "cable": {
                str(self.cable1.pk): sorted([self.circuit_a.pk, self.circuit_b.pk]),
                str(self.cable2.pk): [self.circuit_b.pk],
                str(self.cable3.pk): [],
            }
        }

    def test_post_combines_reference_types(self):
        response = self.client_api.post(
            self.URL,
            {"cable": [self.cable2.pk], "front_port": [self.fp.pk]},
            format="json",
        )
        assert response.status_code == 200, response.content
        result_ids = {c["id"] for c in response.data["results"]}
        assert result_ids == {self.circuit_a.pk, self.circuit_b.pk}
        assert response.data["by_reference"]["front_port"] == {str(self.fp.pk): [self.circuit_a.pk]}
        assert response.data["by_reference"]["cable"] == {str(self.cable2.pk): [self.circuit_b.pk]}

    def test_post_empty_body_returns_empty_envelope(self):
        response = self.client_api.post(self.URL, {}, format="json")
        assert response.status_code == 200, response.content
        assert response.data == {"results": [], "by_reference": {}}

    def test_post_unknown_key_returns_400(self):
        response = self.client_api.post(self.URL, {"cables": [self.cable1.pk]}, format="json")
        assert response.status_code == 400

    def test_post_non_integer_id_returns_400(self):
        response = self.client_api.post(self.URL, {"cable": ["abc"]}, format="json")
        assert response.status_code == 400

    def test_post_non_list_value_returns_400(self):
        response = self.client_api.post(self.URL, {"cable": self.cable1.pk}, format="json")
        assert response.status_code == 400

    def test_post_non_object_body_returns_400(self):
        response = self.client_api.post(self.URL, [self.cable1.pk], format="json")
        assert response.status_code == 400


class TestProviderCircuitQueries(TestCase):
    """Provider-maintenance impact queries (issue #135)."""

    @classmethod
    def setUpTestData(cls):
        from tests.conftest import make_provider_circuit

        cls.span = make_provider_circuit("Query")
        cls.riding = make_protected_circuit("Riding", cls.span.circuit)
        cls.riding.sync_provider_circuits()
        cls.other = FiberCircuit.objects.create(name="NotRiding", strand_count=1)

    def setUp(self):
        self.client_api = make_authed_client(username="pcq-api")

    def test_filter_by_provider(self):
        from netbox_fms.filters import FiberCircuitFilterSet

        fs = FiberCircuitFilterSet({"provider_id": [self.span.provider.pk]}, queryset=FiberCircuit.objects.all())
        assert list(fs.qs) == [self.riding]

    def test_filter_by_provider_circuit(self):
        from netbox_fms.filters import FiberCircuitFilterSet

        fs = FiberCircuitFilterSet({"provider_circuit_id": [self.span.circuit.pk]}, queryset=FiberCircuit.objects.all())
        assert list(fs.qs) == [self.riding]

    def test_protecting_endpoint_accepts_provider_circuit(self):
        response = self.client_api.get(
            f"/api/plugins/fms/fiber-circuits/protecting/?provider_circuit={self.span.circuit.pk}"
        )
        assert response.status_code == 200
        assert [c["id"] for c in response.json()] == [self.riding.pk]


class TestAssignAPI(TestCase):
    """The assign and acknowledge-route actions wrap assign_paths / acknowledge_route."""

    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = make_infra("AAPI")
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="AAPI-3", strand_count=3, construction="tight_buffer"
        )
        fc = FiberCable.objects.create(cable=Cable.objects.create(), fiber_cable_type=fct)
        s1, s2, s3 = list(fc.fiber_strands.order_by("position"))
        device = Device.objects.create(name="AAPI-Dev", site=site, device_type=dt, role=role)
        fp_a, fp_b = make_front_port(device, "AAPI-A"), make_front_port(device, "AAPI-B")
        cls.p1, cls.p2 = (make_strand_path(s, end_a=fp_a, end_b=fp_b) for s in (s1, s2))
        cls.open_path = make_strand_path(s3, end_a=fp_a)
        cls.circuit = FiberCircuit.objects.create(
            name="AAPI-C", strand_count=2, status=FiberCircuitStatusChoices.ACTIVE
        )
        cls.other = FiberCircuit.objects.create(name="AAPI-O", strand_count=2, status=FiberCircuitStatusChoices.ACTIVE)
        cls.url = f"/api/plugins/fms/fiber-circuits/{cls.circuit.pk}/"

    def setUp(self):
        self.client_api = make_authed_client("aapi")

    def test_assign_creates_assignments_in_the_given_order(self):
        response = self.client_api.post(self.url + "assign/", {"strand_paths": [self.p2.pk, self.p1.pk]}, format="json")
        assert response.status_code == 201, response.content
        assert [(a["position"], a["strand_path"]["id"]) for a in response.data] == [(1, self.p2.pk), (2, self.p1.pk)]

    def test_assign_refusals_are_400_with_the_reasons(self):
        response = self.client_api.post(self.url + "assign/", {"strand_paths": [self.open_path.pk]}, format="json")
        assert response.status_code == 400
        assert "not terminated at both ends" in response.data["strand_paths"][0]
        response = self.client_api.post(self.url + "assign/", {"strand_paths": [999_999]}, format="json")
        assert response.status_code == 400
        response = self.client_api.post(self.url + "assign/", {"strand_paths": []}, format="json")
        assert response.status_code == 400

    def test_circuit_permissions_alone_do_not_allow_the_actions(self):
        """Editing the circuit is not enough: assigning needs add and acknowledging change on its paths."""
        client = client_with(
            "aapi-circuitonly",
            [(FiberCircuit, ["add", "view", "change"], None), (FiberStrandPath, ["view"], None)],
        )
        assert client.post(self.url + "assign/", {"strand_paths": [self.p1.pk]}, format="json").status_code == 403
        assert client.post(self.url + "acknowledge-route/", {}, format="json").status_code == 403

    def test_assign_allows_incomplete_on_request(self):
        response = self.client_api.post(
            self.url + "assign/", {"strand_paths": [self.open_path.pk], "allow_incomplete": True}, format="json"
        )
        assert response.status_code == 201, response.content
        assert response.data[0]["delivered_incomplete"] is True

    def test_acknowledge_route_clears_broken_assignments(self):
        assign_strand_path(self.circuit, self.p1, assigned_hops=[], is_broken=True, broken_reason="hops_changed")
        FiberCircuit.objects.filter(pk=self.circuit.pk).update(is_broken=True)
        response = self.client_api.post(self.url + "acknowledge-route/", {}, format="json")
        assert response.status_code == 200, response.content
        assert response.data == {"acknowledged": 1, "is_broken": False}

    def test_assignments_cannot_be_posted_directly(self):
        response = self.client_api.post(
            "/api/plugins/fms/fiber-circuit-paths/", {"circuit": self.circuit.pk}, format="json"
        )
        assert response.status_code == 405

    def test_actions_need_the_assignment_permissions(self):
        viewer = client_with("aapi-viewer", [(FiberCircuit, ["view"], None), (FiberStrandPath, ["view"], None)])
        assert viewer.post(self.url + "assign/", {"strand_paths": [self.p1.pk]}, format="json").status_code == 403
        assert viewer.post(self.url + "acknowledge-route/", {}, format="json").status_code == 403

    def test_user_with_add_but_not_change_on_the_circuit_cannot_assign(self):
        """Assigning edits the circuit, so the change permission on that circuit gates it."""
        client = client_with(
            "aapi-addonly",
            [
                (FiberCircuit, ["add", "view"], None),
                (FiberCircuitPath, ["add"], None),
                (FiberStrandPath, ["view"], None),
            ],
        )
        response = client.post(self.url + "assign/", {"strand_paths": [self.p1.pk]}, format="json")
        assert response.status_code == 403
        assert not self.circuit.paths.exists()

    def test_fiber_assigner_without_add_on_the_circuit_can_assign_and_acknowledge(self):
        """The actions edit the circuit: POST maps to change_fibercircuit, not add."""
        client = client_with(
            "aapi-assigner",
            [
                (FiberCircuit, ["view", "change"], None),
                (FiberCircuitPath, ["add", "change"], None),
                (FiberStrandPath, ["view"], None),
            ],
        )
        response = client.post(self.url + "assign/", {"strand_paths": [self.p1.pk]}, format="json")
        assert response.status_code == 201, response.content
        FiberCircuitPath.objects.filter(circuit=self.circuit).update(is_broken=True, broken_reason="hops_changed")
        response = client.post(self.url + "acknowledge-route/", {}, format="json")
        assert response.status_code == 200, response.content
        assert response.data["acknowledged"] == 1

    def test_assign_is_refused_when_the_new_assignments_fall_outside_the_add_constraint(self):
        client = client_with(
            "aapi-addscoped",
            [
                (FiberCircuit, ["view", "change"], None),
                (FiberCircuitPath, ["add"], {"circuit__name": "AAPI-O"}),
                (FiberStrandPath, ["view"], None),
            ],
        )
        response = client.post(self.url + "assign/", {"strand_paths": [self.p1.pk]}, format="json")
        assert response.status_code == 403
        assert not self.circuit.paths.exists()

    def test_acknowledge_is_refused_when_the_assignments_fall_outside_the_change_constraint(self):
        assign_strand_path(self.circuit, self.p1, assigned_hops=[], is_broken=True, broken_reason="hops_changed")
        client = client_with(
            "aapi-changescoped",
            [
                (FiberCircuit, ["view", "change"], None),
                (FiberCircuitPath, ["change"], {"circuit__name": "AAPI-O"}),
            ],
        )
        response = client.post(self.url + "acknowledge-route/", {}, format="json")
        assert response.status_code == 403
        assert self.circuit.paths.get().is_broken is True

    def test_change_permission_constraint_on_the_circuit_is_enforced(self):
        client = client_with(
            "aapi-scoped",
            [
                (FiberCircuit, ["add", "view"], None),
                (FiberCircuit, ["change"], {"name": "AAPI-C"}),
                (FiberCircuitPath, ["add", "change"], None),
                (FiberStrandPath, ["view"], None),
            ],
        )
        other_url = f"/api/plugins/fms/fiber-circuits/{self.other.pk}/"
        assert client.post(other_url + "assign/", {"strand_paths": [self.p1.pk]}, format="json").status_code == 404
        assert client.post(other_url + "acknowledge-route/", {}, format="json").status_code == 404
        assert not self.other.paths.exists()
        assert client.post(self.url + "assign/", {"strand_paths": [self.p1.pk]}, format="json").status_code == 201
        assert client.post(self.url + "acknowledge-route/", {}, format="json").status_code == 200

    def test_assign_cannot_use_a_path_the_user_may_not_view(self):
        client = client_with(
            "aapi-pathscoped",
            [
                (FiberCircuit, ["add", "view", "change"], None),
                (FiberCircuitPath, ["add"], None),
                (FiberStrandPath, ["view"], {"pk": self.p1.pk}),
            ],
        )
        response = client.post(self.url + "assign/", {"strand_paths": [self.p1.pk, self.p2.pk]}, format="json")
        assert response.status_code == 400
        assert not self.circuit.paths.exists()
        response = client.post(self.url + "assign/", {"strand_paths": [self.p1.pk]}, format="json")
        assert response.status_code == 201, response.content


class TestPathFilters(TestCase):
    """The path, anomaly and queue filters over the read-only endpoints."""

    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = make_infra("PFLT")
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="PFLT-2", strand_count=2, construction="tight_buffer"
        )
        cls.fiber_cable_cable = Cable.objects.create()
        fc = FiberCable.objects.create(cable=cls.fiber_cable_cable, fiber_cable_type=fct)
        cls.strand = fc.fiber_strands.order_by("position").first()
        cls.device = Device.objects.create(name="PFLT-1", site=site, device_type=dt, role=role)
        cls.elsewhere = Device.objects.create(name="PFLT-2", site=site, device_type=dt, role=role)
        cls.fp = make_front_port(cls.device, "PFLT-A")
        cls.assigned = make_strand_path(cls.strand, end_a=cls.fp, end_b=cls.fp)
        cls.plain = Cable.objects.create()
        cls.free = make_strand_path(cls.plain)
        circuit = FiberCircuit.objects.create(name="PFLT-C", strand_count=1, status=FiberCircuitStatusChoices.ACTIVE)
        assign_strand_path(circuit, cls.assigned)
        PathAnomaly.objects.create(kind="loop", strand=cls.strand, front_port=cls.fp)
        PathAnomaly.objects.create(kind="dangling_reference")
        PathAnalysisQueue.objects.create(device=cls.device, reason="cable_changed")
        PathAnalysisQueue.objects.create(device=cls.elsewhere, reason="strand_changed")

    def setUp(self):
        self.client_api = make_authed_client("pflt")

    def ids(self, endpoint, query):
        response = self.client_api.get(f"/api/plugins/fms/{endpoint}/?{query}")
        assert response.status_code == 200, response.content
        return sorted(row["id"] for row in response.data["results"])

    def test_strand_path_filters(self):
        paths = "fiber-strand-paths"
        assert self.ids(paths, "assigned=true") == [self.assigned.pk]
        assert self.ids(paths, "assigned=false") == [self.free.pk]
        assert self.ids(paths, f"device_id={self.device.pk}") == [self.assigned.pk]
        assert self.ids(paths, f"device_id={self.elsewhere.pk}") == []
        assert self.ids(paths, f"strand_id={self.strand.pk}") == [self.assigned.pk]
        assert self.ids(paths, f"cable_id={self.fiber_cable_cable.pk}") == [self.assigned.pk]
        assert self.ids(paths, f"cable_id={self.plain.pk}") == [self.free.pk]
        assert self.ids(paths, f"end_a_port_id={self.fp.pk}") == [self.assigned.pk]
        assert self.ids(paths, f"end_b_port_id={self.fp.pk}") == [self.assigned.pk]
        assert self.ids(paths, "completeness=terminated_terminated") == [self.assigned.pk]

    def test_anomaly_and_queue_filters(self):
        assert len(self.ids("path-anomalies", "kind=loop")) == 1
        assert len(self.ids("path-anomalies", f"strand_id={self.strand.pk}")) == 1
        assert len(self.ids("path-anomalies", f"front_port_id={self.fp.pk}")) == 1
        assert len(self.ids("path-analysis-queue", f"device_id={self.device.pk}")) == 1
        assert len(self.ids("path-analysis-queue", "reason=strand_changed")) == 1
