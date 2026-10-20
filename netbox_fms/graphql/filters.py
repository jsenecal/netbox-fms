"""GraphQL filter types for netbox_fms models."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated

import strawberry
import strawberry_django
from dcim.graphql.enums import CableLengthUnitEnum
from netbox.graphql.filter_lookups import FloatLookup, IntegerLookup
from netbox.graphql.filters import BaseModelFilter, NetBoxModelFilter, PrimaryModelFilter
from strawberry.scalars import ID
from strawberry_django import BaseFilterLookup, DateFilterLookup, DatetimeFilterLookup, FilterLookup, StrFilterLookup
from tenancy.graphql.filter_mixins import TenancyFilterMixin

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
    FiberFault,
    FiberStrand,
    FiberStrandPath,
    Ribbon,
    RibbonTemplate,
    SlackLoop,
    SplicePlan,
    SplicePlanEntry,
    SpliceProject,
    TrayProfile,
    TubeAssignment,
)
from .enums import (
    ArmorTypeEnum,
    AssignmentBrokenReasonEnum,
    CableElementTypeEnum,
    ConstructionEnum,
    DeploymentEnum,
    FiberCircuitStatusEnum,
    FiberColorSchemeEnum,
    FiberFaultStatusEnum,
    MarkerTypeEnum,
    PathCompletenessEnum,
    PathEndKindEnum,
    PathEndReasonEnum,
    SheathMaterialEnum,
    SplicePlanStatusEnum,
    StorageMethodEnum,
    TrayRoleEnum,
)

__all__ = (
    "BufferTubeFilter",
    "BufferTubeTemplateFilter",
    "CableElementFilter",
    "CableElementTemplateFilter",
    "ClosureCableEntryFilter",
    "FiberAttenuationSpecFilter",
    "FiberCableFilter",
    "FiberCableTypeFilter",
    "FiberCircuitFilter",
    "FiberCircuitPathFilter",
    "FiberFaultFilter",
    "FiberStrandFilter",
    "FiberStrandPathFilter",
    "RibbonFilter",
    "RibbonTemplateFilter",
    "SlackLoopFilter",
    "SplicePlanEntryFilter",
    "SplicePlanFilter",
    "SpliceProjectFilter",
    "TrayProfileFilter",
    "TubeAssignmentFilter",
)

FILTERS = "netbox_fms.graphql.filters"
DCIM_FILTERS = "dcim.graphql.filters"


#
# Mixins
#


@dataclass
class FiberCableTypeChildFilterMixin:
    fiber_cable_type: Annotated["FiberCableTypeFilter", strawberry.lazy(FILTERS)] | None = (
        strawberry_django.filter_field()
    )
    fiber_cable_type_id: ID | None = strawberry_django.filter_field()


@dataclass
class FiberCableChildFilterMixin:
    fiber_cable: Annotated["FiberCableFilter", strawberry.lazy(FILTERS)] | None = strawberry_django.filter_field()
    fiber_cable_id: ID | None = strawberry_django.filter_field()


@dataclass
class BufferTubeChildFilterMixin:
    buffer_tube: Annotated["BufferTubeFilter", strawberry.lazy(FILTERS)] | None = strawberry_django.filter_field()
    buffer_tube_id: ID | None = strawberry_django.filter_field()


@dataclass
class MarkedComponentFilterMixin:
    """The name, position, color and marker fields shared by tubes, ribbons and strands."""

    name: StrFilterLookup | None = strawberry_django.filter_field()
    position: IntegerLookup | None = strawberry_django.filter_field()
    color: StrFilterLookup | None = strawberry_django.filter_field()
    marker_count: IntegerLookup | None = strawberry_django.filter_field()
    marker_color: StrFilterLookup | None = strawberry_django.filter_field()
    marker_type: BaseFilterLookup[MarkerTypeEnum] | None = strawberry_django.filter_field()


@dataclass
class StrandMarkingFilterMixin:
    """The strand marking fields shared by cable types and tube/ribbon templates."""

    strand_marker_interval: IntegerLookup | None = strawberry_django.filter_field()
    strand_marker_color: StrFilterLookup | None = strawberry_django.filter_field()
    strand_marker_type: BaseFilterLookup[MarkerTypeEnum] | None = strawberry_django.filter_field()


@dataclass
class MarkedTemplateFilterMixin(MarkedComponentFilterMixin, StrandMarkingFilterMixin, FiberCableTypeChildFilterMixin):
    """Tube and ribbon templates: the marked-component and strand marking fields plus fiber count."""

    fiber_count: IntegerLookup | None = strawberry_django.filter_field()
    description: StrFilterLookup | None = strawberry_django.filter_field()


@dataclass
class ClosureFilterMixin:
    closure: Annotated["DeviceFilter", strawberry.lazy(DCIM_FILTERS)] | None = strawberry_django.filter_field()  # noqa: F821
    closure_id: ID | None = strawberry_django.filter_field()


@dataclass
class TrayFilterMixin:
    tray: Annotated["ModuleFilter", strawberry.lazy(DCIM_FILTERS)] | None = strawberry_django.filter_field()  # noqa: F821
    tray_id: ID | None = strawberry_django.filter_field()


#
# Cable types and templates
#


@strawberry_django.filter_type(FiberCableType, lookups=True)
class FiberCableTypeFilter(StrandMarkingFilterMixin, NetBoxModelFilter):
    """GraphQL filter for FiberCableType."""

    manufacturer: Annotated["ManufacturerFilter", strawberry.lazy(DCIM_FILTERS)] | None = (  # noqa: F821
        strawberry_django.filter_field()
    )
    manufacturer_id: ID | None = strawberry_django.filter_field()
    model: StrFilterLookup | None = strawberry_django.filter_field()
    part_number: StrFilterLookup | None = strawberry_django.filter_field()
    construction: BaseFilterLookup[ConstructionEnum] | None = strawberry_django.filter_field()
    strand_count: IntegerLookup | None = strawberry_django.filter_field()
    color_scheme: BaseFilterLookup[FiberColorSchemeEnum] | None = strawberry_django.filter_field()
    sheath_material: BaseFilterLookup[SheathMaterialEnum] | None = strawberry_django.filter_field()
    jacket_color: StrFilterLookup | None = strawberry_django.filter_field()
    is_armored: FilterLookup[bool] | None = strawberry_django.filter_field()
    armor_type: BaseFilterLookup[ArmorTypeEnum] | None = strawberry_django.filter_field()
    deployment: BaseFilterLookup[DeploymentEnum] | None = strawberry_django.filter_field()
    fire_rating: StrFilterLookup | None = strawberry_django.filter_field()
    mark_unit: BaseFilterLookup[CableLengthUnitEnum] | None = strawberry_django.filter_field()
    outer_diameter: FloatLookup | None = strawberry_django.filter_field()
    twist_factor_ratio: FloatLookup | None = strawberry_django.filter_field()
    notes: StrFilterLookup | None = strawberry_django.filter_field()


@strawberry_django.filter_type(FiberAttenuationSpec, lookups=True)
class FiberAttenuationSpecFilter(FiberCableTypeChildFilterMixin, NetBoxModelFilter):
    """GraphQL filter for FiberAttenuationSpec."""

    wavelength_nm: IntegerLookup | None = strawberry_django.filter_field()
    max_loss_db_per_km: FloatLookup | None = strawberry_django.filter_field()


@strawberry_django.filter_type(BufferTubeTemplate, lookups=True)
class BufferTubeTemplateFilter(MarkedTemplateFilterMixin, NetBoxModelFilter):
    """GraphQL filter for BufferTubeTemplate."""


@strawberry_django.filter_type(RibbonTemplate, lookups=True)
class RibbonTemplateFilter(MarkedTemplateFilterMixin, NetBoxModelFilter):
    """GraphQL filter for RibbonTemplate."""

    buffer_tube_template: Annotated["BufferTubeTemplateFilter", strawberry.lazy(FILTERS)] | None = (
        strawberry_django.filter_field()
    )
    buffer_tube_template_id: ID | None = strawberry_django.filter_field()


@strawberry_django.filter_type(CableElementTemplate, lookups=True)
class CableElementTemplateFilter(FiberCableTypeChildFilterMixin, NetBoxModelFilter):
    """GraphQL filter for CableElementTemplate."""

    name: StrFilterLookup | None = strawberry_django.filter_field()
    element_type: BaseFilterLookup[CableElementTypeEnum] | None = strawberry_django.filter_field()
    description: StrFilterLookup | None = strawberry_django.filter_field()


#
# Cables and their components
#


@strawberry_django.filter_type(FiberCable, lookups=True)
class FiberCableFilter(FiberCableTypeChildFilterMixin, NetBoxModelFilter):
    """GraphQL filter for FiberCable."""

    cable: Annotated["CableFilter", strawberry.lazy(DCIM_FILTERS)] | None = strawberry_django.filter_field()  # noqa: F821
    cable_id: ID | None = strawberry_django.filter_field()
    serial_number: StrFilterLookup | None = strawberry_django.filter_field()
    install_date: DateFilterLookup[date] | None = strawberry_django.filter_field()
    installed_by: Annotated["TenantFilter", strawberry.lazy("tenancy.graphql.filters")] | None = (  # noqa: F821
        strawberry_django.filter_field()
    )
    installed_by_id: ID | None = strawberry_django.filter_field()
    start_mark: FloatLookup | None = strawberry_django.filter_field()
    end_mark: FloatLookup | None = strawberry_django.filter_field()
    notes: StrFilterLookup | None = strawberry_django.filter_field()


@strawberry_django.filter_type(BufferTube, lookups=True)
class BufferTubeFilter(MarkedComponentFilterMixin, FiberCableChildFilterMixin, NetBoxModelFilter):
    """GraphQL filter for BufferTube."""


@strawberry_django.filter_type(Ribbon, lookups=True)
class RibbonFilter(
    MarkedComponentFilterMixin, BufferTubeChildFilterMixin, FiberCableChildFilterMixin, NetBoxModelFilter
):
    """GraphQL filter for Ribbon."""


@strawberry_django.filter_type(FiberStrand, lookups=True)
class FiberStrandFilter(
    MarkedComponentFilterMixin, BufferTubeChildFilterMixin, FiberCableChildFilterMixin, NetBoxModelFilter
):
    """GraphQL filter for FiberStrand."""

    ribbon: Annotated["RibbonFilter", strawberry.lazy(FILTERS)] | None = strawberry_django.filter_field()
    ribbon_id: ID | None = strawberry_django.filter_field()
    front_port_a: Annotated["FrontPortFilter", strawberry.lazy(DCIM_FILTERS)] | None = (  # noqa: F821
        strawberry_django.filter_field()
    )
    front_port_a_id: ID | None = strawberry_django.filter_field()
    front_port_b: Annotated["FrontPortFilter", strawberry.lazy(DCIM_FILTERS)] | None = (  # noqa: F821
        strawberry_django.filter_field()
    )
    front_port_b_id: ID | None = strawberry_django.filter_field()


@strawberry_django.filter_type(CableElement, lookups=True)
class CableElementFilter(FiberCableChildFilterMixin, NetBoxModelFilter):
    """GraphQL filter for CableElement."""

    name: StrFilterLookup | None = strawberry_django.filter_field()
    element_type: BaseFilterLookup[CableElementTypeEnum] | None = strawberry_django.filter_field()


#
# Splice planning
#


@strawberry_django.filter_type(SpliceProject, lookups=True)
class SpliceProjectFilter(NetBoxModelFilter):
    """GraphQL filter for SpliceProject."""

    name: StrFilterLookup | None = strawberry_django.filter_field()
    description: StrFilterLookup | None = strawberry_django.filter_field()


@strawberry_django.filter_type(SplicePlan, lookups=True)
class SplicePlanFilter(ClosureFilterMixin, NetBoxModelFilter):
    """GraphQL filter for SplicePlan."""

    project: Annotated["SpliceProjectFilter", strawberry.lazy(FILTERS)] | None = strawberry_django.filter_field()
    project_id: ID | None = strawberry_django.filter_field()
    name: StrFilterLookup | None = strawberry_django.filter_field()
    description: StrFilterLookup | None = strawberry_django.filter_field()
    status: BaseFilterLookup[SplicePlanStatusEnum] | None = strawberry_django.filter_field()
    submitted_by: Annotated["UserFilter", strawberry.lazy("users.graphql.filters")] | None = (  # noqa: F821
        strawberry_django.filter_field()
    )
    submitted_by_id: ID | None = strawberry_django.filter_field()
    diff_stale: FilterLookup[bool] | None = strawberry_django.filter_field()


@strawberry_django.filter_type(SplicePlanEntry, lookups=True)
class SplicePlanEntryFilter(TrayFilterMixin, NetBoxModelFilter):
    """GraphQL filter for SplicePlanEntry."""

    plan: Annotated["SplicePlanFilter", strawberry.lazy(FILTERS)] | None = strawberry_django.filter_field()
    plan_id: ID | None = strawberry_django.filter_field()
    fiber_a: Annotated["FrontPortFilter", strawberry.lazy(DCIM_FILTERS)] | None = strawberry_django.filter_field()  # noqa: F821
    fiber_a_id: ID | None = strawberry_django.filter_field()
    fiber_b: Annotated["FrontPortFilter", strawberry.lazy(DCIM_FILTERS)] | None = strawberry_django.filter_field()  # noqa: F821
    fiber_b_id: ID | None = strawberry_django.filter_field()
    is_express: FilterLookup[bool] | None = strawberry_django.filter_field()
    notes: StrFilterLookup | None = strawberry_django.filter_field()
    change_note: StrFilterLookup | None = strawberry_django.filter_field()


#
# Closures
#


@strawberry_django.filter_type(ClosureCableEntry, lookups=True)
class ClosureCableEntryFilter(ClosureFilterMixin, FiberCableChildFilterMixin, NetBoxModelFilter):
    """GraphQL filter for ClosureCableEntry."""

    entrance_label: StrFilterLookup | None = strawberry_django.filter_field()
    notes: StrFilterLookup | None = strawberry_django.filter_field()


@strawberry_django.filter_type(TrayProfile, lookups=True)
class TrayProfileFilter(NetBoxModelFilter):
    """GraphQL filter for TrayProfile."""

    module_type: Annotated["ModuleTypeFilter", strawberry.lazy(DCIM_FILTERS)] | None = (  # noqa: F821
        strawberry_django.filter_field()
    )
    module_type_id: ID | None = strawberry_django.filter_field()
    tray_role: BaseFilterLookup[TrayRoleEnum] | None = strawberry_django.filter_field()
    splice_capacity: IntegerLookup | None = strawberry_django.filter_field()
    tube_capacity: IntegerLookup | None = strawberry_django.filter_field()
    description: StrFilterLookup | None = strawberry_django.filter_field()


@strawberry_django.filter_type(TubeAssignment, lookups=True)
class TubeAssignmentFilter(ClosureFilterMixin, TrayFilterMixin, BufferTubeChildFilterMixin, NetBoxModelFilter):
    """GraphQL filter for TubeAssignment."""

    position: IntegerLookup | None = strawberry_django.filter_field()
    notes: StrFilterLookup | None = strawberry_django.filter_field()


@strawberry_django.filter_type(SlackLoop, lookups=True)
class SlackLoopFilter(FiberCableChildFilterMixin, NetBoxModelFilter):
    """GraphQL filter for SlackLoop."""

    site: Annotated["SiteFilter", strawberry.lazy(DCIM_FILTERS)] | None = strawberry_django.filter_field()  # noqa: F821
    site_id: ID | None = strawberry_django.filter_field()
    location: Annotated["LocationFilter", strawberry.lazy(DCIM_FILTERS)] | None = strawberry_django.filter_field()  # noqa: F821
    location_id: ID | None = strawberry_django.filter_field()
    start_mark: FloatLookup | None = strawberry_django.filter_field()
    end_mark: FloatLookup | None = strawberry_django.filter_field()
    storage_method: BaseFilterLookup[StorageMethodEnum] | None = strawberry_django.filter_field()
    notes: StrFilterLookup | None = strawberry_django.filter_field()


@strawberry_django.filter_type(FiberFault, lookups=True)
class FiberFaultFilter(FiberCableChildFilterMixin, NetBoxModelFilter):
    """GraphQL filter for FiberFault."""

    status: BaseFilterLookup[FiberFaultStatusEnum] | None = strawberry_django.filter_field()
    reported_at: DatetimeFilterLookup | None = strawberry_django.filter_field()
    resolved_at: DatetimeFilterLookup | None = strawberry_django.filter_field()
    location_mark: FloatLookup | None = strawberry_django.filter_field()
    description: StrFilterLookup | None = strawberry_django.filter_field()


#
# Fiber circuits and analyzed paths
#


@strawberry_django.filter_type(FiberCircuit, lookups=True)
class FiberCircuitFilter(TenancyFilterMixin, PrimaryModelFilter):
    """GraphQL filter for FiberCircuit."""

    name: StrFilterLookup | None = strawberry_django.filter_field()
    cid: StrFilterLookup | None = strawberry_django.filter_field()
    status: BaseFilterLookup[FiberCircuitStatusEnum] | None = strawberry_django.filter_field()
    strand_count: IntegerLookup | None = strawberry_django.filter_field()
    is_broken: FilterLookup[bool] | None = strawberry_django.filter_field()
    provider_circuits: Annotated["CircuitFilter", strawberry.lazy("circuits.graphql.filters")] | None = (  # noqa: F821
        strawberry_django.filter_field()
    )


@strawberry_django.filter_type(FiberCircuitPath, lookups=True)
class FiberCircuitPathFilter(NetBoxModelFilter):
    """GraphQL filter for FiberCircuitPath."""

    circuit: Annotated["FiberCircuitFilter", strawberry.lazy(FILTERS)] | None = strawberry_django.filter_field()
    circuit_id: ID | None = strawberry_django.filter_field()
    strand_path: Annotated["FiberStrandPathFilter", strawberry.lazy(FILTERS)] | None = strawberry_django.filter_field()
    strand_path_id: ID | None = strawberry_django.filter_field()
    position: IntegerLookup | None = strawberry_django.filter_field()
    active: FilterLookup[bool] | None = strawberry_django.filter_field()
    delivered_incomplete: FilterLookup[bool] | None = strawberry_django.filter_field()
    is_broken: FilterLookup[bool] | None = strawberry_django.filter_field()
    broken_reason: BaseFilterLookup[AssignmentBrokenReasonEnum] | None = strawberry_django.filter_field()
    actual_loss_db: FloatLookup | None = strawberry_django.filter_field()
    wavelength_nm: IntegerLookup | None = strawberry_django.filter_field()


@strawberry_django.filter_type(FiberStrandPath, lookups=True)
class FiberStrandPathFilter(BaseModelFilter):
    """GraphQL filter for FiberStrandPath (a plain model: no tags, custom fields or change log)."""

    end_a_port: Annotated["FrontPortFilter", strawberry.lazy(DCIM_FILTERS)] | None = strawberry_django.filter_field()  # noqa: F821
    end_a_port_id: ID | None = strawberry_django.filter_field()
    end_b_port: Annotated["FrontPortFilter", strawberry.lazy(DCIM_FILTERS)] | None = strawberry_django.filter_field()  # noqa: F821
    end_b_port_id: ID | None = strawberry_django.filter_field()
    end_a_kind: BaseFilterLookup[PathEndKindEnum] | None = strawberry_django.filter_field()
    end_b_kind: BaseFilterLookup[PathEndKindEnum] | None = strawberry_django.filter_field()
    end_a_reason: BaseFilterLookup[PathEndReasonEnum] | None = strawberry_django.filter_field()
    end_b_reason: BaseFilterLookup[PathEndReasonEnum] | None = strawberry_django.filter_field()
    completeness: BaseFilterLookup[PathCompletenessEnum] | None = strawberry_django.filter_field()
    route_key: StrFilterLookup | None = strawberry_django.filter_field()
    is_proposed: FilterLookup[bool] | None = strawberry_django.filter_field()
    is_defective: FilterLookup[bool] | None = strawberry_django.filter_field()
    computed_at: DatetimeFilterLookup[datetime] | None = strawberry_django.filter_field()
