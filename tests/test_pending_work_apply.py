"""Regression tests for the closure "Apply all Approved Plans" view (issue #65)."""

import pytest
from dcim.models import Cable, Device, DeviceRole, DeviceType, Manufacturer, Module, ModuleBay, ModuleType, Site
from django.contrib.auth import get_user_model

from netbox_fms.choices import SplicePlanStatusChoices
from netbox_fms.models import SplicePlan, SplicePlanEntry
from tests.conftest import make_front_port

User = get_user_model()


@pytest.mark.django_db(transaction=True)
def test_apply_all_approved_plans_in_autocommit(client):
    """Applying all approved plans must work outside a wrapping transaction.

    Regression test for issue #65: the view evaluated a select_for_update()
    queryset before entering transaction.atomic(), raising
    TransactionManagementError in production (autocommit mode). Runs with
    transaction=True so no test transaction masks the bug.
    """
    site = Site.objects.create(name="PW Site", slug="pw-site")
    mfr = Manufacturer.objects.create(name="PW Mfr", slug="pw-mfr")
    dt = DeviceType.objects.create(manufacturer=mfr, model="PW Closure", slug="pw-closure")
    role = DeviceRole.objects.create(name="PW Role", slug="pw-role")
    closure = Device.objects.create(name="PW-Closure", site=site, device_type=dt, role=role)

    mt = ModuleType.objects.create(manufacturer=mfr, model="PW Tray")
    bay = ModuleBay.objects.create(device=closure, name="Bay 1")
    tray = Module.objects.create(device=closure, module_bay=bay, module_type=mt)
    fp1 = make_front_port(device=closure, module=tray, name="PW-F1")
    fp2 = make_front_port(device=closure, module=tray, name="PW-F2")

    plan = SplicePlan.objects.create(
        closure=closure,
        name="PW Plan",
        status=SplicePlanStatusChoices.APPROVED,
    )
    SplicePlanEntry.objects.create(plan=plan, tray=tray, fiber_a=fp1, fiber_b=fp2)

    user = User.objects.create_user(username="pw-admin", password="pw", is_superuser=True)
    client.force_login(user)

    response = client.post(f"/dcim/devices/{closure.pk}/pending-work/")

    assert response.status_code == 302
    plan.refresh_from_db()
    assert plan.status == SplicePlanStatusChoices.ARCHIVED
    # The planned splice was provisioned as a front-port jumper cable
    assert Cable.objects.count() == 1
