"""Regression tests for the closure "Apply all Approved Plans" view (issue #65)."""

from unittest.mock import patch

import pytest
from dcim.models import Cable, Device, DeviceRole, DeviceType, Manufacturer, Module, ModuleBay, ModuleType, Site
from django.contrib.auth import get_user_model

from netbox_fms.choices import FiberCircuitStatusChoices, SplicePlanStatusChoices
from netbox_fms.models import FiberCircuit, FiberCircuitNode, FiberCircuitPath, SplicePlan, SplicePlanEntry
from tests.conftest import make_front_port

User = get_user_model()


def _build_closure_with_plan(prefix, plan_status=SplicePlanStatusChoices.APPROVED):
    """Create a closure with one tray, two front ports, and one splice plan entry."""
    site = Site.objects.create(name=f"{prefix} Site", slug=f"{prefix.lower()}-site")
    mfr = Manufacturer.objects.create(name=f"{prefix} Mfr", slug=f"{prefix.lower()}-mfr")
    dt = DeviceType.objects.create(manufacturer=mfr, model=f"{prefix} Closure", slug=f"{prefix.lower()}-closure")
    role = DeviceRole.objects.create(name=f"{prefix} Role", slug=f"{prefix.lower()}-role")
    closure = Device.objects.create(name=f"{prefix}-Closure", site=site, device_type=dt, role=role)

    mt = ModuleType.objects.create(manufacturer=mfr, model=f"{prefix} Tray")
    bay = ModuleBay.objects.create(device=closure, name="Bay 1")
    tray = Module.objects.create(device=closure, module_bay=bay, module_type=mt)
    fp1 = make_front_port(device=closure, module=tray, name=f"{prefix}-F1")
    fp2 = make_front_port(device=closure, module=tray, name=f"{prefix}-F2")

    plan = SplicePlan.objects.create(closure=closure, name=f"{prefix} Plan", status=plan_status)
    SplicePlanEntry.objects.create(plan=plan, tray=tray, fiber_a=fp1, fiber_b=fp2)
    return closure, plan, fp1


def _login_superuser(client, username):
    user = User.objects.create_user(username=username, password="pw", is_superuser=True)
    client.force_login(user)


@pytest.mark.django_db
def test_apply_all_without_approved_plans_errors(client):
    """POST with no approved plans redirects with an error and applies nothing."""
    closure, plan, _fp = _build_closure_with_plan("PWNP", plan_status=SplicePlanStatusChoices.DRAFT)
    _login_superuser(client, "pwnp-admin")

    response = client.post(f"/dcim/devices/{closure.pk}/pending-work/")

    assert response.status_code == 302
    plan.refresh_from_db()
    assert plan.status == SplicePlanStatusChoices.DRAFT
    assert Cable.objects.count() == 0


@pytest.mark.django_db
def test_apply_all_blocked_by_protected_circuit(client):
    """Plans touching fibers claimed by an active circuit are rejected untouched."""
    closure, plan, fp1 = _build_closure_with_plan("PWPC")
    circuit = FiberCircuit.objects.create(
        name="PWPC-Circuit",
        status=FiberCircuitStatusChoices.ACTIVE,
        strand_count=1,
    )
    path = FiberCircuitPath.objects.create(circuit=circuit, position=1, origin=fp1, path=[], is_complete=False)
    FiberCircuitNode.objects.create(path=path, position=1, front_port=fp1)
    _login_superuser(client, "pwpc-admin")

    response = client.post(f"/dcim/devices/{closure.pk}/pending-work/")

    assert response.status_code == 302
    plan.refresh_from_db()
    assert plan.status == SplicePlanStatusChoices.APPROVED
    assert Cable.objects.count() == 0


@pytest.mark.django_db
def test_apply_all_rolls_back_on_apply_error(client):
    """An apply_diff failure rolls the whole operation back and reports the error."""
    closure, plan, _fp = _build_closure_with_plan("PWER")
    _login_superuser(client, "pwer-admin")

    with patch("netbox_fms.views.apply_diff", side_effect=ValueError("boom")):
        response = client.post(f"/dcim/devices/{closure.pk}/pending-work/")

    assert response.status_code == 302
    plan.refresh_from_db()
    assert plan.status == SplicePlanStatusChoices.APPROVED
    assert Cable.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_apply_all_approved_plans_in_autocommit(client):
    """Applying all approved plans must work outside a wrapping transaction.

    Regression test for issue #65: the view evaluated a select_for_update()
    queryset before entering transaction.atomic(), raising
    TransactionManagementError in production (autocommit mode). Runs with
    transaction=True so no test transaction masks the bug.
    """
    closure, plan, _fp = _build_closure_with_plan("PW")
    _login_superuser(client, "pw-admin")

    response = client.post(f"/dcim/devices/{closure.pk}/pending-work/")

    assert response.status_code == 302
    plan.refresh_from_db()
    assert plan.status == SplicePlanStatusChoices.ARCHIVED
    # The planned splice was provisioned as a front-port jumper cable
    assert Cable.objects.count() == 1
