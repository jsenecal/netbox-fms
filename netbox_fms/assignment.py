"""Assigning analyzed fiber paths to circuits.

"Assign" is the verb everywhere: a circuit assigns paths, unassigns by
deleting the assignment row, and acknowledges a route that changed under
it. The writers here are the only entry points the wizard, the circuit
action and the API share.
"""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction

from .choices import FiberCircuitStatusChoices, PathCompletenessChoices
from .models import FiberCircuit, FiberCircuitPath, RouteChangeAuthorization, hops_snapshot
from .path_analysis import sync_circuit_broken


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


def authorize_route_change(circuit, source):
    """Record that an approved change (``source``) may re-route the circuit without breaking it."""
    return RouteChangeAuthorization.objects.create(
        circuit=circuit, source_type=ContentType.objects.get_for_model(source), source_id=source.pk
    )
