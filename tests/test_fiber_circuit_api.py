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
