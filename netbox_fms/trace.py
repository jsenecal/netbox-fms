"""Fiber circuit path trace engine.

Adapted from NetBox's CablePath.from_origin(), stripped of wireless/power/circuit
logic, accepting FrontPort as origin instead of requiring PathEndpoint.

IMPORTANT: NetBox 4.5+ uses the PortMapping model to link FrontPort <-> RearPort.
FrontPort has NO rear_port or rear_port_position attributes -- always query
PortMapping to traverse front-to-rear and rear-to-front.
"""

from dcim.models import CableTermination, FrontPort, PortMapping, RearPort
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from .models import SplicePlanEntry


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
    fp_ct = ContentType.objects.get_for_model(FrontPort)
    rp_ct = ContentType.objects.get_for_model(RearPort)

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
        path.append({"type": "cable", "id": cable.pk})

        far_end = "B" if cable_end == "A" else "A"
        far_term = CableTermination.objects.filter(
            cable=cable,
            cable_end=far_end,
            termination_type=rp_ct,
        ).first()

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
            egress_mapping = (
                PortMapping.objects.filter(
                    rear_port=far_rp,
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
        far_splice_end = "B" if splice_end == "A" else "A"

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
