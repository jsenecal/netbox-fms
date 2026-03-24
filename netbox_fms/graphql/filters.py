"""GraphQL filter types for netbox_fms models."""

import strawberry_django

from ..models import (
    BufferTubeTemplate,
    CableElementTemplate,
    ClosureCableEntry,
    FiberCable,
    FiberCableType,
    FiberCircuit,
    FiberCircuitPath,
    RibbonTemplate,
    SlackLoop,
    SplicePlan,
    SplicePlanEntry,
    SpliceProject,
    TrayProfile,
    TubeAssignment,
)

__all__ = (
    "FiberCableTypeFilter",
    "BufferTubeTemplateFilter",
    "RibbonTemplateFilter",
    "CableElementTemplateFilter",
    "FiberCableFilter",
    "SplicePlanFilter",
    "SplicePlanEntryFilter",
    "SpliceProjectFilter",
    "ClosureCableEntryFilter",
    "FiberCircuitFilter",
    "FiberCircuitPathFilter",
    "SlackLoopFilter",
    "TrayProfileFilter",
    "TubeAssignmentFilter",
)


@strawberry_django.filters.filter(FiberCableType)
class FiberCableTypeFilter:
    """GraphQL filter for FiberCableType."""

    id: int | None
    construction: str | None
    fiber_type: str | None
    is_armored: bool | None
    deployment: str | None
    strand_count: int | None


@strawberry_django.filters.filter(BufferTubeTemplate)
class BufferTubeTemplateFilter:
    """GraphQL filter for BufferTubeTemplate."""

    id: int | None
    fiber_cable_type_id: int | None
    name: str | None


@strawberry_django.filters.filter(RibbonTemplate)
class RibbonTemplateFilter:
    """GraphQL filter for RibbonTemplate."""

    id: int | None
    fiber_cable_type_id: int | None
    buffer_tube_template_id: int | None


@strawberry_django.filters.filter(CableElementTemplate)
class CableElementTemplateFilter:
    """GraphQL filter for CableElementTemplate."""

    id: int | None
    fiber_cable_type_id: int | None
    element_type: str | None


@strawberry_django.filters.filter(FiberCable)
class FiberCableFilter:
    """GraphQL filter for FiberCable."""

    id: int | None
    fiber_cable_type_id: int | None
    cable_id: int | None
    name: str | None


@strawberry_django.filters.filter(SplicePlan)
class SplicePlanFilter:
    """GraphQL filter for SplicePlan."""

    id: int | None
    name: str | None
    status: str | None
    closure_id: int | None
    project_id: int | None


@strawberry_django.filters.filter(SplicePlanEntry)
class SplicePlanEntryFilter:
    """GraphQL filter for SplicePlanEntry."""

    id: int | None
    plan_id: int | None
    tray_id: int | None


@strawberry_django.filters.filter(SpliceProject)
class SpliceProjectFilter:
    """GraphQL filter for SpliceProject."""

    id: int | None
    name: str | None


@strawberry_django.filters.filter(ClosureCableEntry)
class ClosureCableEntryFilter:
    """GraphQL filter for ClosureCableEntry."""

    id: int | None
    closure_id: int | None
    fiber_cable_id: int | None


@strawberry_django.filters.filter(FiberCircuit)
class FiberCircuitFilter:
    """GraphQL filter for FiberCircuit."""

    id: int | None
    name: str | None
    cid: str | None
    status: str | None
    strand_count: int | None


@strawberry_django.filters.filter(FiberCircuitPath)
class FiberCircuitPathFilter:
    """GraphQL filter for FiberCircuitPath."""

    id: int | None
    circuit_id: int | None
    is_complete: bool | None


@strawberry_django.filters.filter(SlackLoop)
class SlackLoopFilter:
    """GraphQL filter for SlackLoop."""

    id: int | None
    fiber_cable_id: int | None
    site_id: int | None
    location_id: int | None
    storage_method: str | None
    length_unit: str | None


@strawberry_django.filters.filter(TrayProfile)
class TrayProfileFilter:
    """GraphQL filter for TrayProfile."""

    id: int | None
    tray_role: str | None


@strawberry_django.filters.filter(TubeAssignment)
class TubeAssignmentFilter:
    """GraphQL filter for TubeAssignment."""

    id: int | None
    closure_id: int | None
    tray_id: int | None
