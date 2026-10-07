"""Rear-port pairing rule of the analysis loader."""


def pair_far_rear_port_termination(near_connector, near_terms, far_terms):
    """Pick which far-end rear-port termination continues a tube, or None.

    ``near_terms`` and ``far_terms`` are the rear-port CableTerminations on
    the two ends of one cable, in pk order. With a connector recorded on the
    near end, the far tube is the one sharing the same connector number
    (symmetric trunk profile); a mixed-connector cable is bridged only when
    both ends are single-RP, since there is exactly one way to align
    positions and nothing to disambiguate. Without a connector, only an
    unambiguous single far rear port is followed. The analysis loader pairs
    tubes through this rule so a fiber never changes tube mid-cable.
    """
    if near_connector is not None:
        for far_term in far_terms:
            if far_term.connector == near_connector:
                return far_term
        if len(near_terms) == 1 and len(far_terms) == 1:
            return far_terms[0]
        return None

    return far_terms[0] if len(far_terms) == 1 else None


def paired_rear_port_terminations(a_terms, b_terms):
    """The ``(a_rear_port_id, b_rear_port_id)`` tube pairs of one cable, in A-end order.

    A pair is kept only when :func:`pair_far_rear_port_termination` resolves
    it from either end: a fiber entering at A must land on the B rear port,
    and a fiber entering at that B rear port must land back on A. The
    analysis loader pairs tubes through this one rule so a fiber never
    changes tube mid-cable.
    """
    pairs = []
    for a in a_terms:
        b = pair_far_rear_port_termination(a.connector, a_terms, b_terms)
        if b is not None and pair_far_rear_port_termination(b.connector, b_terms, a_terms) is a:
            pairs.append((a.termination_id, b.termination_id))
    return pairs
