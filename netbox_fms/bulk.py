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
the two things the receivers would have done that still matter: the search
cache for the new objects and the staleness of the closure's splice plans.
A receiver that is connected later will not hear quiet-mode writes.

A writer runs inside the caller's transaction. It validates its whole batch
before the first write and raises ValidationError naming every offender, so
a rejected batch writes nothing.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from dcim.choices import LinkStatusChoices
from dcim.models import Cable, CableTermination, FrontPort
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import prefetch_related_objects
from django.db.models.signals import post_save
from django.utils import timezone
from extras.models import CustomField
from netbox.search.backends import search_backend
from utilities.conversion import to_meters
from utilities.prefetch import get_prefetchable_fields

BATCH_SIZE = 1000


@dataclass(frozen=True)
class SpliceSpec:
    """One splice to create: the two FrontPorts of the closure, and optional Cable attributes."""

    port_a_id: int
    port_b_id: int
    attrs: dict | None = None


def cf_defaults(model) -> dict:
    """Default custom-field values for new objects of a model, as a save through a form would set them."""
    return CustomField.objects.get_defaults_for_model(model) or {}


def announce(model, instances, *, created=True) -> None:
    """Send post_save for objects written in bulk, as NetBox does for bulk-created components."""
    if not instances:
        return
    prefetch_related_objects(instances, *get_prefetchable_fields(model))
    for instance in instances:
        post_save.send(sender=model, instance=instance, created=created, raw=False, using=instance._state.db)


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


def create_splices(closure, splices, *, notify=True) -> list[Cable]:
    """Splice pairs of the closure's FrontPorts: one connected Cable per pair, terminated on both.

    ``splices`` is an iterable of :class:`SpliceSpec`. Each port must be a
    FrontPort of ``closure`` that carries no cable, and may appear once in
    the batch. Returns the new cables in input order.
    """
    from .models import SplicePlan

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

    if notify:
        announce(Cable, cables)
        announce(CableTermination, terminations)
        announce(FrontPort, touched, created=False)
    else:
        search_backend.cache(cables, remove_existing=False)
        SplicePlan.objects.filter(closure=closure, diff_stale=False).update(diff_stale=True)
    return cables
