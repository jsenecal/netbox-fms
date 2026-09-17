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


def make_closure_pair(prefix):
    """Two bare closure devices sharing one make_infra rigging.

    Returns a SimpleNamespace with the make_infra quartet plus dev_a and
    dev_b, named "<prefix>-A" / "<prefix>-B" -- the rigging every
    provisioned-cable test starts from.
    """
    site, mfr, dt, role = make_infra(prefix)
    dev_a = Device.objects.create(name=f"{prefix}-A", site=site, device_type=dt, role=role)
    dev_b = Device.objects.create(name=f"{prefix}-B", site=site, device_type=dt, role=role)
    return SimpleNamespace(site=site, mfr=mfr, device_type=dt, role=role, dev_a=dev_a, dev_b=dev_b)


def make_ribbon_in_tube_type(mfr, model, tubes, ribbons_per_tube, fibers=12):
    """FiberCableType with ``tubes`` buffer tubes of ``ribbons_per_tube`` ribbons each."""
    from netbox_fms.models import BufferTubeTemplate, FiberCableType, RibbonTemplate

    fct = FiberCableType.objects.create(
        manufacturer=mfr,
        model=model,
        strand_count=tubes * ribbons_per_tube * fibers,
        construction="ribbon_in_tube",
    )
    for t in range(1, tubes + 1):
        btt = BufferTubeTemplate.objects.create(fiber_cable_type=fct, name=f"T{t}", position=t, fiber_count=None)
        for r in range(1, ribbons_per_tube + 1):
            RibbonTemplate.objects.create(
                fiber_cable_type=fct,
                buffer_tube_template=btt,
                name=f"T{t}-R{r}",
                position=r,
                fiber_count=fibers,
            )
    return fct


def make_central_core_type(mfr, model, ribbons, fibers=12):
    """FiberCableType with ``ribbons`` central-core ribbons (no buffer tubes)."""
    from netbox_fms.models import FiberCableType, RibbonTemplate

    fct = FiberCableType.objects.create(
        manufacturer=mfr,
        model=model,
        strand_count=ribbons * fibers,
        construction="ribbon",
    )
    for r in range(1, ribbons + 1):
        RibbonTemplate.objects.create(fiber_cable_type=fct, name=f"R{r}", position=r, fiber_count=fibers)
    return fct


def make_authed_client(username="api-test"):
    """Create a superuser and return a DRF APIClient authenticated as them."""
    user = get_user_model().objects.create_superuser(username=username, password="test")
    client = APIClient()
    client.force_authenticate(user)
    return client
