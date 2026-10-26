"""Route walk engine: distance along a cable to the route segment it lands on (#198)."""

from netbox_fms.fault_location import (
    NOTE_BEYOND,
    NOTE_NO_ROUTE,
    RouteLeg,
    SlackPoint,
    locate_on_route,
)


def _node(pk):
    return ("structure", pk)


def _legs(lengths=(100.0, 100.0, 100.0), nodes=(1, 2, 3, 4)):
    return [
        RouteLeg(
            segment_pk=100 + i,
            sequence=i,
            pathway_pk=200 + i,
            length_m=length,
            start_nodes=frozenset({_node(nodes[i - 1])}),
            end_nodes=frozenset({_node(nodes[i])}),
        )
        for i, length in enumerate(lengths, start=1)
    ]


def _locate(legs, distance, cable=330.0, slack=(), from_end="A"):
    return locate_on_route(legs, cable_length_m=cable, distance_m=distance, slack=list(slack), from_end=from_end)


def test_lands_by_scaled_length():
    assert _locate(_legs(), 150).pathway_pk == 202
    assert _locate(_legs(), 231).pathway_pk == 203
    assert _locate(_legs(), 150).note == ""


def test_from_b_end():
    assert _locate(_legs(), 50, from_end="B").pathway_pk == 203


def test_zero_and_exact_boundary():
    assert _locate(_legs(), 0).pathway_pk == 201
    assert _locate(_legs(), 110).pathway_pk == 201


def test_slack_coil_at_boundary():
    slack = [SlackPoint(nodes=frozenset({_node(2)}), length_m=50.0)]
    assert _locate(_legs(), 120, cable=350.0, slack=slack).pathway_pk == 201
    assert _locate(_legs(), 160, cable=350.0, slack=slack).pathway_pk == 202


def test_slack_on_repeated_node_is_spread():
    legs = _legs(nodes=(1, 2, 3, 2))
    slack = [SlackPoint(nodes=frozenset({_node(2)}), length_m=50.0)]
    assert _locate(legs, 100, cable=350.0, slack=slack).pathway_pk == 201
    assert _locate(legs, 120, cable=350.0, slack=slack).pathway_pk == 202


def test_gap_stops():
    legs = _legs()
    legs[1] = RouteLeg(101, 2, None, None, frozenset(), frozenset())
    estimate = _locate(legs, 50)
    assert estimate.pathway_pk is None
    assert estimate.note == "The route has a gap at segment 2."


def test_beyond_and_no_route():
    assert _locate(_legs(), 400).note == NOTE_BEYOND
    assert _locate([], 10).note == NOTE_NO_ROUTE
    slack = [SlackPoint(nodes=frozenset({_node(2)}), length_m=400.0)]
    assert _locate(_legs(), 10, slack=slack).note == NOTE_BEYOND


def test_slack_at_route_start_is_skipped():
    slack = [SlackPoint(nodes=frozenset({_node(1)}), length_m=30.0)]
    assert _locate(_legs(), 20, cable=330.0, slack=slack).pathway_pk == 201
    assert _locate(_legs(), 140, cable=330.0, slack=slack).pathway_pk == 202
