"""Write fiber path analysis results and evaluate circuit assignments.

The hop index has one derivation and one writer: this module. The
incremental job and the reconcile both call it inside one transaction while
holding the analysis advisory lock.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, fields
from datetime import timedelta

from django.db import connection
from django.db.models import Q
from django.utils import timezone
from netbox.plugins import get_plugin_config

from .bulk import BATCH_SIZE
from .choices import AssignmentBrokenReasonChoices
from .models import (
    FiberCircuitPath,
    FiberStrandPath,
    FiberStrandPathHop,
    PathAnalysisQueue,
    PathAnomaly,
    RouteChangeAuthorization,
    hops_snapshot,
    refs_from_json,
)
from .path_graph import fp_node, load_plant, walk_all, walk_nodes

# A plugin-private PostgreSQL advisory lock id, far from NetBox's own keys.
ANALYSIS_LOCK_KEY = 1_960_001

PATH_FIELDS = (
    "end_a_port_id",
    "end_b_port_id",
    "end_a_kind",
    "end_b_kind",
    "end_a_reason",
    "end_b_reason",
    "completeness",
    "route_key",
    "is_proposed",
    "is_defective",
    "computed_at",
)

# The joins from a stored path to the devices it touches: strand landings,
# plain-cable terminations and the end ports. No device index is stored.
PATH_DEVICE_LOOKUPS = (
    "hops__strand__front_port_a__device_id",
    "hops__strand__front_port_b__device_id",
    "hops__cable__terminations___device_id",
    "end_a_port__device_id",
    "end_b_port__device_id",
)


@dataclass
class AnalysisStats:
    """What one analysis run did, for the job log."""

    devices: int = 0
    paths_created: int = 0
    paths_updated: int = 0
    paths_deleted: int = 0
    assignments_broken: int = 0
    assignments_authorized: int = 0

    def summary(self):
        return " ".join(f"{f.name}={getattr(self, f.name)}" for f in fields(self))


def try_analysis_lock():
    """Take the transaction-scoped analysis lock; False when another run holds it."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [ANALYSIS_LOCK_KEY])
        return cursor.fetchone()[0]


def path_ids_through_devices(device_ids):
    """Stored paths with a hop or an end on any of these devices."""
    ids = list(device_ids)
    if not ids:
        return set()
    condition = Q()
    for lookup in PATH_DEVICE_LOOKUPS:
        condition |= Q(**{f"{lookup}__in": ids})
    return set(FiberStrandPath.objects.filter(condition).values_list("pk", flat=True).distinct())


def device_ids_on_paths(device_ids=None):
    """Devices lying on a stored path, restricted to ``device_ids`` when given."""
    found = set()
    for lookup in PATH_DEVICE_LOOKUPS:
        queryset = FiberStrandPath.objects.all()
        if device_ids is not None:
            queryset = queryset.filter(**{f"{lookup}__in": list(device_ids)})
        found |= set(queryset.values_list(lookup, flat=True))
    found.discard(None)
    return found


def _path_fields(chain, computed_at):
    return {
        "end_a_port_id": chain.end_a.port_id,
        "end_b_port_id": chain.end_b.port_id,
        "end_a_kind": chain.end_a.kind,
        "end_b_kind": chain.end_b.kind,
        "end_a_reason": chain.end_a.reason,
        "end_b_reason": chain.end_b.reason,
        "completeness": chain.completeness,
        "route_key": chain.route_key,
        "is_proposed": chain.is_proposed,
        "is_defective": False,
        "computed_at": computed_at,
    }


def _hop_rows(path, chain):
    return [
        FiberStrandPathHop(path=path, position=position, **{f"{kind}_id": ref_id})
        for position, (kind, ref_id) in enumerate(chain.hops, start=1)
    ]


def _anchor(refs):
    """The hop that identifies a stored path: its first strand, else its first hop."""
    return next(((kind, ref_id) for kind, ref_id in refs if kind == "strand"), refs[0])


def _match(chain, by_strand, by_end_hop):
    """The stored path a chain continues: the one holding its first stored strand, else a strandless end hop."""
    for strand_id in chain.strand_ids:
        path = by_strand.get(strand_id)
        if path is not None:
            return path
    if chain.strand_ids:
        return None
    return by_end_hop.get(chain.hops[0]) or by_end_hop.get(chain.hops[-1])


def _keeper(refs, candidates):
    """Of several chains matching one stored path (a cut), the one holding the path's old first hop."""
    anchor = _anchor(refs)
    return next((chain for chain in candidates if anchor in chain.hops), candidates[0])


def _oriented(chain, refs):
    """Flip a chain that runs against its stored path, so end A stays end A and an unchanged path is not rewritten."""
    stored_strands = [ref_id for kind, ref_id in refs if kind == "strand"]
    shared = [strand_id for strand_id in chain.strand_ids if strand_id in stored_strands]
    if len(shared) >= 2:
        if stored_strands.index(shared[0]) > stored_strands.index(shared[-1]):
            return chain.reversed()
        return chain
    anchor = _anchor(refs)
    if chain.hops[0] != anchor and chain.hops[-1] == anchor:
        return chain.reversed()
    return chain


def write_results(chains, stored_paths, *, computed_at):
    """Store chains as paths: rewrite in place, split on cuts, create the new, drop the lost.

    ``stored_paths`` are the paths in scope with their hops prefetched:
    every path through an analyzed device plus every path holding a strand
    of a chain. A path in scope that no chain matches has lost every strand.
    """
    stats = AnalysisStats()
    stored = {path.pk: path for path in stored_paths}
    refs_of = {pk: path.hop_refs() for pk, path in stored.items()}
    by_strand, by_end_hop = {}, {}
    for pk, refs in refs_of.items():
        if not refs:
            # A row whose hops all cascaded away can match nothing.
            continue
        by_end_hop.setdefault(refs[0], stored[pk])
        by_end_hop.setdefault(refs[-1], stored[pk])
        for kind, ref_id in refs:
            if kind == "strand":
                by_strand[ref_id] = stored[pk]
    matched, new_chains = defaultdict(list), []
    for chain in chains:
        path = _match(chain, by_strand, by_end_hop)
        if path is None:
            new_chains.append(chain)
        else:
            matched[path.pk].append(chain)

    unchanged, rewritten = [], []
    for pk, candidates in matched.items():
        path, refs = stored[pk], refs_of[pk]
        keeper = _keeper(refs, candidates)
        keep = _oriented(keeper, refs)  # may be a new, reversed Chain object; identity checks use ``keeper``
        new_chains.extend(chain for chain in candidates if chain is not keeper)
        values = _path_fields(keep, computed_at)
        # Equal hops can still carry different ends (a port gained or lost its far side), so compare those too.
        if keep.hops == refs and all(
            getattr(path, name) == value for name, value in values.items() if name != "computed_at"
        ):
            path.computed_at = computed_at
            unchanged.append(path)
        else:
            for name, value in values.items():
                setattr(path, name, value)
            rewritten.append((path, keep))

    lost = [path for pk, path in stored.items() if pk not in matched]
    stats.paths_deleted, kept = _drop_lost(lost)
    FiberStrandPath.objects.bulk_update(unchanged, ["computed_at"], batch_size=BATCH_SIZE)
    FiberStrandPathHop.objects.filter(path_id__in=[path.pk for path, _chain in rewritten]).delete()
    FiberStrandPath.objects.bulk_update([path for path, _chain in rewritten], PATH_FIELDS, batch_size=BATCH_SIZE)
    created = [FiberStrandPath(**_path_fields(chain, computed_at)) for chain in new_chains]
    FiberStrandPath.objects.bulk_create(created, batch_size=BATCH_SIZE)
    pairs = [*rewritten, *zip(created, new_chains, strict=True)]
    FiberStrandPathHop.objects.bulk_create(
        [hop for path, chain in pairs for hop in _hop_rows(path, chain)], batch_size=BATCH_SIZE
    )
    stats.paths_updated = len(rewritten)
    stats.paths_created = len(created)
    evaluate_assignments([path for path, _chain in rewritten] + kept, stats)
    return stats


def _drop_lost(lost):
    """Delete lost paths nothing references; keep assigned ones as hop-less rows. Returns (deleted, kept)."""
    referenced = set(FiberCircuitPath.objects.filter(strand_path__in=lost).values_list("strand_path_id", flat=True))
    kept = [path for path in lost if path.pk in referenced]
    FiberStrandPath.objects.filter(pk__in=[path.pk for path in lost if path.pk not in referenced]).delete()
    FiberStrandPathHop.objects.filter(path__in=kept).delete()
    return len(lost) - len(kept), kept


def sync_circuit_broken(circuit):
    """Set FiberCircuit.is_broken from its active assignments; logs one change only when it flips."""
    broken = circuit.paths.filter(active=True, is_broken=True).exists()
    if circuit.is_broken == broken:
        return False
    circuit.snapshot()
    circuit.is_broken = broken
    circuit.save()
    return True


def accept_current_hops(assignment):
    """Make the path's current hops the assigned ones and clear the broken flags (not saved)."""
    assignment.snapshot()
    assignment.assigned_hops = hops_snapshot(assignment.strand_path)
    assignment.is_broken, assignment.broken_reason = False, ""


def _end_strands(refs):
    """The first and last strand of a hop list: the strands that sit on the end devices."""
    strands = [ref_id for kind, ref_id in refs if kind == "strand"]
    return (strands[0], strands[-1]) if strands else None


def evaluate_assignments(paths, stats):
    """Compare every active assignment on these paths with its snapshot.

    Equal hops heal a broken assignment. Changed hops are accepted when the
    circuit holds a route-change authorization and the first and last
    strand hops are the same (the ends sit on the same devices); otherwise
    the assignment is broken. One authorization covers every assignment of
    the circuit in this run and is then consumed.
    """
    assignments = list(
        FiberCircuitPath.objects.filter(strand_path__in=paths, active=True)
        .select_related("circuit", "strand_path")
        .prefetch_related("strand_path__hops")
    )
    circuits = {assignment.circuit_id: assignment.circuit for assignment in assignments}
    authorized = set(
        RouteChangeAuthorization.objects.filter(circuit_id__in=circuits).values_list("circuit_id", flat=True)
    )
    consumed = set()
    for assignment in assignments:
        current = assignment.strand_path.hop_refs()
        assigned = refs_from_json(assignment.assigned_hops)
        if current == assigned:
            if not assignment.is_broken:
                continue
            accept_current_hops(assignment)
        elif current and assignment.circuit_id in authorized and _end_strands(current) == _end_strands(assigned):
            accept_current_hops(assignment)
            consumed.add(assignment.circuit_id)
            stats.assignments_authorized += 1
        else:
            reason = AssignmentBrokenReasonChoices.HOPS_CHANGED if current else AssignmentBrokenReasonChoices.PATH_LOST
            if assignment.is_broken and assignment.broken_reason == reason:
                continue  # already reported; a lost path is re-evaluated on every run
            assignment.snapshot()
            assignment.is_broken, assignment.broken_reason = True, reason
            stats.assignments_broken += 1
        assignment.save()
    RouteChangeAuthorization.objects.filter(circuit_id__in=consumed).delete()
    for circuit in circuits.values():
        sync_circuit_broken(circuit)
        circuit.sync_provider_circuits()


def replace_anomalies(anomalies, device_ids=None):
    """Replace the anomaly rows of the analyzed area (all rows when ``device_ids`` is None)."""
    existing = PathAnomaly.objects.all()
    if device_ids is not None:
        ids = list(device_ids)
        existing = existing.filter(
            Q(front_port__device_id__in=ids)
            | Q(strand__front_port_a__device_id__in=ids)
            | Q(strand__front_port_b__device_id__in=ids)
            | Q(strand__fiber_cable__cable__terminations___device_id__in=ids)
        )
    existing.delete()
    PathAnomaly.objects.bulk_create(
        [PathAnomaly(kind=a.kind, strand_id=a.strand_id, front_port_id=a.front_port_id) for a in anomalies],
        batch_size=BATCH_SIZE,
    )


def run_reconcile():
    """Analyze the whole plant against every stored path and purge stale bookkeeping.

    Queue rows created before the start are superseded by this run; rows
    inserted meanwhile keep their own scheduled job. Authorizations older
    than one reconcile cycle were never consumed and are dropped.
    """
    started = timezone.now()
    plant = load_plant(None)
    stats = write_results(walk_all(plant), FiberStrandPath.objects.prefetch_related("hops"), computed_at=started)
    replace_anomalies(plant.anomalies)
    PathAnalysisQueue.objects.filter(created__lt=started).delete()
    cycle = timedelta(minutes=get_plugin_config("netbox_fms", "path_reconcile_interval_minutes"))
    RouteChangeAuthorization.objects.filter(created__lt=started - cycle).delete()
    stats.devices = len(plant.device_ids)
    return stats


def _anomalies_on(plant, device_ids):
    """The region's anomalies that touch these devices: the same scope replace_anomalies clears.

    The loaded region reaches past the analyzed devices; anomalies out there
    are the reconcile's, and inserting them here would duplicate the rows
    the delete never reaches.
    """

    def touches(anomaly):
        if anomaly.front_port_id is not None:
            return plant.fp_device.get(anomaly.front_port_id) in device_ids
        devices = set(plant.cable_devices.get(plant.strand_cable[anomaly.strand_id], ()))
        devices.update(plant.fp_device.get(fp) for fp in plant.strand_ports[anomaly.strand_id] if fp is not None)
        return not devices.isdisjoint(device_ids)

    return [anomaly for anomaly in plant.anomalies if touches(anomaly)]


def analyze_devices(device_ids):
    """Re-analyze the fibers through these devices.

    Loads their region, walks from every front port on them and from the
    ends and strand landings of every stored path through them, and writes
    the chains against those paths plus any path holding a walked strand
    (a splice may have joined a path from elsewhere).
    """
    device_ids = set(device_ids)
    computed_at = timezone.now()
    plant = load_plant(device_ids)
    in_scope = list(
        FiberStrandPath.objects.filter(pk__in=path_ids_through_devices(device_ids)).prefetch_related("hops")
    )
    start_fps = {fp for device_id in device_ids for fp in plant.device_fps.get(device_id, ())}
    for path in in_scope:
        start_fps.update(fp for fp in (path.end_a_port_id, path.end_b_port_id) if fp is not None)
        for kind, ref_id in path.hop_refs():
            if kind == "strand":
                start_fps.update(fp for fp in plant.strand_ports.get(ref_id, (None, None)) if fp is not None)
    chains = walk_nodes(plant, sorted(fp_node(fp) for fp in start_fps))
    strand_ids = {ref_id for chain in chains for kind, ref_id in chain.hops if kind == "strand"}
    stored = {path.pk: path for path in in_scope}
    joined = FiberStrandPath.objects.filter(hops__strand_id__in=strand_ids).exclude(pk__in=stored).distinct()
    for path in joined.prefetch_related("hops"):
        stored[path.pk] = path
    stats = write_results(chains, stored.values(), computed_at=computed_at)
    replace_anomalies(_anomalies_on(plant, device_ids), device_ids=device_ids)
    stats.devices = len(device_ids)
    return stats
