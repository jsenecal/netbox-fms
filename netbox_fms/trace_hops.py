"""Transform flat trace path entries into semantic hop objects."""

from circuits.models import Circuit
from dcim.models import Cable, FrontPort, PortMapping, RearPort
from django.db.models import Q

from .models import FiberStrand, SplicePlanEntry


def _pk_map(queryset, ids):
    """Map pk to object for ``ids`` drawn from ``queryset``; empty when there are none."""
    if not ids:
        return {}
    return {obj.pk: obj for obj in queryset.filter(pk__in=ids)}


def flat_entries(strand_path):
    """Flat trace entries (what build_hops consumes) for a stored fiber path, read from end A.

    A strand hop expands to front port, rear port, cable, rear port, front
    port through the strand's landings and their port mappings, and a splice
    plan entry joining two consecutive strands is recorded between them.
    Plain-cable and provider-circuit hops stay single entries.
    """
    hops = list(strand_path.hops.select_related("strand__fiber_cable"))
    strands = [hop.strand for hop in hops if hop.strand_id is not None]
    fp_ids = {fp for strand in strands for fp in _landings(strand) if fp is not None}
    end_ids = {fp for fp in (strand_path.end_a_port_id, strand_path.end_b_port_id) if fp is not None}
    rear_of = dict(PortMapping.objects.filter(front_port_id__in=fp_ids).values_list("front_port_id", "rear_port_id"))
    device_of = dict(FrontPort.objects.filter(pk__in=fp_ids | end_ids).values_list("pk", "device_id"))
    splices = {
        frozenset((fiber_a, fiber_b)): pk
        for pk, fiber_a, fiber_b in SplicePlanEntry.objects.filter(
            Q(fiber_a_id__in=fp_ids) | Q(fiber_b_id__in=fp_ids)
        ).values_list("pk", "fiber_a_id", "fiber_b_id")
    }
    # The devices the walk reaches after each strand: the next strand's
    # landings, or the B end after the last one. Orients a strand that a
    # plain-cable or provider hop separates from the previous landing.
    ahead = [{device_of.get(strand_path.end_b_port_id)}]
    for strand in reversed(strands[1:]):
        ahead.append({device_of.get(fp) for fp in _landings(strand)})
    ahead.reverse()
    entries, previous_exit = [], strand_path.end_a_port_id
    for hop in hops:
        if hop.strand_id is None:
            kind, ref_id = hop.ref
            entries.append({"type": kind, "id": ref_id})
            continue
        entry_fp, exit_fp = _orient_strand(hop.strand, previous_exit, ahead.pop(0), device_of)
        splice = splices.get(frozenset((previous_exit, entry_fp)))
        if splice is not None:
            entries.append({"type": "splice_entry", "id": splice})
        _append_port(entries, entry_fp, rear_of)
        entries.append({"type": "cable", "id": hop.strand.fiber_cable.cable_id})
        _append_port(entries, exit_fp, rear_of, rear_first=True)
        previous_exit = exit_fp
    return entries


def _landings(strand):
    return (strand.front_port_a_id, strand.front_port_b_id)


def _orient_strand(strand, previous_exit, ahead, device_of):
    """(entry, exit) landings of a strand hop.

    The entry is the landing on the device the walk is on (the previous
    exit's device). When neither landing is there -- a plain cable or a
    provider circuit lies between -- the exit is the landing on a device
    the walk reaches next (``ahead``: the next strand's devices, or the B
    end's). Half-landed strands fall back to A then B.
    """
    fp_a, fp_b = _landings(strand)
    if previous_exit is not None:
        here = device_of.get(previous_exit)
        if fp_b is not None and (fp_b == previous_exit or device_of.get(fp_b) == here):
            return fp_b, fp_a
        if fp_a is not None and (fp_a == previous_exit or device_of.get(fp_a) == here):
            return fp_a, fp_b
    if fp_a is not None and device_of.get(fp_a) in ahead:
        return fp_b, fp_a
    return fp_a, fp_b


def _append_port(entries, fp_id, rear_of, *, rear_first=False):
    """Front port then its rear port (or the reverse) when the strand lands on a port."""
    if fp_id is None:
        return
    port_entries = [{"type": "front_port", "id": fp_id}]
    rp_id = rear_of.get(fp_id)
    if rp_id is not None:
        port_entries.append({"type": "rear_port", "id": rp_id})
    entries.extend(reversed(port_entries) if rear_first else port_entries)


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
