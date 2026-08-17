"""Regression tests for object-permission enforcement in the custom API views.

Regression tests for the netbox_fms views flagged in
jsenecal/netbox-pathways#123: views that bypassed NetBox object-level
permissions by subclassing plain DRF classes or querying bare managers.
"""

from dcim.models import (
    Cable,
    Device,
    FrontPort,
    Module,
    ModuleBay,
    ModuleType,
)
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from rest_framework.test import APIClient
from users.models import ObjectPermission

from netbox_fms.choices import FiberCircuitStatusChoices, SplicePlanStatusChoices
from netbox_fms.models import (
    FiberCable,
    FiberCableType,
    FiberCircuit,
    FiberCircuitNode,
    FiberCircuitPath,
    SplicePlan,
    SplicePlanEntry,
)
from tests.conftest import make_infra

User = get_user_model()


def _constrained_client(model, constraints, username):
    """API client for a user whose view permission on ``model`` carries ``constraints``."""
    user = User.objects.create_user(username=username, password="x")  # noqa: S106
    perm = ObjectPermission.objects.create(
        name=f"perm-{username}",
        enabled=True,
        actions=["view"],
        constraints=constraints,
    )
    perm.object_types.set([ContentType.objects.get_for_model(model)])
    perm.users.add(user)
    client = APIClient()
    # Re-fetch so no stale permission cache rides along on the user instance
    client.force_authenticate(user=User.objects.get(pk=user.pk))
    return client


def _no_perm_client(username):
    """API client for an authenticated user holding no permissions at all."""
    user = User.objects.create_user(username=username, password="x")  # noqa: S106
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class TestCircuitEndpointPermissions(TestCase):
    """The circuit-node viewset and the protecting view must honour constraints."""

    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = make_infra("PermC")
        device = Device.objects.create(name="PermC-1", site=site, device_type=dt, role=role)
        fp = FrontPort.objects.create(device=device, name="PermC-FP", type="lc")
        cls.cable = Cable.objects.create()

        cls.nodes = {}
        for name in ("Perm-A", "Perm-B"):
            circuit = FiberCircuit.objects.create(
                name=name,
                status=FiberCircuitStatusChoices.ACTIVE,
                strand_count=1,
            )
            path = FiberCircuitPath.objects.create(
                circuit=circuit,
                position=1,
                origin=fp,
                path=[{"type": "cable", "id": cls.cable.pk}],
                is_complete=False,
            )
            cls.nodes[name] = FiberCircuitNode.objects.create(path=path, position=1, cable=cls.cable)

    def test_circuit_nodes_list_honours_constraints(self):
        client = _constrained_client(
            FiberCircuitNode,
            {"path__circuit__name": "Perm-A"},
            "perm-nodes",
        )
        resp = client.get("/api/plugins/fms/fiber-circuit-nodes/")
        assert resp.status_code == 200
        ids = {r["id"] for r in resp.data["results"]}
        assert ids == {self.nodes["Perm-A"].pk}

    def test_protecting_view_honours_constraints(self):
        client = _constrained_client(FiberCircuit, {"name": "Perm-A"}, "perm-protecting")
        resp = client.get(f"/api/plugins/fms/fiber-circuits/protecting/?cable={self.cable.pk}")
        assert resp.status_code == 200
        names = {c["name"] for c in resp.data}
        assert names == {"Perm-A"}


class TestClaimsEndpointPermissions(TestCase):
    """The fiber-claims view must not serve plan entries the user cannot view."""

    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = make_infra("PermF")
        cls.closure = Device.objects.create(name="PermF-1", site=site, device_type=dt, role=role)
        mt = ModuleType.objects.create(manufacturer=mfr, model="PermF Tray")
        mb = ModuleBay.objects.create(device=cls.closure, name="Bay 1", position="1")
        tray = Module.objects.create(device=cls.closure, module_bay=mb, module_type=mt)
        fa = FrontPort.objects.create(device=cls.closure, module=tray, name="PermF-A", type="lc")
        fb = FrontPort.objects.create(device=cls.closure, module=tray, name="PermF-B", type="lc")
        plan = SplicePlan.objects.create(
            closure=cls.closure,
            name="PermF-Plan",
            status=SplicePlanStatusChoices.DRAFT,
        )
        SplicePlanEntry.objects.create(plan=plan, tray=tray, fiber_a=fa, fiber_b=fb)

    def test_claims_hidden_from_user_without_permission(self):
        client = _no_perm_client("perm-claims")
        resp = client.get(f"/api/plugins/fms/closures/{self.closure.pk}/fiber-claims/")
        assert resp.status_code == 200
        assert resp.data == []


class TestClosureStrandsEndpointPermissions(TestCase):
    """The closure-strands view must not serve cable/strand data the user cannot view."""

    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = make_infra("PermS")
        cls.closure = Device.objects.create(name="PermS-1", site=site, device_type=dt, role=role)
        fp = FrontPort.objects.create(device=cls.closure, name="PermS-FP", type="lc")
        cable = Cable.objects.create(a_terminations=[fp])
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="PermS-TB6", strand_count=6, construction="tight_buffer"
        )
        FiberCable.objects.create(cable=cable, fiber_cable_type=fct)

    def test_strands_hidden_from_user_without_permission(self):
        client = _no_perm_client("perm-strands")
        resp = client.get(f"/api/plugins/fms/closure-strands/{self.closure.pk}/")
        assert resp.status_code == 200
        assert resp.data["cables"] == []
        assert resp.data["trays"] == []
