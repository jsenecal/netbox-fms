"""Regression tests for the closure Pending Work and plan import views."""

from unittest.mock import patch

import pytest
from dcim.models import Cable, Device, Module, ModuleBay, ModuleType
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from users.models import ObjectPermission

from netbox_fms.choices import FiberCircuitStatusChoices, SplicePlanStatusChoices
from netbox_fms.models import FiberCircuit, FiberCircuitNode, FiberCircuitPath, SplicePlan, SplicePlanEntry
from tests.conftest import connect_front_ports, make_front_port, make_infra

User = get_user_model()


def _build_closure_with_plan(prefix, plan_status=SplicePlanStatusChoices.APPROVED):
    """Create a closure with one tray, two front ports, and one splice plan entry."""
    site, mfr, dt, role = make_infra(prefix)
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
def test_apply_all_requires_approve_permission(client):
    """A user without approve_spliceplan cannot batch-apply approved plans.

    Regression test for issue #111: every apply path must be gated on the
    approve_spliceplan permission, including the closure Pending Work view.
    """
    closure, plan, _fp = _build_closure_with_plan("PWNA")
    user = User.objects.create_user(username="pwna-viewer", password="pw")  # noqa: S106
    perm = ObjectPermission.objects.create(name="pwna-view-device", actions=["view"])
    perm.object_types.add(ContentType.objects.get_for_model(Device))
    perm.users.add(user)
    client.force_login(user)

    response = client.post(f"/dcim/devices/{closure.pk}/pending-work/")

    assert response.status_code == 302
    plan.refresh_from_db()
    assert plan.status == SplicePlanStatusChoices.APPROVED
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


@pytest.mark.django_db
def test_pending_work_renders_unassigned_group_distinctly(client):
    """The bucket-0 group renders as a warning, not a normal tray row (issue #164)."""
    closure, plan, _fp1 = _build_closure_with_plan("PWUB")
    tray = plan.entries.first().tray
    fp3 = make_front_port(device=closure, module=tray, name="PWUB-F3")
    loose = make_front_port(device=closure, name="PWUB-Loose")
    SplicePlanEntry.objects.create(plan=plan, tray=tray, fiber_a=fp3, fiber_b=loose)
    _login_superuser(client, "pwub-admin")

    response = client.get(f"/dcim/devices/{closure.pk}/pending-work/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Unassigned tubes" in content
    assert "splices on tubes not assigned to any tray" in content


@pytest.mark.django_db
def test_import_view_warns_about_skipped_unassigned(client):
    """The import view surfaces the count of skipped device-level pairs (issue #164)."""
    closure, plan, _fp = _build_closure_with_plan("PWIW", plan_status=SplicePlanStatusChoices.DRAFT)
    plan.entries.all().delete()
    loose_a = make_front_port(device=closure, name="PWIW-LA")
    loose_b = make_front_port(device=closure, name="PWIW-LB")
    connect_front_ports(loose_a, loose_b)
    _login_superuser(client, "pwiw-admin")

    response = client.post(f"/plugins/fms/splice-plans/{plan.pk}/import/", follow=True)

    rendered_messages = [str(m) for m in response.context["messages"]]
    assert any(m.startswith("Imported 0 connections") for m in rendered_messages)
    assert any("Skipped 1 splice(s) on tubes not assigned to any tray" in m for m in rendered_messages)
    assert plan.entries.count() == 0


@pytest.mark.django_db
def test_import_view_warns_about_skipped_claimed(client):
    """The import view surfaces the count of pairs claimed by another plan (issue #174)."""
    closure, claimer, fp1 = _build_closure_with_plan("PWIC", plan_status=SplicePlanStatusChoices.DRAFT)
    fp2 = claimer.entries.get().fiber_b
    connect_front_ports(fp1, fp2)
    plan = SplicePlan.objects.create(closure=closure, name="PWIC Second Plan")
    _login_superuser(client, "pwic-admin")

    response = client.post(f"/plugins/fms/splice-plans/{plan.pk}/import/", follow=True)

    rendered_messages = [str(m) for m in response.context["messages"]]
    assert any(m.startswith("Imported 0 connections") for m in rendered_messages)
    assert any("Skipped 1 splice(s) on fibers already claimed by another active plan" in m for m in rendered_messages)
    assert plan.entries.count() == 0


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
