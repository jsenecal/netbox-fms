"""GraphQL schema definition for netbox_fms plugin."""

import strawberry
import strawberry_django

from .types import (
    BufferTubeTemplateType,
    BufferTubeType,
    CableElementTemplateType,
    CableElementType,
    ClosureCableEntryType,
    FiberCableInstanceType,
    FiberCableTypeType,
    FiberCircuitPathType,
    FiberCircuitType,
    FiberStrandType,
    RibbonTemplateType,
    RibbonType,
    SlackLoopType,
    SplicePlanEntryType,
    SplicePlanType,
    SpliceProjectType,
    WavelengthChannelType,
    WavelengthServiceType,
    WdmChannelTemplateType,
    WdmDeviceTypeProfileType,
    WdmNodeInstanceType,
    WdmTrunkPortType,
)


@strawberry.type(name="Query")
class NetBoxFMSQuery:
    """Root GraphQL query type exposing all netbox_fms models."""

    fiber_cable_type: FiberCableTypeType = strawberry_django.field()
    fiber_cable_type_list: list[FiberCableTypeType] = strawberry_django.field()

    buffer_tube_template: BufferTubeTemplateType = strawberry_django.field()
    buffer_tube_template_list: list[BufferTubeTemplateType] = strawberry_django.field()

    ribbon_template: RibbonTemplateType = strawberry_django.field()
    ribbon_template_list: list[RibbonTemplateType] = strawberry_django.field()

    cable_element_template: CableElementTemplateType = strawberry_django.field()
    cable_element_template_list: list[CableElementTemplateType] = strawberry_django.field()

    fiber_cable: FiberCableInstanceType = strawberry_django.field()
    fiber_cable_list: list[FiberCableInstanceType] = strawberry_django.field()

    buffer_tube: BufferTubeType = strawberry_django.field()
    buffer_tube_list: list[BufferTubeType] = strawberry_django.field()

    ribbon: RibbonType = strawberry_django.field()
    ribbon_list: list[RibbonType] = strawberry_django.field()

    fiber_strand: FiberStrandType = strawberry_django.field()
    fiber_strand_list: list[FiberStrandType] = strawberry_django.field()

    cable_element: CableElementType = strawberry_django.field()
    cable_element_list: list[CableElementType] = strawberry_django.field()

    splice_plan: SplicePlanType = strawberry_django.field()
    splice_plan_list: list[SplicePlanType] = strawberry_django.field()

    splice_plan_entry: SplicePlanEntryType = strawberry_django.field()
    splice_plan_entry_list: list[SplicePlanEntryType] = strawberry_django.field()

    splice_project: SpliceProjectType = strawberry_django.field()
    splice_project_list: list[SpliceProjectType] = strawberry_django.field()

    closure_cable_entry: ClosureCableEntryType = strawberry_django.field()
    closure_cable_entry_list: list[ClosureCableEntryType] = strawberry_django.field()

    fiber_circuit: FiberCircuitType = strawberry_django.field()
    fiber_circuit_list: list[FiberCircuitType] = strawberry_django.field()

    fiber_circuit_path: FiberCircuitPathType = strawberry_django.field()
    fiber_circuit_path_list: list[FiberCircuitPathType] = strawberry_django.field()

    slack_loop: SlackLoopType = strawberry_django.field()
    slack_loop_list: list[SlackLoopType] = strawberry_django.field()

    wdm_device_type_profile: WdmDeviceTypeProfileType = strawberry_django.field()
    wdm_device_type_profile_list: list[WdmDeviceTypeProfileType] = strawberry_django.field()

    wdm_channel_template: WdmChannelTemplateType = strawberry_django.field()
    wdm_channel_template_list: list[WdmChannelTemplateType] = strawberry_django.field()

    wdm_node: WdmNodeInstanceType = strawberry_django.field()
    wdm_node_list: list[WdmNodeInstanceType] = strawberry_django.field()

    wdm_trunk_port: WdmTrunkPortType = strawberry_django.field()
    wdm_trunk_port_list: list[WdmTrunkPortType] = strawberry_django.field()

    wavelength_channel: WavelengthChannelType = strawberry_django.field()
    wavelength_channel_list: list[WavelengthChannelType] = strawberry_django.field()

    wavelength_service: WavelengthServiceType = strawberry_django.field()
    wavelength_service_list: list[WavelengthServiceType] = strawberry_django.field()


schema = [NetBoxFMSQuery]
