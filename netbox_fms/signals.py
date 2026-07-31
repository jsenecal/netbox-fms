"""Signal handlers for splice plan diff cache invalidation and PortMapping protection."""

import contextvars
import logging

from django.core.exceptions import ValidationError
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save

from . import naming

logger = logging.getLogger("netbox.plugins.netbox_fms")

_fms_bypass = contextvars.ContextVar("fms_bypass", default=False)


class fms_portmapping_bypass:  # noqa: N801
    """Context manager to bypass PortMapping protection in FMS plugin code."""

    def __enter__(self):
        self._token = _fms_bypass.set(True)
        return self

    def __exit__(self, *args):
        _fms_bypass.reset(self._token)


def _is_fms_managed_device(device_id):
    """Return True if the device has FMS-provisioned fiber ports."""
    from dcim.models import CableTermination, RearPort
    from django.contrib.contenttypes.models import ContentType

    from .models import FiberCable

    rp_ct = ContentType.objects.get_for_model(RearPort)
    rp_ids = set(RearPort.objects.filter(device_id=device_id).values_list("pk", flat=True))
    if not rp_ids:
        return False

    cable_ids = set(
        CableTermination.objects.filter(
            termination_type=rp_ct,
            termination_id__in=rp_ids,
        ).values_list("cable_id", flat=True)
    )
    return FiberCable.objects.filter(cable_id__in=cable_ids).exists()


def _portmapping_pre_save(sender, instance, **kwargs):
    """Block external PortMapping changes on FMS-managed devices."""
    if _fms_bypass.get():
        return
    if _is_fms_managed_device(instance.device_id):
        raise ValidationError("PortMappings on FMS-managed devices can only be modified through the FMS plugin.")


def _portmapping_pre_delete(sender, instance, **kwargs):
    """Block external PortMapping deletion on FMS-managed devices."""
    if _fms_bypass.get():
        return
    if _is_fms_managed_device(instance.device_id):
        raise ValidationError("PortMappings on FMS-managed devices can only be modified through the FMS plugin.")


def _invalidate_plans_for_cable(cable):
    """If this cable terminates on FrontPorts of a closure with a SplicePlan, mark diff stale."""
    from dcim.models import CableTermination, FrontPort
    from django.contrib.contenttypes.models import ContentType

    from .models import SplicePlan

    fp_ct = ContentType.objects.get_for_model(FrontPort)

    device_ids = set(
        FrontPort.objects.filter(
            pk__in=CableTermination.objects.filter(
                cable=cable,
                termination_type=fp_ct,
            ).values("termination_id"),
            module__isnull=False,
        ).values_list("device_id", flat=True)
    )

    if device_ids:
        SplicePlan.objects.filter(
            closure_id__in=device_ids,
            diff_stale=False,
        ).update(diff_stale=True)


def _tray_name_for(front_port):
    """Tray module bay name for a FrontPort, or None if it is not on a tray."""
    module = front_port.module
    return module.module_bay.name if module else None


def _tray_position_for(port, tube):
    """TubeAssignment position for ``port``'s placement of ``tube``, or None.

    Resolved by the port's OWN buffer tube, not by its tray alone.
    ``TubeAssignment``'s unique constraint is (closure, buffer_tube), so
    several tubes routinely share one tray; a (closure, tray) filter with
    ``.first()`` returns an arbitrary sibling -- the lowest position, under
    ``Meta.ordering`` -- while ``sync_tube_assignment_ports`` renders with the
    real ``assignment.position``. The two paths would then disagree and a
    port's name would flip-flop on every cable save.

    ``tray_id`` stays in the filter so the position always describes the tray
    the port is actually sitting on: a port moved to another tray by hand
    renders that tray's name with no position, rather than a position
    belonging to a tray it left.
    """
    from .models import TubeAssignment

    if not port.module_id or tube is None:
        return None
    return (
        TubeAssignment.objects.filter(
            closure_id=port.device_id,
            tray_id=port.module_id,
            buffer_tube_id=getattr(tube, "pk", tube),
        )
        .values_list("position", flat=True)
        .first()
    )


def _rename_ports_for_cable(cable):
    """Rebuild RearPort/FrontPort names and labels from the cable type's naming templates.

    Uses FiberCable -> FiberStrand -> FrontPort -> PortMapping -> RearPort
    to discover ports, avoiding dependency on CableTerminations which may be
    rebuilt during Cable.save().

    Runs on every ``Cable`` post_save, so a template render failure must
    never propagate: it is caught, logged, and the ports are left unchanged
    rather than breaking an unrelated cable save.

    ``end`` is normally "A" or "B", but ``_determine_cable_end`` can return
    "AB" for a self-looping cable (both sides terminated on the same
    device). That device-level value now reaches a REAR port's ``{{ end }}``
    only: a RearPort spans a whole tube and has no strand, so nothing finer
    is available for it. A FrontPort's end is derived from its strand
    instead -- "A" when the strand's ``front_port_a`` is this port, else
    "B" -- matching ``_provision_device_ports`` and
    ``services.render_port_strings``, the other two paths that write front
    port names, so a front port's name cannot flip-flop depending on which
    path last touched it. A FrontPort with no strand falls back to the
    device-level value.
    """
    from dcim.models import FrontPort, PortMapping, RearPort

    from .models import FiberCable
    from .services import _determine_cable_end

    try:
        fc = FiberCable.objects.get(cable=cable)
    except FiberCable.DoesNotExist:
        return

    # Collect all FrontPort IDs linked to this FiberCable's strands
    fp_ids = set()
    for field in ("front_port_a_id", "front_port_b_id"):
        ids = fc.fiber_strands.exclude(**{field: None}).values_list(field, flat=True)
        fp_ids.update(ids)

    if not fp_ids:
        return

    # Get RearPorts via PortMappings on these FrontPorts
    pms = list(PortMapping.objects.filter(front_port_id__in=fp_ids).select_related("rear_port", "front_port"))
    if not pms:
        return

    rp_set = {pm.rear_port_id for pm in pms}
    rps = {rp.pk: rp for rp in RearPort.objects.filter(pk__in=rp_set)}

    # Detect tubed vs non-tubed based on whether the FiberCable has buffer tubes
    is_tubed = fc.buffer_tubes.exists()

    # Build tube position mapping from BufferTubes
    tube_positions = {}  # rp_id -> tube_position
    if is_tubed:
        from django.db.models import Q

        for rp_id in rps:
            rp_fp_ids = {pm.front_port_id for pm in pms if pm.rear_port_id == rp_id}
            strand = (
                fc.fiber_strands.filter(Q(front_port_a_id__in=rp_fp_ids) | Q(front_port_b_id__in=rp_fp_ids))
                .select_related("buffer_tube")
                .first()
            )
            if strand and strand.buffer_tube:
                tube_positions[rp_id] = strand.buffer_tube.position

    fct = fc.fiber_cable_type
    tubes_by_position = {t.position: t for t in fc.buffer_tubes.all()}
    strand_by_fp = {}
    for strand in fc.fiber_strands.select_related("ribbon").all():
        for fp_id in (strand.front_port_a_id, strand.front_port_b_id):
            if fp_id:
                strand_by_fp[fp_id] = strand

    rps_to_update = []
    fps_to_update = []
    rp_fields = set()
    fp_fields = set()
    end_by_device_id = {}

    try:
        for rp_id, rp in rps.items():
            tube = tubes_by_position.get(tube_positions.get(rp_id))
            device = rp.device
            if device.pk not in end_by_device_id:
                end_by_device_id[device.pk] = _determine_cable_end(cable, device)
            end = end_by_device_id[device.pk]
            rp_ctx = naming.port_context(
                cable=cable,
                cable_type=fct,
                device=device,
                end=end,
                color_scheme=fct.color_scheme,
                tube=tube,
                tray=_tray_name_for(rp),
                tray_position=_tray_position_for(rp, tube),
            )
            changed = naming.apply_rendered(
                rp,
                name=fct.resolve_rear_port_name(**rp_ctx),
                label=fct.resolve_rear_port_label(**rp_ctx),
            )
            if changed:
                rp_fields |= changed
                rps_to_update.append(rp)

            for pm in pms:
                if pm.rear_port_id != rp_id:
                    continue
                fp = pm.front_port
                strand = strand_by_fp.get(fp.pk)
                # A front port sits on one end of one strand, so its end is
                # the strand's, never the device-level "AB".
                fp_end = end if strand is None else ("A" if strand.front_port_a_id == fp.pk else "B")
                fp_ctx = naming.port_context(
                    cable=cable,
                    cable_type=fct,
                    device=device,
                    end=fp_end,
                    color_scheme=fct.color_scheme,
                    tube=tube,
                    strand=strand,
                    strand_local=pm.rear_port_position,
                    tray=_tray_name_for(fp),
                    tray_position=_tray_position_for(fp, tube),
                )
                changed = naming.apply_rendered(
                    fp,
                    name=fct.resolve_front_port_name(**fp_ctx),
                    label=fct.resolve_front_port_label(**fp_ctx),
                )
                if changed:
                    fp_fields |= changed
                    fps_to_update.append(fp)
    except naming.NamingError:
        logger.exception("Naming template failed for cable %s; port names left unchanged", cable)
        return

    # Only update the columns some render actually changed. With no label
    # template configured (the default) that is ["name"] alone, exactly as it
    # was before naming templates existed -- pre-existing port labels, such as
    # those on ports adopted from a DeviceType template, are never touched.
    if rps_to_update:
        RearPort.objects.bulk_update(rps_to_update, sorted(rp_fields))
    if fps_to_update:
        FrontPort.objects.bulk_update(fps_to_update, sorted(fp_fields))


def _cable_post_save(sender, instance, **kwargs):
    """Invalidate splice plan diff cache and sync port names when a cable is saved."""
    _invalidate_plans_for_cable(instance)
    _rename_ports_for_cable(instance)


def _cable_pre_delete(sender, instance, **kwargs):
    """Invalidate splice plan diff cache before a cable is deleted."""
    _invalidate_plans_for_cable(instance)


def _fibercable_post_save(sender, instance, **kwargs):
    """Sync port names when a FiberCable is linked to a Cable."""
    if instance.cable_id:
        _rename_ports_for_cable(instance.cable)


def _closure_cable_entry_post_delete(sender, instance, **kwargs):
    """Clean up TubeAssignments when a ClosureCableEntry is deleted."""
    from .models import TubeAssignment

    TubeAssignment.objects.filter(
        closure_id=instance.closure_id,
        buffer_tube__fiber_cable_id=instance.fiber_cable_id,
    ).delete()


def _tube_assignment_pre_save(sender, instance, **kwargs):
    """Release the previously synced ports when an assignment is re-pointed."""
    if not instance.pk:
        return
    old = sender.objects.filter(pk=instance.pk).values("closure_id", "tray_id", "buffer_tube_id").first()
    if old is None:
        return
    new = (instance.closure_id, instance.tray_id, instance.buffer_tube_id)
    if (old["closure_id"], old["tray_id"], old["buffer_tube_id"]) != new:
        from .services import clear_tube_assignment_ports

        clear_tube_assignment_ports(old["closure_id"], old["tray_id"], old["buffer_tube_id"])


def _tube_assignment_post_save(sender, instance, **kwargs):
    """Place the tube's closure-side front ports on the assigned tray."""
    from .services import sync_tube_assignment_ports

    sync_tube_assignment_ports(instance)


def _tube_assignment_post_delete(sender, instance, **kwargs):
    """Return the tube's front ports to device level."""
    from .services import clear_tube_assignment_ports

    clear_tube_assignment_ports(instance.closure_id, instance.tray_id, instance.buffer_tube_id)


def connect_signals():
    """Connect cable and device signals. Called from AppConfig.ready()."""
    from dcim.models import Cable

    post_save.connect(_cable_post_save, sender=Cable, dispatch_uid="fms_cable_post_save")
    pre_delete.connect(_cable_pre_delete, sender=Cable, dispatch_uid="fms_cable_pre_delete")

    from .models import FiberCable

    post_save.connect(_fibercable_post_save, sender=FiberCable, dispatch_uid="fms_fibercable_post_save")

    from dcim.models import PortMapping

    pre_save.connect(_portmapping_pre_save, sender=PortMapping, dispatch_uid="fms_portmapping_pre_save")
    pre_delete.connect(_portmapping_pre_delete, sender=PortMapping, dispatch_uid="fms_portmapping_pre_delete")

    from .models import ClosureCableEntry

    post_delete.connect(
        _closure_cable_entry_post_delete,
        sender=ClosureCableEntry,
        dispatch_uid="fms_closure_cable_entry_post_delete",
    )

    from .models import TubeAssignment

    pre_save.connect(_tube_assignment_pre_save, sender=TubeAssignment, dispatch_uid="fms_tube_assignment_pre_save")
    post_save.connect(_tube_assignment_post_save, sender=TubeAssignment, dispatch_uid="fms_tube_assignment_post_save")
    post_delete.connect(
        _tube_assignment_post_delete, sender=TubeAssignment, dispatch_uid="fms_tube_assignment_post_delete"
    )
