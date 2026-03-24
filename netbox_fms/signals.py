"""Signal handlers for splice plan diff cache invalidation and PortMapping protection."""

import contextvars

from django.core.exceptions import ValidationError
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save

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


def _rename_ports_for_cable(cable):
    """Rebuild RearPort/FrontPort names from structural data for a cable.

    Uses FiberCable -> FiberStrand -> FrontPort -> PortMapping -> RearPort
    to discover ports, avoiding dependency on CableTerminations which may be
    rebuilt during Cable.save().
    """
    from dcim.models import FrontPort, PortMapping, RearPort

    from .models import FiberCable

    try:
        fc = FiberCable.objects.get(cable=cable)
    except FiberCable.DoesNotExist:
        return

    label = str(cable)

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

    rps_to_update = []
    fps_to_update = []

    for rp_id, rp in rps.items():
        tube_pos = tube_positions.get(rp_id)

        if is_tubed and tube_pos:
            new_name = f"{label}:T{tube_pos}"
        else:
            new_name = label
        new_name = new_name[:64]

        if rp.name != new_name:
            rp.name = new_name
            rps_to_update.append(rp)

        for pm in pms:
            if pm.rear_port_id != rp_id:
                continue
            fp = pm.front_port
            if is_tubed and tube_pos:
                fp_new = f"{label}:T{tube_pos}:F{pm.rear_port_position}"
            else:
                fp_new = f"{label}:F{pm.rear_port_position}"
            fp_new = fp_new[:64]

            if fp.name != fp_new:
                fp.name = fp_new
                fps_to_update.append(fp)

    if rps_to_update:
        RearPort.objects.bulk_update(rps_to_update, ["name"])
    if fps_to_update:
        FrontPort.objects.bulk_update(fps_to_update, ["name"])


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
