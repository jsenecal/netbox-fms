from dcim.api.serializers import (
    CableSerializer,
    DeviceSerializer,
    FrontPortSerializer,
    ManufacturerSerializer,
    ModuleSerializer,
)
from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from ..models import (
    BufferTube,
    BufferTubeTemplate,
    CableElement,
    CableElementTemplate,
    ClosureCableEntry,
    FiberCable,
    FiberCableType,
    FiberPathLoss,
    FiberStrand,
    Ribbon,
    RibbonTemplate,
    SplicePlan,
    SplicePlanEntry,
    SpliceProject,
)

# Re-export FrontPortSerializer for use in nested fields
__all__ = ("FrontPortSerializer",)


class FiberCableTypeSerializer(NetBoxModelSerializer):
    manufacturer = ManufacturerSerializer(nested=True)
    instance_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = FiberCableType
        fields = (
            "id",
            "url",
            "display",
            "manufacturer",
            "model",
            "part_number",
            "construction",
            "fiber_type",
            "strand_count",
            "sheath_material",
            "jacket_color",
            "is_armored",
            "armor_type",
            "deployment",
            "fire_rating",
            "notes",
            "instance_count",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "manufacturer", "model", "construction", "strand_count")


class BufferTubeTemplateSerializer(NetBoxModelSerializer):
    fiber_cable_type = FiberCableTypeSerializer(nested=True)

    class Meta:
        model = BufferTubeTemplate
        fields = (
            "id",
            "url",
            "display",
            "fiber_cable_type",
            "name",
            "position",
            "color",
            "stripe_color",
            "fiber_count",
            "description",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "position", "fiber_count")


class CableElementTemplateSerializer(NetBoxModelSerializer):
    fiber_cable_type = FiberCableTypeSerializer(nested=True)

    class Meta:
        model = CableElementTemplate
        fields = (
            "id",
            "url",
            "display",
            "fiber_cable_type",
            "name",
            "element_type",
            "description",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "element_type")


class RibbonTemplateSerializer(NetBoxModelSerializer):
    fiber_cable_type = FiberCableTypeSerializer(nested=True)
    buffer_tube_template = BufferTubeTemplateSerializer(nested=True, required=False, allow_null=True)

    class Meta:
        model = RibbonTemplate
        fields = (
            "id",
            "url",
            "display",
            "fiber_cable_type",
            "buffer_tube_template",
            "name",
            "position",
            "color",
            "stripe_color",
            "fiber_count",
            "description",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "position", "fiber_count")


class FiberCableSerializer(NetBoxModelSerializer):
    cable = CableSerializer(nested=True)
    fiber_cable_type = FiberCableTypeSerializer(nested=True)

    class Meta:
        model = FiberCable
        fields = (
            "id",
            "url",
            "display",
            "cable",
            "fiber_cable_type",
            "serial_number",
            "install_date",
            "notes",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "cable", "fiber_cable_type")


class BufferTubeSerializer(NetBoxModelSerializer):
    class Meta:
        model = BufferTube
        fields = (
            "id",
            "url",
            "display",
            "fiber_cable",
            "name",
            "position",
            "color",
            "stripe_color",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "position")


class RibbonSerializer(NetBoxModelSerializer):
    class Meta:
        model = Ribbon
        fields = (
            "id",
            "url",
            "display",
            "fiber_cable",
            "buffer_tube",
            "name",
            "position",
            "color",
            "stripe_color",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "position")


class FiberStrandSerializer(NetBoxModelSerializer):
    front_port = FrontPortSerializer(nested=True, required=False, allow_null=True)

    class Meta:
        model = FiberStrand
        fields = (
            "id",
            "url",
            "display",
            "fiber_cable",
            "buffer_tube",
            "ribbon",
            "name",
            "position",
            "color",
            "front_port",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "position")


class CableElementSerializer(NetBoxModelSerializer):
    class Meta:
        model = CableElement
        fields = (
            "id",
            "url",
            "display",
            "fiber_cable",
            "name",
            "element_type",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "element_type")


class SpliceProjectSerializer(NetBoxModelSerializer):
    class Meta:
        model = SpliceProject
        fields = (
            "id",
            "url",
            "display",
            "name",
            "description",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name")


class ClosureCableEntrySerializer(NetBoxModelSerializer):
    class Meta:
        model = ClosureCableEntry
        fields = (
            "id",
            "url",
            "display",
            "closure",
            "fiber_cable",
            "entrance_label",
            "notes",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "closure", "fiber_cable")


class SplicePlanSerializer(NetBoxModelSerializer):
    closure = DeviceSerializer(nested=True)
    project = SpliceProjectSerializer(nested=True, required=False, allow_null=True)
    entry_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = SplicePlan
        fields = (
            "id",
            "url",
            "display",
            "closure",
            "project",
            "name",
            "description",
            "status",
            "cached_diff",
            "diff_stale",
            "entry_count",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "status")


class SplicePlanEntrySerializer(NetBoxModelSerializer):
    plan = SplicePlanSerializer(nested=True)
    tray = ModuleSerializer(nested=True)
    fiber_a = FrontPortSerializer(nested=True)
    fiber_b = FrontPortSerializer(nested=True)

    class Meta:
        model = SplicePlanEntry
        fields = (
            "id",
            "url",
            "display",
            "plan",
            "tray",
            "fiber_a",
            "fiber_b",
            "notes",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "fiber_a", "fiber_b")


class FiberPathLossSerializer(NetBoxModelSerializer):
    cable = CableSerializer(nested=True)

    class Meta:
        model = FiberPathLoss
        fields = (
            "id",
            "url",
            "display",
            "cable",
            "measured_loss_db",
            "calculated_loss_db",
            "wavelength_nm",
            "test_date",
            "otdr_file",
            "notes",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "cable", "wavelength_nm")


# ---------------------------------------------------------------------------
# Splice toolkit serializers
# ---------------------------------------------------------------------------


class ClosureStrandSerializer(serializers.Serializer):
    """Serializer for strands grouped by cable/tube for the splice editor."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    position = serializers.IntegerField()
    color = serializers.CharField()
    front_port_id = serializers.IntegerField(allow_null=True)
    live_spliced_to = serializers.IntegerField(allow_null=True)
    plan_entry_id = serializers.IntegerField(allow_null=True)
    plan_spliced_to = serializers.IntegerField(allow_null=True)


class TubeGroupSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    color = serializers.CharField()
    strands = ClosureStrandSerializer(many=True)


class CableGroupSerializer(serializers.Serializer):
    fiber_cable_id = serializers.IntegerField()
    cable_label = serializers.CharField()
    tubes = TubeGroupSerializer(many=True)
    loose_strands = ClosureStrandSerializer(many=True)


class ProvisionPortsInputSerializer(serializers.Serializer):
    fiber_cable_id = serializers.IntegerField()
    device_id = serializers.IntegerField()
    port_type = serializers.CharField(default="splice")
