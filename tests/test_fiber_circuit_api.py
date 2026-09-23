from dcim.models import Cable, Device
from django.test import TestCase

from netbox_fms.choices import FiberCircuitStatusChoices
from netbox_fms.models import FiberCircuit, FiberCircuitNode, FiberCircuitPath
from tests.conftest import make_authed_client, make_front_port, make_infra


def make_protected_circuit(name, origin, node_refs):
    """Active circuit with one path from ``origin`` and one FiberCircuitNode
    per entry of ``node_refs``, each a single-key dict naming the node's
    reference FK (e.g. ``{"cable": cable}`` or ``{"front_port": fp}``)."""
    circuit = FiberCircuit.objects.create(name=name, status=FiberCircuitStatusChoices.ACTIVE, strand_count=1)
    path = FiberCircuitPath.objects.create(
        circuit=circuit,
        position=1,
        origin=origin,
        path=[{"type": "cable", "id": ref["cable"].pk} for ref in node_refs if "cable" in ref],
        is_complete=False,
    )
    for position, ref in enumerate(node_refs, start=1):
        FiberCircuitNode.objects.create(path=path, position=position, **ref)
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
        site, mfr, dt, role = make_infra("Prot")
        device = Device.objects.create(name="ProtDev-1", site=site, device_type=dt, role=role)
        fp = make_front_port(device, "ProtFP")
        cls.cable = Cable.objects.create()
        make_protected_circuit("Prot-Circuit", fp, [{"cable": cls.cable}])

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
        cls.circuit_a = make_protected_circuit("Bulk-A", cls.fp, [{"cable": cls.cable1}, {"front_port": cls.fp}])
        cls.circuit_b = make_protected_circuit("Bulk-B", cls.fp, [{"cable": cls.cable1}, {"cable": cls.cable2}])

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

        site, mfr, dt, role = make_infra("PCQ")
        device = Device.objects.create(name="PCQ-Dev", site=site, device_type=dt, role=role)
        origin = make_front_port(device, "PCQ-FP")
        cls.span = make_provider_circuit("Query")
        cls.riding = make_protected_circuit("Riding", origin, [{"provider_circuit": cls.span.circuit}])
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
