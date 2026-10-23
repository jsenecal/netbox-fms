"""GraphQL enums for netbox_fms choice fields."""

import strawberry

from ..choices import (
    ArmorTypeChoices,
    AssignmentBrokenReasonChoices,
    CableElementTypeChoices,
    ConstructionChoices,
    DeploymentChoices,
    FiberCircuitStatusChoices,
    FiberColorSchemeChoices,
    FiberFaultStatusChoices,
    MarkerTypeChoices,
    PathCompletenessChoices,
    PathEndKindChoices,
    PathEndReasonChoices,
    SheathMaterialChoices,
    SplicePlanStatusChoices,
    StorageMethodChoices,
    TrayRoleChoices,
)

__all__ = (
    "ArmorTypeEnum",
    "AssignmentBrokenReasonEnum",
    "CableElementTypeEnum",
    "ConstructionEnum",
    "DeploymentEnum",
    "FiberCircuitStatusEnum",
    "FiberColorSchemeEnum",
    "FiberFaultStatusEnum",
    "MarkerTypeEnum",
    "PathCompletenessEnum",
    "PathEndKindEnum",
    "PathEndReasonEnum",
    "SheathMaterialEnum",
    "SplicePlanStatusEnum",
    "StorageMethodEnum",
    "TrayRoleEnum",
)

# FireRatingChoices has no enum: its blank "not applicable" value cannot be a
# member name, so fire_rating filters as a string.
ArmorTypeEnum = strawberry.enum(ArmorTypeChoices.as_enum())
AssignmentBrokenReasonEnum = strawberry.enum(AssignmentBrokenReasonChoices.as_enum())
CableElementTypeEnum = strawberry.enum(CableElementTypeChoices.as_enum())
ConstructionEnum = strawberry.enum(ConstructionChoices.as_enum())
DeploymentEnum = strawberry.enum(DeploymentChoices.as_enum())
FiberCircuitStatusEnum = strawberry.enum(FiberCircuitStatusChoices.as_enum())
FiberColorSchemeEnum = strawberry.enum(FiberColorSchemeChoices.as_enum())
FiberFaultStatusEnum = strawberry.enum(FiberFaultStatusChoices.as_enum())
MarkerTypeEnum = strawberry.enum(MarkerTypeChoices.as_enum())
PathCompletenessEnum = strawberry.enum(PathCompletenessChoices.as_enum())
PathEndKindEnum = strawberry.enum(PathEndKindChoices.as_enum())
PathEndReasonEnum = strawberry.enum(PathEndReasonChoices.as_enum())
SheathMaterialEnum = strawberry.enum(SheathMaterialChoices.as_enum())
SplicePlanStatusEnum = strawberry.enum(SplicePlanStatusChoices.as_enum())
StorageMethodEnum = strawberry.enum(StorageMethodChoices.as_enum())
TrayRoleEnum = strawberry.enum(TrayRoleChoices.as_enum())
