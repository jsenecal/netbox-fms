"""Signal handlers for splice plan diff cache invalidation and PortMapping protection."""

import contextvars
import logging

from django.core.exceptions import ValidationError
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save

from . import naming

logger = logging.getLogger(__name__)

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
    from .models import FiberCable
    from .services import rear_port_cable_ids

    return FiberCable.objects.filter(cable_id__in=rear_port_cable_ids(device_id)).exists()


def _block_external_portmapping_change(instance):
    """Raise unless the change runs under the FMS bypass or the device is unmanaged."""
    if _fms_bypass.get():
        return
    if _is_fms_managed_device(instance.device_id):
        raise ValidationError("PortMappings on FMS-managed devices can only be modified through the FMS plugin.")


def _portmapping_pre_save(sender, instance, **kwargs):
    """Block external PortMapping changes on FMS-managed devices."""
    _block_external_portmapping_change(instance)


def _deletion_originates_from_device(origin):
    """Return True when a deletion cascade started at a dcim.Device.

    ``origin`` is the model instance or queryset ``delete()`` was called on,
    passed along by Django with every cascaded pre_delete signal.
    """
    from dcim.models import Device
    from django.db.models import QuerySet

    if isinstance(origin, Device):
        return True
    return isinstance(origin, QuerySet) and origin.model is Device


def _portmapping_pre_delete(sender, instance, origin=None, **kwargs):
    """Block external PortMapping deletion on FMS-managed devices.

    Deleting the device itself is allowed: removing a closure legitimately
    cascades through its PortMappings (a PortMapping only ever references
    ports of its own device, so a Device-originated cascade cannot reach
    another device's mappings). Any other origin -- the mapping itself, or
    a port being deleted out from under it -- stays blocked.
    """
    if _deletion_originates_from_device(origin):
        return
    _block_external_portmapping_change(instance)


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


def _cable_strand_ports(fc):
    """Discover a FiberCable's provisioned ports, without touching CableTerminations.

    Walks FiberCable -> FiberStrand -> FrontPort -> PortMapping (the rear
    ports hang off the mappings), avoiding dependency on CableTerminations
    which may be rebuilt during Cable.save(). Shared by the label-rerender
    path and the name planners (adoption one-shot, convert_port_names) so
    they cannot drift apart on which ports count as FMS-provisioned.

    Returns ``(strand_by_fp_id, pms)``: the strand backing each FrontPort id
    (with buffer_tube and ribbon preloaded), and the PortMapping list (with
    both ports and their devices preloaded).
    """
    from dcim.models import PortMapping

    strand_by_fp_id = {}
    for strand in fc.fiber_strands.select_related("buffer_tube", "ribbon"):
        for fp_id in (strand.front_port_a_id, strand.front_port_b_id):
            if fp_id is not None:
                strand_by_fp_id[fp_id] = strand

    if not strand_by_fp_id:
        return strand_by_fp_id, []

    pms = list(
        PortMapping.objects.filter(front_port_id__in=strand_by_fp_id).select_related(
            "front_port__device", "rear_port__device"
        )
    )
    return strand_by_fp_id, pms


def _rear_port_strand_groups(strand_by_fp_id, pms):
    """Yield ``(rear_port, strands)`` once per rear port, in mapping order.

    The shared consumption of :func:`_cable_strand_ports` output for
    per-rear-port decisions -- naming (services.plan_port_names) and
    labeling (label re-render) must group the same way or drift.
    """
    strands_by_rp = {}
    order = []
    for pm in pms:
        if pm.rear_port_id not in strands_by_rp:
            strands_by_rp[pm.rear_port_id] = []
            order.append(pm.rear_port)
        strands_by_rp[pm.rear_port_id].append(strand_by_fp_id[pm.front_port_id])
    for rp in order:
        yield rp, strands_by_rp[rp.pk]


def _render_cable_port_labels(fc):
    """Propose fresh labels for every FMS-provisioned port of a FiberCable.

    Returns ``{port: label}`` covering the strand FrontPorts and, through
    their PortMappings, the RearPorts on both ends. A target whose template
    is opted out (``naming.render`` returns None) contributes nothing, so
    the stored labels stay untouched. Raises :class:`naming.NamingError` on
    a broken template -- callers decide how to degrade.
    """
    compiled = naming.compile_labels()
    if not any(compiled.values()):
        return {}

    strand_by_fp_id, pms = _cable_strand_ports(fc)
    if not pms:
        return {}

    fct = fc.fiber_cable_type
    cable = fc.cable
    end_by_device_id = {}

    def _end(device):
        # _determine_cable_end runs queries; a cable rarely spans more than
        # two devices, so memoize per device.
        if device.pk not in end_by_device_id:
            from .services import _determine_cable_end

            end_by_device_id[device.pk] = _determine_cable_end(cable, device)
        return end_by_device_id[device.pk]

    def _ctx(device, tube=None, strand=None, ribbon=None, tray_assignment=None):
        return naming.port_context(
            cable=cable,
            cable_type=fct,
            device=device,
            end=_end(device),
            color_scheme=fct.color_scheme,
            tube=tube,
            strand=strand,
            ribbon=ribbon,
            tray_assignment=tray_assignment,
        )

    # (closure_id, buffer_tube_id) -> TubeAssignment, feeding the front-only
    # tray tokens; one query for the whole cable
    from .models import TubeAssignment
    from .services import shared_ribbon

    tube_ids = {s.buffer_tube_id for s in strand_by_fp_id.values() if s.buffer_tube_id}
    device_ids = {pm.front_port.device_id for pm in pms}
    assignment_by_key = {
        (ta.closure_id, ta.buffer_tube_id): ta
        for ta in TubeAssignment.objects.filter(buffer_tube_id__in=tube_ids, closure_id__in=device_ids).select_related(
            "tray"
        )
    }

    proposed = {}
    for pm in pms:
        strand = strand_by_fp_id[pm.front_port_id]
        fp = pm.front_port
        label = naming.render(
            naming.FRONT_PORT_LABEL,
            compiled,
            _ctx(
                fp.device,
                tube=strand.buffer_tube,
                strand=strand,
                tray_assignment=assignment_by_key.get((fp.device_id, strand.buffer_tube_id)),
            ),
        )
        if label is not None:
            proposed[fp] = label

    for rp, rp_strands in _rear_port_strand_groups(strand_by_fp_id, pms):
        # Every strand mapped to one rear port shares its buffer tube by
        # construction, so the first strand supplies the tube; the ribbon
        # only renders when the whole group shares it (services.shared_ribbon).
        label = naming.render(
            naming.REAR_PORT_LABEL,
            compiled,
            _ctx(rp.device, tube=rp_strands[0].buffer_tube, ribbon=shared_ribbon(rp_strands)),
        )
        if label is not None:
            proposed[rp] = label
    return proposed


def _stage_label_changes(proposed):
    """Assign changed labels onto the ports; return ``[(port, old_label)]``."""
    staged = []
    for port, label in proposed.items():
        if port.label != label:
            staged.append((port, port.label))
            port.label = label
    return staged


def _write_label_changes(staged):
    """Persist staged label changes."""
    from .services import bulk_update_port_field

    bulk_update_port_field([port for port, _old_label in staged], "label")


def _relabel_ports_for_cable(cable):
    """Re-render port labels after a cable save (e.g. a relabel).

    The label defaults embed the cable's display label, so a rename of the
    cable must flow into the labels of its provisioned ports. A broken
    template degrades to leaving every label alone.
    """
    from .models import FiberCable

    try:
        fc = FiberCable.objects.select_related("cable", "fiber_cable_type").get(cable=cable)
    except FiberCable.DoesNotExist:
        return

    try:
        staged = _stage_label_changes(_render_cable_port_labels(fc))
    except naming.NamingError as exc:
        logger.warning("Port label re-render skipped for cable %s: %s", cable.pk, exc)
        return
    if staged:
        _write_label_changes(staged)


def _cable_post_save(sender, instance, **kwargs):
    """Invalidate splice plan diff cache and re-render port labels on cable save.

    Port NAMES are deliberately not touched: they are write-once pk-based
    identifiers, so nothing about a cable save can require a rename. Only
    the labels -- the mutable display layer -- follow the cable.
    """
    _invalidate_plans_for_cable(instance)
    _relabel_ports_for_cable(instance)


def _cable_pre_delete(sender, instance, **kwargs):
    """Invalidate splice plan diff cache before a cable is deleted."""
    _invalidate_plans_for_cable(instance)


def _fibercable_post_save(sender, instance, **kwargs):
    """Re-render port labels when a FiberCable is linked to a Cable."""
    if instance.cable_id:
        _relabel_ports_for_cable(instance.cable)


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


def _relabel_for_tube_assignment(assignment):
    """Re-render the tube's cable labels when a template uses a tray token.

    Skipped entirely for tray-free templates (the defaults): an assignment
    change cannot alter such labels, and cable saves already cover every
    other trigger.
    """
    if not naming.labels_use_tray():
        return
    from django.core.exceptions import ObjectDoesNotExist

    try:
        fc = assignment.buffer_tube.fiber_cable
    except ObjectDoesNotExist:
        # Cascading delete: the tube is going away with its cable.
        return
    if fc.cable_id:
        _relabel_ports_for_cable(fc.cable)


def _tube_assignment_post_save(sender, instance, **kwargs):
    """Place the tube's closure-side front ports on the assigned tray."""
    from .services import sync_tube_assignment_ports

    sync_tube_assignment_ports(instance)
    _relabel_for_tube_assignment(instance)


def _tube_assignment_post_delete(sender, instance, **kwargs):
    """Return the tube's front ports to device level."""
    from .services import clear_tube_assignment_ports

    clear_tube_assignment_ports(instance.closure_id, instance.tray_id, instance.buffer_tube_id)
    _relabel_for_tube_assignment(instance)


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
