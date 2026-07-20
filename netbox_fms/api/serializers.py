from dcim.api.serializers import (
    CableSerializer,
    DeviceSerializer,
    FrontPortSerializer,
    ManufacturerSerializer,
    ModuleSerializer,
    ModuleTypeSerializer,
)
from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers
from tenancy.api.serializers import TenantSerializer

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
    FiberCircuitNode,
    FiberCircuitPath,
    FiberStrand,
    Ribbon,
    RibbonTemplate,
    SlackLoop,
    SplicePlan,
    SplicePlanEntry,
    SpliceProject,
    TrayProfile,
    TubeAssignment,
)

# Re-export FrontPortSerializer for use in nested fields
__all__ = ("FrontPortSerializer",)


class FiberCableTypeSerializer(NetBoxModelSerializer):
    """Serializer for FiberCableType model."""

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
            "strand_count",
            "color_scheme",
            "outer_diameter",
            "twist_factor_ratio",
            "mark_unit",
            "sheath_material",
            "jacket_color",
            "is_armored",
            "armor_type",
            "deployment",
            "fire_rating",
            "strand_marker_interval",
            "strand_marker_color",
            "strand_marker_type",
            "notes",
            "instance_count",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "manufacturer", "model", "construction", "strand_count")


class FiberAttenuationSpecSerializer(NetBoxModelSerializer):
    """Serializer for FiberAttenuationSpec model."""

    fiber_cable_type = FiberCableTypeSerializer(nested=True)

    class Meta:
        model = FiberAttenuationSpec
        fields = (
            "id",
            "url",
            "display",
            "fiber_cable_type",
            "wavelength_nm",
            "max_loss_db_per_km",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "wavelength_nm", "max_loss_db_per_km")


class BufferTubeTemplateSerializer(NetBoxModelSerializer):
    """Serializer for BufferTubeTemplate model."""

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
            "marker_count",
            "marker_color",
            "marker_type",
            "strand_marker_interval",
            "strand_marker_color",
            "strand_marker_type",
            "fiber_count",
            "description",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "position", "fiber_count")


class CableElementTemplateSerializer(NetBoxModelSerializer):
    """Serializer for CableElementTemplate model."""

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
    """Serializer for RibbonTemplate model."""

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
            "marker_count",
            "marker_color",
            "marker_type",
            "strand_marker_interval",
            "strand_marker_color",
            "strand_marker_type",
            "fiber_count",
            "description",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "position", "fiber_count")


class FiberCableSerializer(NetBoxModelSerializer):
    """Serializer for FiberCable model."""

    cable = CableSerializer(nested=True)
    fiber_cable_type = FiberCableTypeSerializer(nested=True)
    installed_by = TenantSerializer(nested=True, required=False, allow_null=True)
    glass_length = serializers.DecimalField(
        max_digits=14,
        decimal_places=4,
        read_only=True,
        allow_null=True,
        help_text=(
            "Optical-fibre length, computed as cable.length * (1 + fiber_cable_type.twist_factor_ratio). "
            "Returns null when either operand is missing."
        ),
    )

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
            "installed_by",
            "start_mark",
            "end_mark",
            "glass_length",
            "notes",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "cable", "fiber_cable_type")


class BufferTubeSerializer(NetBoxModelSerializer):
    """Serializer for BufferTube model."""

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
            "marker_count",
            "marker_color",
            "marker_type",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "position")


class RibbonSerializer(NetBoxModelSerializer):
    """Serializer for Ribbon model."""

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
            "marker_count",
            "marker_color",
            "marker_type",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "position")


class FiberStrandSerializer(NetBoxModelSerializer):
    """Serializer for FiberStrand model."""

    front_port_a = FrontPortSerializer(nested=True, required=False, allow_null=True)
    front_port_b = FrontPortSerializer(nested=True, required=False, allow_null=True)

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
            "marker_count",
            "marker_color",
            "marker_type",
            "front_port_a",
            "front_port_b",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "position")


class CableElementSerializer(NetBoxModelSerializer):
    """Serializer for CableElement model."""

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
    """Serializer for SpliceProject model."""

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
    """Serializer for ClosureCableEntry model."""

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
    """Serializer for SplicePlan model."""

    closure = DeviceSerializer(nested=True)
    project = SpliceProjectSerializer(nested=True, required=False, allow_null=True)
    entry_count = serializers.IntegerField(read_only=True, default=0)
    status = serializers.CharField(read_only=True)

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
            "submitted_by",
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
    """Serializer for SplicePlanEntry model."""

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
            "is_express",
            "change_note",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "fiber_a", "fiber_b")


class SlackLoopSerializer(NetBoxModelSerializer):
    """Serializer for SlackLoop model."""

    loop_length = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    mark_unit = serializers.CharField(read_only=True, help_text="Unit, sourced from FiberCableType.mark_unit.")

    class Meta:
        model = SlackLoop
        fields = (
            "id",
            "url",
            "display",
            "fiber_cable",
            "site",
            "location",
            "start_mark",
            "end_mark",
            "loop_length",
            "mark_unit",
            "storage_method",
            "notes",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "fiber_cable", "start_mark", "end_mark")


class TrayProfileSerializer(NetBoxModelSerializer):
    """Serializer for TrayProfile model."""

    module_type = ModuleTypeSerializer(nested=True)

    class Meta:
        model = TrayProfile
        fields = (
            "id",
            "url",
            "display",
            "module_type",
            "tray_role",
            "description",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "module_type", "tray_role")


class TubeAssignmentSerializer(NetBoxModelSerializer):
    """Serializer for TubeAssignment model."""

    closure = DeviceSerializer(nested=True)
    tray = ModuleSerializer(nested=True)
    buffer_tube = BufferTubeSerializer(nested=True)
    confirm_reassign = serializers.BooleanField(
        write_only=True,
        required=False,
        default=False,
        help_text="Move front ports that already belong to another module onto the selected tray.",
    )

    class Meta:
        model = TubeAssignment
        fields = (
            "id",
            "url",
            "display",
            "closure",
            "tray",
            "buffer_tube",
            "position",
            "notes",
            "confirm_reassign",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "closure", "tray", "buffer_tube")

    def validate(self, data):
        confirm = data.pop("confirm_reassign", False)
        data = super().validate(data)
        if confirm:
            return data
        instance = self.instance
        candidate = TubeAssignment(
            pk=instance.pk if instance else None,
            closure=data.get("closure") or (instance.closure if instance else None),
            tray=data.get("tray") or (instance.tray if instance else None),
            buffer_tube=data.get("buffer_tube") or (instance.buffer_tube if instance else None),
        )
        if candidate.closure_id and candidate.tray_id and candidate.buffer_tube_id:
            conflicts = candidate.conflicting_front_ports()
            if conflicts:
                names = ", ".join(sorted(port.name for port in conflicts))
                raise serializers.ValidationError(
                    {
                        "confirm_reassign": (
                            f"The following front ports already belong to another module: {names}. "
                            "Set confirm_reassign to move them."
                        )
                    }
                )
        return data


# ---------------------------------------------------------------------------
# Fiber Circuit serializers
# ---------------------------------------------------------------------------


class FiberCircuitSerializer(NetBoxModelSerializer):
    """Serializer for FiberCircuit model."""

    class Meta:
        model = FiberCircuit
        fields = (
            "id",
            "url",
            "display",
            "name",
            "cid",
            "status",
            "description",
            "strand_count",
            "tenant",
            "comments",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "cid", "status")


class FiberCircuitPathSerializer(NetBoxModelSerializer):
    """Serializer for FiberCircuitPath model.

    ``calculated_loss_db`` is a computed list of
    ``[wavelength_nm, loss_db]`` pairs derived from each cable's
    ``FiberAttenuationSpec`` rows and glass length; it is read-only.
    """

    calculated_loss_db = serializers.SerializerMethodField()

    def get_calculated_loss_db(self, obj):
        return [[wl, str(loss)] for wl, loss in obj.calculated_loss_db]

    class Meta:
        model = FiberCircuitPath
        fields = (
            "id",
            "url",
            "display",
            "circuit",
            "position",
            "origin",
            "destination",
            "path",
            "is_complete",
            "calculated_loss_db",
            "actual_loss_db",
            "wavelength_nm",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "position", "is_complete")


class FiberCircuitNodeSerializer(serializers.ModelSerializer):
    """Serializer for FiberCircuitNode model."""

    class Meta:
        model = FiberCircuitNode
        fields = ("id", "path", "position", "cable", "front_port", "rear_port", "fiber_strand", "splice_entry")
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Splice toolkit serializers
# ---------------------------------------------------------------------------


class ClosureStrandSerializer(serializers.Serializer):
    """Serializer for strands grouped by cable/tube for the splice editor."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    position = serializers.IntegerField()
    color = serializers.CharField()
    front_port_a_id = serializers.IntegerField(allow_null=True)
    live_spliced_to = serializers.IntegerField(allow_null=True)
    plan_entry_id = serializers.IntegerField(allow_null=True)
    plan_spliced_to = serializers.IntegerField(allow_null=True)


class TubeGroupSerializer(serializers.Serializer):
    """Serializer for a buffer tube and its contained strands."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    color = serializers.CharField()
    strands = ClosureStrandSerializer(many=True)


class CableGroupSerializer(serializers.Serializer):
    """Serializer for a fiber cable's tubes and loose strands."""

    fiber_cable_id = serializers.IntegerField()
    cable_label = serializers.CharField()
    tubes = TubeGroupSerializer(many=True)
    loose_strands = ClosureStrandSerializer(many=True)
