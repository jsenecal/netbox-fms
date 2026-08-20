from dcim.models import DeviceRole, DeviceType, FrontPort, Manufacturer, Site

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
