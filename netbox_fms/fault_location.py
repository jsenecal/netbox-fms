"""Locate a fault along a cable route from an OTDR distance.

The walk is pure: it takes plain dataclasses and does arithmetic, so it needs neither the database nor
netbox-pathways.
"""

from dataclasses import dataclass, replace

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
class Estimate:
    pathway_pk: int | None
    note: str


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


def locate_on_route(legs, *, cable_length_m, distance_m, slack, from_end):
    """Return the pathway holding the point `distance_m` along the cable, measured from `from_end`.

    The drawn route lengths are scaled so they add up to the cable's real length once placed slack
    is taken out. A distance inside a placed slack coil lands on the leg before it.
    """
    if not legs:
        return Estimate(None, NOTE_NO_ROUTE)
    for leg in legs:
        if leg.pathway_pk is None or not leg.length_m or leg.length_m <= 0:
            return Estimate(None, NOTE_GAP.format(sequence=leg.sequence))
    if from_end == "B":
        legs = [_flip(leg) for leg in reversed(legs)]
    placed = _placed_slack(legs, slack)
    factor = (cable_length_m - sum(placed.values())) / sum(leg.length_m for leg in legs)
    if factor <= 0:
        return Estimate(None, NOTE_BEYOND)
    remaining = distance_m
    for index, leg in enumerate(legs):
        coil = placed.get(index, 0.0)
        if remaining <= coil:
            return Estimate(legs[max(index - 1, 0)].pathway_pk, "")
        remaining -= coil
        scaled = leg.length_m * factor
        if remaining <= scaled:
            return Estimate(leg.pathway_pk, "")
        remaining -= scaled
    return Estimate(None, NOTE_BEYOND)
