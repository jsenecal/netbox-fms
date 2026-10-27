from contextlib import contextmanager
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from dcim.models import Device, DeviceRole, DeviceType, FrontPort, Manufacturer, Module, ModuleBay, ModuleType, Site
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import RequestFactory
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def no_analysis_job_enqueue():
    """Keep every test off Redis: receivers committing in a TransactionTestCase would enqueue for real.

    A test that checks scheduling inspects ``PathAnalysisJob.enqueue`` (the patched mock).
    """
    from netbox_fms.jobs import PathAnalysisJob

    with patch.object(PathAnalysisJob, "enqueue"):
        yield


# Port name templates the name-template tests configure; the rear guard keeps
# tubeless constructions renderable.
NAME_TEMPLATES = {
    "front_port_name_template": "{{ cable }}-{{ end }}-F{{ strand }}",
    "rear_port_name_template": "{{ cable }}-{{ end }}{% if tube_name %}-{{ tube_name }}{% endif %}",
}


def port_names(device, model):
    """Sorted names of a device's ports of one model (FrontPort or RearPort)."""
    return sorted(model.objects.filter(device=device).values_list("name", flat=True))


def port_labels(device, model):
    """Sorted labels of a device's ports of one model (FrontPort or RearPort)."""
    return sorted(model.objects.filter(device=device).values_list("label", flat=True))


def call_command_capture(name, *args):
    """Run a management command and return its (stdout, stderr) text."""
    out, err = StringIO(), StringIO()
    call_command(name, *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


# Counter to ensure unique FrontPort names across tests (no longer needed but kept for safety)
_fp_counter = 0


def render_left_page(extension_cls, obj, path="/"):
    """Render a PluginTemplateExtension's left_page() for obj outside a full view."""
    request = RequestFactory().get(path)
    extension = extension_cls(context={"object": obj, "request": request, "config": {}})
    return extension.left_page()


def make_infra(prefix):
    """Create the site/manufacturer/device-type/role quartet most fixtures need."""
    site = Site.objects.create(name=f"{prefix} Site", slug=f"{prefix.lower()}-site")
    mfr = Manufacturer.objects.create(name=f"{prefix} Mfr", slug=f"{prefix.lower()}-mfr")
    dt = DeviceType.objects.create(manufacturer=mfr, model=f"{prefix} FOSC", slug=f"{prefix.lower()}-fosc")
    role = DeviceRole.objects.create(name=f"{prefix} Closure", slug=f"{prefix.lower()}-closure")
    return site, mfr, dt, role


def stored_columns(obj, drop=()):
    """Every stored column of a row except its pk, its timestamps and the named ones."""
    skip = {"id", "created", "last_updated", *drop}
    return {f.attname: getattr(obj, f.attname) for f in obj._meta.concrete_fields if f.attname not in skip}


def place_in_rack(device, prefix):
    """Give a device a Location and a Rack, so the columns NetBox caches from them are not all NULL."""
    from dcim.models import Location, Rack

    location = Location.objects.create(name=f"{prefix} Room", slug=f"{prefix.lower()}-room", site=device.site)
    rack = Rack.objects.create(name=f"{prefix} Rack", site=device.site, location=location)
    device.location, device.rack = location, rack
    device.save()
    return device


@contextmanager
def saves_seen(*models):
    """Collect (model, pk, created) for every post_save of the given models."""
    from django.db.models.signals import post_save

    seen = []

    def receiver(sender, instance, created, **kwargs):
        seen.append((sender, instance.pk, created))

    for model in models:
        post_save.connect(receiver, sender=model)
    try:
        yield seen
    finally:
        for model in models:
            post_save.disconnect(receiver, sender=model)


def rolled_back(fn, dump):
    """Run fn, take dump(), then undo everything fn wrote; returns (fn's result, the dump)."""
    from django.db import transaction

    with transaction.atomic():
        result = fn()
        snapshot = dump()
        transaction.set_rollback(True)
    return result, snapshot


def is_indexed(obj, value):
    """True when NetBox's search cache holds this value for the object."""
    from core.models import ObjectType
    from extras.models import CachedValue

    return CachedValue.objects.filter(
        object_type=ObjectType.objects.get_for_model(type(obj)), object_id=obj.pk, value=value
    ).exists()


def changes_logged(fn):
    """(model, action) counts of the ObjectChanges fn writes inside a request; fn's writes are undone."""
    import uuid
    from collections import Counter

    from core.models import ObjectChange
    from django.db import transaction
    from netbox.context_managers import event_tracking

    request = RequestFactory().get("/")
    request.id = uuid.uuid4()
    request.user = get_user_model().objects.get_or_create(username="changes-logged")[0]
    with transaction.atomic():
        with event_tracking(request):
            fn()
        found = Counter(
            ObjectChange.objects.filter(request_id=request.id).values_list("changed_object_type__model", "action")
        )
        transaction.set_rollback(True)
    return found


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


def make_closure(prefix):
    """A bare closure Device named "<prefix>-Closure" on fresh make_infra rigging.

    Returns a SimpleNamespace with the make_infra quartet (site, mfr,
    device_type, role) plus closure.
    """
    site, mfr, dt, role = make_infra(prefix)
    closure = Device.objects.create(name=f"{prefix}-Closure", site=site, device_type=dt, role=role)
    return SimpleNamespace(site=site, mfr=mfr, device_type=dt, role=role, closure=closure)


def make_closure_with_tray(prefix, port_count=2, port_type="splice"):
    """Create a closure Device holding one tray Module with FrontPorts on it.

    Extends make_closure's namespace with tray and ports (a list of
    port_count FrontPorts named "<prefix>-F<n>" attached to the tray), so
    callers can build plans, cables, or sibling devices from the same rigging.
    """
    rig = make_closure(prefix)
    mt = ModuleType.objects.create(manufacturer=rig.mfr, model=f"{prefix} Tray")
    rig.tray = make_tray_module(rig.closure, mt, "Bay 1")
    rig.ports = [
        make_front_port(rig.closure, f"{prefix}-F{n}", module=rig.tray, port_type=port_type)
        for n in range(1, port_count + 1)
    ]
    return rig


def land_strands(fc, front_ports, rear_port=None, fk="front_port_a"):
    """Point a cable's strands, in position order, at the given FrontPorts.

    With ``rear_port``, also create the PortMappings (rear positions 1..N)
    the FMS port walk follows. Runs under the PortMapping bypass because
    the pair becomes FMS-managed the moment the strand FK lands.
    """
    from dcim.models import PortMapping

    from netbox_fms.signals import fms_portmapping_bypass

    strands = list(fc.fiber_strands.order_by("position"))
    with fms_portmapping_bypass():
        for i, (strand, fp) in enumerate(zip(strands, front_ports, strict=True), start=1):
            if rear_port is not None:
                PortMapping.objects.get_or_create(
                    device=fp.device, front_port=fp, rear_port=rear_port, front_port_position=1, rear_port_position=i
                )
            setattr(strand, fk, fp)
            strand.save(update_fields=[fk])
    return strands


def connect_tube_cable(cable, tube_pairs):
    """Terminate a multi-tube trunk cable on RearPorts, one tube at a time.

    ``tube_pairs`` lists ``(a_rear_port, b_rear_port)`` per tube in tube
    order; the n-th pair gets connector ``n`` on both ends, which is how the
    analysis loader tells tubes of one cable apart.
    """
    from dcim.models import CableTermination, RearPort
    from django.contrib.contenttypes.models import ContentType

    rp_ct = ContentType.objects.get_for_model(RearPort)
    for connector, (a_rp, b_rp) in enumerate(tube_pairs, start=1):
        for cable_end, rp in (("A", a_rp), ("B", b_rp)):
            CableTermination.objects.create(
                cable=cable,
                cable_end=cable_end,
                termination_type=rp_ct,
                termination_id=rp.pk,
                connector=connector,
                positions=list(range(1, rp.positions + 1)),
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


def make_tray_type(mfr, model, role="splice_tray", **profile_fields):
    """ModuleType with a TrayProfile of the given role; role=None leaves it unprofiled.

    Extra keyword arguments (splice_capacity, tube_capacity, ...) go onto
    the profile.
    """
    from netbox_fms.models import TrayProfile

    module_type = ModuleType.objects.create(manufacturer=mfr, model=model)
    if role is not None:
        TrayProfile.objects.create(module_type=module_type, tray_role=role, **profile_fields)
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


class ClosurePairMixin:
    """TestCase mixin exposing a make_closure_pair rig as ``mfr`` / ``dev_a`` / ``dev_b``.

    Subclasses set ``prefix`` so their objects do not collide with another
    module's rig in the shared test database.
    """

    prefix = "PAIR"

    @classmethod
    def setUpTestData(cls):
        pair = make_closure_pair(cls.prefix)
        cls.mfr = pair.mfr
        cls.dev_a = pair.dev_a
        cls.dev_b = pair.dev_b


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


class AuthedAPIClientMixin:
    """TestCase mixin: ``self.client`` is a DRF APIClient authenticated as ``cls.user``.

    Set ``cls.user`` in setUpTestData; Django builds a fresh ``self.client``
    from ``client_class`` before every test, so it cannot live there itself.
    """

    client_class = APIClient

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.user)


def make_authed_client(username="api-test"):
    """Create a superuser and return a DRF APIClient authenticated as them."""
    user = get_user_model().objects.create_superuser(username=username, password="test")
    client = APIClient()
    client.force_authenticate(user)
    return client


def user_with(username, grants):
    """A user whose permissions are ``grants``: (model, actions, constraints) triples."""
    from django.contrib.contenttypes.models import ContentType
    from users.models import ObjectPermission

    user = get_user_model().objects.create_user(username=username, password="x")  # noqa: S106
    for index, (model, actions, constraints) in enumerate(grants):
        perm = ObjectPermission.objects.create(
            name=f"{username}-{index}", enabled=True, actions=actions, constraints=constraints
        )
        perm.object_types.set([ContentType.objects.get_for_model(model)])
        perm.users.add(user)
    # Re-fetch so no stale permission cache rides along on the user instance
    return get_user_model().objects.get(pk=user.pk)


def client_with(username, grants):
    """API client whose permissions are ``grants``: (model, actions, constraints) triples."""
    client = APIClient()
    client.force_authenticate(user=user_with(username, grants))
    return client


def superuser_client(username):
    """Session-logged-in Django client for a new superuser (for the UI and GraphQL views)."""
    from django.test import Client

    client = Client()
    client.force_login(get_user_model().objects.create_superuser(username, f"{username}@example.com", "pw"))
    return client


def ui_client_with(username, grants):
    """Session-logged-in Django client whose permissions are ``grants`` (for the UI views)."""
    from django.test import Client

    client = Client()
    client.force_login(user_with(username, grants))
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


def make_mapped_rear_ports(device, rear_names, front_name, positions=12):
    """Splice RearPorts named ``rear_names``, each mapped position by position to its own FrontPorts.

    ``front_name`` is a format string over ``rp`` (the rear port name),
    ``i`` (the position on that rear port) and ``n`` (the running count
    across all rear ports). Returns ``(rear_ports, front_ports)`` with the
    front ports in rear port order, then position -- global strand order
    for a cable adopting them in sequence.
    """
    from dcim.models import PortMapping, RearPort

    rear_ports, front_ports = [], []
    for rear_name in rear_names:
        rp = RearPort.objects.create(device=device, name=rear_name, type="splice", positions=positions)
        rear_ports.append(rp)
        for i in range(1, positions + 1):
            name = front_name.format(rp=rear_name, i=i, n=len(front_ports) + 1)
            fp = FrontPort.objects.create(device=device, name=name, type="splice")
            PortMapping.objects.create(
                device=device, front_port=fp, rear_port=rp, front_port_position=1, rear_port_position=i
            )
            front_ports.append(fp)
    return rear_ports, front_ports


def make_strand_path(*hops, end_a=None, end_b=None, end_a_kind=None, end_b_kind=None, **fields):
    """An analysis-shaped FiberStrandPath with these hops, for tests that need one without walking.

    ``hops`` are FiberStrand, dcim.Cable or circuits.Circuit instances in
    order. Ends default to terminated when a port is given, open otherwise.
    """
    from django.utils import timezone

    from netbox_fms.choices import PathCompletenessChoices, PathEndKindChoices
    from netbox_fms.models import FiberStrand, FiberStrandPath, FiberStrandPathHop
    from netbox_fms.path_graph import route_key_for

    kind_a = end_a_kind or (PathEndKindChoices.TERMINATED if end_a else PathEndKindChoices.OPEN)
    kind_b = end_b_kind or (PathEndKindChoices.TERMINATED if end_b else PathEndKindChoices.OPEN)
    cable_ids = [
        hop.fiber_cable.cable_id if isinstance(hop, FiberStrand) else hop.pk
        for hop in hops
        if hop._meta.model_name != "circuit"
    ]
    path = FiberStrandPath.objects.create(
        end_a_port=end_a,
        end_b_port=end_b,
        end_a_kind=kind_a,
        end_b_kind=kind_b,
        completeness=PathCompletenessChoices.from_end_kinds(kind_a, kind_b),
        route_key=route_key_for(cable_ids),
        computed_at=timezone.now(),
        **fields,
    )
    field_for = {"fiberstrand": "strand", "cable": "cable", "circuit": "provider_circuit"}
    for position, hop in enumerate(hops, start=1):
        FiberStrandPathHop.objects.create(path=path, position=position, **{field_for[hop._meta.model_name]: hop})
    return path


def assign_strand_path(circuit, strand_path, position=None, **fields):
    """Assign a path to a circuit the way assign_paths does, without the picker checks."""
    from netbox_fms.models import FiberCircuitPath, hops_snapshot

    if position is None:
        position = (circuit.paths.order_by("-position").values_list("position", flat=True).first() or 0) + 1
    fields.setdefault("assigned_hops", hops_snapshot(strand_path))
    return FiberCircuitPath.objects.create(circuit=circuit, strand_path=strand_path, position=position, **fields)


def make_cable_between(label, a_device, b_device, length=None):
    """A labelled dcim Cable from a new front port on a_device to one on b_device, optionally with a length in m."""
    from dcim.models import Cable

    return Cable.objects.create(
        label=label,
        a_terminations=[make_front_port(a_device, f"{label}-A")],
        b_terminations=[make_front_port(b_device, f"{label}-B")],
        length=length,
        length_unit="m" if length is not None else "",
    )


def make_route(cable, lengths, *, set_length=True, reverse=()):
    """Straight east-running chain of pathways (SRID 3348 meters), one per entry in lengths.

    Pathways join at shared Structures; CableSegments run 1..n from the cable's A end. A pathway whose
    0-based index is in reverse is drawn west, from its route end back to its route start.
    """
    from django.contrib.gis.geos import LineString, Point
    from netbox_pathways.models import CableSegment, DirectBuried, Structure

    def structure(index, x):
        return Structure.objects.create(name=f"route-{cable.pk}-{index}", geometry=Point(x, 0, srid=3348))

    x = 0.0
    start = structure(0, x)
    segments = []
    for seq, length in enumerate(lengths, start=1):
        end = structure(seq, x + length)
        ends, coords = (start, end), [(x, 0), (x + length, 0)]
        if seq - 1 in reverse:
            ends, coords = ends[::-1], coords[::-1]
        pathway = DirectBuried.objects.create(
            start_structure=ends[0],
            end_structure=ends[1],
            path=LineString(coords, srid=3348),
            length=length if set_length else None,
        )
        segments.append(CableSegment.objects.create(cable=cable, pathway=pathway, sequence=seq))
        start, x = end, x + length
    return segments


def create_fault_with_location(**fields):
    """Create a FiberFault, then write its location state straight to the row.

    FiberFault.save() re-estimates from evidence and wipes a location that has none, so a test
    that needs an estimated distance seeds it the way an estimator result would land.
    """
    from netbox_fms.models import FiberFault

    keys = ("located_at_status", "located_at", "distance_from_a", "estimate_note")
    location = {key: fields.pop(key) for key in keys if key in fields}
    fault = FiberFault.objects.create(**fields)
    if location:
        FiberFault.objects.filter(pk=fault.pk).update(**location)
        fault.refresh_from_db()
    return fault
