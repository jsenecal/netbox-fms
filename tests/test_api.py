"""API endpoint coverage tests for netbox_fms plugin."""

from dcim.models import (
    Cable,
    Device,
    DeviceRole,
    DeviceType,
    FrontPort,
    Manufacturer,
    Module,
    ModuleBay,
    ModuleType,
    Site,
)
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from netbox_fms.models import (
    FiberCable,
    FiberCableType,
    FiberCircuit,
    FiberCircuitPath,
    SplicePlan,
    SplicePlanEntry,
    WavelengthService,
)


def _make_authed_client():
    """Create a superuser and return an authenticated APIClient."""
    user_model = get_user_model()
    user = user_model.objects.create_superuser("api-test", "api@test.com", "testpass")
    client = APIClient()
    client.force_authenticate(user)
    return client


def _make_base_infra(prefix="t"):
    """Create site, manufacturer, device type, role. Return (site, mfr, dt, role)."""
    site = Site.objects.create(name=f"{prefix} Site", slug=f"{prefix}-site")
    mfr = Manufacturer.objects.create(name=f"{prefix} Mfr", slug=f"{prefix}-mfr")
    dt = DeviceType.objects.create(manufacturer=mfr, model=f"{prefix} DT", slug=f"{prefix}-dt")
    role = DeviceRole.objects.create(name=f"{prefix} Role", slug=f"{prefix}-role")
    return site, mfr, dt, role


# ---------------------------------------------------------------------------
# Existing bulk-update and quick-add tests
# ---------------------------------------------------------------------------


class TestBulkUpdateAPI(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="API Site", slug="api-site")
        mfr = Manufacturer.objects.create(name="API Mfr", slug="api-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Closure", slug="api-closure")
        role = DeviceRole.objects.create(name="API Role", slug="api-role")
        cls.closure = Device.objects.create(name="C-API", site=site, device_type=dt, role=role)

        mt = ModuleType.objects.create(manufacturer=mfr, model="Tray")
        bay = ModuleBay.objects.create(device=cls.closure, name="Bay 1")
        cls.tray = Module.objects.create(device=cls.closure, module_bay=bay, module_type=mt)

        cls.fp1 = FrontPort.objects.create(device=cls.closure, module=cls.tray, name="F1", type="lc")
        cls.fp2 = FrontPort.objects.create(device=cls.closure, module=cls.tray, name="F2", type="lc")
        cls.fp3 = FrontPort.objects.create(device=cls.closure, module=cls.tray, name="F3", type="lc")
        cls.fp4 = FrontPort.objects.create(device=cls.closure, module=cls.tray, name="F4", type="lc")

        cls.plan = SplicePlan.objects.create(closure=cls.closure, name="API Plan")

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser("testadmin", "test@test.com", "password")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_bulk_add(self):
        url = f"/api/plugins/fms/splice-plans/{self.plan.pk}/bulk-update/"
        resp = self.client.post(
            url,
            {
                "add": [{"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk}],
                "remove": [],
            },
            format="json",
        )
        assert resp.status_code == 200, resp.content
        assert SplicePlanEntry.objects.filter(plan=self.plan).count() == 1

    def test_bulk_remove(self):
        SplicePlanEntry.objects.create(
            plan=self.plan,
            tray=self.tray,
            fiber_a=self.fp3,
            fiber_b=self.fp4,
        )
        url = f"/api/plugins/fms/splice-plans/{self.plan.pk}/bulk-update/"
        resp = self.client.post(
            url,
            {
                "add": [],
                "remove": [{"fiber_a": self.fp3.pk, "fiber_b": self.fp4.pk}],
            },
            format="json",
        )
        assert resp.status_code == 200, resp.content
        assert SplicePlanEntry.objects.filter(plan=self.plan).count() == 0

    def test_bulk_atomic_rollback(self):
        """Invalid add should rollback entire transaction."""
        url = f"/api/plugins/fms/splice-plans/{self.plan.pk}/bulk-update/"
        resp = self.client.post(
            url,
            {
                "add": [
                    {"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk},
                    {"fiber_a": 999999, "fiber_b": self.fp3.pk},  # Invalid
                ],
                "remove": [],
            },
            format="json",
        )
        assert resp.status_code == 400
        assert SplicePlanEntry.objects.filter(plan=self.plan).count() == 0


class TestQuickAddAPI(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="QA Site", slug="qa-site")
        mfr = Manufacturer.objects.create(name="QA Mfr", slug="qa-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Closure", slug="qa-closure")
        role = DeviceRole.objects.create(name="QA Role", slug="qa-role")
        cls.closure = Device.objects.create(name="C-QA", site=site, device_type=dt, role=role)

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser("qaadmin", "qa@test.com", "password")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_quick_add_creates_plan(self):
        url = "/api/plugins/fms/splice-plans/quick-add/"
        resp = self.client.post(
            url,
            {
                "name": "Quick Plan",
                "closure": self.closure.pk,
                "status": "draft",
                "description": "",
            },
            format="json",
        )
        assert resp.status_code == 201, resp.content
        assert resp.json()["name"] == "Quick Plan"
        assert SplicePlan.objects.filter(closure=self.closure).exists()

    def test_quick_add_duplicate_closure_fails(self):
        SplicePlan.objects.create(closure=self.closure, name="Existing")
        url = "/api/plugins/fms/splice-plans/quick-add/"
        resp = self.client.post(
            url,
            {
                "name": "Dupe Plan",
                "closure": self.closure.pk,
                "status": "draft",
            },
            format="json",
        )
        assert resp.status_code in (400, 500), f"Expected 400 or 500 but got {resp.status_code}"
        assert resp.status_code != 201  # Must not succeed


# ---------------------------------------------------------------------------
# FiberCircuit retrace action
# ---------------------------------------------------------------------------


class TestFiberCircuitRetraceAPI(TestCase):
    """POST /api/plugins/fms/fiber-circuits/{pk}/retrace/ should return 200."""

    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = _make_base_infra("retrace")
        cls.device = Device.objects.create(name="Dev-Retrace", site=site, device_type=dt, role=role)
        cls.fp = FrontPort.objects.create(device=cls.device, name="FP-Origin", type="lc")
        cls.circuit = FiberCircuit.objects.create(name="FC-Retrace", strand_count=1, status="planned")
        cls.path = FiberCircuitPath.objects.create(circuit=cls.circuit, position=1, origin=cls.fp)

    def setUp(self):
        self.client = _make_authed_client()

    def test_retrace_returns_200(self):
        url = f"/api/plugins/fms/fiber-circuits/{self.circuit.pk}/retrace/"
        resp = self.client.post(url, format="json")
        assert resp.status_code == 200, resp.content
        data = resp.json()
        assert data["name"] == "FC-Retrace"


# ---------------------------------------------------------------------------
# FiberCircuitPath trace action
# ---------------------------------------------------------------------------


class TestFiberCircuitPathTraceAPI(TestCase):
    """GET /api/plugins/fms/fiber-circuit-paths/{pk}/trace/ should return 200 with hops."""

    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = _make_base_infra("trace")
        cls.device = Device.objects.create(name="Dev-Trace", site=site, device_type=dt, role=role)
        cls.fp = FrontPort.objects.create(device=cls.device, name="FP-Trace", type="lc")
        cls.circuit = FiberCircuit.objects.create(name="FC-Trace", strand_count=1, status="planned")
        cls.path = FiberCircuitPath.objects.create(circuit=cls.circuit, position=1, origin=cls.fp)

    def setUp(self):
        self.client = _make_authed_client()

    def test_trace_returns_200_with_hops(self):
        url = f"/api/plugins/fms/fiber-circuit-paths/{self.path.pk}/trace/"
        resp = self.client.get(url)
        assert resp.status_code == 200, resp.content
        data = resp.json()
        assert "hops" in data
        assert data["circuit_name"] == "FC-Trace"
        assert "wavelength_services" in data


# ---------------------------------------------------------------------------
# WavelengthService stitch action
# ---------------------------------------------------------------------------


class TestWavelengthServiceStitchAPI(TestCase):
    """GET /api/plugins/fms/wavelength-services/{pk}/stitch/ should return 200."""

    @classmethod
    def setUpTestData(cls):
        cls.service = WavelengthService.objects.create(
            name="WS-Stitch",
            wavelength_nm="1550.12",
            status="planned",
        )

    def setUp(self):
        self.client = _make_authed_client()

    def test_stitch_returns_200_with_hops(self):
        url = f"/api/plugins/fms/wavelength-services/{self.service.pk}/stitch/"
        resp = self.client.get(url)
        assert resp.status_code == 200, resp.content
        data = resp.json()
        assert data["service_name"] == "WS-Stitch"
        assert "hops" in data
        assert isinstance(data["hops"], list)


# ---------------------------------------------------------------------------
# FiberCircuitProtecting API
# ---------------------------------------------------------------------------


class TestFiberCircuitProtectingAPI(TestCase):
    """GET /api/plugins/fms/fiber-circuits/protecting/ should return 200."""

    def setUp(self):
        self.client = _make_authed_client()

    def test_protecting_no_params_returns_empty(self):
        url = "/api/plugins/fms/fiber-circuits/protecting/"
        resp = self.client.get(url)
        assert resp.status_code == 200, resp.content
        assert resp.json() == []

    def test_protecting_with_cable_param(self):
        url = "/api/plugins/fms/fiber-circuits/protecting/?cable=999999"
        resp = self.client.get(url)
        assert resp.status_code == 200, resp.content
        assert resp.json() == []

    def test_protecting_with_front_port_param(self):
        url = "/api/plugins/fms/fiber-circuits/protecting/?front_port=999999"
        resp = self.client.get(url)
        assert resp.status_code == 200, resp.content
        assert resp.json() == []


# ---------------------------------------------------------------------------
# SplicePlan diff action
# ---------------------------------------------------------------------------


class TestSplicePlanDiffAPI(TestCase):
    """GET /api/plugins/fms/splice-plans/{pk}/diff/ should return 200."""

    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = _make_base_infra("diff")
        cls.closure = Device.objects.create(name="C-Diff", site=site, device_type=dt, role=role)
        cls.plan = SplicePlan.objects.create(closure=cls.closure, name="Diff Plan")

    def setUp(self):
        self.client = _make_authed_client()

    def test_diff_returns_200(self):
        url = f"/api/plugins/fms/splice-plans/{self.plan.pk}/diff/"
        resp = self.client.get(url)
        assert resp.status_code == 200, resp.content


# ---------------------------------------------------------------------------
# SplicePlan import-from-device action
# ---------------------------------------------------------------------------


class TestSplicePlanImportFromDeviceAPI(TestCase):
    """POST /api/plugins/fms/splice-plans/{pk}/import-from-device/ should return 200."""

    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = _make_base_infra("imp")
        cls.closure = Device.objects.create(name="C-Import", site=site, device_type=dt, role=role)
        cls.plan = SplicePlan.objects.create(closure=cls.closure, name="Import Plan")

    def setUp(self):
        self.client = _make_authed_client()

    def test_import_from_device_returns_200(self):
        url = f"/api/plugins/fms/splice-plans/{self.plan.pk}/import-from-device/"
        resp = self.client.post(url, format="json")
        assert resp.status_code == 200, resp.content
        data = resp.json()
        assert "imported" in data


# ---------------------------------------------------------------------------
# SplicePlan apply action
# ---------------------------------------------------------------------------


class TestSplicePlanApplyAPI(TestCase):
    """POST /api/plugins/fms/splice-plans/{pk}/apply/ should return 200."""

    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = _make_base_infra("apply")
        cls.closure = Device.objects.create(name="C-Apply", site=site, device_type=dt, role=role)
        cls.plan = SplicePlan.objects.create(closure=cls.closure, name="Apply Plan")

    def setUp(self):
        self.client = _make_authed_client()

    def test_apply_empty_plan_returns_200(self):
        url = f"/api/plugins/fms/splice-plans/{self.plan.pk}/apply/"
        resp = self.client.post(url, format="json")
        assert resp.status_code == 200, resp.content


# ---------------------------------------------------------------------------
# ClosureStrands API
# ---------------------------------------------------------------------------


class TestClosureStrandsAPI(TestCase):
    """GET /api/plugins/fms/closure-strands/{device_id}/ should return 200."""

    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = _make_base_infra("cstrands")
        cls.device = Device.objects.create(name="Closure-Strands", site=site, device_type=dt, role=role)

    def setUp(self):
        self.client = _make_authed_client()

    def test_closure_strands_empty_returns_200(self):
        url = f"/api/plugins/fms/closure-strands/{self.device.pk}/"
        resp = self.client.get(url)
        assert resp.status_code == 200, resp.content
        data = resp.json()
        assert data["cables"] == []
        assert isinstance(data["trays"], list)


# ---------------------------------------------------------------------------
# ProvisionPorts API
# ---------------------------------------------------------------------------


class TestProvisionPortsAPI(TestCase):
    """POST /api/plugins/fms/provision-ports/ should create ports and return 201."""

    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = _make_base_infra("prov")
        cls.device = Device.objects.create(name="Dev-Prov", site=site, device_type=dt, role=role)
        # Create a FiberCableType with strand_count=2
        cls.fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="Test FCT",
            construction="tight_buffer",
            fiber_type="os2",
            strand_count=2,
        )
        # Create a Cable (minimal)
        cable = Cable.objects.create()
        # Create FiberCable (auto-instantiates strands from type)
        cls.fiber_cable = FiberCable.objects.create(cable=cable, fiber_cable_type=cls.fct)

    def setUp(self):
        self.client = _make_authed_client()

    def test_provision_ports_returns_201(self):
        url = "/api/plugins/fms/provision-ports/"
        resp = self.client.post(
            url,
            {
                "fiber_cable_id": self.fiber_cable.pk,
                "device_id": self.device.pk,
            },
            format="json",
        )
        assert resp.status_code == 201, resp.content
        data = resp.json()
        assert data["count"] == 2
        assert "rear_port_id" in data
        assert len(data["front_port_ids"]) == 2

    def test_provision_ports_missing_cable_returns_404(self):
        url = "/api/plugins/fms/provision-ports/"
        resp = self.client.post(
            url,
            {
                "fiber_cable_id": 999999,
                "device_id": self.device.pk,
            },
            format="json",
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# WDM CRUD list endpoints
# ---------------------------------------------------------------------------


class TestWdmListEndpoints(TestCase):
    """GET list endpoints for WDM models should return 200."""

    def setUp(self):
        self.client = _make_authed_client()

    def test_wdm_profiles_list(self):
        resp = self.client.get("/api/plugins/fms/wdm-profiles/")
        assert resp.status_code == 200, resp.content

    def test_wdm_channel_templates_list(self):
        resp = self.client.get("/api/plugins/fms/wdm-channel-templates/")
        assert resp.status_code == 200, resp.content

    def test_wdm_nodes_list(self):
        resp = self.client.get("/api/plugins/fms/wdm-nodes/")
        assert resp.status_code == 200, resp.content

    def test_wdm_trunk_ports_list(self):
        resp = self.client.get("/api/plugins/fms/wdm-trunk-ports/")
        assert resp.status_code == 200, resp.content

    def test_wavelength_channels_list(self):
        resp = self.client.get("/api/plugins/fms/wavelength-channels/")
        assert resp.status_code == 200, resp.content

    def test_wavelength_services_list(self):
        resp = self.client.get("/api/plugins/fms/wavelength-services/")
        assert resp.status_code == 200, resp.content


# ---------------------------------------------------------------------------
# Core CRUD list endpoints
# ---------------------------------------------------------------------------


class TestCoreListEndpoints(TestCase):
    """GET list endpoints for core models should return 200."""

    def setUp(self):
        self.client = _make_authed_client()

    def test_cable_types_list(self):
        resp = self.client.get("/api/plugins/fms/cable-types/")
        assert resp.status_code == 200, resp.content

    def test_buffer_tube_templates_list(self):
        resp = self.client.get("/api/plugins/fms/buffer-tube-templates/")
        assert resp.status_code == 200, resp.content

    def test_ribbon_templates_list(self):
        resp = self.client.get("/api/plugins/fms/ribbon-templates/")
        assert resp.status_code == 200, resp.content

    def test_cable_element_templates_list(self):
        resp = self.client.get("/api/plugins/fms/cable-element-templates/")
        assert resp.status_code == 200, resp.content

    def test_fiber_cables_list(self):
        resp = self.client.get("/api/plugins/fms/fiber-cables/")
        assert resp.status_code == 200, resp.content

    def test_buffer_tubes_list(self):
        resp = self.client.get("/api/plugins/fms/buffer-tubes/")
        assert resp.status_code == 200, resp.content

    def test_ribbons_list(self):
        resp = self.client.get("/api/plugins/fms/ribbons/")
        assert resp.status_code == 200, resp.content

    def test_fiber_strands_list(self):
        resp = self.client.get("/api/plugins/fms/fiber-strands/")
        assert resp.status_code == 200, resp.content

    def test_cable_elements_list(self):
        resp = self.client.get("/api/plugins/fms/cable-elements/")
        assert resp.status_code == 200, resp.content

    def test_splice_projects_list(self):
        resp = self.client.get("/api/plugins/fms/splice-projects/")
        assert resp.status_code == 200, resp.content

    def test_splice_plans_list(self):
        resp = self.client.get("/api/plugins/fms/splice-plans/")
        assert resp.status_code == 200, resp.content

    def test_splice_plan_entries_list(self):
        resp = self.client.get("/api/plugins/fms/splice-plan-entries/")
        assert resp.status_code == 200, resp.content

    def test_closure_cable_entries_list(self):
        resp = self.client.get("/api/plugins/fms/closure-cable-entries/")
        assert resp.status_code == 200, resp.content

    def test_slack_loops_list(self):
        resp = self.client.get("/api/plugins/fms/slack-loops/")
        assert resp.status_code == 200, resp.content

    def test_fiber_circuits_list(self):
        resp = self.client.get("/api/plugins/fms/fiber-circuits/")
        assert resp.status_code == 200, resp.content

    def test_fiber_circuit_paths_list(self):
        resp = self.client.get("/api/plugins/fms/fiber-circuit-paths/")
        assert resp.status_code == 200, resp.content

    def test_fiber_circuit_nodes_list(self):
        resp = self.client.get("/api/plugins/fms/fiber-circuit-nodes/")
        assert resp.status_code == 200, resp.content


# ---------------------------------------------------------------------------
# Optimistic Locking
# ---------------------------------------------------------------------------


class TestOptimisticLocking(TestCase):
    """Bulk-update should reject saves when the plan was modified by another user."""

    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = _make_base_infra("lock")
        cls.closure = Device.objects.create(name="C-Lock", site=site, device_type=dt, role=role)

        mt = ModuleType.objects.create(manufacturer=mfr, model="Lock Tray")
        bay = ModuleBay.objects.create(device=cls.closure, name="Bay Lock")
        cls.tray = Module.objects.create(device=cls.closure, module_bay=bay, module_type=mt)

        cls.fp1 = FrontPort.objects.create(device=cls.closure, module=cls.tray, name="LF1", type="lc")
        cls.fp2 = FrontPort.objects.create(device=cls.closure, module=cls.tray, name="LF2", type="lc")
        cls.fp3 = FrontPort.objects.create(device=cls.closure, module=cls.tray, name="LF3", type="lc")
        cls.fp4 = FrontPort.objects.create(device=cls.closure, module=cls.tray, name="LF4", type="lc")

    def setUp(self):
        self.plan = SplicePlan.objects.create(closure=self.closure, name="Lock Plan")
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser("lockuser", "lock@test.com", "password")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = f"/api/plugins/fms/splice-plans/{self.plan.pk}/bulk-update/"

    def test_save_succeeds_with_correct_version(self):
        """Save with matching plan_version should succeed."""
        version = self.plan.last_updated.isoformat()
        resp = self.client.post(
            self.url,
            {
                "add": [{"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk}],
                "remove": [],
                "plan_version": version,
            },
            format="json",
        )
        assert resp.status_code == 200, resp.content
        assert SplicePlanEntry.objects.filter(plan=self.plan).count() == 1
        # Response should include new plan_version
        assert resp.json().get("plan_version") is not None

    def test_save_rejected_with_stale_version(self):
        """Save with outdated plan_version should be rejected with 409."""
        stale_version = self.plan.last_updated.isoformat()

        # Simulate another user modifying the plan
        SplicePlanEntry.objects.create(
            plan=self.plan, tray=self.tray, fiber_a=self.fp3, fiber_b=self.fp4
        )
        self.plan.save()  # updates last_updated

        resp = self.client.post(
            self.url,
            {
                "add": [{"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk}],
                "remove": [],
                "plan_version": stale_version,
            },
            format="json",
        )
        assert resp.status_code == 409, resp.content
        assert "modified by another user" in resp.json()["error"]

    def test_save_succeeds_without_version(self):
        """Save without plan_version should succeed (backwards compatible)."""
        resp = self.client.post(
            self.url,
            {
                "add": [{"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk}],
                "remove": [],
            },
            format="json",
        )
        assert resp.status_code == 200, resp.content

    def test_version_updates_after_save(self):
        """After a successful save, the returned plan_version should be newer."""
        old_version = self.plan.last_updated.isoformat()
        resp = self.client.post(
            self.url,
            {
                "add": [{"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk}],
                "remove": [],
                "plan_version": old_version,
            },
            format="json",
        )
        assert resp.status_code == 200
        new_version = resp.json()["plan_version"]
        assert new_version is not None
        assert new_version != old_version

    def test_sequential_saves_with_updated_version(self):
        """Two sequential saves by same user should both succeed when version is updated."""
        # First save
        version = self.plan.last_updated.isoformat()
        resp1 = self.client.post(
            self.url,
            {
                "add": [{"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk}],
                "remove": [],
                "plan_version": version,
            },
            format="json",
        )
        assert resp1.status_code == 200
        version2 = resp1.json()["plan_version"]

        # Second save with updated version
        resp2 = self.client.post(
            self.url,
            {
                "add": [{"fiber_a": self.fp3.pk, "fiber_b": self.fp4.pk}],
                "remove": [],
                "plan_version": version2,
            },
            format="json",
        )
        assert resp2.status_code == 200
        assert SplicePlanEntry.objects.filter(plan=self.plan).count() == 2
