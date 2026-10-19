"""GraphQL object types for netbox_fms models."""

from decimal import Decimal
from typing import Annotated

import strawberry
import strawberry_django
from netbox.graphql.scalars import BigInt
from netbox.graphql.types import BaseObjectType, NetBoxObjectType

from ..models import (
    BufferTube,
    BufferTubeTemplate,
    CableElement,
    CableElementTemplate,
    ClosureCableEntry,
    FiberAttenuationSpec,
    FiberCable,
    FiberCableType,
    FiberCircuit,
    FiberCircuitPath,
    FiberStrand,
    FiberStrandPath,
    FiberStrandPathHop,
    Ribbon,
    RibbonTemplate,
    SlackLoop,
    SplicePlan,
    SplicePlanEntry,
    SpliceProject,
    TrayProfile,
    TubeAssignment,
)
from .filters import (
    BufferTubeFilter,
    BufferTubeTemplateFilter,
    CableElementFilter,
    CableElementTemplateFilter,
    ClosureCableEntryFilter,
    FiberAttenuationSpecFilter,
    FiberCableFilter,
    FiberCableTypeFilter,
    FiberCircuitFilter,
    FiberCircuitPathFilter,
    FiberStrandFilter,
    FiberStrandPathFilter,
    RibbonFilter,
    RibbonTemplateFilter,
    SlackLoopFilter,
    SplicePlanEntryFilter,
    SplicePlanFilter,
    SpliceProjectFilter,
    TrayProfileFilter,
    TubeAssignmentFilter,
)

__all__ = (
    "FiberCableTypeType",
    "FiberAttenuationSpecType",
    "BufferTubeTemplateType",
    "RibbonTemplateType",
    "CableElementTemplateType",
    "FiberCableInstanceType",
    "BufferTubeType",
    "RibbonType",
    "FiberStrandType",
    "CableElementType",
    "SplicePlanType",
    "SplicePlanEntryType",
    "SpliceProjectType",
    "ClosureCableEntryType",
    "FiberCircuitType",
    "FiberCircuitPathType",
    "FiberStrandPathType",
    "FiberStrandPathHopType",
    "SlackLoopType",
    "TrayProfileType",
    "TubeAssignmentType",
)


@strawberry_django.type(FiberCableType, fields="__all__", filters=FiberCableTypeFilter)
class FiberCableTypeType(NetBoxObjectType):
    """GraphQL type for FiberCableType."""

    jacket_color: str
    strand_marker_color: str
    buffer_tube_template_count: BigInt
    ribbon_template_count: BigInt
    cable_element_template_count: BigInt

    buffer_tube_templates: list[Annotated["BufferTubeTemplateType", strawberry.lazy(".types")]]
    ribbon_templates: list[Annotated["RibbonTemplateType", strawberry.lazy(".types")]]
    cable_element_templates: list[Annotated["CableElementTemplateType", strawberry.lazy(".types")]]
    attenuation_specs: list[Annotated["FiberAttenuationSpecType", strawberry.lazy(".types")]]
    instances: list[Annotated["FiberCableInstanceType", strawberry.lazy(".types")]]


@strawberry_django.type(FiberAttenuationSpec, fields="__all__", filters=FiberAttenuationSpecFilter)
class FiberAttenuationSpecType(NetBoxObjectType):
    """GraphQL type for FiberAttenuationSpec."""


@strawberry_django.type(BufferTubeTemplate, fields="__all__", filters=BufferTubeTemplateFilter)
class BufferTubeTemplateType(NetBoxObjectType):
    """GraphQL type for BufferTubeTemplate."""

    color: str
    marker_color: str
    strand_marker_color: str

    ribbon_templates: list[Annotated["RibbonTemplateType", strawberry.lazy(".types")]]


@strawberry_django.type(RibbonTemplate, fields="__all__", filters=RibbonTemplateFilter)
class RibbonTemplateType(NetBoxObjectType):
    """GraphQL type for RibbonTemplate."""

    color: str
    marker_color: str
    strand_marker_color: str


@strawberry_django.type(CableElementTemplate, fields="__all__", filters=CableElementTemplateFilter)
class CableElementTemplateType(NetBoxObjectType):
    """GraphQL type for CableElementTemplate."""


@strawberry_django.type(FiberCable, fields="__all__", filters=FiberCableFilter)
class FiberCableInstanceType(NetBoxObjectType):
    """GraphQL type for FiberCable."""

    buffer_tubes: list[Annotated["BufferTubeType", strawberry.lazy(".types")]]
    ribbons: list[Annotated["RibbonType", strawberry.lazy(".types")]]
    fiber_strands: list[Annotated["FiberStrandType", strawberry.lazy(".types")]]
    cable_elements: list[Annotated["CableElementType", strawberry.lazy(".types")]]

    @strawberry_django.field
    def glass_length(self) -> Decimal | None:
        """Optical-fibre length, derived from sheath length and the cable type's twist factor."""
        return self.glass_length


@strawberry_django.type(BufferTube, fields="__all__", filters=BufferTubeFilter)
class BufferTubeType(NetBoxObjectType):
    """GraphQL type for BufferTube."""

    color: str
    marker_color: str

    ribbons: list[Annotated["RibbonType", strawberry.lazy(".types")]]
    fiber_strands: list[Annotated["FiberStrandType", strawberry.lazy(".types")]]


@strawberry_django.type(Ribbon, fields="__all__", filters=RibbonFilter)
class RibbonType(NetBoxObjectType):
    """GraphQL type for Ribbon."""

    color: str
    marker_color: str

    fiber_strands: list[Annotated["FiberStrandType", strawberry.lazy(".types")]]


@strawberry_django.type(FiberStrand, fields="__all__", filters=FiberStrandFilter)
class FiberStrandType(NetBoxObjectType):
    """GraphQL type for FiberStrand."""

    color: str
    marker_color: str


@strawberry_django.type(CableElement, fields="__all__", filters=CableElementFilter)
class CableElementType(NetBoxObjectType):
    """GraphQL type for CableElement."""


@strawberry_django.type(SplicePlan, fields="__all__", filters=SplicePlanFilter)
class SplicePlanType(NetBoxObjectType):
    """GraphQL type for SplicePlan."""

    entries: list[Annotated["SplicePlanEntryType", strawberry.lazy(".types")]]


@strawberry_django.type(SplicePlanEntry, fields="__all__", filters=SplicePlanEntryFilter)
class SplicePlanEntryType(NetBoxObjectType):
    """GraphQL type for SplicePlanEntry."""


@strawberry_django.type(SpliceProject, fields="__all__", filters=SpliceProjectFilter)
class SpliceProjectType(NetBoxObjectType):
    """GraphQL type for SpliceProject."""


@strawberry_django.type(ClosureCableEntry, fields="__all__", filters=ClosureCableEntryFilter)
class ClosureCableEntryType(NetBoxObjectType):
    """GraphQL type for ClosureCableEntry."""


@strawberry_django.type(FiberCircuit, fields="__all__", filters=FiberCircuitFilter)
class FiberCircuitType(NetBoxObjectType):
    """GraphQL type for FiberCircuit."""

    paths: list[Annotated["FiberCircuitPathType", strawberry.lazy(".types")]]


@strawberry_django.type(FiberCircuitPath, fields="__all__", filters=FiberCircuitPathFilter)
class FiberCircuitPathType(NetBoxObjectType):
    """GraphQL type for FiberCircuitPath."""

    circuit: Annotated["FiberCircuitType", strawberry.lazy(".types")]
    strand_path: Annotated["FiberStrandPathType", strawberry.lazy(".types")]


@strawberry_django.type(FiberStrandPathHop, fields="__all__")
class FiberStrandPathHopType(BaseObjectType):
    """GraphQL type for one hop of an analyzed fiber path."""


@strawberry_django.type(FiberStrandPath, fields="__all__", filters=FiberStrandPathFilter)
class FiberStrandPathType(BaseObjectType):
    """GraphQL type for an analyzed fiber path (read-only)."""

    hops: list[Annotated["FiberStrandPathHopType", strawberry.lazy(".types")]]
    assignments: list[Annotated["FiberCircuitPathType", strawberry.lazy(".types")]]


@strawberry_django.type(SlackLoop, fields="__all__", filters=SlackLoopFilter)
class SlackLoopType(NetBoxObjectType):
    """GraphQL type for SlackLoop."""


@strawberry_django.type(TrayProfile, fields="__all__", filters=TrayProfileFilter)
class TrayProfileType(NetBoxObjectType):
    """GraphQL type for TrayProfile."""

    module_type: Annotated["ModuleTypeType", strawberry.lazy("dcim.graphql.types")] | None  # noqa: F821


@strawberry_django.type(TubeAssignment, fields="__all__", filters=TubeAssignmentFilter)
class TubeAssignmentType(NetBoxObjectType):
    """GraphQL type for TubeAssignment."""

    closure: Annotated["DeviceType", strawberry.lazy("dcim.graphql.types")] | None  # noqa: F821
    tray: Annotated["ModuleType", strawberry.lazy("dcim.graphql.types")] | None  # noqa: F821
    buffer_tube: Annotated["BufferTubeType", strawberry.lazy(".types")] | None
