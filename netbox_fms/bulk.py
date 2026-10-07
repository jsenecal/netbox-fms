"""Bulk writers for the fibre plant: many splices or tube assignments in a few statements.

Creating a splice through the ORM saves a Cable, two CableTerminations and
both FrontPorts one at a time, each save running every post_save receiver.
That is right for one splice and far too slow for a plant of them. The
writers here insert the rows in bulk and reproduce what the per-object
saves store (the termination's cached device columns, the cable fields on
the port, custom-field defaults).

Every writer has two modes:

``notify=True`` (the default, for interactive use) sends ``post_save`` for
each created or changed object after the bulk write, the way NetBox itself
does when it instantiates a device's components. Change logging, search and
every other receiver keep working.

``notify=False`` (for imports) sends nothing. The writer then does itself
what the receivers would have done that still matters: the search cache for
the new objects, the staleness of the closure's splice plans, the move of a
tube's ports onto its tray with the labels that follow, and (for port
provisioning, in services) the device's port counters. What quiet mode does
not do: notify users subscribed to a changed port, tell netbox-wdm about
ports created on a WDM node, or attach netbox-oss service components. A
receiver that is connected later will not hear quiet-mode writes either.

A writer validates its whole batch before the first write and raises
ValidationError naming every offender, so a rejected batch writes nothing.
Its writes are several statements: call it inside a transaction.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dcim.choices import LinkStatusChoices
from dcim.models import Cable, CablePath, CableTermination, FrontPort, Module
from dcim.utils import create_cablepaths, object_to_path_node
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import prefetch_related_objects
from django.db.models.signals import post_save
from django.utils import timezone
from extras.models import CustomField
from netbox.context import query_cache
from netbox.search.backends import search_backend
from utilities.conversion import to_meters
from utilities.prefetch import get_prefetchable_fields

if TYPE_CHECKING:
    from .models import TubeAssignment

BATCH_SIZE = 1000


@dataclass(frozen=True)
class SpliceSpec:
    """One splice to create: the two FrontPorts of the closure, and optional Cable attributes."""

    port_a_id: int
    port_b_id: int
    attrs: dict | None = None


@dataclass(frozen=True)
class TubeSpec:
    """One tube to route to a splice tray of the closure, with optional custom-field values."""

    buffer_tube_id: int
    tray_id: int
    custom_field_data: dict | None = None


@contextmanager
def cached_lookups():
    """Memoize NetBox's object-type and custom-field lookups for the duration, as a request does.

    Outside a request nothing caches them, so indexing or announcing a
    thousand objects asks the database the same two questions a thousand
    times. Inside a request the request's own cache is left in charge.
    """
    if query_cache.get() is not None:
        yield
        return
    token = query_cache.set(defaultdict(dict))
    try:
        yield
    finally:
        query_cache.reset(token)


def cf_defaults(model) -> dict:
    """Default custom-field values for new objects of a model, as a save through a form would set them."""
    return CustomField.objects.get_defaults_for_model(model) or {}


def announce(model, instances, *, created=True) -> None:
    """Send post_save for objects written in bulk, as NetBox does for bulk-created components."""
    if not instances:
        return
    prefetch_related_objects(instances, *get_prefetchable_fields(model))
    for instance in instances:
        post_save.send(
            sender=model, instance=instance, created=created, raw=False, using=instance._state.db, update_fields=None
        )


def _check_splices(closure, specs) -> dict:
    """The closure's ports named by the specs, by pk; raises when any spec cannot be created."""
    port_ids = [pk for spec in specs for pk in (spec.port_a_id, spec.port_b_id)]
    ports = {port.pk: port for port in FrontPort.objects.filter(pk__in=set(port_ids))}
    uses = Counter(port_ids)
    errors = []
    for pk in sorted(uses):
        port = ports.get(pk)
        if port is None or port.device_id != closure.pk:
            errors.append(f"Port {pk} is not a front port of {closure}.")
        elif port.cable_id is not None:
            errors.append(f"Port {pk} ({port.name}) already carries a cable.")
        if uses[pk] > 1:
            errors.append(f"Port {pk} is named {uses[pk]} times in this batch.")
    if errors:
        raise ValidationError(errors)
    return ports


def _jumper(spec, defaults) -> Cable:
    attrs = dict(spec.attrs or {})
    custom_field_data = {**defaults, **(attrs.pop("custom_field_data", None) or {})}
    attrs.setdefault("status", LinkStatusChoices.STATUS_CONNECTED)
    cable = Cable(custom_field_data=custom_field_data, **attrs)
    # Cable.save() derives these two; a bulk insert has to.
    if cable.length is None:
        cable.length_unit = None
        cable._abs_length = None
    elif cable.length_unit:
        cable._abs_length = to_meters(cable.length, cable.length_unit)
    return cable


def rebuild_paths_through(ports) -> None:
    """Rebuild every NetBox CablePath that runs through any of ``ports``.

    NetBox retraces paths only when Cable.save() sends its trace_paths
    signal, and the bulk writers never call save(); without this, a path
    that dead-ended at a port stays incomplete after the port is cabled.
    One overlap query finds every affected path once; NetBox's own
    rebuild_paths() queries once per port and would retrace a path again for
    every touched port it crosses.
    """
    nodes = [object_to_path_node(port) for port in ports]
    for path in CablePath.objects.filter(_nodes__overlap=nodes):
        path.delete()
        create_cablepaths(path.origins)


@cached_lookups()
def create_splices(closure, splices, *, notify=True) -> list[Cable]:
    """Splice pairs of the closure's FrontPorts: one connected Cable per pair, terminated on both.

    ``splices`` is an iterable of :class:`SpliceSpec`. Each port must be a
    FrontPort of ``closure`` that carries no cable, and may appear once in
    the batch. Returns the new cables in input order.
    """
    from .signals import mark_plans_stale

    specs = list(splices)
    if not specs:
        return []
    ports = _check_splices(closure, specs)

    defaults = cf_defaults(Cable)
    cables = [_jumper(spec, defaults) for spec in specs]
    Cable.objects.bulk_create(cables, batch_size=BATCH_SIZE)

    fp_ct = ContentType.objects.get_for_model(FrontPort)
    now = timezone.now()
    terminations, touched = [], []
    for spec, cable in zip(specs, cables, strict=True):
        for end, port_id in (("A", spec.port_a_id), ("B", spec.port_b_id)):
            # The columns CableTermination.cache_related_objects() fills on save.
            terminations.append(
                CableTermination(
                    cable=cable,
                    cable_end=end,
                    termination_type=fp_ct,
                    termination_id=port_id,
                    _device_id=closure.pk,
                    _rack_id=closure.rack_id,
                    _location_id=closure.location_id,
                    _site_id=closure.site_id,
                )
            )
            port = ports[port_id]
            if notify:
                port.snapshot()
            # What set_cable_termination() puts on the terminating object.
            port.cable = cable
            port.cable_end = end
            port.cable_connector = None
            port.cable_positions = None
            port.last_updated = now
            touched.append(port)
    CableTermination.objects.bulk_create(terminations, batch_size=BATCH_SIZE)
    FrontPort.objects.bulk_update(
        touched, ["cable", "cable_end", "cable_connector", "cable_positions", "last_updated"], batch_size=BATCH_SIZE
    )
    rebuild_paths_through(touched)

    if notify:
        announce(Cable, cables)
        announce(CableTermination, terminations)
        announce(FrontPort, touched, created=False)
    else:
        search_backend.cache(cables, remove_existing=False)
        mark_plans_stale([closure.pk])
    return cables


def _check_tubes(closure, specs) -> dict:
    """The tubes named by the specs, by pk; raises when any spec breaks a rule of TubeAssignment.clean()."""
    from .models import BufferTube, ClosureCableEntry, TubeAssignment
    from .services import is_splice_tray

    tube_ids = [spec.buffer_tube_id for spec in specs]
    trays = {
        tray.pk: tray
        for tray in Module.objects.filter(pk__in={spec.tray_id for spec in specs}).select_related(
            "module_type__tray_profile"
        )
    }
    tubes = {
        tube.pk: tube for tube in BufferTube.objects.filter(pk__in=set(tube_ids)).select_related("fiber_cable__cable")
    }
    entering = set(ClosureCableEntry.objects.filter(closure=closure).values_list("fiber_cable_id", flat=True))
    assigned = set(
        TubeAssignment.objects.filter(closure=closure, buffer_tube_id__in=set(tube_ids)).values_list(
            "buffer_tube_id", flat=True
        )
    )
    errors = []
    for pk, uses in sorted(Counter(tube_ids).items()):
        tube = tubes.get(pk)
        if tube is None or tube.fiber_cable_id not in entering:
            errors.append(f"Tube {pk}: its fiber cable does not enter {closure}.")
        if pk in assigned:
            errors.append(f"Tube {pk} is already assigned on {closure}.")
        if uses > 1:
            errors.append(f"Tube {pk} is named {uses} times in this batch.")
    for pk in sorted({spec.tray_id for spec in specs}):
        tray = trays.get(pk)
        if tray is None or tray.device_id != closure.pk:
            errors.append(f"Module {pk} is not a tray of the closure {closure}.")
        elif not is_splice_tray(tray):
            errors.append(f"Module {pk} ({tray}) is not a splice tray.")
    if errors:
        raise ValidationError(errors)
    return tubes


def closure_side_ports(closure_id, tube_ids) -> dict[int, list[int]]:
    """Tube pk -> the FrontPorts of its strands that sit on the closure, by pk.

    A strand contributes at most one port: front_port_a when it is on the
    closure, else front_port_b when that one is. This is the one definition
    of which ports a tube assignment moves.
    """
    from .models import FiberStrand

    ports: dict[int, list[int]] = {pk: [] for pk in tube_ids}
    rows = FiberStrand.objects.filter(buffer_tube_id__in=tube_ids).values_list(
        "buffer_tube_id", "front_port_a_id", "front_port_a__device_id", "front_port_b_id", "front_port_b__device_id"
    )
    for tube_id, port_a, device_a, port_b, device_b in rows:
        if port_a is not None and device_a == closure_id:
            ports[tube_id].append(port_a)
        elif port_b is not None and device_b == closure_id:
            ports[tube_id].append(port_b)
    return ports


@cached_lookups()
def assign_tubes(closure, assignments, *, notify=True) -> list[TubeAssignment]:
    """Route buffer tubes to splice trays of the closure and move their strand ports onto the trays.

    With ``notify=True`` each assignment is saved on its own, as before:
    the receivers move its ports one save at a time, so every move is
    logged. With ``notify=False`` the assignments are inserted together and
    each tray's ports are moved with one update.

    ``assignments`` is an iterable of :class:`TubeSpec`; the caller chooses
    the trays. A tray must be a splice-tray module of ``closure``, a tube
    must belong to a cable that enters it and may not be assigned there
    yet. Capacity is not enforced here, as nowhere else: an over-full tray
    is reported, never refused. Returns the assignments in input order.
    """
    from .models import TubeAssignment
    from .signals import relabel_tray_labels

    specs = list(assignments)
    if not specs:
        return []
    tubes = _check_tubes(closure, specs)

    defaults = cf_defaults(TubeAssignment)
    rows = [
        TubeAssignment(
            closure=closure,
            tray_id=spec.tray_id,
            buffer_tube_id=spec.buffer_tube_id,
            custom_field_data={**defaults, **(spec.custom_field_data or {})},
        )
        for spec in specs
    ]
    if notify:
        # The per-object path: its receivers move the ports one save at a time, so each move is logged.
        for row in rows:
            row.save()
        return rows

    TubeAssignment.objects.bulk_create(rows, batch_size=BATCH_SIZE)
    ports = closure_side_ports(closure.pk, list(tubes))
    by_tray: dict[int, list[int]] = {}
    for spec in specs:
        by_tray.setdefault(spec.tray_id, []).extend(ports[spec.buffer_tube_id])
    now = timezone.now()
    for tray_id, port_ids in by_tray.items():
        FrontPort.objects.filter(pk__in=port_ids).exclude(module_id=tray_id).update(module_id=tray_id, last_updated=now)
    relabel_tray_labels({tube.fiber_cable for tube in tubes.values()})
    return rows
