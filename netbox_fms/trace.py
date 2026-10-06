"""Fiber circuit path trace engine.

Adapted from NetBox's CablePath.from_origin(), stripped of wireless/power
logic, accepting FrontPort as origin instead of requiring PathEndpoint.
Mid-span provider circuits are crossed as opaque segments: a trunk cable
landing on a CircuitTermination hops to the circuit's other termination and
continues, recording only the core Circuit -- never provider-side detail.

IMPORTANT: NetBox 4.5+ uses the PortMapping model to link FrontPort <-> RearPort.
FrontPort has NO rear_port or rear_port_position attributes -- always query
PortMapping to traverse front-to-rear and rear-to-front.
"""

from circuits.models import CircuitTermination
from dcim.models import CableTermination, FrontPort, PortMapping, RearPort
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from .models import SplicePlanEntry


def _other_end(cable_end):
    """Return the opposite cable end label."""
    return "B" if cable_end == "A" else "A"


def _far_circuit_termination(cable, cable_end, ct_ct):
    """The CableTermination on the far end of ``cable`` landing on a CircuitTermination, or None."""
    return CableTermination.objects.filter(
        cable=cable,
        cable_end=_other_end(cable_end),
        termination_type=ct_ct,
    ).first()


def pair_far_rear_port_termination(near_connector, near_terms, far_terms):
    """Pick which far-end rear-port termination continues a tube, or None.

    ``near_terms`` and ``far_terms`` are the rear-port CableTerminations on
    the two ends of one cable, in pk order. With a connector recorded on the
    near end, the far tube is the one sharing the same connector number
    (symmetric trunk profile); a mixed-connector cable is bridged only when
    both ends are single-RP, since there is exactly one way to align
    positions and nothing to disambiguate. Without a connector, only an
    unambiguous single far rear port is followed. The trace engine and the
    circuit wizard both pair tubes through this rule so a fiber never
    changes tube mid-cable.
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
    analysis loader and the circuit wizard both pair tubes through this one
    rule so a fiber never changes tube mid-cable.
    """
    pairs = []
    for a in a_terms:
        b = pair_far_rear_port_termination(a.connector, a_terms, b_terms)
        if b is not None and pair_far_rear_port_termination(b.connector, b_terms, a_terms) is a:
            pairs.append((a.termination_id, b.termination_id))
    return pairs


def _resolve_far_rear_port(cable, cable_end, near_connector, rp_ct):
    """Pick the far-end rear-port termination of a cable crossing, or None."""
    end_terms = CableTermination.objects.filter(cable=cable, termination_type=rp_ct).order_by("pk")
    near_terms = list(end_terms.filter(cable_end=cable_end))
    far_terms = list(end_terms.filter(cable_end=_other_end(cable_end)))
    return pair_far_rear_port_termination(near_connector, near_terms, far_terms)


def _hop_provider_circuits(far_ct_term, path, visited_circuits, rp_ct, ct_ct):
    """Cross a chain of provider circuits cabled inline in the path.

    ``far_ct_term`` is a CableTermination landing on a CircuitTermination.
    Hop each circuit end-to-end (recording a ``provider_circuit`` path
    entry and the far-side cable) until a cable lands on a rear port.
    Return that rear port's CableTermination, or None when the chain
    dangles or revisits a circuit. The provider span is opaque: only the
    core Circuit is recorded, never provider-side detail.
    """
    term = far_ct_term
    while term is not None:
        near_ct = CircuitTermination.objects.get(pk=term.termination_id)
        if near_ct.circuit_id in visited_circuits:
            return None
        visited_circuits.add(near_ct.circuit_id)
        path.append({"type": "provider_circuit", "id": near_ct.circuit_id})

        other_ct = (
            CircuitTermination.objects.filter(circuit_id=near_ct.circuit_id)
            .exclude(term_side=near_ct.term_side)
            .first()
        )
        if other_ct is None:
            return None

        egress_term = (
            CableTermination.objects.filter(termination_type=ct_ct, termination_id=other_ct.pk)
            .select_related("cable")
            .first()
        )
        if egress_term is None:
            return None

        cable = egress_term.cable
        path.append({"type": "cable", "id": cable.pk})

        rp_term = _resolve_far_rear_port(cable, egress_term.cable_end, egress_term.connector, rp_ct)
        if rp_term is not None:
            return rp_term

        term = _far_circuit_termination(cable, egress_term.cable_end, ct_ct)

    return None


def trace_fiber_path(origin_front_port):
    """Trace a fiber path starting from a FrontPort.

    Returns a dict with:
        origin: FrontPort
        destination: FrontPort or None
        path: list of {"type": str, "id": int} dicts
        is_complete: bool
    """
    path = []
    current_fp = origin_front_port
    visited_fps = set()
    visited_circuits = set()
    fp_ct = ContentType.objects.get_for_model(FrontPort)
    rp_ct = ContentType.objects.get_for_model(RearPort)
    ct_ct = ContentType.objects.get_for_model(CircuitTermination)

    while True:
        if current_fp.pk in visited_fps:
            break
        visited_fps.add(current_fp.pk)

        # Step 1: INGRESS -- record FrontPort
        path.append({"type": "front_port", "id": current_fp.pk})

        # Follow PortMapping: FrontPort -> RearPort
        mapping = (
            PortMapping.objects.filter(
                front_port=current_fp,
            )
            .select_related("rear_port")
            .first()
        )

        if mapping is None:
            return {"origin": origin_front_port, "destination": None, "path": path, "is_complete": False}

        rear_port = mapping.rear_port
        ingress_rp_position = mapping.rear_port_position
        path.append({"type": "rear_port", "id": rear_port.pk})

        # Step 2: CABLE CROSSING
        term = (
            CableTermination.objects.filter(
                termination_type=rp_ct,
                termination_id=rear_port.pk,
            )
            .select_related("cable")
            .first()
        )

        if term is None:
            return {"origin": origin_front_port, "destination": None, "path": path, "is_complete": False}

        cable = term.cable
        cable_end = term.cable_end
        near_connector = term.connector
        path.append({"type": "cable", "id": cable.pk})

        far_term = _resolve_far_rear_port(cable, cable_end, near_connector, rp_ct)

        if far_term is None:
            # No far rear port: the cable may land on a provider circuit's
            # termination instead of a panel.
            ct_term = _far_circuit_termination(cable, cable_end, ct_ct)
            if ct_term is not None:
                far_term = _hop_provider_circuits(ct_term, path, visited_circuits, rp_ct, ct_ct)

        if far_term is None:
            return {"origin": origin_front_port, "destination": None, "path": path, "is_complete": False}

        far_rp = RearPort.objects.get(pk=far_term.termination_id)
        path.append({"type": "rear_port", "id": far_rp.pk})

        # Step 3: EGRESS -- follow PortMapping: RearPort -> FrontPort
        egress_mapping = (
            PortMapping.objects.filter(
                rear_port=far_rp,
                rear_port_position=ingress_rp_position,
            )
            .select_related("front_port")
            .first()
        )

        if egress_mapping is None:
            return {"origin": origin_front_port, "destination": None, "path": path, "is_complete": False}

        egress_fp = egress_mapping.front_port
        path.append({"type": "front_port", "id": egress_fp.pk})

        # Step 4: SPLICE CHECK
        splice_term = (
            CableTermination.objects.filter(
                termination_type=fp_ct,
                termination_id=egress_fp.pk,
            )
            .select_related("cable")
            .first()
        )

        if splice_term is None:
            return {"origin": origin_front_port, "destination": egress_fp, "path": path, "is_complete": True}

        splice_cable = splice_term.cable
        splice_end = splice_term.cable_end
        far_splice_end = _other_end(splice_end)

        far_splice_term = CableTermination.objects.filter(
            cable=splice_cable,
            cable_end=far_splice_end,
            termination_type=fp_ct,
        ).first()

        if far_splice_term is None:
            return {"origin": origin_front_port, "destination": egress_fp, "path": path, "is_complete": True}

        next_fp = FrontPort.objects.get(pk=far_splice_term.termination_id)

        splice_entry = SplicePlanEntry.objects.filter(
            Q(fiber_a=egress_fp, fiber_b=next_fp) | Q(fiber_a=next_fp, fiber_b=egress_fp)
        ).first()

        if splice_entry:
            path.append({"type": "splice_entry", "id": splice_entry.pk})

        current_fp = next_fp

    return {"origin": origin_front_port, "destination": None, "path": path, "is_complete": False}
