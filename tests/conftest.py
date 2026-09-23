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


def connect_front_ports(port_a, port_b):
    """Create a zero-length jumper cable between two FrontPorts."""
    from dcim.models import Cable, CableTermination
    from django.contrib.contenttypes.models import ContentType

    fp_ct = ContentType.objects.get_for_model(FrontPort)
    cable = Cable.objects.create(length=0, length_unit="m")
    CableTermination.objects.create(cable=cable, cable_end="A", termination_type=fp_ct, termination_id=port_a.pk)
    CableTermination.objects.create(cable=cable, cable_end="B", termination_type=fp_ct, termination_id=port_b.pk)
    return cable


def make_tray_type(mfr, model, role="splice_tray"):
    """ModuleType with a TrayProfile of the given role; role=None leaves it unprofiled."""
    from netbox_fms.models import TrayProfile

    module_type = ModuleType.objects.create(manufacturer=mfr, model=model)
    if role is not None:
        TrayProfile.objects.create(module_type=module_type, tray_role=role)
    return module_type


def make_tray_module(closure, module_type, bay_name):
    """Install a module of the given type on the closure in a fresh bay."""
    bay = ModuleBay.objects.create(device=closure, name=bay_name)
    return Module.objects.create(device=closure, module_bay=bay, module_type=module_type)


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


def make_provider_circuit(prefix):
    """Provider + type + circuit with A and Z terminations, uncabled."""
    from circuits.models import Circuit, CircuitTermination, CircuitType, Provider

    provider = Provider.objects.create(name=f"{prefix} Provider", slug=f"{prefix.lower()}-provider")
    ctype, _ = CircuitType.objects.get_or_create(name="Dark Fiber", slug="dark-fiber")
    circuit = Circuit.objects.create(cid=f"{prefix}-DF-1", provider=provider, type=ctype)
    term_a = CircuitTermination.objects.create(circuit=circuit, term_side="A")
    term_z = CircuitTermination.objects.create(circuit=circuit, term_side="Z")
    return SimpleNamespace(provider=provider, circuit=circuit, term_a=term_a, term_z=term_z)


def connect_rp_to_ct(rear_port, circuit_termination):
    """Cable a RearPort (end A) to a CircuitTermination (end B)."""
    from circuits.models import CircuitTermination
    from dcim.models import Cable, CableTermination, RearPort
    from django.contrib.contenttypes.models import ContentType

    cable = Cable.objects.create()
    rp_ct = ContentType.objects.get_for_model(RearPort)
    ct_ct = ContentType.objects.get_for_model(CircuitTermination)
    CableTermination.objects.create(cable=cable, cable_end="A", termination_type=rp_ct, termination_id=rear_port.pk)
    CableTermination.objects.create(
        cable=cable, cable_end="B", termination_type=ct_ct, termination_id=circuit_termination.pk
    )
    return cable


def connect_ct_to_ct(termination_a, termination_b):
    """Cable two CircuitTerminations together (back-to-back circuits)."""
    from circuits.models import CircuitTermination
    from dcim.models import Cable, CableTermination
    from django.contrib.contenttypes.models import ContentType

    cable = Cable.objects.create()
    ct_ct = ContentType.objects.get_for_model(CircuitTermination)
    CableTermination.objects.create(cable=cable, cable_end="A", termination_type=ct_ct, termination_id=termination_a.pk)
    CableTermination.objects.create(cable=cable, cable_end="B", termination_type=ct_ct, termination_id=termination_b.pk)
    return cable


def make_mapped_endpoint(prefix):
    """Closure with one RearPort mapped 1:1 to one FrontPort, ready to cable."""
    from dcim.models import PortMapping, RearPort

    ns = make_closure_with_tray(prefix, port_count=0)
    rp = RearPort.objects.create(device=ns.closure, module=ns.tray, name=f"{prefix}-RP", type="lc", positions=1)
    fp = make_front_port(ns.closure, f"{prefix}-FP", module=ns.tray)
    PortMapping.objects.create(
        device=ns.closure, front_port=fp, rear_port=rp, front_port_position=1, rear_port_position=1
    )
    return SimpleNamespace(closure=ns.closure, tray=ns.tray, rp=rp, fp=fp)
