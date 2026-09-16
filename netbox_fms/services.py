"""Diff computation engine for splice plans and link topology services."""

import logging

from dcim.models import Cable, CableTermination, Device, FrontPort, Module, ModuleBay, PortMapping, RearPort
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction

from . import naming
from .choices import FiberCircuitStatusChoices, SplicePlanStatusChoices
from .models import ClosureCableEntry, FiberCable, FiberCircuitNode, SplicePlanEntry
from .signals import fms_portmapping_bypass

logger = logging.getLogger(__name__)


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
            if first.ribbon_id is not None:
                name = naming.rear_port_name(cable_id, ribbon=ordinals[first.ribbon_id])
                rear_ctx = _ctx(tube=first.buffer_tube, ribbon=container)
            elif first.buffer_tube_id is not None:
                name = naming.rear_port_name(cable_id, tube=container.position)
                rear_ctx = _ctx(tube=container)
            else:
                name = naming.rear_port_name(cable_id)
                rear_ctx = _ctx()
            rp = RearPort.objects.create(
                device=device,
                name=name,
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


def plan_port_names(fc):
    """Propose write-once names for a FiberCable's provisioned ports.

    Names are rebuilt within the EXISTING rear-port structure: each rear
    port is named for the one container (ribbon, else tube) shared by every
    strand mapped to it, falling back to the bare cable pk when its strands
    span containers (e.g. a legacy tube-grouped ribbon cable, or an adopted
    panel port covering the whole cable). Front ports always get the
    absolute-number name.

    Returns ``(renames, problems)``: ``renames`` is ``[(port, new_name)]``
    limited to ports whose name actually changes, and ``problems`` lists
    human-readable collision descriptions. Callers must not apply a plan
    that carries problems -- names are unique per device, so a partial
    rename would strand the cable between schemes.
    """
    from dcim.models import FrontPort, RearPort

    from .signals import _cable_strand_ports

    strand_by_fp_id, pms = _cable_strand_ports(fc)
    cable_id = fc.cable_id
    ordinals = ribbon_ordinals(strand_by_fp_id.values())

    strands_by_rp = {}
    for pm in pms:
        strands_by_rp.setdefault(pm.rear_port_id, []).append(strand_by_fp_id[pm.front_port_id])

    proposed = {}  # port -> new name
    seen_fp_ids = set()
    for pm in pms:
        if pm.front_port_id in seen_fp_ids:
            continue
        seen_fp_ids.add(pm.front_port_id)
        strand = strand_by_fp_id[pm.front_port_id]
        proposed[pm.front_port] = naming.front_port_name(cable_id, strand.position)

    seen_rp_ids = set()
    for pm in pms:
        if pm.rear_port_id in seen_rp_ids:
            continue
        seen_rp_ids.add(pm.rear_port_id)
        rp_strands = strands_by_rp[pm.rear_port_id]
        ribbon_ids = {s.ribbon_id for s in rp_strands}
        tube_ids = {s.buffer_tube_id for s in rp_strands}
        if ribbon_ids != {None} and len(ribbon_ids) == 1:
            name = naming.rear_port_name(cable_id, ribbon=ordinals[next(iter(ribbon_ids))])
        elif tube_ids != {None} and len(tube_ids) == 1:
            name = naming.rear_port_name(cable_id, tube=rp_strands[0].buffer_tube.position)
        else:
            name = naming.rear_port_name(cable_id)
        proposed[pm.rear_port] = name

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
    """Persist a collision-free rename plan, grouped per port model."""
    by_model = {}
    for port, name in renames:
        port.name = name
        by_model.setdefault(type(port), []).append(port)
    for model, ports in by_model.items():
        model.objects.bulk_update(ports, ["name"], batch_size=500)


@transaction.atomic
def link_cable_topology(cable, fiber_cable_type, device, port_type="splice", port_mapping=None):
    """Create FiberCable, adopt or create ports, set cable profile.

    Args:
        cable: dcim.Cable instance
        fiber_cable_type: FiberCableType instance
        device: dcim.Device where ports will be created/adopted
        port_type: port type string (default "splice")
        port_mapping: optional dict {strand_position: frontport_id} for adopt path

    Returns: (FiberCable, warnings_list)
    Raises: NeedsMappingConfirmation if existing ports found without port_mapping
    """
    warnings = []
    rp_ct = ContentType.objects.get_for_model(RearPort)

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

    # Create FiberCable (triggers _instantiate_components)
    fc = FiberCable.objects.create(cable=cable, fiber_cable_type=fiber_cable_type)

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
            # One-shot naming: converge the adopted ports on the write-once
            # scheme now, because no ongoing sync will ever rename them later.
            renames, problems = plan_port_names(fc)
            if problems:
                warnings.append(
                    "Adopted port names left unchanged; generated names would collide: " + "; ".join(problems)
                )
            else:
                apply_port_names(renames)
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
    the scope explicitly: get_live_state (feeding the diff/apply engine)
    passes only tray-mounted ports, while the closure-strands editor view
    passes every port of the closure so splices on device-level ports
    (unassigned tubes) still render.
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


def get_live_state(closure):
    """
    Read current FrontPort<->FrontPort connections on a closure's tray modules.
    Returns: {tray_module_id: set((port_a_id, port_b_id), ...)}
    Pairs are normalized: (min_id, max_id).
    """
    port_module_pairs = FrontPort.objects.filter(
        device=closure,
        module__isnull=False,
    ).values_list("pk", "module_id")

    port_to_module = dict(port_module_pairs)
    tray_frontport_ids = set(port_to_module.keys())

    if not tray_frontport_ids:
        return {}

    state = {}
    for port_a_id, port_b_id in front_port_splice_pairs(tray_frontport_ids):
        pair = (min(port_a_id, port_b_id), max(port_a_id, port_b_id))

        mod_a = port_to_module[port_a_id]
        mod_b = port_to_module[port_b_id]
        state.setdefault(mod_a, set()).add(pair)
        if mod_a != mod_b:
            state.setdefault(mod_b, set()).add(pair)

    return state


def get_desired_state(plan):
    """
    Read desired FrontPort<->FrontPort connections from a SplicePlan's entries.
    Returns: {tray_module_id: set((port_a_id, port_b_id), ...)}
    Only includes pairs where both ports belong to the closure device.
    """
    closure = plan.closure
    local_fp_ids = set(FrontPort.objects.filter(device=closure, module__isnull=False).values_list("pk", flat=True))

    entries = list(plan.entries.values_list("tray_id", "fiber_a_id", "fiber_b_id"))

    fb_ids = {fb_id for _, _, fb_id in entries}
    fb_to_module = dict(FrontPort.objects.filter(pk__in=fb_ids).values_list("pk", "module_id"))

    state = {}
    for tray_id, fa_id, fb_id in entries:
        # Skip pairs where either port is not on this closure's trays
        if fa_id not in local_fp_ids or fb_id not in local_fp_ids:
            continue

        pair = (min(fa_id, fb_id), max(fa_id, fb_id))
        state.setdefault(tray_id, set()).add(pair)

        fb_module_id = fb_to_module.get(fb_id)
        if fb_module_id and fb_module_id != tray_id:
            state.setdefault(fb_module_id, set()).add(pair)

    return state


def compute_diff(plan):
    """
    Compute the diff between desired and live state.
    Returns: {tray_module_id: {"add": list, "remove": list, "unchanged": list}}
    Keys are int tray IDs. Values are lists of [port_a_id, port_b_id] pairs.
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


def import_live_state(plan):
    """
    Bootstrap a plan from the closure's current live connections.
    Creates SplicePlanEntry rows for each existing FrontPort<->FrontPort pair.
    Returns the number of entries created.
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

    entries = []
    for port_a_id, port_b_id in all_pairs:
        tray_id = port_to_module.get(port_a_id)
        if tray_id is None:
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
    return len(entries)


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
    """
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
