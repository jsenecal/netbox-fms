from typing import Annotated

import strawberry
import strawberry_django
from netbox.graphql.types import NetBoxObjectType

from ..models import (
    BufferTube,
    BufferTubeTemplate,
    CableElement,
    CableElementTemplate,
    ClosureCableEntry,
    FiberCable,
    FiberCableType,
    FiberCircuit,
    FiberCircuitPath,
    FiberStrand,
    Ribbon,
    RibbonTemplate,
    SplicePlan,
    SplicePlanEntry,
    SpliceProject,
)

__all__ = (
    "FiberCableTypeType",
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
)


@strawberry_django.type(FiberCableType, fields="__all__")
class FiberCableTypeType(NetBoxObjectType):
    buffer_tube_templates: list[Annotated["BufferTubeTemplateType", strawberry.lazy(".types")]]
    ribbon_templates: list[Annotated["RibbonTemplateType", strawberry.lazy(".types")]]
    cable_element_templates: list[Annotated["CableElementTemplateType", strawberry.lazy(".types")]]
    instances: list[Annotated["FiberCableInstanceType", strawberry.lazy(".types")]]


@strawberry_django.type(BufferTubeTemplate, fields="__all__")
class BufferTubeTemplateType(NetBoxObjectType):
    ribbon_templates: list[Annotated["RibbonTemplateType", strawberry.lazy(".types")]]


@strawberry_django.type(RibbonTemplate, fields="__all__")
class RibbonTemplateType(NetBoxObjectType):
    pass


@strawberry_django.type(CableElementTemplate, fields="__all__")
class CableElementTemplateType(NetBoxObjectType):
    pass


@strawberry_django.type(FiberCable, fields="__all__")
class FiberCableInstanceType(NetBoxObjectType):
    buffer_tubes: list[Annotated["BufferTubeType", strawberry.lazy(".types")]]
    ribbons: list[Annotated["RibbonType", strawberry.lazy(".types")]]
    fiber_strands: list[Annotated["FiberStrandType", strawberry.lazy(".types")]]
    cable_elements: list[Annotated["CableElementType", strawberry.lazy(".types")]]


@strawberry_django.type(BufferTube, fields="__all__")
class BufferTubeType(NetBoxObjectType):
    ribbons: list[Annotated["RibbonType", strawberry.lazy(".types")]]
    fiber_strands: list[Annotated["FiberStrandType", strawberry.lazy(".types")]]


@strawberry_django.type(Ribbon, fields="__all__")
class RibbonType(NetBoxObjectType):
    fiber_strands: list[Annotated["FiberStrandType", strawberry.lazy(".types")]]


@strawberry_django.type(FiberStrand, fields="__all__")
class FiberStrandType(NetBoxObjectType):
    pass


@strawberry_django.type(CableElement, fields="__all__")
class CableElementType(NetBoxObjectType):
    pass


@strawberry_django.type(SplicePlan, fields="__all__")
class SplicePlanType(NetBoxObjectType):
    entries: list[Annotated["SplicePlanEntryType", strawberry.lazy(".types")]]


@strawberry_django.type(SplicePlanEntry, fields="__all__")
class SplicePlanEntryType(NetBoxObjectType):
    pass


@strawberry_django.type(SpliceProject, fields="__all__")
class SpliceProjectType(NetBoxObjectType):
    pass


@strawberry_django.type(ClosureCableEntry, fields="__all__")
class ClosureCableEntryType(NetBoxObjectType):
    pass


@strawberry_django.type(FiberCircuit, fields="__all__")
class FiberCircuitType(NetBoxObjectType):
    paths: list[Annotated["FiberCircuitPathType", strawberry.lazy(".types")]]


@strawberry_django.type(FiberCircuitPath, fields="__all__")
class FiberCircuitPathType(NetBoxObjectType):
    circuit: Annotated["FiberCircuitType", strawberry.lazy(".types")]
