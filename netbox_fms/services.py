"""Diff computation engine for splice plans."""

from dcim.models import Cable, CableTermination, FrontPort  # noqa: F401
from django.contrib.contenttypes.models import ContentType


def get_live_state(closure):
    """
    Read current FrontPort<->FrontPort connections on a closure's tray modules.
    Returns: {tray_module_id: set((port_a_id, port_b_id), ...)}
    Pairs are normalized: (min_id, max_id).
    """
    tray_frontport_ids = set(
        FrontPort.objects.filter(
            device=closure,
            module__isnull=False,
        ).values_list("pk", flat=True)
    )

    if not tray_frontport_ids:
        return {}

    port_to_module = dict(FrontPort.objects.filter(pk__in=tray_frontport_ids).values_list("pk", "module_id"))

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
    """
    state = {}
    for tray_id, fa_id, fb_id in plan.entries.values_list("tray_id", "fiber_a_id", "fiber_b_id"):
        pair = (min(fa_id, fb_id), max(fa_id, fb_id))
        state.setdefault(tray_id, set()).add(pair)

        # For inter-platter: also add to fiber_b's tray if different
        fb_module_id = FrontPort.objects.filter(pk=fb_id).values_list("module_id", flat=True).first()
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
    from dcim.models import FrontPort

    from .models import SplicePlanEntry

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

    SplicePlanEntry.objects.bulk_create(entries)
    plan.diff_stale = True
    plan.save(update_fields=["diff_stale"])
    return len(entries)


def apply_diff(plan):
    """
    Execute the diff: create cables for "add", delete cables for "remove".
    Returns {"added": int, "removed": int}.
    """
    from dcim.models import CableTermination, FrontPort
    from django.contrib.contenttypes.models import ContentType
    from django.db import transaction

    from .choices import SplicePlanStatusChoices

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

        # Process additions
        for port_a_id, port_b_id in all_adds:
            cable = Cable(length=0, length_unit="m")
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
