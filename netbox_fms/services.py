"""Diff computation engine for splice plans and link topology services."""

import logging
from collections import defaultdict
from dataclasses import dataclass

from dcim.models import Cable, CableTermination, Device, FrontPort, Module, ModuleBay, PortMapping, RearPort
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q

from . import naming
from .choices import FiberCircuitStatusChoices, SplicePlanStatusChoices, TrayRoleChoices
from .models import (
    BufferTube,
    ClosureCableEntry,
    FiberCable,
    FiberCircuit,
    FiberCircuitNode,
    SplicePlanEntry,
    TubeAssignment,
)
from .signals import fms_portmapping_bypass

logger = logging.getLogger(__name__)

# Diff-state bucket for splice pairs not attributable to any tray: a front
# port sits at device level (module=None) while its buffer tube is not
# assigned to a tray. Module pks start at 1, so 0 can never collide with a
# real tray, and it survives get_or_recompute_diff()'s int/str cache
# round-trip like any tray id.
UNASSIGNED_TRAY_ID = 0


class PlanNotApplicable(ValidationError):  # noqa: N818
    """Raised when a splice plan is not in a status that allows applying."""


class NeedsMappingConfirmation(Exception):  # noqa: N818
    """Raised when existing ports are found and need user confirmation."""

    def __init__(self, proposed_mapping, warnings=None):
        self.proposed_mapping = proposed_mapping
        self.warnings = warnings or []
        super().__init__("Port mapping confirmation required")


def propose_port_mapping(strand_count, frontports_by_position):
    """Build a position-based mapping from strand positions to FrontPorts.

    Args:
        strand_count: int — number of strands in the FiberCableType
        frontports_by_position: dict {rear_port_position: FrontPort}

    Returns: dict {strand_position: frontport_id}
    """
    mapping = {}
    for pos in range(1, strand_count + 1):
        fp = frontports_by_position.get(pos)
        if fp:
            mapping[pos] = fp.pk
    return mapping


def _determine_cable_end(cable, device):
    """Return 'A', 'B', or 'AB' based on which terminations exist on device."""
    rp_ct = ContentType.objects.get_for_model(RearPort)
    device_rp_ids = set(RearPort.objects.filter(device=device).values_list("pk", flat=True))
    if not device_rp_ids:
        return "A"

    terms = CableTermination.objects.filter(
        cable=cable,
        termination_type=rp_ct,
        termination_id__in=device_rp_ids,
    ).values_list("cable_end", flat=True)
    ends = set(terms)
    if "A" in ends and "B" in ends:
        return "AB"
    if "B" in ends:
        return "B"
    return "A"


def is_intra_closure_jumper(cable):
    """Return True when every termination of a cable is a FrontPort on one device.

    Such a cable is a splice jumper -- the zero-length cable applying a
    splice plan creates between two tray front ports of a closure -- not
    outside-plant fiber topology, so it must never carry a FiberCable.
    """
    terms = list(CableTermination.objects.filter(cable=cable).values_list("termination_type_id", "_device_id"))
    if not terms:
        return False
    fp_ct_id = ContentType.objects.get_for_model(FrontPort).pk
    if any(ct_id != fp_ct_id for ct_id, _ in terms):
        return False
    return len({device_id for _, device_id in terms}) == 1


def fiber_cable_terminates_on(fiber_cable, device_id):
    """Return True when the fiber cable's dcim.Cable terminates on the device.

    The single definition of "this cable reaches this closure" shared by
    ClosureCableEntry validation and the gland-label view guard.
    """
    return fiber_cable.cable_id in device_cable_ids(device_id)


def fiber_cable_for(cable):
    """The cable's FiberCable with its type preloaded, or None."""
    return FiberCable.objects.filter(cable=cable).select_related("fiber_cable_type").first()


def device_cable_ids(device_id):
    """Return the ids of every dcim.Cable terminating on a device."""
    return set(
        CableTermination.objects.filter(_device_id=device_id)
        .exclude(cable__isnull=True)
        .values_list("cable_id", flat=True)
    )


def rear_port_cable_ids(device_id):
    """Return the ids of the cables terminating on a device's rear ports."""
    return set(
        CableTermination.objects.filter(
            termination_type=ContentType.objects.get_for_model(RearPort),
            termination_id__in=RearPort.objects.filter(device_id=device_id).values("pk"),
        ).values_list("cable_id", flat=True)
    )


def device_topology_cable_ids(device_id):
    """Return the ids of the cables forming a closure's fiber topology.

    A cable qualifies when it terminates on one of the device's rear ports,
    or when it already carries a FiberCable. Splice jumpers, which join two
    tray front ports of the same closure and never carry a FiberCable, are
    excluded.
    """
    cable_ids = device_cable_ids(device_id)
    if not cable_ids:
        return cable_ids

    rear_terminated = rear_port_cable_ids(device_id) & cable_ids
    linked = set(FiberCable.objects.filter(cable_id__in=cable_ids).values_list("cable_id", flat=True))
    return rear_terminated | linked


def _render_port_label(compiled, target, context):
    """Render one port label for a new port, degrading to "" if it fails.

    ``None`` from :func:`naming.render` means the operator opted the target
    out of label management; a new port then starts with a blank label, the
    same coercion applied on a render failure.
    """
    if compiled is None:
        return ""
    try:
        return naming.render(target, compiled, context) or ""
    except naming.NamingError as exc:
        logger.warning("Port label render failed; leaving the label blank: %s", exc)
        return ""


def _compile_label_templates():
    """Compile the label templates, degrading to None (no labels) if broken."""
    try:
        return naming.compile_labels()
    except naming.NamingError as exc:
        logger.warning("Port label templates are invalid; provisioning ports without labels: %s", exc)
        return None


def strand_port_groups(strands):
    """Group strands by their innermost physical container, in fiber order.

    The rear-port structure mirrors the cable's actual hierarchy: a strand
    belongs to its ribbon when it has one (the mass-fusion splice unit,
    even inside a tube), else its buffer tube, else the cable itself.
    Returns ``[(container, [strands])]`` where ``container`` is a Ribbon,
    a BufferTube, or None, ordered by first strand position.
    """
    groups = {}
    ordered = []
    for strand in strands:
        if strand.ribbon_id is not None:
            key, container = ("R", strand.ribbon_id), strand.ribbon
        elif strand.buffer_tube_id is not None:
            key, container = ("T", strand.buffer_tube_id), strand.buffer_tube
        else:
            key, container = ("N", None), None
        if key not in groups:
            groups[key] = (container, [])
            ordered.append(groups[key])
        groups[key][1].append(strand)
    return ordered


def _provision_device_ports(fc, device, port_type, fk_field):
    """Create greenfield ports on a device for every strand of a FiberCable.

    One RearPort per physical container -- buffer tube for loose-tube
    fibers, RIBBON for ribbon fibers (ribbon-in-tube and central-core
    alike), or a single RearPort for a containerless cable -- with one
    FrontPort per strand joined by PortMappings numbered within the
    container. Each strand's ``fk_field`` ("front_port_a"/"front_port_b")
    is pointed at its new FrontPort. Does NOT create CableTerminations --
    callers terminate the cable on the returned RearPorts themselves.

    Names follow the write-once pk grammar (``netbox_fms.naming``); every
    port is also created with a rendered label, degrading to blank labels
    on a broken template rather than failing the provisioning.

    Returns: list of (container_or_None, rear_port, fiber_count) tuples,
    in fiber order.
    """
    provisioned = []
    strands = list(fc.fiber_strands.select_related("buffer_tube", "ribbon").order_by("position"))
    cable_id = fc.cable_id
    fct = fc.fiber_cable_type
    compiled = _compile_label_templates()
    end = "A" if fk_field == "front_port_a" else "B"
    ordinals = ribbon_ordinals(strands)

    def _ctx(tube=None, strand=None, ribbon=None):
        return naming.port_context(
            cable=fc.cable,
            cable_type=fct,
            device=device,
            end=end,
            color_scheme=fct.color_scheme,
            tube=tube,
            strand=strand,
            ribbon=ribbon,
        )

    with fms_portmapping_bypass():
        for container, group_strands in strand_port_groups(strands):
            first = group_strands[0]
            rear_ctx = _ctx(tube=first.buffer_tube, ribbon=first.ribbon if first.ribbon_id is not None else None)
            rp = RearPort.objects.create(
                device=device,
                name=rear_name_for_group(cable_id, group_strands, ordinals),
                label=_render_port_label(compiled, naming.REAR_PORT_LABEL, rear_ctx),
                type=port_type,
                positions=len(group_strands),
            )
            for i, strand in enumerate(group_strands, start=1):
                fp = FrontPort.objects.create(
                    device=device,
                    name=naming.front_port_name(cable_id, strand.position),
                    label=_render_port_label(
                        compiled, naming.FRONT_PORT_LABEL, _ctx(tube=strand.buffer_tube, strand=strand)
                    ),
                    type=port_type,
                )
                PortMapping.objects.create(
                    device=device,
                    front_port=fp,
                    rear_port=rp,
                    front_port_position=1,
                    rear_port_position=i,
                )
                setattr(strand, fk_field, fp)
                strand.save(update_fields=[fk_field])
            provisioned.append((container, rp, len(group_strands)))

    return provisioned


def ribbon_ordinals(strands):
    """Cable-wide ribbon numbers, keyed by ribbon id, in fiber order.

    ``Ribbon.position`` restarts inside every tube, so it cannot name a
    ribbon uniquely across the cable. The absolute fiber positions can:
    walking the strands in position order and numbering each ribbon on
    first sight yields the physical count order (tube-major for
    ribbon-in-tube, template order for central-core).
    """
    ordinals = {}
    for strand in sorted(strands, key=lambda s: s.position):
        if strand.ribbon_id is not None and strand.ribbon_id not in ordinals:
            ordinals[strand.ribbon_id] = len(ordinals) + 1
    return ordinals


def shared_ribbon(strands):
    """Return the one ribbon every strand belongs to, else None.

    A rear port represents a ribbon only when every strand mapped to it
    belongs to that one ribbon; legacy tube-grouped ribbon cables span
    several ribbons per rear port and get no ribbon treatment.
    """
    ribbon_ids = {s.ribbon_id for s in strands}
    if len(ribbon_ids) == 1 and None not in ribbon_ids:
        return strands[0].ribbon
    return None


def shared_tube(strands):
    """Return the one buffer tube every strand belongs to, else None."""
    tube_ids = {s.buffer_tube_id for s in strands}
    if len(tube_ids) == 1 and None not in tube_ids:
        return strands[0].buffer_tube
    return None


def rear_name_for_group(cable_id, strands, ordinals):
    """Write-once rear port name for the container shared by a strand group.

    Ribbon wins over tube (it is the mass-fusion splice unit); strands
    spanning containers -- a legacy tube-grouped ribbon cable, or an
    adopted whole-cable panel port -- fall back to the bare cable pk.
    """
    ribbon = shared_ribbon(strands)
    if ribbon is not None:
        return naming.rear_port_name(cable_id, ribbon=ordinals[ribbon.pk])
    tube = shared_tube(strands)
    if tube is not None:
        return naming.rear_port_name(cable_id, tube=tube.position)
    return naming.rear_port_name(cable_id)


def bulk_update_port_field(ports, field):
    """bulk_update one changed field on a mixed FrontPort/RearPort set."""
    by_model = {}
    for port in ports:
        by_model.setdefault(type(port), []).append(port)
    for model, group in by_model.items():
        model.objects.bulk_update(group, [field], batch_size=500)


def is_splice_tray(module):
    """True when the module's type carries a splice-tray profile."""
    profile = getattr(module.module_type, "tray_profile", None)
    return profile is not None and profile.tray_role == TrayRoleChoices.SPLICE_TRAY


def _device_template_port_names(device):
    """Names the DeviceType's templates gave the device's own front ports.

    Device-level templates carry no ``{module}`` token, so resolving them
    is a plain string read (virtual-chassis positions aside). NetBox 4.7
    added the device-aware ``{vc_position}`` placeholder and with it the
    ``device`` argument; older releases resolve ``{module}`` only.
    """
    templates = device.device_type.frontporttemplates.all()
    try:
        return {t.resolve_name(device=device) for t in templates}
    except TypeError:
        return {t.resolve_name() for t in templates}


def fms_owned_front_port_ids(pms):
    """Ids of the mapped FrontPorts that FMS created, judged by placement.

    FMS records that it touched a port (the strand FK) but not whether it
    created it, so adopted and provisioned ports look alike. Where the port
    sits tells them apart: tube assignment parks ports on splice trays
    only, so a port on one is ours; FMS creates ports at device level and
    leaves them there until a tray assignment moves them, so a device-level
    port is ours unless the DeviceType's templates account for its name;
    FMS never places a port on any other module, so such a port was
    instantiated from the ModuleType or moved there by hand.
    """
    owned = set()
    template_names_by_device_id = {}
    for pm in pms:
        fp = pm.front_port
        if fp.module_id is not None:
            if is_splice_tray(fp.module):
                owned.add(fp.pk)
            continue
        if fp.device_id not in template_names_by_device_id:
            template_names_by_device_id[fp.device_id] = _device_template_port_names(fp.device)
        if fp.name not in template_names_by_device_id[fp.device_id]:
            owned.add(fp.pk)
    return owned


def plan_port_names(fc):
    """Propose write-once names for the ports FMS created on a FiberCable.

    Only ports FMS owns (:func:`fms_owned_front_port_ids`) are renamed; a
    rear port follows its mapped front ports and is left alone as soon as
    one of them is foreign. Names are rebuilt within the EXISTING rear-port
    structure: each rear port is named for the one container (ribbon, else
    tube) shared by every strand mapped to it, falling back to the bare
    cable pk when its strands span containers (e.g. a legacy tube-grouped
    ribbon cable). Front ports always get the absolute-number name.

    Returns ``(renames, problems)``: ``renames`` is ``[(port, new_name)]``
    limited to ports whose name actually changes, and ``problems`` lists
    human-readable collision descriptions. Callers must not apply a plan
    that carries problems -- names are unique per device, so a partial
    rename would strand the cable between schemes.
    """
    from dcim.models import FrontPort, RearPort

    from .signals import _cable_strand_ports, _rear_port_strand_groups

    strand_by_fp_id, pms = _cable_strand_ports(fc)
    cable_id = fc.cable_id
    ordinals = ribbon_ordinals(strand_by_fp_id.values())
    owned_fp_ids = fms_owned_front_port_ids(pms)
    foreign_rp_ids = {pm.rear_port_id for pm in pms if pm.front_port_id not in owned_fp_ids}

    proposed = {}  # port -> new name
    seen_fp_ids = set()
    for pm in pms:
        if pm.front_port_id in seen_fp_ids or pm.front_port_id not in owned_fp_ids:
            continue
        seen_fp_ids.add(pm.front_port_id)
        strand = strand_by_fp_id[pm.front_port_id]
        proposed[pm.front_port] = naming.front_port_name(cable_id, strand.position)

    for rp, rp_strands in _rear_port_strand_groups(strand_by_fp_id, pms):
        if rp.pk not in foreign_rp_ids:
            proposed[rp] = rear_name_for_group(cable_id, rp_strands, ordinals)

    renames = [(port, name) for port, name in proposed.items() if port.name != name]

    problems = []
    for model in (FrontPort, RearPort):
        planned = [(port, name) for port, name in renames if isinstance(port, model)]
        by_device = {}
        for port, name in planned:
            key = (port.device_id, name)
            if key in by_device:
                problems.append(f"{model.__name__} name {name!r} proposed for two ports on device {port.device}")
            by_device[key] = port
        # A proposed name matching the current name of a DIFFERENT port in the
        # plan is also refused: the end state would be consistent, but the
        # non-deferrable unique constraint can reject the swap mid-update.
        current = {(port.device_id, port.name): port.pk for port, _ in planned}
        renamed_ids = {port.pk for port, _ in planned}
        for (device_id, name), port in by_device.items():
            if current.get((device_id, name), port.pk) != port.pk:
                problems.append(f"{model.__name__} {name!r} is still held by another port being renamed")
                continue
            holder = model.objects.filter(device_id=device_id, name=name).exclude(pk__in=renamed_ids).first()
            if holder is not None:
                problems.append(
                    f"{model.__name__} {name!r} would collide with existing port {holder.pk} on {holder.device}"
                )

    return renames, problems


def apply_port_names(renames):
    """Persist a collision-free rename plan."""
    for port, name in renames:
        port.name = name
    bulk_update_port_field([port for port, _name in renames], "name")


@transaction.atomic
def link_cable_topology(cable, fiber_cable_type, device, port_type="splice", port_mapping=None):
    """Link a cable's FiberCable strands to ports, adopting or creating them.

    Creates the FiberCable when the cable has none; a cable that already
    carries one (e.g. created through the FiberCable form, which links no
    strands) is linked in place -- pass ``fiber_cable_type=None`` then, the
    existing FiberCable fixes the type.

    Args:
        cable: dcim.Cable instance
        fiber_cable_type: FiberCableType instance, or None when the cable
            already carries a FiberCable
        device: dcim.Device where ports will be created/adopted
        port_type: port type string (default "splice")
        port_mapping: optional dict {strand_position: frontport_id} for adopt path

    Returns: (FiberCable, warnings_list)
    Raises: NeedsMappingConfirmation if existing ports found without port_mapping
    """
    warnings = []
    rp_ct = ContentType.objects.get_for_model(RearPort)

    existing_fc = fiber_cable_for(cable)
    if existing_fc is not None:
        if fiber_cable_type is not None and fiber_cable_type.pk != existing_fc.fiber_cable_type_id:
            raise ValueError(
                f"Cable already carries a FiberCable of type {existing_fc.fiber_cable_type}; "
                "pass fiber_cable_type=None to link its strands."
            )
        fiber_cable_type = existing_fc.fiber_cable_type
    elif fiber_cable_type is None:
        raise ValueError("fiber_cable_type is required when the cable has no FiberCable yet.")

    # Detect pre-existing RearPorts terminated by this cable on this device
    existing_term_rp_ids = set(
        CableTermination.objects.filter(
            cable=cable,
            termination_type=rp_ct,
        )
        .filter(termination_id__in=RearPort.objects.filter(device=device).values("pk"))
        .values_list("termination_id", flat=True)
    )

    if existing_term_rp_ids:
        # Adopt path: collect FrontPorts mapped to these RearPorts. A cable may
        # terminate on several RearPorts (one per tube/module), each mapping its
        # own positions 1..N, so offset per-RearPort positions to global strand
        # positions. Order RearPorts by termination connector when set, falling
        # back to natural name order.
        connector_by_rp = dict(
            CableTermination.objects.filter(
                cable=cable,
                termination_type=rp_ct,
                termination_id__in=existing_term_rp_ids,
            ).values_list("termination_id", "connector")
        )
        rear_ports = list(RearPort.objects.filter(pk__in=existing_term_rp_ids))
        rear_ports.sort(key=lambda rp: (connector_by_rp.get(rp.pk) is None, connector_by_rp.get(rp.pk) or 0))

        fps_by_position = {}
        offset = 0
        for rp in rear_ports:
            for pm in PortMapping.objects.filter(rear_port=rp).select_related("front_port"):
                fps_by_position[offset + pm.rear_port_position] = pm.front_port
            offset += rp.positions

        if port_mapping is None:
            proposed = propose_port_mapping(fiber_cable_type.strand_count, fps_by_position)
            confirm_warnings = []
            if len(fps_by_position) != fiber_cable_type.strand_count:
                confirm_warnings.append(
                    f"Count mismatch: {fiber_cable_type.strand_count} strands "
                    f"but {len(fps_by_position)} existing ports."
                )
            raise NeedsMappingConfirmation(proposed, confirm_warnings)

    # Create the FiberCable (triggers _instantiate_components) unless the
    # cable already carries one, whose existing strands get linked instead
    fc = existing_fc or FiberCable.objects.create(cable=cable, fiber_cable_type=fiber_cable_type)

    # Set cable profile (use queryset update to avoid Cable.save() side effects)
    profile_key = fiber_cable_type.get_cable_profile()
    if profile_key:
        Cable.objects.filter(pk=cable.pk).update(profile=profile_key)
        cable.profile = profile_key
    else:
        warnings.append("Profile not found in registry; cable profile not set.")

    # Determine cable side
    cable_end = _determine_cable_end(cable, device)
    fk_field = "front_port_a" if cable_end in ("A", "AB") else "front_port_b"

    with fms_portmapping_bypass():
        if existing_term_rp_ids and port_mapping is not None:
            # Adopt path: link strands to existing FrontPorts
            for strand in fc.fiber_strands.all().order_by("position"):
                fp_id = port_mapping.get(strand.position)
                if fp_id:
                    setattr(strand, fk_field, FrontPort.objects.get(pk=fp_id))
                    strand.save(update_fields=[fk_field])
        else:
            # Greenfield path: create ports, then terminate the cable on them.
            # connector/positions enable profile-based tracing: connectors are
            # numbered over the provisioned groups (tubes or ribbons) in fiber
            # order, matching the profile derived by get_cable_profile().
            for connector, (_container, rp, fiber_count) in enumerate(
                _provision_device_ports(fc, device, port_type, fk_field), start=1
            ):
                CableTermination.objects.create(
                    cable=cable,
                    cable_end=cable_end if cable_end != "AB" else "A",
                    termination_type=rp_ct,
                    termination_id=rp.pk,
                    connector=connector,
                    positions=list(range(1, fiber_count + 1)),
                )

    return fc, warnings


@transaction.atomic
def create_closure_cable(*, device_a, device_b, fiber_cable_type, port_type="splice", cable_attrs=None):
    """Create a dcim.Cable + FiberCable between two closures, greenfield.

    Follows the create-then-terminate choreography: the Cable is created
    unterminated via the ORM (Cable.clean() only requires both-end
    terminations at creation through full_clean paths), the FiberCable is
    created (auto-instantiating tubes/strands), ports are provisioned on
    both devices, then a_terminations/b_terminations are assigned and the
    cable re-saved so Cable.save() builds CableTerminations with
    connector/positions for profile-based tracing. Registers the cable at
    both closures with blank ClosureCableEntries.

    Returns: (FiberCable, warnings_list)
    """
    if device_a == device_b:
        raise ValueError("Cable ends must be different devices.")
    warnings = []
    cable = Cable(**(cable_attrs or {}))
    cable.save()
    fc = FiberCable.objects.create(cable=cable, fiber_cable_type=fiber_cable_type)

    provisioned_a = _provision_device_ports(fc, device_a, port_type, "front_port_a")
    provisioned_b = _provision_device_ports(fc, device_b, port_type, "front_port_b")

    profile_key = fiber_cable_type.get_cable_profile()
    if profile_key:
        cable.profile = profile_key
    else:
        warnings.append("Profile not found in registry; cable profile not set.")

    cable.a_terminations = [rp for _, rp, _ in provisioned_a]
    cable.b_terminations = [rp for _, rp, _ in provisioned_b]
    cable.full_clean()
    cable.save()

    ClosureCableEntry.objects.create(closure=device_a, fiber_cable=fc)
    ClosureCableEntry.objects.create(closure=device_b, fiber_cable=fc)
    return fc, warnings


def front_port_splice_pairs(front_port_ids):
    """Return (a_id, b_id) pairs of cables fully terminated inside a FrontPort id set.

    Each pair is a live splice jumper within the given scope. Callers choose
    the scope explicitly: get_live_state (feeding the diff/apply engine) and
    the closure-strands editor view both pass every front port of the
    closure, so splices on device-level ports (unassigned tubes) are seen
    by the engine and the editor alike.
    """
    fp_ct = ContentType.objects.get_for_model(FrontPort)
    terminations = CableTermination.objects.filter(
        termination_type=fp_ct,
        termination_id__in=front_port_ids,
    ).values_list("cable_id", "termination_id", "cable_end")

    cable_terms = {}
    for cable_id, term_id, cable_end in terminations:
        cable_terms.setdefault(cable_id, {})[cable_end] = term_id

    pairs = []
    for ends in cable_terms.values():
        if "A" not in ends or "B" not in ends:
            continue
        a_id, b_id = ends["A"], ends["B"]
        if a_id in front_port_ids and b_id in front_port_ids:
            pairs.append((a_id, b_id))
    return pairs


@dataclass
class TrayUtilization:
    """What one tray module holds, measured against its TrayProfile.

    Capacity is a count of splice positions, never a map of which position
    a splice sits in. A position joins one A-side and one B-side strand, so
    the tray can physically hold twice that many strands. Tube capacity is
    optional: None means the profile sets no limit.
    """

    tray: Module
    profile: object
    tubes: int = 0
    strands: int = 0
    splices: int = 0

    @property
    def splice_capacity(self):
        return self.profile.splice_capacity

    @property
    def tube_capacity(self):
        return self.profile.tube_capacity

    @property
    def strand_capacity(self):
        return 2 * self.profile.splice_capacity

    @property
    def remaining_strands(self):
        return self.strand_capacity - self.strands

    @property
    def remaining_tubes(self):
        if self.tube_capacity is None:
            return None
        return self.tube_capacity - self.tubes

    @property
    def over_tubes(self):
        return self.tube_capacity is not None and self.tubes > self.tube_capacity

    @property
    def over_strands(self):
        return self.strands > self.strand_capacity

    @property
    def over_splices(self):
        return self.splices > self.splice_capacity

    @property
    def over_capacity(self):
        return self.over_tubes or self.over_strands or self.over_splices

    def fits(self, tube_count, strand_count):
        """True if adding tube_count tubes carrying strand_count strands stays within capacity."""
        if self.remaining_tubes is not None and tube_count > self.remaining_tubes:
            return False
        return strand_count <= self.remaining_strands


def tray_utilization(closure):
    """Return {module_id: TrayUtilization} for every profiled module on the closure.

    Tubes and strands come from TubeAssignment rows; splices are the live
    splice pairs get_live_state attributes to the tray, so a splice whose
    other end sits on a device-level port still counts on the tray that
    holds it.
    """
    modules = Module.objects.filter(device=closure, module_type__tray_profile__isnull=False).select_related(
        "module_type__tray_profile"
    )
    result = {m.pk: TrayUtilization(tray=m, profile=m.module_type.tray_profile) for m in modules}
    if not result:
        return result

    per_tray = (
        TubeAssignment.objects.filter(closure=closure, tray_id__in=result)
        .values("tray_id")
        .annotate(tubes=Count("pk", distinct=True), strands=Count("buffer_tube__fiber_strands"))
    )
    for row in per_tray:
        result[row["tray_id"]].tubes = row["tubes"]
        result[row["tray_id"]].strands = row["strands"]

    for tray_id, pairs in get_live_state(closure).items():
        if tray_id in result:
            result[tray_id].splices = len(pairs)
    return result


def auto_assign_tubes(closure):
    """Assign every unassigned tube on the closure to a splice tray with room.

    Tubes at the same position across cables (T1 from Cable A and T1 from
    Cable B) are placed together on the first tray that can take the whole
    group, since they are the tubes most likely to be spliced to each
    other; trays fill in order rather than round-robin so a closure uses as
    few trays as its capacity allows. A group that fits nowhere is split
    tube by tube. Trays are never filled past their profile capacity; tubes
    that fit nowhere stay unassigned.
    """
    trays = sorted(
        (u for u in tray_utilization(closure).values() if is_splice_tray(u.tray)),
        key=lambda u: u.tray.pk,
    )
    if not trays:
        return

    assigned_tube_ids = TubeAssignment.objects.filter(closure=closure).values_list("buffer_tube_id", flat=True)
    cable_ids = ClosureCableEntry.objects.filter(closure=closure).values_list("fiber_cable_id", flat=True)
    unassigned = (
        BufferTube.objects.filter(fiber_cable_id__in=cable_ids)
        .exclude(pk__in=assigned_tube_ids)
        .annotate(strand_total=Count("fiber_strands"))
        .order_by("position", "fiber_cable__pk")
    )

    by_position = defaultdict(list)
    for tube in unassigned:
        by_position[tube.position].append(tube)

    def place(tray, tubes):
        for tube in tubes:
            TubeAssignment.objects.create(closure=closure, tray=tray.tray, buffer_tube=tube)
        tray.tubes += len(tubes)
        tray.strands += sum(t.strand_total for t in tubes)

    def first_fit(tubes):
        total = sum(t.strand_total for t in tubes)
        for tray in trays:
            if tray.fits(len(tubes), total):
                place(tray, tubes)
                return True
        return False

    for position in sorted(by_position):
        tubes = by_position[position]
        if not first_fit(tubes):
            for tube in tubes:
                first_fit([tube])


def get_live_state(closure):
    """
    Read current FrontPort<->FrontPort connections on a closure's front ports.
    Returns: {tray_module_id: set((port_a_id, port_b_id), ...)}
    Pairs are normalized: (min_id, max_id). Every front port of the closure
    is considered; pairs touching a device-level port (unassigned tube) are
    grouped under UNASSIGNED_TRAY_ID for that end.
    """
    port_to_module = dict(FrontPort.objects.filter(device=closure).values_list("pk", "module_id"))
    frontport_ids = set(port_to_module.keys())

    if not frontport_ids:
        return {}

    state = {}
    for port_a_id, port_b_id in front_port_splice_pairs(frontport_ids):
        pair = (min(port_a_id, port_b_id), max(port_a_id, port_b_id))

        mod_a = port_to_module[port_a_id] or UNASSIGNED_TRAY_ID
        mod_b = port_to_module[port_b_id] or UNASSIGNED_TRAY_ID
        state.setdefault(mod_a, set()).add(pair)
        if mod_a != mod_b:
            state.setdefault(mod_b, set()).add(pair)

    return state


def get_desired_state(plan):
    """
    Read desired FrontPort<->FrontPort connections from a SplicePlan's entries.
    Returns: {tray_module_id: set((port_a_id, port_b_id), ...)}
    Only includes pairs where both ports belong to the closure device.
    Fiber A keeps the entry's recorded tray attribution while it is
    tray-mounted; a device-level port on either end books the pair under
    UNASSIGNED_TRAY_ID instead, mirroring get_live_state's bucketing.
    """
    closure = plan.closure
    local_fp_to_module = dict(FrontPort.objects.filter(device=closure).values_list("pk", "module_id"))

    entries = list(plan.entries.values_list("tray_id", "fiber_a_id", "fiber_b_id"))

    state = {}
    for tray_id, fa_id, fb_id in entries:
        # Skip pairs where either port is not on this closure device
        if fa_id not in local_fp_to_module or fb_id not in local_fp_to_module:
            continue

        pair = (min(fa_id, fb_id), max(fa_id, fb_id))
        fa_bucket = tray_id if local_fp_to_module[fa_id] is not None else UNASSIGNED_TRAY_ID
        state.setdefault(fa_bucket, set()).add(pair)

        fb_bucket = local_fp_to_module[fb_id] or UNASSIGNED_TRAY_ID
        if fb_bucket != fa_bucket:
            state.setdefault(fb_bucket, set()).add(pair)

    return state


def compute_diff(plan):
    """
    Compute the diff between desired and live state.
    Returns: {tray_module_id: {"add": list, "remove": list, "unchanged": list}}
    Keys are int tray IDs, plus UNASSIGNED_TRAY_ID for pairs touching
    device-level ports. Values are lists of [port_a_id, port_b_id] pairs.
    """
    live = get_live_state(plan.closure)
    desired = get_desired_state(plan)

    all_tray_ids = set(live.keys()) | set(desired.keys())

    diff = {}
    for tray_id in all_tray_ids:
        live_pairs = live.get(tray_id, set())
        desired_pairs = desired.get(tray_id, set())
        diff[tray_id] = {
            "add": [list(p) for p in (desired_pairs - live_pairs)],
            "remove": [list(p) for p in (live_pairs - desired_pairs)],
            "unchanged": [list(p) for p in (desired_pairs & live_pairs)],
        }

    return diff


def get_or_recompute_diff(plan):
    """
    Return cached diff if fresh, otherwise recompute and cache.
    Always returns dict with int tray_id keys.
    """
    if not plan.diff_stale and plan.cached_diff is not None:
        return {int(k): v for k, v in plan.cached_diff.items()}

    diff = compute_diff(plan)

    # JSON requires string keys
    plan.cached_diff = {str(k): v for k, v in diff.items()}
    plan.diff_stale = False
    plan.save(update_fields=["cached_diff", "diff_stale"])

    return diff


def _claimed_front_port_ids(plan, port_ids):
    """Front port ids among ``port_ids`` claimed by other active plans on the closure.

    Fiber exclusivity lets only one non-archived plan reference a fiber, so a
    live-state import must leave those fibers to the plan that holds them
    instead of tripping SplicePlanEntry's validation.
    """
    if not port_ids:
        return set()
    active_statuses = (
        SplicePlanStatusChoices.DRAFT,
        SplicePlanStatusChoices.PENDING_APPROVAL,
        SplicePlanStatusChoices.APPROVED,
    )
    rows = (
        SplicePlanEntry.objects.filter(
            plan__closure_id=plan.closure_id,
            plan__status__in=active_statuses,
        )
        .exclude(plan_id=plan.pk)
        .filter(Q(fiber_a_id__in=port_ids) | Q(fiber_b_id__in=port_ids))
        .values_list("fiber_a_id", "fiber_b_id")
    )
    claimed = set()
    for fa_id, fb_id in rows:
        claimed.add(fa_id)
        claimed.add(fb_id)
    return claimed


def import_live_state(plan):
    """
    Bootstrap a plan from the closure's current live connections.
    Creates SplicePlanEntry rows for each existing FrontPort<->FrontPort pair.

    A pair is anchored on a tray-mounted port (fiber_a, whose module is the
    entry's tray); a pair whose ports both sit at device level (unassigned
    tubes) cannot become an entry -- SplicePlanEntry.tray is NOT NULL -- so
    it is skipped and counted instead of imported silently or crashing. Pairs
    touching a fiber already claimed by another active plan are likewise
    skipped and counted: fiber exclusivity reserves them for that plan.
    Pairs touching a fiber the plan's own entries already reference are
    skipped too, making a re-import a sync that only picks up live splices
    the plan does not know about yet.

    Returns {"imported": int, "skipped_unassigned": int, "skipped_claimed": int,
    "skipped_existing": int}.
    """
    live = get_live_state(plan.closure)

    # Collect unique pairs across all trays
    all_pairs = set()
    for pairs in live.values():
        all_pairs.update(pairs)

    # Build port -> module lookup
    port_ids = set()
    for pa, pb in all_pairs:
        port_ids.add(pa)
        port_ids.add(pb)
    port_to_module = dict(FrontPort.objects.filter(pk__in=port_ids).values_list("pk", "module_id"))
    claimed_ids = _claimed_front_port_ids(plan, port_ids)

    own_ids = set()
    if all_pairs:
        for fa_id, fb_id in plan.entries.values_list("fiber_a_id", "fiber_b_id"):
            own_ids.add(fa_id)
            own_ids.add(fb_id)

    entries = []
    skipped_unassigned = 0
    skipped_claimed = 0
    skipped_existing = 0
    for port_a_id, port_b_id in all_pairs:
        if port_a_id in own_ids or port_b_id in own_ids:
            skipped_existing += 1
            continue
        if port_a_id in claimed_ids or port_b_id in claimed_ids:
            skipped_claimed += 1
            continue
        if port_to_module.get(port_a_id) is None:
            # fiber_a must carry the tray; lead with the tray-mounted port
            port_a_id, port_b_id = port_b_id, port_a_id
        tray_id = port_to_module.get(port_a_id)
        if tray_id is None:
            skipped_unassigned += 1
            continue
        entries.append(
            SplicePlanEntry(
                plan=plan,
                tray_id=tray_id,
                fiber_a_id=port_a_id,
                fiber_b_id=port_b_id,
            )
        )

    for entry in entries:
        entry.full_clean()

    SplicePlanEntry.objects.bulk_create(entries)
    plan.diff_stale = True
    plan.save(update_fields=["diff_stale"])
    return {
        "imported": len(entries),
        "skipped_unassigned": skipped_unassigned,
        "skipped_claimed": skipped_claimed,
        "skipped_existing": skipped_existing,
    }


def protecting_nodes(front_port_ids, user=None):
    """
    FiberCircuitNodes on active (non-decommissioned) circuits referencing
    the given front ports.

    Integrity checks (blocking edits to circuit-protected splices) must
    leave ``user`` unset so every circuit counts regardless of the
    requesting user's permissions; display contexts pass ``user`` to
    restrict the rows to that user's visible objects.
    """
    qs = FiberCircuitNode.objects.all()
    if user is not None:
        qs = qs.restrict(user, "view")
    return (
        qs.filter(front_port_id__in=front_port_ids)
        .exclude(path__circuit__status=FiberCircuitStatusChoices.DECOMMISSIONED)
        .select_related("path__circuit")
    )


def protecting_circuit_groups(references, user):
    """
    Map each input reference to the circuits whose paths it carries.

    ``references`` maps FiberCircuitNode reference field names ("cable",
    "front_port", ...) to lists of object IDs. Returns ``(circuit_ids,
    groups)``: ``groups`` is ``{param: {ref_id: set of circuit IDs}}``
    covering every input ID (an empty set marks a reference carrying no
    circuit), and ``circuit_ids`` is their union.

    Rows are restricted to circuits the user may view. Decommissioned
    circuits are excluded for the same reason ``protecting_nodes`` excludes
    them; since decommissioning deletes a circuit's nodes, the exclusion is
    belt-and-suspenders rather than load-bearing.
    """
    restricted = FiberCircuit.objects.restrict(user, "view").exclude(status=FiberCircuitStatusChoices.DECOMMISSIONED)
    circuit_ids = set()
    groups = {}
    for param, ids in references.items():
        matched = {ref_id: set() for ref_id in ids}
        pairs = FiberCircuitNode.objects.filter(**{f"{param}_id__in": ids}, path__circuit__in=restricted).values_list(
            f"{param}_id", "path__circuit_id"
        )
        for ref_id, circuit_id in pairs:
            matched[ref_id].add(circuit_id)
            circuit_ids.add(circuit_id)
        groups[param] = matched
    return circuit_ids, groups


def apply_diff(plan):
    """
    Execute the full plan-vs-live diff: create cables for "add", delete
    cables for "remove". Only approved plans may be applied; the check
    lives here so every apply path honours the approval workflow. On
    success the plan is archived. Returns {"added": int, "removed": int}.
    """
    if plan.status != SplicePlanStatusChoices.APPROVED:
        raise PlanNotApplicable(
            f"Cannot apply plan '{plan}': status is '{plan.status}' -- only approved plans can be applied."
        )

    diff = compute_diff(plan)

    fp_ct = ContentType.objects.get_for_model(FrontPort)
    added = 0
    removed = 0

    # Deduplicate inter-platter pairs (same pair appears on both trays)
    all_adds = set()
    all_removes = set()
    for _tray_id, tray_diff in diff.items():
        for pair in tray_diff["add"]:
            all_adds.add(tuple(pair))
        for pair in tray_diff["remove"]:
            all_removes.add(tuple(pair))

    with transaction.atomic():
        # Process removals
        for port_a_id, port_b_id in all_removes:
            cable_ids_a = set(
                CableTermination.objects.filter(termination_type=fp_ct, termination_id=port_a_id).values_list(
                    "cable_id", flat=True
                )
            )
            cable_ids_b = set(
                CableTermination.objects.filter(termination_type=fp_ct, termination_id=port_b_id).values_list(
                    "cable_id", flat=True
                )
            )
            common = cable_ids_a & cable_ids_b
            for cable_id in common:
                Cable.objects.filter(pk=cable_id).delete()
                removed += 1

        # Process additions — clear any existing terminations first (re-splice case)
        add_port_ids = {p for pair in all_adds for p in pair}
        conflicting_terms = CableTermination.objects.filter(
            termination_type=fp_ct,
            termination_id__in=add_port_ids,
        )
        conflicting_cable_ids = set(conflicting_terms.values_list("cable_id", flat=True))
        if conflicting_cable_ids:
            Cable.objects.filter(pk__in=conflicting_cable_ids).delete()

        for port_a_id, port_b_id in all_adds:
            cable = Cable(
                status="connected",
            )
            cable.save()
            CableTermination.objects.create(
                cable=cable,
                cable_end="A",
                termination_type=fp_ct,
                termination_id=port_a_id,
            )
            CableTermination.objects.create(
                cable=cable,
                cable_end="B",
                termination_type=fp_ct,
                termination_id=port_b_id,
            )
            added += 1

        # Archive the applied plan so it becomes a read-only historical record
        plan.status = SplicePlanStatusChoices.ARCHIVED
        plan.cached_diff = None
        plan.diff_stale = True
        plan.save(update_fields=["status", "cached_diff", "diff_stale"])

    return {"added": added, "removed": removed}


@transaction.atomic
def create_splice_closure(
    *,
    name,
    site,
    device_type,
    role,
    status,
    tray_module_type,
    tray_count,
    basket_module_type=None,
    basket_count=0,
    location=None,
):
    """Create a splice closure Device with tray (and optional basket) modules.

    All objects are full_clean()ed; any failure rolls back the entire closure.
    Returns the created Device.
    """
    device = Device(
        name=name,
        site=site,
        location=location,
        device_type=device_type,
        role=role,
        status=status,
    )
    device.full_clean()
    device.save()

    def _add_modules(prefix, module_type, count):
        for i in range(1, count + 1):
            bay = ModuleBay(device=device, name=f"{prefix} {i}")
            bay.full_clean()
            bay.save()
            module = Module(device=device, module_bay=bay, module_type=module_type)
            module.full_clean()
            module.save()

    _add_modules("Tray", tray_module_type, tray_count)
    if basket_module_type is not None:
        _add_modules("Basket", basket_module_type, basket_count)

    return device


def _tube_assignment_target_ports(closure_id, buffer_tube_id):
    """FrontPorts of the tube's strands that live on the closure device.

    Each strand contributes at most one port (front_port_a or front_port_b,
    whichever terminates on the closure); strands without a port there are
    skipped.
    """
    from .models import FiberStrand

    ports = []
    strands = FiberStrand.objects.filter(buffer_tube_id=buffer_tube_id).select_related("front_port_a", "front_port_b")
    for strand in strands:
        for port in (strand.front_port_a, strand.front_port_b):
            if port is not None and port.device_id == closure_id:
                ports.append(port)
                break
    return ports


def sync_tube_assignment_ports(assignment):
    """Place the tube's closure-side strand front ports on the assignment's tray.

    Overwrites unconditionally; conflict blocking happens at form/serializer
    validation. Saves ports individually so NetBox change logging records
    each move.

    Defence in depth behind TubeAssignment.clean(): a write path that skips
    validation must not park strand ports on a module that is not a splice
    tray, so such a sync is skipped with a warning instead.
    """
    if not is_splice_tray(assignment.tray):
        logger.warning(
            "Skipping port sync for tube assignment %s: module %s is not a splice tray.",
            assignment.pk,
            assignment.tray,
        )
        return
    for port in _tube_assignment_target_ports(assignment.closure_id, assignment.buffer_tube_id):
        if port.module_id != assignment.tray_id:
            port.snapshot()
            port.module_id = assignment.tray_id
            port.save()


def clear_tube_assignment_ports(closure_id, tray_id, buffer_tube_id):
    """Return the tube's closure-side ports to device level.

    Only touches ports still sitting on the given tray; ports moved
    elsewhere by hand are left alone. Takes ids so it can run from a
    post_delete signal.
    """
    for port in _tube_assignment_target_ports(closure_id, buffer_tube_id):
        if port.module_id == tray_id:
            port.snapshot()
            port.module_id = None
            port.save()
