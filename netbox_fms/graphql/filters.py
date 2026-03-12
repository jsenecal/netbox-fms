import strawberry_django

from ..models import (
    BufferTubeTemplate,
    CableElementTemplate,
    FiberCable,
    FiberCableType,
    FiberPathLoss,
    RibbonTemplate,
    SplicePlan,
    SplicePlanEntry,
)

__all__ = (
    "FiberCableTypeFilter",
    "BufferTubeTemplateFilter",
    "RibbonTemplateFilter",
    "CableElementTemplateFilter",
    "FiberCableFilter",
    "SplicePlanFilter",
    "SplicePlanEntryFilter",
    "FiberPathLossFilter",
)


@strawberry_django.filters.filter(FiberCableType)
class FiberCableTypeFilter:
    id: int | None
    construction: str | None
    fiber_type: str | None
    is_armored: bool | None
    deployment: str | None


@strawberry_django.filters.filter(BufferTubeTemplate)
class BufferTubeTemplateFilter:
    id: int | None


@strawberry_django.filters.filter(RibbonTemplate)
class RibbonTemplateFilter:
    id: int | None


@strawberry_django.filters.filter(CableElementTemplate)
class CableElementTemplateFilter:
    id: int | None


@strawberry_django.filters.filter(FiberCable)
class FiberCableFilter:
    id: int | None


@strawberry_django.filters.filter(SplicePlan)
class SplicePlanFilter:
    id: int | None
    name: str | None
    status: str | None


@strawberry_django.filters.filter(SplicePlanEntry)
class SplicePlanEntryFilter:
    id: int | None


@strawberry_django.filters.filter(FiberPathLoss)
class FiberPathLossFilter:
    id: int | None
    wavelength_nm: int | None
