"""Estimate how far along its cable a fault lies, and find that spot on the cable's route.

The estimate turns a jacket mark or an OTDR shot into a distance from the cable's A end; it needs no
netbox-pathways. The route walk (``locate_on_route``) then places a distance on the cable's route for the
map. It is pure: it takes plain dataclasses and does arithmetic. The adapters below read the cable, its
route and its slack loops into those dataclasses; netbox-pathways is imported inside them, behind
``pathways_installed()``, as ``pathways_compat`` describes.
"""

from dataclasses import dataclass, replace
from decimal import Decimal
from itertools import pairwise

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from utilities.conversion import to_meters

from . import pathways_compat
from .assignment import path_hop_ends
from .choices import FiberFaultLocatedAtStatusChoices
from .models import FiberFault, FiberStrandPath

NOTE_NO_PATHWAYS = "netbox-pathways is not installed."
NOTE_NO_ROUTE = "The cable has no recorded route."
NOTE_GAP = "The route has a gap at segment {sequence}."
NOTE_BEYOND = "The distance runs past the end of the cable."
NOTE_NO_LENGTH = "Cable {cable} has no length."
NOTE_NO_START_MARK = "The cable has no start mark."
NOTE_OTHER_CABLE = "The shot lands on cable {cable}, not this fault's cable."
NOTE_ORIGIN_OFF_PATH = "The shot's origin is not on the shot strand's path."
NOTE_UNKNOWN_HOP = "Hop {position} of the shot's path has no known length."
NOTE_NO_PATH = "The shot strand has no analyzed path."
NOTE_PATH_MISSES_CABLE = "The shot strand's path does not cross this fault's cable."
NOTE_NOT_ON_ROUTE = "The pathway is not on this cable's route."


@dataclass(frozen=True)
class RouteLeg:
    """One route segment of a cable, in route order, with the pathways endpoints at each side."""

    segment_pk: int
    sequence: int
    pathway_pk: int | None
    length_m: float | None
    start_nodes: frozenset
    end_nodes: frozenset


@dataclass(frozen=True)
class SlackPoint:
    """Slack coiled at a place; empty nodes mean the coil is not placed on the route."""

    nodes: frozenset
    length_m: float


@dataclass(frozen=True)
class RoutePlace:
    """The route segment a distance falls in, or the reason it cannot be placed."""

    segment_pk: int | None
    pathway_pk: int | None
    note: str


@dataclass(frozen=True)
class Estimate:
    """A distance from the cable's A end in meters, or the reason it cannot be estimated."""

    distance_m: float | None
    note: str

    def as_decimal(self):
        """The distance as stored on a fault: meters, to the centimeter."""
        return Decimal(f"{self.distance_m:.2f}")


def _flip(leg):
    return replace(leg, start_nodes=leg.end_nodes, end_nodes=leg.start_nodes)


def _placed_slack(legs, slack):
    """Map boundary index to coiled length; boundary i sits before legs[i], len(legs) is the far end.

    A coil is placed only when its nodes touch exactly one boundary. A node a route revisits touches
    several, so its coil cannot be pinned down and is left to the scale factor instead.
    """
    boundaries = [legs[0].start_nodes]
    boundaries += [before.end_nodes & after.start_nodes for before, after in zip(legs, legs[1:], strict=False)]
    boundaries.append(legs[-1].end_nodes)
    placed = {}
    for point in slack:
        hits = [i for i, nodes in enumerate(boundaries) if nodes & point.nodes]
        if len(hits) == 1:
            placed[hits[0]] = placed.get(hits[0], 0.0) + point.length_m
    return placed


def _route_problem(legs):
    """Why the legs cannot be walked, or "" when they can."""
    if not legs:
        return NOTE_NO_ROUTE
    for leg in legs:
        if leg.pathway_pk is None or not leg.length_m or leg.length_m <= 0:
            return NOTE_GAP.format(sequence=leg.sequence)
    return ""


def _walk(legs, cable_length_m, slack):
    """Where each leg starts and ends along the cable, where the far-end coil finishes, and why the legs
    cannot be walked ("" when they can).

    The drawn route lengths are scaled so they add up to the cable's real length once placed slack is taken out.
    """
    problem = _route_problem(legs)
    if problem:
        return [], 0.0, problem
    placed = _placed_slack(legs, slack)
    factor = (cable_length_m - sum(placed.values())) / sum(leg.length_m for leg in legs)
    if factor <= 0:
        return [], 0.0, NOTE_BEYOND
    spans, position = [], 0.0
    for index, leg in enumerate(legs):
        position += placed.get(index, 0.0)
        start = position
        position += leg.length_m * factor
        spans.append((start, position))
    return spans, position + placed.get(len(legs), 0.0), ""


def _place(leg):
    return RoutePlace(leg.segment_pk, leg.pathway_pk, "")


def locate_on_route(legs, *, cable_length_m, distance_m, slack):
    """Return the leg holding the point `distance_m` along the cable from its A end.

    A distance inside a placed slack coil lands on the leg before it, or on the last leg for a far-end coil.
    """
    spans, total, note = _walk(legs, cable_length_m, slack)
    if note:
        return RoutePlace(None, None, note)
    for index, (start, end) in enumerate(spans):
        if distance_m <= end:
            return _place(legs[index - 1] if index and distance_m <= start else legs[index])
    if distance_m <= total:
        return _place(legs[-1])
    return RoutePlace(None, None, NOTE_BEYOND)


def pathway_midpoint(legs, *, cable_length_m, slack, pathway_pk):
    """The distance from the A end to the middle of the cable's first leg through the pathway."""
    spans, _total, note = _walk(legs, cable_length_m, slack)
    if note:
        return Estimate(None, note)
    for leg, (start, end) in zip(legs, spans, strict=True):
        if leg.pathway_pk == pathway_pk:
            return Estimate((start + end) / 2, "")
    return Estimate(None, NOTE_NOT_ON_ROUTE)


def _endpoint_nodes(pathway, side):
    """The pathways graph nodes at one side ("start" or "end") of a pathway."""
    if pathway is None:
        return frozenset()
    nodes = (
        ("structure", getattr(pathway, f"{side}_structure_id")),
        ("location", getattr(pathway, f"{side}_location_id")),
    )
    return frozenset(node for node in nodes if node[1] is not None)


def _starting_at(leg, nodes):
    """The leg turned to start at nodes; as drawn unless only its end touches them."""
    if leg.end_nodes & nodes and not leg.start_nodes & nodes:
        return _flip(leg)
    return leg


def _oriented(legs, cable_id):
    """The legs turned so each one starts where the one before it ends, whatever way its pathway is drawn.

    The first leg ends at the joint it shares with the second; a lone leg starts at the cable's A end. A leg
    that cannot be told apart that way stays as drawn.
    """
    from netbox_pathways.anchors import cable_end_nodes

    if len(legs) < 2:
        return [_starting_at(leg, frozenset(cable_end_nodes(cable_id, "A").nodes)) for leg in legs]
    joint = legs[1].start_nodes | legs[1].end_nodes
    oriented = [_flip(_starting_at(_flip(legs[0]), joint))]
    for leg in legs[1:]:
        oriented.append(_starting_at(leg, oriented[-1].end_nodes))
    return oriented


def route_legs(cable_id):
    """The cable's route segments as RouteLegs, in route order from end A, each oriented along the route.

    A segment that does not join the one before it follows a gap, so its leg gets no length.
    """
    from django.contrib.gis.db.models.functions import Length
    from netbox_pathways.models import Pathway
    from netbox_pathways.routing import validate_cable_route

    route = validate_cable_route(cable_id)
    segments = route["segments"]
    after_gap = {gap["after_segment_id"] for gap in route["gaps"]}
    follows_gap = {segment.pk for before, segment in pairwise(segments) if before.pk in after_gap}
    drawn = dict(
        Pathway.objects.filter(pk__in=[s.pathway_id for s in segments])
        .annotate(drawn=Length("path"))
        .values_list("pk", "drawn")
    )
    legs = []
    for segment in segments:
        pathway = segment.pathway
        length = None
        if pathway is not None and segment.pk not in follows_gap:
            length = pathway.length if pathway.length is not None else getattr(drawn[pathway.pk], "m", None)
        legs.append(
            RouteLeg(
                segment_pk=segment.pk,
                sequence=segment.sequence,
                pathway_pk=segment.pathway_id,
                length_m=length,
                start_nodes=_endpoint_nodes(pathway, "start"),
                end_nodes=_endpoint_nodes(pathway, "end"),
            )
        )
    return _oriented(legs, cable_id)


def slack_points(fiber_cable):
    """The cable's slack loops as SlackPoints; loops on a cable type without a mark unit are left out."""
    from netbox_pathways.registry import LOCATION_IDENTITY_ACCESSOR

    unit = fiber_cable.fiber_cable_type.mark_unit
    if not unit:
        return []
    points = []
    for loop in fiber_cable.slack_loops.select_related("location"):
        nodes = set()
        if loop.location is not None:
            nodes.add(("location", loop.location.pk))
            structure = getattr(loop.location, LOCATION_IDENTITY_ACCESSOR, None)
            if structure is not None:
                nodes.add(("structure", structure.pk))
        points.append(SlackPoint(frozenset(nodes), float(to_meters(loop.loop_length, unit))))
    return points


def _dcim_length_m(cable):
    return None if cable.length is None else float(to_meters(cable.length, cable.length_unit))


def cable_length_m(fiber_cable):
    """The cable's length in meters: the dcim length, else the span of its sheath marks, else None."""
    length = _dcim_length_m(fiber_cable.cable)
    unit = fiber_cable.fiber_cable_type.mark_unit
    if length is None and unit and fiber_cable.start_mark is not None and fiber_cable.end_mark is not None:
        length = float(to_meters(abs(fiber_cable.end_mark - fiber_cable.start_mark), unit))
    return length


def _route_inputs(fiber_cable):
    """The route walk's keyword arguments for the cable, or the reason its length is unknown ("" when known)."""
    length = cable_length_m(fiber_cable)
    if length is None:
        return {}, NOTE_NO_LENGTH.format(cable=fiber_cable.cable)
    legs = route_legs(fiber_cable.cable_id)
    return {"legs": legs, "cable_length_m": length, "slack": slack_points(fiber_cable)}, ""


def place_on_route(fault):
    """The route segment holding the fault's distance from the A end; None when the fault has no distance."""
    if fault.distance_from_a is None:
        return None
    if not pathways_compat.pathways_installed():
        return RoutePlace(None, None, NOTE_NO_PATHWAYS)
    inputs, note = _route_inputs(fault.fiber_cable)
    if note:
        return RoutePlace(None, None, note)
    return locate_on_route(**inputs, distance_m=float(fault.distance_from_a))


def distance_at_pathway(fiber_cable, pathway_pk):
    """The distance from the A end to the middle of the cable's stretch through the pathway."""
    inputs, note = _route_inputs(fiber_cable)
    if note:
        return Estimate(None, note)
    return pathway_midpoint(**inputs, pathway_pk=pathway_pk)


def _distance_on_cable(fiber_cable, distance_m, from_end, next_hop=None):
    """The point `distance_m` into the fault's cable from `from_end`, as a distance from its A end.

    A distance past the cable's end lands on next_hop's cable when there is one.
    """
    length = cable_length_m(fiber_cable)
    if length is None:
        return Estimate(None, NOTE_NO_LENGTH.format(cable=fiber_cable.cable))
    if distance_m > length:
        return Estimate(None, NOTE_OTHER_CABLE.format(cable=_hop_label(next_hop)) if next_hop else NOTE_BEYOND)
    return Estimate(distance_m if from_end == "A" else length - distance_m, "")


def estimate_from_mark(fault):
    """Estimate from the jacket mark; the cable's start mark is read at its A end."""
    fiber_cable = fault.fiber_cable
    unit = fiber_cable.fiber_cable_type.mark_unit
    if fiber_cable.start_mark is None or not unit:
        return Estimate(None, NOTE_NO_START_MARK)
    return Estimate(float(to_meters(abs(fault.location_mark - fiber_cable.start_mark), unit)), "")


def _hop_label(hop):
    return hop.strand.fiber_cable.cable if hop.strand_id else hop.cable or hop.provider_circuit


def _hop_length_m(hop):
    if hop.strand_id:
        return cable_length_m(hop.strand.fiber_cable)
    return _dcim_length_m(hop.cable) if hop.cable_id else None


def _cable_end_at(cable, devices):
    """The end ("A" or "B") of the cable that terminates on one of the devices, or None."""
    return next((term.cable_end for term in cable.terminations.all() if term._device_id in devices), None)


def _joints(path, hops):
    """The devices at each joint of the path; joint i sits before hops[i], the last one after the final hop."""
    joints = [set() for _ in range(len(hops) + 1)]
    for index, (_hop, ends) in enumerate(hops):
        joints[index].update(ends[:1])
        joints[index + 1].update(ends[-1:])
    if path.end_a_port_id:
        joints[0].add(path.end_a_port.device_id)
    if path.end_b_port_id:
        joints[-1].add(path.end_b_port.device_id)
    return joints


def _land(fault, distance_m, devices, next_hop=None):
    """Walk the fault's cable from its end at one of the devices."""
    from_end = _cable_end_at(fault.fiber_cable.cable, devices)
    if from_end is None:
        return Estimate(None, NOTE_ORIGIN_OFF_PATH)
    return _distance_on_cable(fault.fiber_cable, distance_m, from_end, next_hop)


def estimate_from_otdr(fault):
    """Estimate from the OTDR shot, walking the shot strand's path from the origin to the fault's cable.

    Without a strand the origin must be an end of the fault's cable. A path that passes the origin more
    than once is walked from the pass nearest the fault's cable.
    """
    distance = float(fault.otdr_distance)
    if fault.otdr_strand_id is None:
        return _land(fault, distance, {fault.otdr_origin_id})
    path = FiberStrandPath.objects.filter(hops__strand_id=fault.otdr_strand_id).first()
    if path is None:
        return Estimate(None, NOTE_NO_PATH)
    hops = list(path_hop_ends(path))
    target = next(
        (
            i
            for i, (hop, _ends) in enumerate(hops)
            if hop.strand_id and hop.strand.fiber_cable_id == fault.fiber_cable_id
        ),
        None,
    )
    if target is None:
        return Estimate(None, NOTE_PATH_MISSES_CABLE)
    joints = _joints(path, hops)
    at = [j for j, devices in enumerate(joints) if fault.otdr_origin_id in devices]
    if not at:
        return Estimate(None, NOTE_ORIGIN_OFF_PATH)
    origin = min(at, key=lambda j: target - j if j <= target else j - target - 1)
    if origin <= target:
        earlier, beyond, entry = hops[origin:target], hops[target + 1 :], joints[target]
    else:
        earlier, beyond, entry = hops[target + 1 : origin][::-1], hops[:target][::-1], joints[target + 1]
    remaining = distance
    for hop, _ends in earlier:
        length = _hop_length_m(hop)
        if length is None:
            return Estimate(None, NOTE_UNKNOWN_HOP.format(position=hop.position))
        if remaining < length:
            return Estimate(None, NOTE_OTHER_CABLE.format(cable=_hop_label(hop)))
        remaining -= length
    return _land(fault, remaining, entry, beyond[0][0] if beyond else None)


def apply_estimate(fault):
    """Re-estimate the fault's distance from its evidence; a confirmed location is left alone. Does not save."""
    if fault.located_at_status == FiberFaultLocatedAtStatusChoices.CONFIRMED:
        return
    if fault.location_mark is None and fault.otdr_distance is None:
        fault.clear_located_at()
        return
    estimate = estimate_from_mark(fault) if fault.location_mark is not None else estimate_from_otdr(fault)
    fault.clear_located_at()
    if estimate.distance_m is None:
        fault.estimate_note = estimate.note
    else:
        fault.distance_from_a = estimate.as_decimal()
        fault.located_at_status = FiberFaultLocatedAtStatusChoices.ESTIMATED


def fault_to_change(user, pk):
    """The fault, if the user may see it (404) and change it (403)."""
    fault = get_object_or_404(FiberFault.objects.restrict(user, "view"), pk=pk)
    if not user.has_perm("netbox_fms.change_fiberfault", fault):
        raise PermissionDenied("Changing a fault requires change_fiberfault.")
    return fault


def confirm_estimate(fault):
    """Confirm an estimated location and save; False (nothing changed) when there is no estimate to confirm."""
    if fault.located_at_status != FiberFaultLocatedAtStatusChoices.ESTIMATED:
        return False
    fault.snapshot()
    fault.confirm_located_at()
    fault.save()
    return True


def reestimate(fault):
    """Run the estimator again and save; False (nothing changed) while the location is confirmed.

    ``FiberFault.save()`` recomputes only when the evidence changed, so changed cable lengths are picked up
    here by calling the estimator directly.
    """
    if fault.located_at_status == FiberFaultLocatedAtStatusChoices.CONFIRMED:
        return False
    fault.snapshot()
    apply_estimate(fault)
    fault.save()
    return True
