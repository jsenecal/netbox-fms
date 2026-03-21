"""GraphQL object types for netbox_fms models."""

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
    SlackLoop,
    SplicePlan,
    SplicePlanEntry,
    SpliceProject,
    WavelengthChannel,
    WavelengthService,
    WdmChannelTemplate,
    WdmDeviceTypeProfile,
    WdmNode,
    WdmTrunkPort,
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
    "SlackLoopType",
    "WdmDeviceTypeProfileType",
    "WdmChannelTemplateType",
    "WdmNodeInstanceType",
    "WdmTrunkPortType",
    "WavelengthChannelType",
    "WavelengthServiceType",
)


@strawberry_django.type(FiberCableType, fields="__all__")
class FiberCableTypeType(NetBoxObjectType):
    """GraphQL type for FiberCableType."""

    buffer_tube_templates: list[Annotated["BufferTubeTemplateType", strawberry.lazy(".types")]]
    ribbon_templates: list[Annotated["RibbonTemplateType", strawberry.lazy(".types")]]
    cable_element_templates: list[Annotated["CableElementTemplateType", strawberry.lazy(".types")]]
    instances: list[Annotated["FiberCableInstanceType", strawberry.lazy(".types")]]


@strawberry_django.type(BufferTubeTemplate, fields="__all__")
class BufferTubeTemplateType(NetBoxObjectType):
    """GraphQL type for BufferTubeTemplate."""

    ribbon_templates: list[Annotated["RibbonTemplateType", strawberry.lazy(".types")]]


@strawberry_django.type(RibbonTemplate, fields="__all__")
class RibbonTemplateType(NetBoxObjectType):
    """GraphQL type for RibbonTemplate."""


@strawberry_django.type(CableElementTemplate, fields="__all__")
class CableElementTemplateType(NetBoxObjectType):
    """GraphQL type for CableElementTemplate."""


@strawberry_django.type(FiberCable, fields="__all__")
class FiberCableInstanceType(NetBoxObjectType):
    """GraphQL type for FiberCable."""

    buffer_tubes: list[Annotated["BufferTubeType", strawberry.lazy(".types")]]
    ribbons: list[Annotated["RibbonType", strawberry.lazy(".types")]]
    fiber_strands: list[Annotated["FiberStrandType", strawberry.lazy(".types")]]
    cable_elements: list[Annotated["CableElementType", strawberry.lazy(".types")]]


@strawberry_django.type(BufferTube, fields="__all__")
class BufferTubeType(NetBoxObjectType):
    """GraphQL type for BufferTube."""

    ribbons: list[Annotated["RibbonType", strawberry.lazy(".types")]]
    fiber_strands: list[Annotated["FiberStrandType", strawberry.lazy(".types")]]


@strawberry_django.type(Ribbon, fields="__all__")
class RibbonType(NetBoxObjectType):
    """GraphQL type for Ribbon."""

    fiber_strands: list[Annotated["FiberStrandType", strawberry.lazy(".types")]]


@strawberry_django.type(FiberStrand, fields="__all__")
class FiberStrandType(NetBoxObjectType):
    """GraphQL type for FiberStrand."""


@strawberry_django.type(CableElement, fields="__all__")
class CableElementType(NetBoxObjectType):
    """GraphQL type for CableElement."""


@strawberry_django.type(SplicePlan, fields="__all__")
class SplicePlanType(NetBoxObjectType):
    """GraphQL type for SplicePlan."""

    entries: list[Annotated["SplicePlanEntryType", strawberry.lazy(".types")]]


@strawberry_django.type(SplicePlanEntry, fields="__all__")
class SplicePlanEntryType(NetBoxObjectType):
    """GraphQL type for SplicePlanEntry."""


@strawberry_django.type(SpliceProject, fields="__all__")
class SpliceProjectType(NetBoxObjectType):
    """GraphQL type for SpliceProject."""


@strawberry_django.type(ClosureCableEntry, fields="__all__")
class ClosureCableEntryType(NetBoxObjectType):
    """GraphQL type for ClosureCableEntry."""


@strawberry_django.type(FiberCircuit, fields="__all__")
class FiberCircuitType(NetBoxObjectType):
    """GraphQL type for FiberCircuit."""

    paths: list[Annotated["FiberCircuitPathType", strawberry.lazy(".types")]]


@strawberry_django.type(FiberCircuitPath, fields="__all__")
class FiberCircuitPathType(NetBoxObjectType):
    """GraphQL type for FiberCircuitPath."""

    circuit: Annotated["FiberCircuitType", strawberry.lazy(".types")]


@strawberry_django.type(SlackLoop, fields="__all__")
class SlackLoopType(NetBoxObjectType):
    """GraphQL type for SlackLoop."""


@strawberry_django.type(WdmDeviceTypeProfile, fields="__all__")
class WdmDeviceTypeProfileType(NetBoxObjectType):
    """GraphQL type for WdmDeviceTypeProfile."""

    channel_templates: list[Annotated["WdmChannelTemplateType", strawberry.lazy(".types")]]


@strawberry_django.type(WdmChannelTemplate, fields="__all__")
class WdmChannelTemplateType(NetBoxObjectType):
    """GraphQL type for WdmChannelTemplate."""


@strawberry_django.type(WdmNode, fields="__all__")
class WdmNodeInstanceType(NetBoxObjectType):
    """GraphQL type for WdmNode."""

    trunk_ports: list[Annotated["WdmTrunkPortType", strawberry.lazy(".types")]]
    channels: list[Annotated["WavelengthChannelType", strawberry.lazy(".types")]]


@strawberry_django.type(WdmTrunkPort, fields="__all__")
class WdmTrunkPortType(NetBoxObjectType):
    """GraphQL type for WdmTrunkPort."""


@strawberry_django.type(WavelengthChannel, fields="__all__")
class WavelengthChannelType(NetBoxObjectType):
    """GraphQL type for WavelengthChannel."""


@strawberry_django.type(WavelengthService, fields="__all__")
class WavelengthServiceType(NetBoxObjectType):
    """GraphQL type for WavelengthService."""
