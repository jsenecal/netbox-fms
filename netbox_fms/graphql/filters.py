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
    SplicePlan,
    SplicePlanEntry,
    SpliceProject,
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
)


@strawberry_django.filters.filter(FiberCableType)
class FiberCableTypeFilter:
    id: int | None
    construction: str | None
    fiber_type: str | None
    is_armored: bool | None
    deployment: str | None
    strand_count: int | None


@strawberry_django.filters.filter(BufferTubeTemplate)
class BufferTubeTemplateFilter:
    id: int | None
    fiber_cable_type_id: int | None
    name: str | None


@strawberry_django.filters.filter(RibbonTemplate)
class RibbonTemplateFilter:
    id: int | None
    fiber_cable_type_id: int | None
    buffer_tube_template_id: int | None


@strawberry_django.filters.filter(CableElementTemplate)
class CableElementTemplateFilter:
    id: int | None
    fiber_cable_type_id: int | None
    element_type: str | None


@strawberry_django.filters.filter(FiberCable)
class FiberCableFilter:
    id: int | None
    fiber_cable_type_id: int | None
    cable_id: int | None
    name: str | None


@strawberry_django.filters.filter(SplicePlan)
class SplicePlanFilter:
    id: int | None
    name: str | None
    status: str | None
    closure_id: int | None
    project_id: int | None


@strawberry_django.filters.filter(SplicePlanEntry)
class SplicePlanEntryFilter:
    id: int | None
    plan_id: int | None
    tray_id: int | None


@strawberry_django.filters.filter(SpliceProject)
class SpliceProjectFilter:
    id: int | None
    name: str | None


@strawberry_django.filters.filter(ClosureCableEntry)
class ClosureCableEntryFilter:
    id: int | None
    closure_id: int | None
    fiber_cable_id: int | None


@strawberry_django.filters.filter(FiberCircuit)
class FiberCircuitFilter:
    id: int | None
    name: str | None
    cid: str | None
    status: str | None
    strand_count: int | None


@strawberry_django.filters.filter(FiberCircuitPath)
class FiberCircuitPathFilter:
    id: int | None
    circuit_id: int | None
    is_complete: bool | None
