"""Assigning analyzed fiber paths to circuits.

"Assign" is the verb everywhere: a circuit assigns paths, unassigns by
deleting the assignment row, and acknowledges a route that changed under
it. The writers here are the only entry points the wizard, the circuit
action and the API share.
"""

from __future__ import annotations

from dataclasses import dataclass

from dcim.models import Cable, Device, PortMapping
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .choices import FiberCircuitStatusChoices, PathCompletenessChoices
from .models import FiberCircuit, FiberCircuitPath, FiberStrandPath, RouteChangeAuthorization, hops_snapshot
from .path_analysis import sync_circuit_broken
from .provisioning import _is_contiguous


def _assignment_errors(circuit, paths, allow_incomplete):
    errors = []
    if circuit.status == FiberCircuitStatusChoices.DECOMMISSIONED:
        errors.append("Cannot assign fiber paths to a decommissioned circuit.")
    pks = [path.pk for path in paths]
    if len(set(pks)) != len(pks):
        errors.append("A fiber path is listed more than once.")
    active = circuit.paths.filter(active=True).count()
    if active + len(paths) > circuit.strand_count:
        errors.append(
            f"Assigning {len(paths)} path(s) would exceed the circuit's strand count ({circuit.strand_count}); "
            f"{active} already assigned."
        )
    taken = set(
        FiberCircuitPath.objects.filter(strand_path_id__in=pks, active=True).values_list("strand_path_id", flat=True)
    )
    for path in paths:
        if path.pk in taken:
            errors.append(f"{path} is already assigned to a circuit.")
        if path.completeness != PathCompletenessChoices.TERMINATED_TERMINATED and not allow_incomplete:
            errors.append(f"{path} is not terminated at both ends; allow incomplete paths to assign it.")
    return errors


def assign_paths(circuit, strand_paths, *, allow_incomplete=False):
    """Assign these analyzed paths to the circuit in one transaction; returns the new assignments.

    Refused as a whole, with a ValidationError naming every problem, when
    the circuit is decommissioned, a path is listed twice, the strand count
    would be exceeded, a path already has an active assignment, or a path
    is incomplete without ``allow_incomplete``.
    """
    paths = list(strand_paths)
    with transaction.atomic():
        circuit = FiberCircuit.objects.select_for_update().get(pk=circuit.pk)
        errors = _assignment_errors(circuit, paths, allow_incomplete)
        if errors:
            raise ValidationError(errors)
        last = circuit.paths.order_by("-position").values_list("position", flat=True).first() or 0
        assignments = []
        for offset, path in enumerate(paths, start=1):
            assignment = FiberCircuitPath(
                circuit=circuit,
                strand_path=path,
                position=last + offset,
                assigned_hops=hops_snapshot(path),
                delivered_incomplete=path.completeness != PathCompletenessChoices.TERMINATED_TERMINATED,
            )
            assignment.save()
            assignments.append(assignment)
        circuit.sync_provider_circuits()
    return assignments


def acknowledge_route(circuit):
    """Accept the current hops of every broken assignment of the circuit; returns how many were broken."""
    with transaction.atomic():
        broken = list(circuit.paths.filter(active=True, is_broken=True).select_related("strand_path"))
        for assignment in broken:
            assignment.snapshot()
            assignment.assigned_hops = hops_snapshot(assignment.strand_path)
            assignment.is_broken, assignment.broken_reason = False, ""
            assignment.save()
        sync_circuit_broken(circuit)
    return len(broken)


def visible_paths(user, ids):
    """The fiber paths with these ids, in order, through the user's view permission.

    Refused as a whole when any id is unknown or hidden from the user, so a
    selection is never silently narrowed.
    """
    by_pk = FiberStrandPath.objects.restrict(user, "view").in_bulk(ids)
    if len(by_pk) != len(set(ids)):
        raise ValidationError("Unknown fiber path id(s).")
    return [by_pk[pk] for pk in ids]


def require_assign_permission(user):
    if not user.has_perm("netbox_fms.add_fibercircuitpath"):
        raise PermissionDenied("Assigning fiber paths requires add_fibercircuitpath.")


def require_acknowledge_permission(user):
    if not user.has_perm("netbox_fms.change_fibercircuitpath"):
        raise PermissionDenied("Acknowledging a route requires change_fibercircuitpath.")


def assign_paths_for(user, circuit, strand_paths, *, allow_incomplete=False):
    """assign_paths for a user: needs add on assignments, and the rows written must satisfy its constraints.

    The model-level permission check ignores object constraints, so the rows
    just written are re-read through the user's restricted queryset; a
    shortfall raises PermissionDenied and the whole transaction rolls back.
    The caller has already resolved the circuit through its change permission.
    """
    require_assign_permission(user)
    with transaction.atomic():
        assignments = assign_paths(circuit, strand_paths, allow_incomplete=allow_incomplete)
        allowed = FiberCircuitPath.objects.restrict(user, "add").filter(pk__in=[a.pk for a in assignments])
        if allowed.count() != len(assignments):
            raise PermissionDenied("These assignments are outside your add permission on fiber circuit paths.")
    return assignments


def acknowledge_route_for(user, circuit):
    """acknowledge_route for a user: needs change on assignments, including on every broken one."""
    require_acknowledge_permission(user)
    affected = circuit.paths.filter(active=True, is_broken=True)
    permitted = FiberCircuitPath.objects.restrict(user, "change").filter(pk__in=affected.values("pk"))
    if permitted.count() != affected.count():
        raise PermissionDenied("These assignments are outside your change permission on fiber circuit paths.")
    return acknowledge_route(circuit)


def authorize_route_change(circuit, source):
    """Record that an approved change (``source``) may re-route the circuit without breaking it."""
    return RouteChangeAuthorization.objects.create(
        circuit=circuit, source_type=ContentType.objects.get_for_model(source), source_id=source.pk
    )


@dataclass
class PathGroup:
    """``strand_count`` assignable paths sharing one route, with the ranking facts."""

    route_key: str
    paths: list[FiberStrandPath]
    is_contiguous: bool
    hop_count: int
    lowest_position: int

    @property
    def path_ids(self):
        return [path.pk for path in self.paths]


def _as_ids(objects):
    return {obj if isinstance(obj, int) else obj.pk for obj in objects}


def _candidate_paths(circuit_status, allow_incomplete):
    queryset = FiberStrandPath.objects.filter(is_defective=False).exclude(assignments__active=True)
    if not allow_incomplete:
        queryset = queryset.filter(completeness=PathCompletenessChoices.TERMINATED_TERMINATED)
    if circuit_status != FiberCircuitStatusChoices.PLANNED:
        queryset = queryset.filter(is_proposed=False)
    return list(
        queryset.select_related("end_a_port", "end_b_port").prefetch_related(
            "hops__strand__front_port_a",
            "hops__strand__front_port_b",
            "hops__strand__fiber_cable",
            "hops__cable__terminations",
        )
    )


def _device_sequence(path):
    """The devices a path visits from end A to end B, consecutive duplicates collapsed."""
    devices = [path.end_a_port.device_id] if path.end_a_port_id else []
    previous = devices[-1] if devices else None
    for hop in path.hops.all():
        if hop.strand_id:
            ends = [fp.device_id for fp in (hop.strand.front_port_a, hop.strand.front_port_b) if fp is not None]
        elif hop.cable_id:
            ends = [term._device_id for term in hop.cable.terminations.all() if term._device_id is not None]
        else:
            continue
        if len(ends) == 2 and ends[1] == previous:
            ends.reverse()
        for device_id in ends:
            if not devices or devices[-1] != device_id:
                devices.append(device_id)
        if devices:
            previous = devices[-1]
    if path.end_b_port_id and (not devices or devices[-1] != path.end_b_port.device_id):
        devices.append(path.end_b_port.device_id)
    return devices


def _cable_ids(path):
    return {
        hop.strand.fiber_cable.cable_id if hop.strand_id else hop.cable_id
        for hop in path.hops.all()
        if not hop.provider_circuit_id
    }


def _is_subsequence(wanted, sequence):
    position = 0
    for device_id in sequence:
        if position < len(wanted) and device_id == wanted[position]:
            position += 1
    return position == len(wanted)


def _passes_filters(
    path,
    devices,
    *,
    must_pass_through,
    avoid_devices,
    avoid_cables,
    avoid_sites,
    avoid_tenants,
    ends_at,
    site_of,
    tenant_of_device,
    tenant_of_cable,
):
    cables = _cable_ids(path)
    if avoid_devices & set(devices) or avoid_cables & cables:
        return False
    if avoid_sites & {site_of.get(d) for d in devices}:
        return False
    if avoid_tenants & ({tenant_of_device.get(d) for d in devices} | {tenant_of_cable.get(c) for c in cables}):
        return False
    if ends_at and not ends_at <= {
        path.end_a_port.device_id if path.end_a_port_id else None,
        path.end_b_port.device_id if path.end_b_port_id else None,
    }:
        return False
    return _is_subsequence(must_pass_through, devices)


def _first_strand_position(path):
    return next((hop.strand.position for hop in path.hops.all() if hop.strand_id), 0)


def _group_is_contiguous(paths, mapping_of):
    """Adjacent positions of one rear port at every strand hop of the route (the wizard's rule, per cable)."""
    # Paths sharing a route key cross the same cables, but one may cross a cable as a plain-cable hop with no
    # landed strand; only paths whose strand hops sit at the same hop positions can be compared per cable.
    shapes = {tuple(bool(hop.strand_id) for hop in path.hops.all()) for path in paths}
    if len(shapes) != 1:
        return False
    strands_per_path = [[hop.strand for hop in path.hops.all() if hop.strand_id] for path in paths]
    if not strands_per_path[0]:
        return False
    for index in range(len(strands_per_path[0])):
        records = []
        for strands in strands_per_path:
            mapping = mapping_of.get(strands[index].front_port_a_id)
            if mapping is None:
                return False
            records.append({"entry_rp_id": mapping[0], "position": mapping[1]})
        if not _is_contiguous(records):
            return False
    return True


def find_assignable_path_groups(
    strand_count,
    *,
    circuit_status,
    allow_incomplete=False,
    must_pass_through=(),
    avoid_devices=(),
    avoid_cables=(),
    avoid_sites=(),
    avoid_tenants=(),
    ends_at=None,
):
    """Groups of ``strand_count`` assignable paths sharing one route, best first.

    Assignable: no active assignment, not defective, terminated at both ends
    unless ``allow_incomplete``, and not proposed unless the circuit is
    planned. ``must_pass_through`` is an ordered device list the route must
    visit in that order; each ``avoid_*`` drops paths touching those
    objects; ``ends_at`` (a device or devices) must each hold an end.
    Ranking: contiguity (adjacent positions in one tube on every cable),
    then hop count, then lowest strand position -- the wizard's order.
    """
    candidates = _candidate_paths(circuit_status, allow_incomplete)
    sequences = {path.pk: _device_sequence(path) for path in candidates}
    device_ids = {d for seq in sequences.values() for d in seq}
    cable_ids = {c for path in candidates for c in _cable_ids(path)}
    site_of, tenant_of_device = {}, {}
    for pk, site_id, tenant_id in Device.objects.filter(pk__in=device_ids).values_list("pk", "site_id", "tenant_id"):
        site_of[pk], tenant_of_device[pk] = site_id, tenant_id
    tenant_of_cable = dict(Cable.objects.filter(pk__in=cable_ids).values_list("pk", "tenant_id"))
    if ends_at is None:
        ends = set()
    elif isinstance(ends_at, (Device, int)):
        ends = _as_ids([ends_at])
    else:
        ends = _as_ids(ends_at)
    filters = {
        "must_pass_through": [d if isinstance(d, int) else d.pk for d in must_pass_through],
        "avoid_devices": _as_ids(avoid_devices),
        "avoid_cables": _as_ids(avoid_cables),
        "avoid_sites": _as_ids(avoid_sites),
        "avoid_tenants": _as_ids(avoid_tenants),
        "ends_at": ends,
        "site_of": site_of,
        "tenant_of_device": tenant_of_device,
        "tenant_of_cable": tenant_of_cable,
    }
    by_route = {}
    for path in candidates:
        if _passes_filters(path, sequences[path.pk], **filters):
            by_route.setdefault(path.route_key, []).append(path)

    first_fps = {
        hop.strand.front_port_a_id
        for paths in by_route.values()
        for p in paths
        for hop in p.hops.all()
        if hop.strand_id
    }
    mapping_of = {
        fp: (rp, position)
        for fp, rp, position in PortMapping.objects.filter(front_port_id__in=first_fps).values_list(
            "front_port_id", "rear_port_id", "rear_port_position"
        )
    }
    groups = []
    for route_key, paths in by_route.items():
        paths.sort(key=lambda p: (_first_strand_position(p), p.pk))
        for start in range(len(paths) - strand_count + 1):
            window = paths[start : start + strand_count]
            groups.append(
                PathGroup(
                    route_key=route_key,
                    paths=window,
                    is_contiguous=_group_is_contiguous(window, mapping_of),
                    hop_count=len(window[0].hop_refs()),
                    lowest_position=_first_strand_position(window[0]),
                )
            )
    groups.sort(key=lambda g: (not g.is_contiguous, g.hop_count, g.lowest_position))
    return groups


def viewable_groups(groups, user):
    """The picker groups whose every path the user may view; a partly hidden group cannot be assigned anyway."""
    visible = set(
        FiberStrandPath.objects.restrict(user, "view")
        .filter(pk__in=[pk for group in groups for pk in group.path_ids])
        .values_list("pk", flat=True)
    )
    return [group for group in groups if visible.issuperset(group.path_ids)]
