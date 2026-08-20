from types import SimpleNamespace

from dcim.models import Device, DeviceRole, DeviceType, FrontPort, Manufacturer, Module, ModuleBay, ModuleType, Site
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

# Counter to ensure unique FrontPort names across tests (no longer needed but kept for safety)
_fp_counter = 0


def make_infra(prefix):
    """Create the site/manufacturer/device-type/role quartet most fixtures need."""
    site = Site.objects.create(name=f"{prefix} Site", slug=f"{prefix.lower()}-site")
    mfr = Manufacturer.objects.create(name=f"{prefix} Mfr", slug=f"{prefix.lower()}-mfr")
    dt = DeviceType.objects.create(manufacturer=mfr, model=f"{prefix} FOSC", slug=f"{prefix.lower()}-fosc")
    role = DeviceRole.objects.create(name=f"{prefix} Closure", slug=f"{prefix.lower()}-closure")
    return site, mfr, dt, role


def make_front_port(device, name, module=None, port_type="lc"):
    """
    Create a FrontPort.
    NetBox 4.5+ FrontPort no longer requires a backing RearPort.
    """
    global _fp_counter
    _fp_counter += 1
    kwargs = {
        "device": device,
        "name": name,
        "type": port_type,
    }
    if module is not None:
        kwargs["module"] = module
    return FrontPort.objects.create(**kwargs)


def make_closure_with_tray(prefix, port_count=2, port_type="splice"):
    """Create a closure Device holding one tray Module with FrontPorts on it.

    Returns a SimpleNamespace exposing the make_infra quartet (site, mfr,
    device_type, role) plus closure, tray, and ports (a list of port_count
    FrontPorts named "<prefix>-F<n>" attached to the tray), so callers can
    build plans, cables, or sibling devices from the same rigging.
    """
    site, mfr, dt, role = make_infra(prefix)
    closure = Device.objects.create(name=f"{prefix}-Closure", site=site, device_type=dt, role=role)
    mt = ModuleType.objects.create(manufacturer=mfr, model=f"{prefix} Tray")
    bay = ModuleBay.objects.create(device=closure, name="Bay 1")
    tray = Module.objects.create(device=closure, module_bay=bay, module_type=mt)
    ports = [
        make_front_port(closure, f"{prefix}-F{n}", module=tray, port_type=port_type) for n in range(1, port_count + 1)
    ]
    return SimpleNamespace(
        site=site,
        mfr=mfr,
        device_type=dt,
        role=role,
        closure=closure,
        tray=tray,
        ports=ports,
    )


def make_authed_client(username="api-test"):
    """Create a superuser and return a DRF APIClient authenticated as them."""
    user = get_user_model().objects.create_superuser(username=username, password="test")
    client = APIClient()
    client.force_authenticate(user)
    return client
