"""Transform flat trace path entries into semantic hop objects."""

from circuits.models import Circuit
from dcim.models import Cable, FrontPort, RearPort

from .models import FiberStrand, SplicePlanEntry


def _pk_map(queryset, ids):
    """Map pk to object for ``ids`` drawn from ``queryset``; empty when there are none."""
    if not ids:
        return {}
    return {obj.pk: obj for obj in queryset.filter(pk__in=ids)}


def build_hops(path_entries):
    """Transform flat path entries into grouped hops."""
    if not path_entries:
        return []

    # Bulk prefetch all referenced objects
    fp_ids = [e["id"] for e in path_entries if e["type"] == "front_port"]
    rp_ids = [e["id"] for e in path_entries if e["type"] == "rear_port"]
    cable_ids = [e["id"] for e in path_entries if e["type"] == "cable"]
    splice_ids = [e["id"] for e in path_entries if e["type"] == "splice_entry"]
    pc_ids = [e["id"] for e in path_entries if e["type"] == "provider_circuit"]

    fp_map = _pk_map(FrontPort.objects.select_related("device__role", "device__site"), fp_ids)
    rp_map = _pk_map(RearPort.objects.select_related("device__role", "device__site"), rp_ids)
    cable_map = _pk_map(Cable.objects.all(), cable_ids)
    splice_map = _pk_map(SplicePlanEntry.objects.select_related("plan", "tray"), splice_ids)
    pc_map = _pk_map(Circuit.objects.select_related("provider"), pc_ids)

    # Prefetch strands for all FrontPorts in path
    strand_by_fp = {}
    if fp_ids:
        strands = FiberStrand.objects.landed_on(fp_ids).select_related("fiber_cable__fiber_cable_type", "buffer_tube")
        for s in strands:
            if s.front_port_a_id:
                strand_by_fp[s.front_port_a_id] = s
            if s.front_port_b_id:
                strand_by_fp[s.front_port_b_id] = s

    hops = []
    i = 0

    while i < len(path_entries):
        entry = path_entries[i]

        if entry["type"] == "front_port":
            fp = fp_map.get(entry["id"])
            if not fp:
                i += 1
                continue
            device = fp.device

            if i + 1 < len(path_entries) and path_entries[i + 1]["type"] == "rear_port":
                rp = rp_map.get(path_entries[i + 1]["id"])

                if hops and hops[-1].get("_pending_device_id") == device.pk:
                    closure_hop = hops[-1]
                    closure_hop["egress"] = {
                        "front_port": {"id": fp.pk, "name": fp.name},
                        "rear_port": {"id": rp.pk, "name": rp.name} if rp else None,
                    }
                    del closure_hop["_pending_device_id"]
                    i += 2
                    continue

                hop = _make_device_hop(device)
                hop["ports"] = {
                    "front_port": {"id": fp.pk, "name": fp.name},
                    "rear_port": {"id": rp.pk, "name": rp.name} if rp else None,
                }
                hop["_pending_device_id"] = device.pk
                hops.append(hop)
                i += 2
            else:
                hop = _make_device_hop(device)
                hop["ports"] = {"front_port": {"id": fp.pk, "name": fp.name}}
                hops.append(hop)
                i += 1

        elif entry["type"] == "cable":
            cable = cable_map.get(entry["id"])
            prev_fp_id = _get_last_front_port_id(hops)
            strand = strand_by_fp.get(prev_fp_id)

            hop = {
                "type": "cable",
                "id": cable.pk if cable else entry["id"],
                "label": (cable.label or f"Cable #{cable.pk}") if cable else f"Cable #{entry['id']}",
            }
            if strand:
                fc = strand.fiber_cable
                fct = fc.fiber_cable_type if fc else None
                hop["fiber_type"] = cable.get_type_display() if cable else None
                hop["strand_count"] = fct.strand_count if fct else None
                hop["strand_position"] = strand.position
                hop["strand_color"] = strand.color
                hop["tube_name"] = strand.buffer_tube.name if strand.buffer_tube else None
                hop["tube_color"] = strand.buffer_tube.color if strand.buffer_tube else None
                hop["fiber_cable_id"] = fc.pk if fc else None
                hop["fiber_cable_url"] = fc.get_absolute_url() if fc else None
            hops.append(hop)
            i += 1

        elif entry["type"] == "rear_port":
            rp = rp_map.get(entry["id"])
            if not rp:
                i += 1
                continue
            device = rp.device

            if i + 1 < len(path_entries) and path_entries[i + 1]["type"] == "front_port":
                fp = fp_map.get(path_entries[i + 1]["id"])
                hop = _make_device_hop(device)
                hop["ingress"] = {
                    "rear_port": {"id": rp.pk, "name": rp.name},
                    "front_port": {"id": fp.pk, "name": fp.name} if fp else None,
                }
                hop["_pending_device_id"] = device.pk
                hops.append(hop)
                i += 2
            else:
                i += 1

        elif entry["type"] == "provider_circuit":
            circuit = pc_map.get(entry["id"])
            hops.append(
                {
                    "type": "provider_circuit",
                    "id": entry["id"],
                    "cid": circuit.cid if circuit else f"Circuit #{entry['id']}",
                    "provider": circuit.provider.name if circuit else None,
                    "url": circuit.get_absolute_url() if circuit else None,
                }
            )
            i += 1

        elif entry["type"] == "splice_entry":
            se = splice_map.get(entry["id"])
            if se:
                for h in reversed(hops):
                    if h["type"] == "device":
                        h["splice"] = {
                            "id": se.pk,
                            "plan_name": se.plan.name,
                            "tray": str(se.tray) if se.tray else None,
                            "is_express": se.is_express,
                        }
                        break
            i += 1

        else:
            i += 1

    for h in hops:
        h.pop("_pending_device_id", None)

    return hops


def _make_device_hop(device):
    """Create a device hop dict from a Device instance."""
    return {
        "type": "device",
        "id": device.pk,
        "name": device.name,
        "role": device.role.name if device.role else None,
        "site": device.site.name if device.site else None,
        "url": device.get_absolute_url(),
    }


def _get_last_front_port_id(hops):
    """Return the last FrontPort ID found in the hop list, or None."""
    for h in reversed(hops):
        if h["type"] == "device":
            if "egress" in h and h["egress"].get("front_port"):
                return h["egress"]["front_port"]["id"]
            if "ingress" in h and h["ingress"].get("front_port"):
                return h["ingress"]["front_port"]["id"]
            if "ports" in h and h["ports"].get("front_port"):
                return h["ports"]["front_port"]["id"]
    return None
