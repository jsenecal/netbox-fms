"""Fiber circuit provisioning engine.

Provides DAG-based pathfinding to discover available fiber routes between two
devices (closures) and a transactional factory to create FiberCircuit instances
from selected proposals.

IMPORTANT: NetBox 4.5+ uses the PortMapping model to link FrontPort <-> RearPort.
FrontPort has NO rear_port or rear_port_position attributes.
"""

import re
from collections import defaultdict
from itertools import combinations

from dcim.models import Cable, CableTermination, Device, FrontPort, PortMapping, RearPort
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q

from .choices import FiberCircuitStatusChoices, SplicePlanStatusChoices
from .models import (
    FiberCircuitNode,
    FiberCircuitPath,
    FiberStrand,
    SplicePlan,
    SplicePlanEntry,
)

# ---------------------------------------------------------------------------
# DAG construction helpers
# ---------------------------------------------------------------------------


def _build_device_graph(origin_device, destination_device):
    """Build a directed graph of devices connected by cables.

    Returns:
        edges: dict mapping (device_a_id, device_b_id) -> list of cable info dicts
        adjacency: dict mapping device_id -> set of neighbor device_ids
        all_device_ids: set of all device IDs found
    """
    rp_ct = ContentType.objects.get_for_model(RearPort)

    # Find all cables that connect RearPorts on devices
    # Get all cable terminations on RearPorts
    all_terms = CableTermination.objects.filter(
        termination_type=rp_ct,
    ).select_related("cable")

    # Group terminations by cable
    cable_terms = defaultdict(list)
    for term in all_terms:
        cable_terms[term.cable_id].append(term)

    edges = defaultdict(list)  # (dev_a_id, dev_b_id) -> [cable_info, ...]
    adjacency = defaultdict(set)
    all_device_ids = set()

    for cable_id, terms in cable_terms.items():
        a_terms = [t for t in terms if t.cable_end == "A"]
        b_terms = [t for t in terms if t.cable_end == "B"]
        if not a_terms or not b_terms:
            continue

        # Get the devices for each side
        a_rp_ids = [t.termination_id for t in a_terms]
        b_rp_ids = [t.termination_id for t in b_terms]

        a_rps = RearPort.objects.filter(pk__in=a_rp_ids).values_list("pk", "device_id")
        b_rps = RearPort.objects.filter(pk__in=b_rp_ids).values_list("pk", "device_id")

        a_rp_map = dict(a_rps)
        b_rp_map = dict(b_rps)

        for a_term in a_terms:
            a_dev_id = a_rp_map.get(a_term.termination_id)
            if a_dev_id is None:
                continue
            for b_term in b_terms:
                b_dev_id = b_rp_map.get(b_term.termination_id)
                if b_dev_id is None:
                    continue

                cable_info = {
                    "cable_id": cable_id,
                    "rp_a_id": a_term.termination_id,
                    "rp_b_id": b_term.termination_id,
                    "dev_a_id": a_dev_id,
                    "dev_b_id": b_dev_id,
                }
                # Add edges in both directions for pathfinding
                edges[(a_dev_id, b_dev_id)].append(cable_info)
                edges[(b_dev_id, a_dev_id)].append(cable_info)
                adjacency[a_dev_id].add(b_dev_id)
                adjacency[b_dev_id].add(a_dev_id)
                all_device_ids.add(a_dev_id)
                all_device_ids.add(b_dev_id)

    return edges, adjacency, all_device_ids


def _find_all_simple_paths(adjacency, origin_id, dest_id, max_depth=10):
    """Find all simple paths (no repeated nodes) between origin and destination.

    Returns list of lists of device IDs.
    """
    paths = []
    stack = [(origin_id, [origin_id])]

    while stack:
        current, path = stack.pop()
        if current == dest_id:
            paths.append(path)
            continue
        if len(path) > max_depth:
            continue
        for neighbor in adjacency.get(current, set()):
            if neighbor not in path:
                stack.append((neighbor, path + [neighbor]))

    return paths


def _get_port_mappings_for_rearport(rp_id):
    """Get all PortMappings for a RearPort, returning {rp_position: fp_id}."""
    mappings = PortMapping.objects.filter(rear_port_id=rp_id).values_list("rear_port_position", "front_port_id")
    return dict(mappings)


def _get_occupied_front_port_ids():
    """Return set of FrontPort IDs already used in active FiberCircuitNodes."""
    return set(
        FiberCircuitNode.objects.filter(
            front_port__isnull=False,
            path__circuit__status__in=[
                FiberCircuitStatusChoices.PLANNED,
                FiberCircuitStatusChoices.STAGED,
                FiberCircuitStatusChoices.ACTIVE,
            ],
        ).values_list("front_port_id", flat=True)
    )


def _get_existing_splices_map(device_id):
    """Return dict mapping (fp_a_id, fp_b_id) -> SplicePlanEntry for a device."""
    entries = SplicePlanEntry.objects.filter(
        plan__closure_id=device_id,
    ).values_list("fiber_a_id", "fiber_b_id", "pk")
    result = {}
    for fa, fb, pk in entries:
        result[(fa, fb)] = pk
        result[(fb, fa)] = pk
    return result


# ---------------------------------------------------------------------------
# Strand availability along a route
# ---------------------------------------------------------------------------


def _find_available_strand_groups(route_device_ids, edges, strand_count, occupied_fps):
    """Find groups of `strand_count` strands available across all hops of a route.

    A route is a list of device IDs. For each consecutive pair, we need a cable
    connecting them. Each strand must use the same position across all cables
    (i.e., position 1 on all cables, position 2 on all cables, etc.).

    Returns list of candidate dicts, each containing:
        - strands: list of strand info dicts (one per strand)
        - hops: list of hop info dicts
        - new_splice_count: int
        - existing_splice_count: int
    """
    if len(route_device_ids) < 2:
        return []

    # For each hop, find the cables and their available positions
    hops = []
    for i in range(len(route_device_ids) - 1):
        dev_a_id = route_device_ids[i]
        dev_b_id = route_device_ids[i + 1]
        cable_infos = edges.get((dev_a_id, dev_b_id), [])
        if not cable_infos:
            return []  # No cable for this hop
        hops.append(
            {
                "dev_a_id": dev_a_id,
                "dev_b_id": dev_b_id,
                "cable_infos": cable_infos,
            }
        )

    # For each cable in each hop, find available positions
    # We need to find positions available across ALL hops
    # A position is available if the corresponding FrontPorts on both sides are not occupied

    # Build per-hop availability: for each hop, what (cable_idx, position) -> (fp_a, fp_b) pairs are available
    hop_availabilities = []
    for hop in hops:
        avail = []  # list of (cable_info, position, fp_entry_side, fp_exit_side)
        for cable_info in hop["cable_infos"]:
            rp_a_id = cable_info["rp_a_id"]
            rp_b_id = cable_info["rp_b_id"]

            # Determine which RP is on entry side and which on exit side
            # based on direction of travel
            if cable_info["dev_a_id"] == hop["dev_a_id"]:
                entry_rp_id = rp_a_id
                exit_rp_id = rp_b_id
            else:
                entry_rp_id = rp_b_id
                exit_rp_id = rp_a_id

            entry_map = _get_port_mappings_for_rearport(entry_rp_id)
            exit_map = _get_port_mappings_for_rearport(exit_rp_id)

            # Find positions available on both sides
            common_positions = set(entry_map.keys()) & set(exit_map.keys())
            for pos in sorted(common_positions):
                fp_entry = entry_map[pos]
                fp_exit = exit_map[pos]
                if fp_entry not in occupied_fps and fp_exit not in occupied_fps:
                    avail.append(
                        {
                            "cable_info": cable_info,
                            "position": pos,
                            "fp_entry_id": fp_entry,
                            "fp_exit_id": fp_exit,
                            "entry_rp_id": entry_rp_id,
                            "exit_rp_id": exit_rp_id,
                        }
                    )
        hop_availabilities.append(avail)

    # Now find strand groups that work across all hops
    # For simplicity with multiple hops, we need to find combinations where:
    # - At intermediate closures, the exit FP of one hop can be spliced to the entry FP of next hop
    # - We pick `strand_count` such paths

    if len(hops) == 1:
        # Simple case: single hop, just pick strand_count positions from available
        avail = hop_availabilities[0]
        if len(avail) < strand_count:
            return []
        return _generate_single_hop_candidates(avail, strand_count, route_device_ids)

    # Multi-hop: need to find compatible strands across hops
    return _generate_multi_hop_candidates(hops, hop_availabilities, strand_count, route_device_ids, occupied_fps)


def _generate_single_hop_candidates(avail, strand_count, route_device_ids):
    """Generate candidates for a single-hop route."""
    candidates = []

    # Group by cable for strand_adjacency scoring
    by_cable = defaultdict(list)
    for a in avail:
        by_cable[a["cable_info"]["cable_id"]].append(a)

    for _cable_id, cable_avail in by_cable.items():
        if len(cable_avail) < strand_count:
            continue

        # Generate contiguous groups first (for adjacency), then any combo
        # Try contiguous groups
        sorted_avail = sorted(cable_avail, key=lambda x: x["position"])
        for start in range(len(sorted_avail) - strand_count + 1):
            group = sorted_avail[start : start + strand_count]
            positions = [g["position"] for g in group]
            is_contiguous = all(positions[j + 1] - positions[j] == 1 for j in range(len(positions) - 1))

            strands = []
            for g in group:
                strands.append(
                    {
                        "hops": [
                            {
                                "cable_id": g["cable_info"]["cable_id"],
                                "fp_entry_id": g["fp_entry_id"],
                                "fp_exit_id": g["fp_exit_id"],
                                "entry_rp_id": g["entry_rp_id"],
                                "exit_rp_id": g["exit_rp_id"],
                                "position": g["position"],
                            }
                        ],
                        "position": g["position"],
                    }
                )

            candidates.append(
                {
                    "strands": strands,
                    "route": route_device_ids,
                    "hop_count": len(route_device_ids) - 1,
                    "new_splice_count": 0,
                    "existing_splice_count": 0,
                    "is_contiguous": is_contiguous,
                    "lowest_position": min(positions),
                    "splices_needed": [],
                }
            )

    return candidates


def _generate_multi_hop_candidates(hops, hop_availabilities, strand_count, route_device_ids, occupied_fps):
    """Generate candidates for multi-hop routes.

    For each intermediate closure, we need to check if a splice exists or needs
    to be created between the exit FP of one cable and the entry FP of the next.
    """
    # Build splice maps for intermediate closures
    splice_maps = {}
    for i in range(1, len(route_device_ids) - 1):
        dev_id = route_device_ids[i]
        splice_maps[dev_id] = _get_existing_splices_map(dev_id)

    # For multi-hop, we need to find paths through intermediate closures.
    # Build per-strand paths by following available positions through hops.
    # At each intermediate closure, the exit FP of hop i must connect to the
    # entry FP of hop i+1 (via splice).

    # Step 1: For each hop, index available strands by their exit/entry FP device
    # Step 2: Find chains of strands that connect through intermediate closures

    # Build chains recursively
    def _find_chains(hop_idx, prev_exit_fps=None):
        """Find all valid strand chains from hop_idx onward.

        prev_exit_fps: if set, the exit FP IDs from the previous hop that we need
                       to connect to via splice at the intermediate closure.

        Returns list of chains, each chain is a list of (hop_idx, avail_entry) tuples.
        """
        avail = hop_availabilities[hop_idx]
        chains = []

        for a in avail:
            # If we have a previous hop, check that this entry FP can be spliced
            # to the previous exit FP (they must be on the same device)
            if prev_exit_fps is not None:
                # a["fp_entry_id"] needs to connect to one of prev_exit_fps
                # Check if any of prev_exit_fps can splice to this entry FP
                # (they should be on same device - the intermediate closure)
                entry_fp = a["fp_entry_id"]

                # Check if entry FP is occupied by splice check
                if entry_fp in occupied_fps:
                    continue

                valid_prev = None
                for prev_fp in prev_exit_fps:
                    # Both FPs should be on this intermediate device
                    # A splice can connect them
                    valid_prev = prev_fp
                    break

                if valid_prev is None:
                    continue

                if hop_idx == len(hops) - 1:
                    # Last hop - just add this strand
                    chains.append([(hop_idx, a, valid_prev)])
                else:
                    # Recurse to next hop
                    sub_chains = _find_chains(hop_idx + 1, {a["fp_exit_id"]})
                    for sc in sub_chains:
                        chains.append([(hop_idx, a, valid_prev)] + sc)
            else:
                if hop_idx == len(hops) - 1:
                    chains.append([(hop_idx, a, None)])
                else:
                    sub_chains = _find_chains(hop_idx + 1, {a["fp_exit_id"]})
                    for sc in sub_chains:
                        chains.append([(hop_idx, a, None)] + sc)

        return chains

    all_chains = _find_chains(0)

    if len(all_chains) < strand_count:
        return []

    # Now select groups of strand_count chains
    candidates = []
    # Limit combinations to avoid explosion
    max_chains = min(len(all_chains), 50)
    chain_subset = all_chains[:max_chains]

    if strand_count == 1:
        for chain in chain_subset:
            candidate = _chain_to_candidate(chain, route_device_ids, splice_maps)
            if candidate:
                candidates.append(candidate)
    else:
        # Try to find groups of strand_count non-overlapping chains
        for combo in combinations(range(len(chain_subset)), strand_count):
            chains = [chain_subset[i] for i in combo]
            # Check no FP overlap
            all_fps = set()
            overlap = False
            for chain in chains:
                for _hop_idx, a, _prev_fp in chain:
                    if a["fp_entry_id"] in all_fps or a["fp_exit_id"] in all_fps:
                        overlap = True
                        break
                    all_fps.add(a["fp_entry_id"])
                    all_fps.add(a["fp_exit_id"])
                if overlap:
                    break
            if overlap:
                continue

            candidate = _chains_to_candidate(chains, route_device_ids, splice_maps)
            if candidate:
                candidates.append(candidate)

            if len(candidates) >= 50:
                break

    return candidates


def _chain_to_candidate(chain, route_device_ids, splice_maps):
    """Convert a single chain to a candidate dict."""
    return _chains_to_candidate([chain], route_device_ids, splice_maps)


def _chains_to_candidate(chains, route_device_ids, splice_maps):
    """Convert multiple chains to a single candidate dict."""
    strands = []
    total_new_splices = 0
    total_existing_splices = 0
    all_splices_needed = []
    positions = []

    for chain in chains:
        strand_hops = []
        for hop_idx, a, prev_exit_fp in chain:
            strand_hops.append(
                {
                    "cable_id": a["cable_info"]["cable_id"],
                    "fp_entry_id": a["fp_entry_id"],
                    "fp_exit_id": a["fp_exit_id"],
                    "entry_rp_id": a["entry_rp_id"],
                    "exit_rp_id": a["exit_rp_id"],
                    "position": a["position"],
                }
            )

            # Check splice at entry (intermediate closure)
            if prev_exit_fp is not None:
                dev_id = route_device_ids[hop_idx]  # intermediate closure
                splice_key = (prev_exit_fp, a["fp_entry_id"])
                if splice_key in splice_maps.get(dev_id, {}):
                    total_existing_splices += 1
                else:
                    total_new_splices += 1
                    all_splices_needed.append(
                        {
                            "device_id": dev_id,
                            "fp_a_id": prev_exit_fp,
                            "fp_b_id": a["fp_entry_id"],
                        }
                    )

        strands.append(
            {
                "hops": strand_hops,
                "position": strand_hops[0]["position"] if strand_hops else 0,
            }
        )
        if strand_hops:
            positions.append(strand_hops[0]["position"])

    is_contiguous = len(positions) > 1 and all(
        sorted(positions)[j + 1] - sorted(positions)[j] == 1 for j in range(len(positions) - 1)
    )

    return {
        "strands": strands,
        "route": route_device_ids,
        "hop_count": len(route_device_ids) - 1,
        "new_splice_count": total_new_splices,
        "existing_splice_count": total_existing_splices,
        "is_contiguous": is_contiguous,
        "lowest_position": min(positions) if positions else 0,
        "splices_needed": all_splices_needed,
    }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _score_candidate(candidate, priorities):
    """Score a candidate based on user-ordered priority list.

    Returns a tuple suitable for sorting (lower is better).
    """
    score = []
    for priority in priorities:
        if priority == "hop_count":
            score.append(candidate["hop_count"])
        elif priority == "new_splices":
            score.append(candidate["new_splice_count"])
        elif priority == "strand_adjacency":
            # 0 if contiguous, 1 if not
            score.append(0 if candidate["is_contiguous"] else 1)
        elif priority == "lowest_strand":
            score.append(candidate["lowest_position"])
    return tuple(score)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def find_fiber_paths(origin_device, destination_device, strand_count=1, priorities=None, max_results=20):
    """Find available fiber paths between two devices.

    Args:
        origin_device: Origin Device (closure)
        destination_device: Destination Device (closure)
        strand_count: Number of strands needed
        priorities: List of scoring priority names, in order. Options:
            "hop_count", "new_splices", "strand_adjacency", "lowest_strand"
        max_results: Maximum number of results to return

    Returns:
        List of proposal dicts, ranked by score. Each contains:
            - strands: list of strand info (one per strand_count)
            - route: list of device IDs
            - hop_count: number of intermediate hops
            - new_splice_count: splices that need to be created
            - existing_splice_count: splices already in place
            - splices_needed: list of splice info dicts
    """
    if priorities is None:
        priorities = ["hop_count", "new_splices", "strand_adjacency", "lowest_strand"]

    edges, adjacency, all_device_ids = _build_device_graph(origin_device, destination_device)

    if origin_device.pk not in all_device_ids or destination_device.pk not in all_device_ids:
        return []

    routes = _find_all_simple_paths(adjacency, origin_device.pk, destination_device.pk)
    if not routes:
        return []

    occupied_fps = _get_occupied_front_port_ids()

    all_candidates = []
    for route in routes:
        candidates = _find_available_strand_groups(route, edges, strand_count, occupied_fps)
        all_candidates.extend(candidates)

    # Score and sort
    all_candidates.sort(key=lambda c: _score_candidate(c, priorities))

    return all_candidates[:max_results]


def create_circuit_from_proposal(proposal, name_template="Circuit-{n}", name=None, splice_project=None):
    """Create a FiberCircuit from a selected proposal.

    Args:
        proposal: A proposal dict from find_fiber_paths()
        name_template: Name template with {n} placeholder for auto-increment
        name: Literal circuit name (takes precedence over name_template)
        splice_project: Optional SpliceProject instance to link new SplicePlans to

    Returns:
        The created FiberCircuit instance
    """
    from .models import FiberCircuit

    fp_ct = ContentType.objects.get_for_model(FrontPort)

    with transaction.atomic():
        # Resolve circuit name: literal name takes precedence
        if name:
            circuit_name = name
        else:
            circuit_name = _resolve_name_template(name_template)

        # Create the FiberCircuit
        circuit = FiberCircuit(
            name=circuit_name,
            status=FiberCircuitStatusChoices.PLANNED,
            strand_count=len(proposal["strands"]),
        )
        circuit.save()

        # Create FiberCircuitPath per strand
        for idx, strand in enumerate(proposal["strands"]):
            hops = strand["hops"]
            origin_fp_id = hops[0]["fp_entry_id"]
            destination_fp_id = hops[-1]["fp_exit_id"]

            # Build path JSON
            path_json = []
            for hop in hops:
                path_json.append({"type": "front_port", "id": hop["fp_entry_id"]})
                path_json.append({"type": "rear_port", "id": hop["entry_rp_id"]})
                path_json.append({"type": "cable", "id": hop["cable_id"]})
                path_json.append({"type": "rear_port", "id": hop["exit_rp_id"]})
                path_json.append({"type": "front_port", "id": hop["fp_exit_id"]})

            fcp = FiberCircuitPath.objects.create(
                circuit=circuit,
                position=idx + 1,
                origin_id=origin_fp_id,
                destination_id=destination_fp_id,
                path=path_json,
                is_complete=True,
            )

            # Create FiberCircuitNode rows for protection
            node_pos = 1
            for entry in path_json:
                kwargs = {"path": fcp, "position": node_pos}
                if entry["type"] == "cable":
                    kwargs["cable_id"] = entry["id"]
                elif entry["type"] == "front_port":
                    kwargs["front_port_id"] = entry["id"]
                elif entry["type"] == "rear_port":
                    kwargs["rear_port_id"] = entry["id"]
                FiberCircuitNode.objects.create(**kwargs)
                node_pos += 1

            # Create strand nodes
            fp_ids = [e["id"] for e in path_json if e["type"] == "front_port"]
            strands = FiberStrand.objects.filter(
                Q(front_port_a_id__in=fp_ids) | Q(front_port_b_id__in=fp_ids)
            ).distinct()
            for fs in strands:
                FiberCircuitNode.objects.create(path=fcp, position=node_pos, fiber_strand=fs)
                node_pos += 1

        # Create splices for new connections
        for splice_info in proposal.get("splices_needed", []):
            device_id = splice_info["device_id"]
            fp_a_id = splice_info["fp_a_id"]
            fp_b_id = splice_info["fp_b_id"]

            # Create 0-length cable for splice
            splice_cable = Cable.objects.create(length=0, length_unit="m")
            CableTermination.objects.create(
                cable=splice_cable,
                cable_end="A",
                termination_type=fp_ct,
                termination_id=fp_a_id,
            )
            CableTermination.objects.create(
                cable=splice_cable,
                cable_end="B",
                termination_type=fp_ct,
                termination_id=fp_b_id,
            )

            # Create SplicePlanEntry — link to project if provided
            if splice_project:
                # Create a new plan for this closure, linked to the project
                plan, _ = SplicePlan.objects.get_or_create(
                    closure_id=device_id,
                    project=splice_project,
                    defaults={
                        "name": f"{Device.objects.get(pk=device_id).name} — {splice_project.name}",
                        "status": SplicePlanStatusChoices.DRAFT,
                    },
                )
            else:
                plan = SplicePlan.objects.filter(closure_id=device_id).first()
            if plan:
                # Find the tray (module) for fiber_a
                fp_a = FrontPort.objects.get(pk=fp_a_id)
                SplicePlanEntry.objects.create(
                    plan=plan,
                    tray_id=fp_a.module_id,
                    fiber_a_id=fp_a_id,
                    fiber_b_id=fp_b_id,
                )
                plan.diff_stale = True
                plan.save(update_fields=["diff_stale"])

    return circuit


def _resolve_name_template(name_template):
    """Resolve a name template with {n} auto-increment.

    Uses select_for_update for concurrency safety.
    """
    from .models import FiberCircuit

    if "{n}" not in name_template:
        return name_template

    # Extract prefix (everything before {n})
    prefix = name_template.split("{n}")[0]
    suffix = name_template.split("{n}")[-1] if name_template.endswith("{n}") is False else ""

    # Find the highest existing number with this prefix
    existing = FiberCircuit.objects.select_for_update().filter(name__startswith=prefix).values_list("name", flat=True)

    max_n = 0
    pattern = re.compile(re.escape(prefix) + r"(\d+)" + re.escape(suffix) + r"$")
    for name in existing:
        match = pattern.match(name)
        if match:
            n = int(match.group(1))
            if n > max_n:
                max_n = n

    return name_template.replace("{n}", str(max_n + 1))
