import django_filters
from dcim.choices import CableLengthUnitChoices
from dcim.models import Cable, Device, Location, Manufacturer, Module, Site
from django.db import models
from django.utils.translation import gettext_lazy as _
from netbox.filtersets import NetBoxModelFilterSet
from tenancy.models import Tenant

from .choices import (
    ArmorTypeChoices,
    ConstructionChoices,
    DeploymentChoices,
    FiberCircuitStatusChoices,
    FiberTypeChoices,
    FireRatingChoices,
    SheathMaterialChoices,
    SplicePlanStatusChoices,
    StorageMethodChoices,
    WavelengthChannelStatusChoices,
    WavelengthServiceStatusChoices,
    WdmGridChoices,
    WdmNodeTypeChoices,
)
from .models import (
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


class FiberCableTypeFilterSet(NetBoxModelFilterSet):
    """FilterSet for FiberCableType model."""

    manufacturer_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Manufacturer.objects.all(),
        field_name="manufacturer",
        label=_("Manufacturer (ID)"),
    )
    manufacturer = django_filters.ModelMultipleChoiceFilter(
        queryset=Manufacturer.objects.all(),
        field_name="manufacturer__slug",
        to_field_name="slug",
        label=_("Manufacturer (slug)"),
    )
    construction = django_filters.MultipleChoiceFilter(choices=ConstructionChoices)
    fiber_type = django_filters.MultipleChoiceFilter(choices=FiberTypeChoices)
    sheath_material = django_filters.MultipleChoiceFilter(choices=SheathMaterialChoices)
    is_armored = django_filters.BooleanFilter()
    armor_type = django_filters.MultipleChoiceFilter(choices=ArmorTypeChoices)
    deployment = django_filters.MultipleChoiceFilter(choices=DeploymentChoices)
    fire_rating = django_filters.MultipleChoiceFilter(choices=FireRatingChoices)
    strand_count = django_filters.NumberFilter()

    class Meta:
        model = FiberCableType
        fields = (
            "id",
            "manufacturer_id",
            "model",
            "part_number",
            "construction",
            "fiber_type",
            "strand_count",
            "sheath_material",
            "is_armored",
            "armor_type",
            "deployment",
            "fire_rating",
        )

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            models.Q(model__icontains=value)
            | models.Q(part_number__icontains=value)
            | models.Q(notes__icontains=value)
            | models.Q(manufacturer__name__icontains=value)
        )


class BufferTubeTemplateFilterSet(NetBoxModelFilterSet):
    """FilterSet for BufferTubeTemplate model."""

    fiber_cable_type_id = django_filters.ModelMultipleChoiceFilter(
        queryset=FiberCableType.objects.all(),
        field_name="fiber_cable_type",
        label=_("Fiber Cable Type (ID)"),
    )

    class Meta:
        model = BufferTubeTemplate
        fields = ("id", "fiber_cable_type_id", "name", "fiber_count")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(name__icontains=value) | models.Q(description__icontains=value))


class RibbonTemplateFilterSet(NetBoxModelFilterSet):
    """FilterSet for RibbonTemplate model."""

    fiber_cable_type_id = django_filters.ModelMultipleChoiceFilter(
        queryset=FiberCableType.objects.all(),
        field_name="fiber_cable_type",
        label=_("Fiber Cable Type (ID)"),
    )
    buffer_tube_template_id = django_filters.ModelMultipleChoiceFilter(
        queryset=BufferTubeTemplate.objects.all(),
        field_name="buffer_tube_template",
        label=_("Buffer Tube Template (ID)"),
    )

    class Meta:
        model = RibbonTemplate
        fields = ("id", "fiber_cable_type_id", "buffer_tube_template_id", "name", "fiber_count")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(name__icontains=value) | models.Q(description__icontains=value))


class CableElementTemplateFilterSet(NetBoxModelFilterSet):
    """FilterSet for CableElementTemplate model."""

    fiber_cable_type_id = django_filters.ModelMultipleChoiceFilter(
        queryset=FiberCableType.objects.all(),
        field_name="fiber_cable_type",
        label=_("Fiber Cable Type (ID)"),
    )

    class Meta:
        model = CableElementTemplate
        fields = ("id", "fiber_cable_type_id", "name", "element_type")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(name__icontains=value) | models.Q(description__icontains=value))


class FiberCableFilterSet(NetBoxModelFilterSet):
    """FilterSet for FiberCable model."""

    fiber_cable_type_id = django_filters.ModelMultipleChoiceFilter(
        queryset=FiberCableType.objects.all(),
        field_name="fiber_cable_type",
        label=_("Fiber Cable Type (ID)"),
    )
    cable_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Cable.objects.all(),
        label=_("Cable (ID)"),
    )
    install_date = django_filters.DateFilter()

    class Meta:
        model = FiberCable
        fields = ("id", "cable_id", "fiber_cable_type_id", "serial_number", "install_date")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            models.Q(serial_number__icontains=value)
            | models.Q(notes__icontains=value)
            | models.Q(cable__label__icontains=value)
            | models.Q(fiber_cable_type__model__icontains=value)
        )


class BufferTubeFilterSet(NetBoxModelFilterSet):
    """FilterSet for BufferTube model."""

    fiber_cable_id = django_filters.ModelMultipleChoiceFilter(
        queryset=FiberCable.objects.all(),
        field_name="fiber_cable",
        label=_("Fiber Cable (ID)"),
    )

    class Meta:
        model = BufferTube
        fields = ("id", "fiber_cable_id", "name", "position")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(name__icontains=value))


class RibbonFilterSet(NetBoxModelFilterSet):
    """FilterSet for Ribbon model."""

    fiber_cable_id = django_filters.ModelMultipleChoiceFilter(
        queryset=FiberCable.objects.all(),
        field_name="fiber_cable",
        label=_("Fiber Cable (ID)"),
    )
    buffer_tube_id = django_filters.ModelMultipleChoiceFilter(
        queryset=BufferTube.objects.all(),
        field_name="buffer_tube",
        label=_("Buffer Tube (ID)"),
    )

    class Meta:
        model = Ribbon
        fields = ("id", "fiber_cable_id", "buffer_tube_id", "name", "position")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(name__icontains=value))


class FiberStrandFilterSet(NetBoxModelFilterSet):
    """FilterSet for FiberStrand model."""

    fiber_cable_id = django_filters.ModelMultipleChoiceFilter(
        queryset=FiberCable.objects.all(),
        field_name="fiber_cable",
        label=_("Fiber Cable (ID)"),
    )
    buffer_tube_id = django_filters.ModelMultipleChoiceFilter(
        queryset=BufferTube.objects.all(),
        field_name="buffer_tube",
        label=_("Buffer Tube (ID)"),
    )
    ribbon_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Ribbon.objects.all(),
        field_name="ribbon",
        label=_("Ribbon (ID)"),
    )
    has_front_port_a = django_filters.BooleanFilter(
        field_name="front_port_a",
        lookup_expr="isnull",
        exclude=True,
        label=_("Has front port A"),
    )
    has_front_port_b = django_filters.BooleanFilter(
        field_name="front_port_b",
        lookup_expr="isnull",
        exclude=True,
        label=_("Has front port B"),
    )

    class Meta:
        model = FiberStrand
        fields = ("id", "fiber_cable_id", "buffer_tube_id", "ribbon_id", "name", "position")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(name__icontains=value))


class CableElementFilterSet(NetBoxModelFilterSet):
    """FilterSet for CableElement model."""

    fiber_cable_id = django_filters.ModelMultipleChoiceFilter(
        queryset=FiberCable.objects.all(),
        field_name="fiber_cable",
        label=_("Fiber Cable (ID)"),
    )

    class Meta:
        model = CableElement
        fields = ("id", "fiber_cable_id", "name", "element_type")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(name__icontains=value))


class SpliceProjectFilterSet(NetBoxModelFilterSet):
    """FilterSet for SpliceProject model."""

    class Meta:
        model = SpliceProject
        fields = ("id", "name")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(name__icontains=value) | models.Q(description__icontains=value))


class SplicePlanFilterSet(NetBoxModelFilterSet):
    """FilterSet for SplicePlan model."""

    closure_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Device.objects.all(),
        field_name="closure",
        label=_("Closure (ID)"),
    )
    project_id = django_filters.ModelMultipleChoiceFilter(
        queryset=SpliceProject.objects.all(),
        field_name="project",
        label=_("Project (ID)"),
    )
    status = django_filters.MultipleChoiceFilter(choices=SplicePlanStatusChoices)

    class Meta:
        model = SplicePlan
        fields = ("id", "closure_id", "project_id", "name", "status")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(name__icontains=value) | models.Q(description__icontains=value))


class SplicePlanEntryFilterSet(NetBoxModelFilterSet):
    """FilterSet for SplicePlanEntry model."""

    plan_id = django_filters.ModelMultipleChoiceFilter(
        queryset=SplicePlan.objects.all(),
        field_name="plan",
        label=_("Plan (ID)"),
    )
    tray_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Module.objects.all(),
        field_name="tray",
        label=_("Tray (ID)"),
    )

    class Meta:
        model = SplicePlanEntry
        fields = ("id", "plan_id", "tray_id", "fiber_a", "fiber_b")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(plan__name__icontains=value))


class ClosureCableEntryFilterSet(NetBoxModelFilterSet):
    """FilterSet for ClosureCableEntry model."""

    closure_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Device.objects.all(),
        field_name="closure",
        label=_("Closure (ID)"),
    )

    class Meta:
        model = ClosureCableEntry
        fields = ("id", "closure_id", "fiber_cable", "entrance_label")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(entrance_label__icontains=value) | models.Q(notes__icontains=value))


class SlackLoopFilterSet(NetBoxModelFilterSet):
    """FilterSet for SlackLoop model."""

    fiber_cable_id = django_filters.ModelMultipleChoiceFilter(
        queryset=FiberCable.objects.all(),
        field_name="fiber_cable",
        label=_("Fiber Cable (ID)"),
    )
    site_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Site.objects.all(),
        field_name="site",
        label=_("Site (ID)"),
    )
    location_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Location.objects.all(),
        field_name="location",
        label=_("Location (ID)"),
    )
    length_unit = django_filters.MultipleChoiceFilter(choices=CableLengthUnitChoices)
    storage_method = django_filters.MultipleChoiceFilter(choices=StorageMethodChoices)

    class Meta:
        model = SlackLoop
        fields = ("id", "fiber_cable_id", "site_id", "location_id", "length_unit", "storage_method")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(notes__icontains=value))


class FiberCircuitFilterSet(NetBoxModelFilterSet):
    """FilterSet for FiberCircuit model."""

    status = django_filters.MultipleChoiceFilter(choices=FiberCircuitStatusChoices)
    tenant_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Tenant.objects.all(),
        field_name="tenant",
        label=_("Tenant (ID)"),
    )

    class Meta:
        model = FiberCircuit
        fields = ("id", "name", "cid", "status", "strand_count", "tenant")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            models.Q(name__icontains=value) | models.Q(cid__icontains=value) | models.Q(description__icontains=value)
        )


class FiberCircuitPathFilterSet(NetBoxModelFilterSet):
    """FilterSet for FiberCircuitPath model."""

    circuit_id = django_filters.ModelMultipleChoiceFilter(
        queryset=FiberCircuit.objects.all(),
        field_name="circuit",
        label=_("Circuit (ID)"),
    )
    is_complete = django_filters.BooleanFilter()

    class Meta:
        model = FiberCircuitPath
        fields = ("id", "circuit", "position", "is_complete", "wavelength_nm")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(circuit__name__icontains=value) | models.Q(circuit__cid__icontains=value))


# ---------------------------------------------------------------------------
# WDM Device Type Profile
# ---------------------------------------------------------------------------


class WdmDeviceTypeProfileFilterSet(NetBoxModelFilterSet):
    """FilterSet for WdmDeviceTypeProfile model."""

    node_type = django_filters.MultipleChoiceFilter(choices=WdmNodeTypeChoices)
    grid = django_filters.MultipleChoiceFilter(choices=WdmGridChoices)

    class Meta:
        model = WdmDeviceTypeProfile
        fields = ("id", "node_type", "grid")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(device_type__model__icontains=value))


# ---------------------------------------------------------------------------
# WDM Channel Template
# ---------------------------------------------------------------------------


class WdmChannelTemplateFilterSet(NetBoxModelFilterSet):
    """FilterSet for WdmChannelTemplate model."""

    profile_id = django_filters.ModelMultipleChoiceFilter(
        queryset=WdmDeviceTypeProfile.objects.all(),
        field_name="profile",
        label=_("Profile (ID)"),
    )

    class Meta:
        model = WdmChannelTemplate
        fields = ("id", "profile", "grid_position", "wavelength_nm", "label")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(label__icontains=value))


# ---------------------------------------------------------------------------
# WDM Node
# ---------------------------------------------------------------------------


class WdmNodeFilterSet(NetBoxModelFilterSet):
    """FilterSet for WdmNode model."""

    node_type = django_filters.MultipleChoiceFilter(choices=WdmNodeTypeChoices)
    grid = django_filters.MultipleChoiceFilter(choices=WdmGridChoices)
    device_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Device.objects.all(),
        field_name="device",
        label=_("Device (ID)"),
    )

    class Meta:
        model = WdmNode
        fields = ("id", "node_type", "grid")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(device__name__icontains=value))


# ---------------------------------------------------------------------------
# WDM Trunk Port
# ---------------------------------------------------------------------------


class WdmTrunkPortFilterSet(NetBoxModelFilterSet):
    """FilterSet for WdmTrunkPort model."""

    wdm_node_id = django_filters.ModelMultipleChoiceFilter(
        queryset=WdmNode.objects.all(),
        field_name="wdm_node",
        label=_("WDM Node (ID)"),
    )

    class Meta:
        model = WdmTrunkPort
        fields = ("id", "wdm_node", "direction", "position")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(direction__icontains=value))


# ---------------------------------------------------------------------------
# Wavelength Channel
# ---------------------------------------------------------------------------


class WavelengthChannelFilterSet(NetBoxModelFilterSet):
    """FilterSet for WavelengthChannel model."""

    wdm_node_id = django_filters.ModelMultipleChoiceFilter(
        queryset=WdmNode.objects.all(),
        field_name="wdm_node",
        label=_("WDM Node (ID)"),
    )
    status = django_filters.MultipleChoiceFilter(choices=WavelengthChannelStatusChoices)

    class Meta:
        model = WavelengthChannel
        fields = ("id", "wdm_node", "status", "grid_position", "wavelength_nm")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(label__icontains=value))


# ---------------------------------------------------------------------------
# Wavelength Service
# ---------------------------------------------------------------------------


class WavelengthServiceFilterSet(NetBoxModelFilterSet):
    """FilterSet for WavelengthService model."""

    status = django_filters.MultipleChoiceFilter(choices=WavelengthServiceStatusChoices)
    tenant_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Tenant.objects.all(),
        field_name="tenant",
        label=_("Tenant (ID)"),
    )

    class Meta:
        model = WavelengthService
        fields = ("id", "name", "status", "wavelength_nm")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(name__icontains=value) | models.Q(description__icontains=value))
