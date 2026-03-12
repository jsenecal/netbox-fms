import django_filters
from dcim.models import Cable, Device, Manufacturer
from django.db import models
from django.utils.translation import gettext_lazy as _
from netbox.filtersets import NetBoxModelFilterSet

from .choices import (
    ArmorTypeChoices,
    ConstructionChoices,
    DeploymentChoices,
    FiberTypeChoices,
    FireRatingChoices,
    SheathMaterialChoices,
    SplicePlanStatusChoices,
)
from .models import (
    BufferTube,
    BufferTubeTemplate,
    CableElement,
    CableElementTemplate,
    FiberCable,
    FiberCableType,
    FiberPathLoss,
    FiberStrand,
    Ribbon,
    RibbonTemplate,
    SplicePlan,
    SplicePlanEntry,
)


class FiberCableTypeFilterSet(NetBoxModelFilterSet):
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
    has_front_port = django_filters.BooleanFilter(
        field_name="front_port",
        lookup_expr="isnull",
        exclude=True,
        label=_("Has front port"),
    )

    class Meta:
        model = FiberStrand
        fields = ("id", "fiber_cable_id", "buffer_tube_id", "ribbon_id", "name", "position")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(name__icontains=value))


class CableElementFilterSet(NetBoxModelFilterSet):
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


class SplicePlanFilterSet(NetBoxModelFilterSet):
    closure_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Device.objects.all(),
        field_name="closure",
        label=_("Closure (ID)"),
    )
    status = django_filters.MultipleChoiceFilter(choices=SplicePlanStatusChoices)

    class Meta:
        model = SplicePlan
        fields = ("id", "closure_id", "name", "status")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(name__icontains=value) | models.Q(description__icontains=value))


class SplicePlanEntryFilterSet(NetBoxModelFilterSet):
    plan_id = django_filters.ModelMultipleChoiceFilter(
        queryset=SplicePlan.objects.all(),
        field_name="plan",
        label=_("Plan (ID)"),
    )

    class Meta:
        model = SplicePlanEntry
        fields = ("id", "plan_id", "fiber_a", "fiber_b", "mode_override")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(plan__name__icontains=value))


class FiberPathLossFilterSet(NetBoxModelFilterSet):
    cable_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Cable.objects.all(),
        field_name="cable",
        label=_("Cable (ID)"),
    )
    wavelength_nm = django_filters.NumberFilter()
    test_date = django_filters.DateFilter()

    class Meta:
        model = FiberPathLoss
        fields = ("id", "cable_id", "wavelength_nm", "test_date")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(notes__icontains=value))
