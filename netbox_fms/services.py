"""Diff computation engine for splice plans and link topology services."""

from dcim.models import Cable, CableTermination, FrontPort, PortMapping, RearPort
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from .choices import SplicePlanStatusChoices
from .models import FiberCable, SplicePlanEntry


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
        # Adopt path: collect FrontPorts mapped to these RearPorts
        fps_by_position = {}
        for rp_id in existing_term_rp_ids:
            for pm in PortMapping.objects.filter(rear_port_id=rp_id).select_related("front_port"):
                fps_by_position[pm.rear_port_position] = pm.front_port

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

    if existing_term_rp_ids and port_mapping is not None:
        # Adopt path: link strands to existing FrontPorts
        for strand in fc.fiber_strands.all().order_by("position"):
            fp_id = port_mapping.get(strand.position)
            if fp_id:
                setattr(strand, fk_field, FrontPort.objects.get(pk=fp_id))
                strand.save(update_fields=[fk_field])
    else:
        # Greenfield path: create ports
        tubes = list(fc.buffer_tubes.all().order_by("position"))
        strands = list(fc.fiber_strands.all().order_by("position"))

        if tubes:
            # One RearPort per tube
            for tube_idx, tube in enumerate(tubes, start=1):
                tube_fiber_count = fc.fiber_strands.filter(buffer_tube=tube).count()
                rp = RearPort.objects.create(
                    device=device,
                    name=f"#{cable.pk}:T{tube.position}",
                    type=port_type,
                    positions=tube_fiber_count,
                )
                # Create CableTermination linking RearPort to cable
                # connector/positions enable profile-based tracing
                CableTermination.objects.create(
                    cable=cable,
                    cable_end=cable_end if cable_end != "AB" else "A",
                    termination_type=rp_ct,
                    termination_id=rp.pk,
                    connector=tube_idx,
                    positions=list(range(1, tube_fiber_count + 1)),
                )
                # Create FrontPorts + PortMappings for each fiber in this tube
                tube_strands = [s for s in strands if s.buffer_tube_id == tube.pk]
                for i, strand in enumerate(tube_strands, start=1):
                    fp = FrontPort.objects.create(
                        device=device,
                        name=f"#{cable.pk}:T{tube.position}:F{strand.position}",
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
        else:
            # Single RearPort for all strands
            rp = RearPort.objects.create(
                device=device,
                name=f"#{cable.pk}",
                type=port_type,
                positions=fiber_cable_type.strand_count,
            )
            CableTermination.objects.create(
                cable=cable,
                cable_end=cable_end if cable_end != "AB" else "A",
                termination_type=rp_ct,
                termination_id=rp.pk,
                connector=1,
                positions=list(range(1, fiber_cable_type.strand_count + 1)),
            )
            for i, strand in enumerate(strands, start=1):
                fp = FrontPort.objects.create(
                    device=device,
                    name=f"#{cable.pk}:F{strand.position}",
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

    return fc, warnings


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

    fp_ct = ContentType.objects.get_for_model(FrontPort)
    terminations = CableTermination.objects.filter(
        termination_type=fp_ct,
        termination_id__in=tray_frontport_ids,
    ).values_list("cable_id", "termination_id", "cable_end")

    cable_terms = {}
    for cable_id, term_id, cable_end in terminations:
        cable_terms.setdefault(cable_id, {})[cable_end] = term_id

    state = {}
    for _cable_id, ends in cable_terms.items():
        if "A" not in ends or "B" not in ends:
            continue
        port_a_id, port_b_id = ends["A"], ends["B"]
        if port_a_id not in tray_frontport_ids or port_b_id not in tray_frontport_ids:
            continue

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


def apply_diff(plan):
    """
    Execute the diff: create cables for "add", delete cables for "remove".
    Returns {"added": int, "removed": int}.
    """
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
                label=f"splice-{port_a_id}-{port_b_id}",
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

        plan.status = SplicePlanStatusChoices.APPLIED
        plan.diff_stale = True
        plan.save(update_fields=["status", "diff_stale"])

    return {"added": added, "removed": removed}
