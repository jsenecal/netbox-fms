"""Pure value types of the path graph (#196): route keys, completeness, orientation."""

from types import SimpleNamespace

from netbox_fms.choices import PathCompletenessChoices, PathEndKindChoices, PathEndReasonChoices
from netbox_fms.path_graph import Chain, ChainEnd, fp_node, route_key_for, rp_node
from netbox_fms.trace import paired_rear_port_terminations

TERMINATED = ChainEnd(1, PathEndKindChoices.TERMINATED, "")
OPEN = ChainEnd(None, PathEndKindChoices.OPEN, PathEndReasonChoices.CABLE_END)


def test_route_key_is_stable_and_order_sensitive():
    assert route_key_for([3, 7, 9]) == route_key_for([3, 7, 9])
    assert route_key_for([3, 7, 9]) != route_key_for([9, 7, 3])
    assert len(route_key_for([3])) == 64


def test_completeness_follows_the_end_kinds():
    assert Chain([("cable", 1)], TERMINATED, TERMINATED, [1]).completeness == "terminated_terminated"
    assert Chain([("cable", 1)], TERMINATED, OPEN, [1]).completeness == "terminated_open"
    assert Chain([("cable", 1)], OPEN, OPEN, [1]).completeness == PathCompletenessChoices.OPEN_OPEN


def test_reversed_swaps_ends_and_reverses_hops_and_cables():
    chain = Chain([("strand", 5), ("provider_circuit", 2), ("strand", 6)], TERMINATED, OPEN, [10, 11])
    back = chain.reversed()
    assert back.hops == [("strand", 6), ("provider_circuit", 2), ("strand", 5)]
    assert back.cable_ids == [11, 10]
    assert (back.end_a, back.end_b) == (OPEN, TERMINATED)
    assert back.route_key != chain.route_key
    assert chain.strand_ids == [5, 6]


def test_nodes_sort_with_front_ports_before_rear_port_positions():
    assert sorted([rp_node(2, 1), fp_node(9), fp_node(3)]) == [fp_node(3), fp_node(9), rp_node(2, 1)]


def _term(termination_id, connector):
    return SimpleNamespace(termination_id=termination_id, connector=connector)


def test_pairing_keeps_only_pairs_that_hold_from_both_ends():
    a_terms = [_term(1, 1), _term(2, 2)]
    b_terms = [_term(11, 1), _term(12, 2)]
    assert paired_rear_port_terminations(a_terms, b_terms) == [(1, 11), (2, 12)]
    # One connector-less rear port on A facing two on B: no pair holds both ways.
    assert paired_rear_port_terminations([_term(1, None)], [_term(11, None), _term(12, None)]) == []
    # Single-RP mixed connector cable: one way to align, so it pairs.
    assert paired_rear_port_terminations([_term(1, 1)], [_term(11, None)]) == [(1, 11)]
