from django.test import TestCase
from rest_framework.test import APIClient

from netbox_fms.choices import FiberCircuitStatusChoices
from netbox_fms.models import FiberCircuit, FiberCircuitNode, FiberCircuitPath


class TestFiberCircuitAPI(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.circuit = FiberCircuit.objects.create(
            name="API-Test",
            status=FiberCircuitStatusChoices.ACTIVE,
            strand_count=2,
        )

    def setUp(self):
        from django.contrib.auth import get_user_model

        user_model = get_user_model()
        self.user = user_model.objects.create_superuser("apicircuit", "apicircuit@test.com", "password")
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.user)

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
        from dcim.models import Cable, Device, DeviceRole, DeviceType, FrontPort, Manufacturer, Site

        site = Site.objects.create(name="Prot Site", slug="prot-site")
        mfr = Manufacturer.objects.create(name="Prot Mfr", slug="prot-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="ProtDev", slug="protdev")
        role = DeviceRole.objects.create(name="Prot Role", slug="prot-role")
        device = Device.objects.create(name="ProtDev-1", site=site, device_type=dt, role=role)
        fp = FrontPort.objects.create(device=device, name="ProtFP", type="lc")

        cls.cable = Cable.objects.create()
        cls.circuit = FiberCircuit.objects.create(
            name="Prot-Circuit",
            status=FiberCircuitStatusChoices.ACTIVE,
            strand_count=1,
        )
        cls.path = FiberCircuitPath.objects.create(
            circuit=cls.circuit,
            position=1,
            origin=fp,
            path=[{"type": "cable", "id": cls.cable.pk}],
            is_complete=False,
        )
        FiberCircuitNode.objects.create(path=cls.path, position=1, cable=cls.cable)

    def setUp(self):
        from django.contrib.auth import get_user_model

        user_model = get_user_model()
        self.user = user_model.objects.create_superuser("prottest", "prot@test.com", "password")
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.user)

    def test_query_by_cable(self):
        response = self.client_api.get(f"/api/plugins/fms/fiber-circuits/protecting/?cable={self.cable.pk}")
        assert response.status_code == 200
        assert len(response.data) >= 1

    def test_query_no_match(self):
        from dcim.models import Cable

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
        from dcim.models import Cable, Device, DeviceRole, DeviceType, FrontPort, Manufacturer, Site

        site = Site.objects.create(name="Bulk Site", slug="bulk-site")
        mfr = Manufacturer.objects.create(name="Bulk Mfr", slug="bulk-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="BulkDev", slug="bulkdev")
        role = DeviceRole.objects.create(name="Bulk Role", slug="bulk-role")
        device = Device.objects.create(name="BulkDev-1", site=site, device_type=dt, role=role)
        cls.fp = FrontPort.objects.create(device=device, name="BulkFP", type="lc")

        cls.cable1 = Cable.objects.create()
        cls.cable2 = Cable.objects.create()
        cls.cable3 = Cable.objects.create()

        # Circuit A rides cable1 and terminates on cls.fp.
        cls.circuit_a = FiberCircuit.objects.create(
            name="Bulk-A", status=FiberCircuitStatusChoices.ACTIVE, strand_count=1
        )
        path_a = FiberCircuitPath.objects.create(
            circuit=cls.circuit_a,
            position=1,
            origin=cls.fp,
            path=[{"type": "cable", "id": cls.cable1.pk}],
            is_complete=False,
        )
        FiberCircuitNode.objects.create(path=path_a, position=1, cable=cls.cable1)
        FiberCircuitNode.objects.create(path=path_a, position=2, front_port=cls.fp)

        # Circuit B rides cable1 and cable2. Cable3 carries nothing.
        cls.circuit_b = FiberCircuit.objects.create(
            name="Bulk-B", status=FiberCircuitStatusChoices.ACTIVE, strand_count=1
        )
        path_b = FiberCircuitPath.objects.create(
            circuit=cls.circuit_b,
            position=1,
            origin=cls.fp,
            path=[{"type": "cable", "id": cls.cable1.pk}],
            is_complete=False,
        )
        FiberCircuitNode.objects.create(path=path_b, position=1, cable=cls.cable1)
        FiberCircuitNode.objects.create(path=path_b, position=2, cable=cls.cable2)

    def setUp(self):
        from django.contrib.auth import get_user_model

        user_model = get_user_model()
        self.user = user_model.objects.create_superuser("bulkprot", "bulkprot@test.com", "password")
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.user)

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
