from django.test import TestCase
from rest_framework.test import APIClient

from netbox_fms.models import FiberCircuit, FiberCircuitPath


class TestTraceAction(TestCase):
    @classmethod
    def setUpTestData(cls):
        from dcim.models import Device, DeviceRole, DeviceType, FrontPort, Manufacturer, Site

        site = Site.objects.create(name="Trace Site", slug="trace-site")
        mfr = Manufacturer.objects.create(name="Trace Mfr", slug="trace-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Dev", slug="trace-dev")
        role = DeviceRole.objects.create(name="Trace Role", slug="trace-role")
        dev = Device.objects.create(name="Dev-T", site=site, device_type=dt, role=role)

        cls.fp = FrontPort.objects.create(device=dev, name="FP-T", type="lc")

        cls.circuit = FiberCircuit.objects.create(name="Test Circuit", strand_count=1)
        cls.path = FiberCircuitPath.objects.create(
            circuit=cls.circuit,
            position=1,
            origin=cls.fp,
            path=[{"type": "front_port", "id": cls.fp.pk}],
            is_complete=False,
        )

    def setUp(self):
        from django.contrib.auth import get_user_model

        user_model = get_user_model()
        self.user = user_model.objects.create_superuser("traceadmin", "t@t.com", "password")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_trace_action_returns_hops(self):
        url = f"/api/plugins/fms/fiber-circuit-paths/{self.path.pk}/trace/"
        resp = self.client.get(url)
        assert resp.status_code == 200, resp.content
        data = resp.json()
        assert "hops" in data
        assert "circuit_name" in data
        assert data["circuit_name"] == "Test Circuit"
        assert data["is_complete"] is False
        assert len(data["hops"]) >= 1

    def test_trace_action_404_invalid_id(self):
        url = "/api/plugins/fms/fiber-circuit-paths/99999/trace/"
        resp = self.client.get(url)
        assert resp.status_code == 404


class TestTraceDetailProviderCircuit(TestCase):
    """Trace-detail dispatch renders the provider-circuit panel (issue #135)."""

    @classmethod
    def setUpTestData(cls):
        from dcim.models import Device, DeviceRole, DeviceType, FrontPort, Manufacturer, Site

        from tests.conftest import make_provider_circuit

        site = Site.objects.create(name="TDPC Site", slug="tdpc-site")
        mfr = Manufacturer.objects.create(name="TDPC Mfr", slug="tdpc-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="TDPC", slug="tdpc-dev")
        role = DeviceRole.objects.create(name="TDPC Role", slug="tdpc-role")
        dev = Device.objects.create(name="TDPC-1", site=site, device_type=dt, role=role)
        fp = FrontPort.objects.create(device=dev, name="TDPC-FP", type="lc")

        cls.span = make_provider_circuit("TDPC")
        circuit = FiberCircuit.objects.create(name="TDPC Circuit", strand_count=1)
        cls.path = FiberCircuitPath.objects.create(
            circuit=circuit,
            position=1,
            origin=fp,
            path=[{"type": "provider_circuit", "id": cls.span.circuit.pk}],
            is_complete=False,
        )

    def setUp(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_superuser("tdpcadmin", "t@t.com", "password")
        self.client.force_login(user)

    def test_provider_circuit_detail_panel(self):
        url = f"/plugins/fms/fiber-circuit-paths/{self.path.pk}/trace-detail/provider_circuit/{self.span.circuit.pk}/"
        resp = self.client.get(url)
        assert resp.status_code == 200
        body = resp.content.decode()
        assert self.span.circuit.cid in body
        assert self.span.provider.name in body
