from dcim.choices import CableLengthUnitChoices, PortTypeChoices
from dcim.models import (
    Cable,
    Device,
    DeviceType,
    FrontPort,
    FrontPortTemplate,
    Location,
    Manufacturer,
    Module,
    RearPort,
    Site,
)
from django import forms
from django.utils.translation import gettext_lazy as _
from netbox.forms import (
    NetBoxModelBulkEditForm,
    NetBoxModelFilterSetForm,
    NetBoxModelForm,
    NetBoxModelImportForm,
)
from tenancy.models import Tenant
from utilities.forms.fields import (
    ColorField,
    CommentField,
    DynamicModelChoiceField,
    DynamicModelMultipleChoiceField,
)
from utilities.forms.rendering import FieldSet

from .choices import (
    CableElementTypeChoices,
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
    BufferTubeTemplate,
    CableElementTemplate,
    ClosureCableEntry,
    FiberCable,
    FiberCableType,
    FiberCircuit,
    FiberCircuitPath,
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

# ---------------------------------------------------------------------------
# FiberCableType
# ---------------------------------------------------------------------------


class FiberCableTypeForm(NetBoxModelForm):
    """Form for creating/editing a FiberCableType."""

    manufacturer = DynamicModelChoiceField(
        queryset=Manufacturer.objects.all(),
        label=_("Manufacturer"),
    )
    jacket_color = ColorField(required=False, label=_("Jacket Color"))
    comments = CommentField()

    fieldsets = (
        FieldSet("manufacturer", "model", "part_number", name=_("Cable Type")),
        FieldSet("construction", "fiber_type", "strand_count", name=_("Fiber Properties")),
        FieldSet("sheath_material", "jacket_color", name=_("Sheath / Jacket")),
        FieldSet("is_armored", "armor_type", name=_("Armor")),
        FieldSet("deployment", "fire_rating", name=_("Deployment & Rating")),
        FieldSet("construction_image", "notes", "tags", name=_("Additional")),
    )

    class Meta:
        model = FiberCableType
        fields = (
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
            "construction_image",
            "notes",
            "tags",
        )


class FiberCableTypeImportForm(NetBoxModelImportForm):
    """Import form for FiberCableType."""

    manufacturer = DynamicModelChoiceField(queryset=Manufacturer.objects.all())
    construction = forms.ChoiceField(choices=ConstructionChoices)
    fiber_type = forms.ChoiceField(choices=FiberTypeChoices)

    class Meta:
        model = FiberCableType
        fields = (
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
            "tags",
        )


class FiberCableTypeBulkEditForm(NetBoxModelBulkEditForm):
    """Bulk edit form for FiberCableType."""

    model = FiberCableType

    manufacturer = DynamicModelChoiceField(queryset=Manufacturer.objects.all(), required=False)
    construction = forms.ChoiceField(choices=ConstructionChoices, required=False)
    fiber_type = forms.ChoiceField(choices=FiberTypeChoices, required=False)
    sheath_material = forms.ChoiceField(choices=SheathMaterialChoices, required=False)
    deployment = forms.ChoiceField(choices=DeploymentChoices, required=False)
    fire_rating = forms.ChoiceField(choices=FireRatingChoices, required=False)

    fieldsets = (
        FieldSet("manufacturer", "construction", "fiber_type"),
        FieldSet("sheath_material", "deployment", "fire_rating"),
    )
    nullable_fields = ("sheath_material", "deployment", "fire_rating")


class FiberCableTypeFilterForm(NetBoxModelFilterSetForm):
    """Filter form for FiberCableType."""

    model = FiberCableType

    manufacturer_id = DynamicModelMultipleChoiceField(
        queryset=Manufacturer.objects.all(),
        required=False,
        label=_("Manufacturer"),
    )
    construction = forms.MultipleChoiceField(choices=ConstructionChoices, required=False)
    fiber_type = forms.MultipleChoiceField(choices=FiberTypeChoices, required=False)
    sheath_material = forms.MultipleChoiceField(choices=SheathMaterialChoices, required=False)
    is_armored = forms.NullBooleanField(required=False, label=_("Armored"))
    deployment = forms.MultipleChoiceField(choices=DeploymentChoices, required=False)
    fire_rating = forms.MultipleChoiceField(choices=FireRatingChoices, required=False)

    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("manufacturer_id", "construction", "fiber_type", name=_("Properties")),
        FieldSet("sheath_material", "is_armored", "deployment", "fire_rating", name=_("Physical")),
    )


# ---------------------------------------------------------------------------
# BufferTubeTemplate
# ---------------------------------------------------------------------------


class BufferTubeTemplateForm(NetBoxModelForm):
    """Form for creating/editing a BufferTubeTemplate."""

    fiber_cable_type = DynamicModelChoiceField(
        queryset=FiberCableType.objects.all(),
        label=_("Fiber Cable Type"),
    )
    color = ColorField(required=False)
    stripe_color = ColorField(required=False)

    fieldsets = (
        FieldSet(
            "fiber_cable_type",
            "name",
            "position",
            "color",
            "stripe_color",
            "fiber_count",
            "description",
            name=_("Buffer Tube"),
        ),
        FieldSet("tags", name=_("Additional")),
    )

    class Meta:
        model = BufferTubeTemplate
        fields = ("fiber_cable_type", "name", "position", "color", "stripe_color", "fiber_count", "description", "tags")


class BufferTubeTemplateBulkEditForm(NetBoxModelBulkEditForm):
    """Bulk edit form for BufferTubeTemplate."""

    model = BufferTubeTemplate

    color = ColorField(required=False)
    stripe_color = ColorField(required=False)
    fiber_count = forms.IntegerField(required=False)

    fieldsets = (FieldSet("color", "stripe_color", "fiber_count"),)
    nullable_fields = ("color", "stripe_color")


# ---------------------------------------------------------------------------
# RibbonTemplate
# ---------------------------------------------------------------------------


class RibbonTemplateForm(NetBoxModelForm):
    """Form for creating/editing a RibbonTemplate."""

    fiber_cable_type = DynamicModelChoiceField(
        queryset=FiberCableType.objects.all(),
        label=_("Fiber Cable Type"),
    )
    buffer_tube_template = DynamicModelChoiceField(
        queryset=BufferTubeTemplate.objects.all(),
        required=False,
        label=_("Buffer Tube Template"),
        query_params={"fiber_cable_type_id": "$fiber_cable_type"},
    )
    color = ColorField(required=False)
    stripe_color = ColorField(required=False)

    fieldsets = (
        FieldSet(
            "fiber_cable_type",
            "buffer_tube_template",
            "name",
            "position",
            "color",
            "stripe_color",
            "fiber_count",
            "description",
            name=_("Ribbon Template"),
        ),
        FieldSet("tags", name=_("Additional")),
    )

    class Meta:
        model = RibbonTemplate
        fields = (
            "fiber_cable_type",
            "buffer_tube_template",
            "name",
            "position",
            "color",
            "stripe_color",
            "fiber_count",
            "description",
            "tags",
        )


class RibbonTemplateBulkEditForm(NetBoxModelBulkEditForm):
    """Bulk edit form for RibbonTemplate."""

    model = RibbonTemplate

    color = ColorField(required=False)
    stripe_color = ColorField(required=False)
    fiber_count = forms.IntegerField(required=False)

    fieldsets = (FieldSet("color", "stripe_color", "fiber_count"),)
    nullable_fields = ("color", "stripe_color")


# ---------------------------------------------------------------------------
# CableElementTemplate
# ---------------------------------------------------------------------------


class CableElementTemplateForm(NetBoxModelForm):
    """Form for creating/editing a CableElementTemplate."""

    fiber_cable_type = DynamicModelChoiceField(
        queryset=FiberCableType.objects.all(),
        label=_("Fiber Cable Type"),
    )

    fieldsets = (
        FieldSet("fiber_cable_type", "name", "element_type", "description", name=_("Cable Element")),
        FieldSet("tags", name=_("Additional")),
    )

    class Meta:
        model = CableElementTemplate
        fields = ("fiber_cable_type", "name", "element_type", "description", "tags")


class CableElementTemplateBulkEditForm(NetBoxModelBulkEditForm):
    """Bulk edit form for CableElementTemplate."""

    model = CableElementTemplate

    element_type = forms.ChoiceField(choices=CableElementTypeChoices, required=False)

    fieldsets = (FieldSet("element_type"),)
    nullable_fields = ()


# ---------------------------------------------------------------------------
# FiberCable (instance)
# ---------------------------------------------------------------------------


class FiberCableForm(NetBoxModelForm):
    """Form for creating/editing a FiberCable."""

    cable = DynamicModelChoiceField(queryset=Cable.objects.all(), label=_("Cable"))
    fiber_cable_type = DynamicModelChoiceField(
        queryset=FiberCableType.objects.all(),
        label=_("Fiber Cable Type"),
    )
    comments = CommentField()

    fieldsets = (
        FieldSet("cable", "fiber_cable_type", name=_("Fiber Cable")),
        FieldSet("serial_number", "install_date", name=_("Identification")),
        FieldSet("notes", "tags", name=_("Additional")),
    )

    class Meta:
        model = FiberCable
        fields = ("cable", "fiber_cable_type", "serial_number", "install_date", "notes", "tags")


class FiberCableImportForm(NetBoxModelImportForm):
    """Import form for FiberCable."""

    cable = DynamicModelChoiceField(queryset=Cable.objects.all())
    fiber_cable_type = DynamicModelChoiceField(queryset=FiberCableType.objects.all())

    class Meta:
        model = FiberCable
        fields = ("cable", "fiber_cable_type", "serial_number", "install_date", "notes", "tags")


class FiberCableBulkEditForm(NetBoxModelBulkEditForm):
    """Bulk edit form for FiberCable."""

    model = FiberCable

    fiber_cable_type = DynamicModelChoiceField(queryset=FiberCableType.objects.all(), required=False)
    install_date = forms.DateField(required=False)

    fieldsets = (FieldSet("fiber_cable_type", "install_date"),)
    nullable_fields = ("install_date",)


class FiberCableFilterForm(NetBoxModelFilterSetForm):
    """Filter form for FiberCable."""

    model = FiberCable

    fiber_cable_type_id = DynamicModelMultipleChoiceField(
        queryset=FiberCableType.objects.all(),
        required=False,
        label=_("Fiber Cable Type"),
    )

    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("fiber_cable_type_id", name=_("Attributes")),
    )


# ---------------------------------------------------------------------------
# SpliceProject
# ---------------------------------------------------------------------------


class SpliceProjectForm(NetBoxModelForm):
    """Form for creating/editing a SpliceProject."""

    comments = CommentField()

    fieldsets = (
        FieldSet("name", "description", name=_("Splice Project")),
        FieldSet("tags", name=_("Additional")),
    )

    class Meta:
        model = SpliceProject
        fields = ("name", "description", "tags")


class SpliceProjectImportForm(NetBoxModelImportForm):
    """Import form for SpliceProject."""

    class Meta:
        model = SpliceProject
        fields = ("name", "description")


class SpliceProjectBulkEditForm(NetBoxModelBulkEditForm):
    """Bulk edit form for SpliceProject."""

    model = SpliceProject
    description = forms.CharField(required=False)
    fieldsets = (FieldSet("description"),)
    nullable_fields = ("description",)


class SpliceProjectFilterForm(NetBoxModelFilterSetForm):
    """Filter form for SpliceProject."""

    model = SpliceProject
    fieldsets = (FieldSet("q", "filter_id", "tag"),)


# ---------------------------------------------------------------------------
# SplicePlan
# ---------------------------------------------------------------------------


class SplicePlanForm(NetBoxModelForm):
    """Form for creating/editing a SplicePlan."""

    closure = DynamicModelChoiceField(queryset=Device.objects.all(), label=_("Closure"))
    project = DynamicModelChoiceField(
        queryset=SpliceProject.objects.all(),
        required=False,
        label=_("Project"),
    )
    comments = CommentField()

    fieldsets = (
        FieldSet("closure", "name", "description", "project", name=_("Splice Plan")),
        FieldSet("status", name=_("Configuration")),
        FieldSet("tags", name=_("Additional")),
    )

    class Meta:
        model = SplicePlan
        fields = ("closure", "name", "description", "project", "status", "tags")


class SplicePlanImportForm(NetBoxModelImportForm):
    """Import form for SplicePlan."""

    closure = DynamicModelChoiceField(queryset=Device.objects.all())
    status = forms.ChoiceField(choices=SplicePlanStatusChoices)

    class Meta:
        model = SplicePlan
        fields = ("closure", "name", "description", "status", "tags")


class SplicePlanBulkEditForm(NetBoxModelBulkEditForm):
    """Bulk edit form for SplicePlan."""

    model = SplicePlan

    status = forms.ChoiceField(choices=SplicePlanStatusChoices, required=False)

    fieldsets = (FieldSet("status"),)
    nullable_fields = ()


class SplicePlanFilterForm(NetBoxModelFilterSetForm):
    """Filter form for SplicePlan."""

    model = SplicePlan

    closure_id = DynamicModelMultipleChoiceField(
        queryset=Device.objects.all(),
        required=False,
        label=_("Closure"),
    )
    status = forms.MultipleChoiceField(choices=SplicePlanStatusChoices, required=False)

    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("closure_id", "status", name=_("Attributes")),
    )


# ---------------------------------------------------------------------------
# SplicePlanEntry
# ---------------------------------------------------------------------------


class SplicePlanEntryForm(NetBoxModelForm):
    """Form for creating/editing a SplicePlanEntry."""

    plan = DynamicModelChoiceField(queryset=SplicePlan.objects.all(), label=_("Plan"))
    tray = DynamicModelChoiceField(queryset=Module.objects.all(), label=_("Tray"))
    fiber_a = DynamicModelChoiceField(queryset=FrontPort.objects.all(), label=_("Fiber A"))
    fiber_b = DynamicModelChoiceField(queryset=FrontPort.objects.all(), label=_("Fiber B"))

    fieldsets = (
        FieldSet("plan", "tray", "fiber_a", "fiber_b", name=_("Splice Entry")),
        FieldSet("notes", name=_("Notes")),
        FieldSet("tags", name=_("Additional")),
    )

    class Meta:
        model = SplicePlanEntry
        fields = ("plan", "tray", "fiber_a", "fiber_b", "notes", "is_express", "tags")


class SplicePlanEntryFilterForm(NetBoxModelFilterSetForm):
    """Filter form for SplicePlanEntry."""

    model = SplicePlanEntry

    plan_id = DynamicModelMultipleChoiceField(
        queryset=SplicePlan.objects.all(),
        required=False,
        label=_("Plan"),
    )

    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("plan_id", name=_("Attributes")),
    )


# ---------------------------------------------------------------------------
# ClosureCableEntry
# ---------------------------------------------------------------------------


class ClosureCableEntryForm(NetBoxModelForm):
    """Form for creating/editing a ClosureCableEntry."""

    closure = DynamicModelChoiceField(queryset=Device.objects.all(), label=_("Closure"))
    fiber_cable = DynamicModelChoiceField(queryset=FiberCable.objects.all(), label=_("Fiber Cable"))

    fieldsets = (
        FieldSet("closure", "fiber_cable", "entrance_label", name=_("Cable Entry")),
        FieldSet("notes", name=_("Notes")),
        FieldSet("tags", name=_("Additional")),
    )

    class Meta:
        model = ClosureCableEntry
        fields = ("closure", "fiber_cable", "entrance_label", "notes", "tags")


class ClosureCableEntryFilterForm(NetBoxModelFilterSetForm):
    """Filter form for ClosureCableEntry."""

    model = ClosureCableEntry
    closure_id = DynamicModelMultipleChoiceField(
        queryset=Device.objects.all(),
        required=False,
        label=_("Closure"),
    )
    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("closure_id", name=_("Attributes")),
    )


# ---------------------------------------------------------------------------
# SlackLoop
# ---------------------------------------------------------------------------


class SlackLoopForm(NetBoxModelForm):
    """Form for creating/editing a SlackLoop."""

    fiber_cable = DynamicModelChoiceField(queryset=FiberCable.objects.all(), label=_("Fiber Cable"))
    site = DynamicModelChoiceField(queryset=Site.objects.all(), label=_("Site"))
    location = DynamicModelChoiceField(
        queryset=Location.objects.all(),
        required=False,
        label=_("Location"),
        query_params={"site_id": "$site"},
    )

    fieldsets = (
        FieldSet("fiber_cable", "site", "location", name=_("Slack Loop")),
        FieldSet("start_mark", "end_mark", "length_unit", name=_("Position")),
        FieldSet("storage_method", name=_("Storage")),
        FieldSet("notes", "tags", name=_("Additional")),
    )

    class Meta:
        model = SlackLoop
        fields = (
            "fiber_cable",
            "site",
            "location",
            "start_mark",
            "end_mark",
            "length_unit",
            "storage_method",
            "notes",
            "tags",
        )


class SlackLoopImportForm(NetBoxModelImportForm):
    """Import form for SlackLoop."""

    fiber_cable = DynamicModelChoiceField(queryset=FiberCable.objects.all())
    length_unit = forms.ChoiceField(choices=CableLengthUnitChoices)
    storage_method = forms.ChoiceField(choices=StorageMethodChoices, required=False)

    class Meta:
        model = SlackLoop
        fields = (
            "fiber_cable",
            "site",
            "location",
            "start_mark",
            "end_mark",
            "length_unit",
            "storage_method",
            "notes",
        )


class SlackLoopBulkEditForm(NetBoxModelBulkEditForm):
    """Bulk edit form for SlackLoop."""

    model = SlackLoop

    site = DynamicModelChoiceField(queryset=Site.objects.all(), required=False)
    location = DynamicModelChoiceField(queryset=Location.objects.all(), required=False)
    length_unit = forms.ChoiceField(choices=CableLengthUnitChoices, required=False)
    storage_method = forms.ChoiceField(choices=StorageMethodChoices, required=False)

    fieldsets = (FieldSet("site", "location", "length_unit", "storage_method"),)
    nullable_fields = ("location", "storage_method")


class SlackLoopFilterForm(NetBoxModelFilterSetForm):
    """Filter form for SlackLoop."""

    model = SlackLoop

    fiber_cable_id = DynamicModelMultipleChoiceField(
        queryset=FiberCable.objects.all(),
        required=False,
        label=_("Fiber Cable"),
    )
    site_id = DynamicModelMultipleChoiceField(
        queryset=Site.objects.all(),
        required=False,
        label=_("Site"),
    )
    location_id = DynamicModelMultipleChoiceField(
        queryset=Location.objects.all(),
        required=False,
        label=_("Location"),
    )
    length_unit = forms.MultipleChoiceField(choices=CableLengthUnitChoices, required=False)
    storage_method = forms.MultipleChoiceField(choices=StorageMethodChoices, required=False)

    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("fiber_cable_id", "site_id", "location_id", name=_("Location")),
        FieldSet("length_unit", "storage_method", name=_("Attributes")),
    )


# ---------------------------------------------------------------------------
# Provision Ports
# ---------------------------------------------------------------------------


class ProvisionPortsForm(forms.Form):
    """Form for provisioning front/rear ports on a device for a fiber cable."""

    fiber_cable = DynamicModelChoiceField(
        queryset=FiberCable.objects.all(),
        label=_("Fiber Cable"),
    )
    device = DynamicModelChoiceField(
        queryset=Device.objects.all(),
        label=_("Device"),
        help_text=_("The device (closure/panel) to provision ports on."),
    )
    port_type = forms.ChoiceField(
        choices=PortTypeChoices,
        label=_("Port Type"),
        initial="splice",
        help_text=_("Defaults to Splice. Override for special cases like MPO cassettes."),
    )

    fieldsets = (
        FieldSet("fiber_cable", "device", name=_("Provision Ports")),
        FieldSet("port_type", name=_("Advanced")),
    )


# ---------------------------------------------------------------------------
# FiberCircuit
# ---------------------------------------------------------------------------


class FiberCircuitForm(NetBoxModelForm):
    """Form for creating/editing a FiberCircuit."""

    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)
    comments = CommentField()

    fieldsets = (
        FieldSet("name", "cid", "status", "strand_count", "tenant", name=_("Circuit")),
        FieldSet("description", "comments", "tags", name=_("Additional")),
    )

    class Meta:
        model = FiberCircuit
        fields = ("name", "cid", "status", "strand_count", "tenant", "description", "comments", "tags")


class FiberCircuitImportForm(NetBoxModelImportForm):
    """Import form for FiberCircuit."""

    class Meta:
        model = FiberCircuit
        fields = ("name", "cid", "status", "strand_count", "description", "comments")


class FiberCircuitBulkEditForm(NetBoxModelBulkEditForm):
    """Bulk edit form for FiberCircuit."""

    model = FiberCircuit

    status = forms.ChoiceField(choices=FiberCircuitStatusChoices, required=False)
    strand_count = forms.IntegerField(required=False)
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)
    description = forms.CharField(required=False)

    fieldsets = (
        FieldSet("status", "strand_count", "tenant", name=_("Circuit")),
        FieldSet("description", name=_("Additional")),
    )
    nullable_fields = ("tenant", "description")


class FiberCircuitFilterForm(NetBoxModelFilterSetForm):
    """Filter form for FiberCircuit."""

    model = FiberCircuit

    status = forms.MultipleChoiceField(choices=FiberCircuitStatusChoices, required=False)
    tenant_id = DynamicModelMultipleChoiceField(
        queryset=Tenant.objects.all(),
        required=False,
        label=_("Tenant"),
    )

    fieldsets = (FieldSet("q", "status", "tenant_id"),)


# ---------------------------------------------------------------------------
# FiberCircuitPath
# ---------------------------------------------------------------------------


class FiberCircuitPathForm(NetBoxModelForm):
    """Form for creating/editing a FiberCircuitPath."""

    circuit = DynamicModelChoiceField(
        queryset=FiberCircuit.objects.all(),
        label=_("Circuit"),
    )

    fieldsets = (
        FieldSet("circuit", "position", "origin", "destination", name=_("Path")),
        FieldSet("calculated_loss_db", "actual_loss_db", "wavelength_nm", name=_("Optical Parameters")),
        FieldSet("tags", name=_("Additional")),
    )

    class Meta:
        model = FiberCircuitPath
        fields = (
            "circuit",
            "position",
            "origin",
            "destination",
            "calculated_loss_db",
            "actual_loss_db",
            "wavelength_nm",
            "tags",
        )


class FiberCircuitPathFilterForm(NetBoxModelFilterSetForm):
    """Filter form for FiberCircuitPath."""

    model = FiberCircuitPath
    circuit_id = DynamicModelChoiceField(
        queryset=FiberCircuit.objects.all(),
        required=False,
        label=_("Circuit"),
    )
    is_complete = forms.NullBooleanField(required=False, label=_("Complete"))


# ---------------------------------------------------------------------------
# Provision Ports / Link Topology
# ---------------------------------------------------------------------------


class LinkTopologyForm(forms.Form):
    """Form for selecting a cable type and port type for link topology preview."""

    fiber_cable_type = DynamicModelChoiceField(
        queryset=FiberCableType.objects.all(),
        label=_("Fiber Cable Type"),
    )
    port_type = forms.ChoiceField(
        choices=PortTypeChoices,
        initial="splice",
        label=_("Port Type"),
        required=False,
    )


# ---------------------------------------------------------------------------
# Insert Slack Loop into Closure
# ---------------------------------------------------------------------------


class InsertSlackLoopForm(forms.Form):
    """Form for the 'Insert into Splice Closure' workflow."""

    closure = DynamicModelChoiceField(
        queryset=Device.objects.all(),
        label=_("Closure"),
        help_text=_("Target splice closure device."),
    )
    a_side_rear_ports = DynamicModelMultipleChoiceField(
        queryset=RearPort.objects.all(),
        label=_("A-side Rear Ports"),
        help_text=_("Closure RearPorts for the A-side cable segment."),
        query_params={"device_id": "$closure"},
    )
    b_side_rear_ports = DynamicModelMultipleChoiceField(
        queryset=RearPort.objects.all(),
        label=_("B-side Rear Ports"),
        help_text=_("Closure RearPorts for the B-side cable segment."),
        query_params={"device_id": "$closure"},
    )
    express_strand_positions = forms.CharField(
        required=False,
        label=_("Express Strand Positions"),
        help_text=_("Comma-separated strand positions that pass through without splicing (e.g., '1,2,3')."),
    )

    def clean_express_strand_positions(self):
        value = self.cleaned_data.get("express_strand_positions", "")
        if not value.strip():
            return set()
        try:
            return {int(x.strip()) for x in value.split(",") if x.strip()}
        except ValueError as err:
            raise forms.ValidationError(_("Enter comma-separated integers.")) from err


# ---------------------------------------------------------------------------
# WDM Device Type Profile
# ---------------------------------------------------------------------------


class WdmDeviceTypeProfileForm(NetBoxModelForm):
    """Form for creating/editing a WdmDeviceTypeProfile."""

    device_type = DynamicModelChoiceField(
        queryset=DeviceType.objects.all(),
        label=_("Device Type"),
    )
    comments = CommentField()

    fieldsets = (
        FieldSet("device_type", "node_type", "grid", name=_("WDM Profile")),
        FieldSet("description", "tags", name=_("Additional")),
    )

    class Meta:
        model = WdmDeviceTypeProfile
        fields = ("device_type", "node_type", "grid", "description", "tags")


class WdmDeviceTypeProfileFilterForm(NetBoxModelFilterSetForm):
    """Filter form for WdmDeviceTypeProfile."""

    model = WdmDeviceTypeProfile

    node_type = forms.MultipleChoiceField(choices=WdmNodeTypeChoices, required=False)
    grid = forms.MultipleChoiceField(choices=WdmGridChoices, required=False)

    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("node_type", "grid", name=_("Attributes")),
    )


class WdmDeviceTypeProfileImportForm(NetBoxModelImportForm):
    """Import form for WdmDeviceTypeProfile."""

    device_type = DynamicModelChoiceField(queryset=DeviceType.objects.all())
    node_type = forms.ChoiceField(choices=WdmNodeTypeChoices)
    grid = forms.ChoiceField(choices=WdmGridChoices)

    class Meta:
        model = WdmDeviceTypeProfile
        fields = ("device_type", "node_type", "grid", "description")


# ---------------------------------------------------------------------------
# WDM Channel Template
# ---------------------------------------------------------------------------


class WdmChannelTemplateForm(NetBoxModelForm):
    """Form for creating/editing a WdmChannelTemplate."""

    profile = DynamicModelChoiceField(
        queryset=WdmDeviceTypeProfile.objects.all(),
        label=_("Profile"),
    )
    front_port_template = DynamicModelChoiceField(
        queryset=FrontPortTemplate.objects.all(),
        required=False,
        label=_("Front Port Template"),
    )

    fieldsets = (
        FieldSet(
            "profile", "grid_position", "wavelength_nm", "label", "front_port_template", name=_("Channel Template")
        ),
        FieldSet("tags", name=_("Additional")),
    )

    class Meta:
        model = WdmChannelTemplate
        fields = ("profile", "grid_position", "wavelength_nm", "label", "front_port_template", "tags")


# ---------------------------------------------------------------------------
# WDM Node
# ---------------------------------------------------------------------------


class WdmNodeForm(NetBoxModelForm):
    """Form for creating/editing a WdmNode."""

    device = DynamicModelChoiceField(
        queryset=Device.objects.all(),
        label=_("Device"),
    )
    comments = CommentField()

    fieldsets = (
        FieldSet("device", "node_type", "grid", name=_("WDM Node")),
        FieldSet("description", "tags", name=_("Additional")),
    )

    class Meta:
        model = WdmNode
        fields = ("device", "node_type", "grid", "description", "tags")


class WdmNodeFilterForm(NetBoxModelFilterSetForm):
    """Filter form for WdmNode."""

    model = WdmNode

    node_type = forms.MultipleChoiceField(choices=WdmNodeTypeChoices, required=False)
    grid = forms.MultipleChoiceField(choices=WdmGridChoices, required=False)

    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("node_type", "grid", name=_("Attributes")),
    )


class WdmNodeImportForm(NetBoxModelImportForm):
    """Import form for WdmNode."""

    device = DynamicModelChoiceField(queryset=Device.objects.all())
    node_type = forms.ChoiceField(choices=WdmNodeTypeChoices)
    grid = forms.ChoiceField(choices=WdmGridChoices)

    class Meta:
        model = WdmNode
        fields = ("device", "node_type", "grid", "description")


# ---------------------------------------------------------------------------
# WDM Trunk Port
# ---------------------------------------------------------------------------


class WdmTrunkPortForm(NetBoxModelForm):
    """Form for creating/editing a WdmTrunkPort."""

    wdm_node = DynamicModelChoiceField(
        queryset=WdmNode.objects.all(),
        label=_("WDM Node"),
    )
    rear_port = DynamicModelChoiceField(
        queryset=RearPort.objects.all(),
        label=_("Rear Port"),
    )

    fieldsets = (
        FieldSet("wdm_node", "rear_port", "direction", "position", name=_("Trunk Port")),
        FieldSet("tags", name=_("Additional")),
    )

    class Meta:
        model = WdmTrunkPort
        fields = ("wdm_node", "rear_port", "direction", "position", "tags")


# ---------------------------------------------------------------------------
# Wavelength Channel
# ---------------------------------------------------------------------------


class WavelengthChannelForm(NetBoxModelForm):
    """Form for creating/editing a WavelengthChannel."""

    wdm_node = DynamicModelChoiceField(
        queryset=WdmNode.objects.all(),
        label=_("WDM Node"),
    )
    front_port = DynamicModelChoiceField(
        queryset=FrontPort.objects.all(),
        required=False,
        label=_("Front Port"),
    )

    fieldsets = (
        FieldSet("wdm_node", "grid_position", "wavelength_nm", "label", "front_port", "status", name=_("Channel")),
        FieldSet("tags", name=_("Additional")),
    )

    class Meta:
        model = WavelengthChannel
        fields = ("wdm_node", "grid_position", "wavelength_nm", "label", "front_port", "status", "tags")


class WavelengthChannelBulkEditForm(NetBoxModelBulkEditForm):
    """Bulk edit form for WavelengthChannel."""

    model = WavelengthChannel

    status = forms.ChoiceField(choices=WavelengthChannelStatusChoices, required=False)

    fieldsets = (FieldSet("status"),)
    nullable_fields = ()


class WavelengthChannelFilterForm(NetBoxModelFilterSetForm):
    """Filter form for WavelengthChannel."""

    model = WavelengthChannel

    status = forms.MultipleChoiceField(choices=WavelengthChannelStatusChoices, required=False)
    wdm_node_id = DynamicModelMultipleChoiceField(
        queryset=WdmNode.objects.all(),
        required=False,
        label=_("WDM Node"),
    )

    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("wdm_node_id", "status", name=_("Attributes")),
    )


# ---------------------------------------------------------------------------
# Wavelength Service
# ---------------------------------------------------------------------------


class WavelengthServiceForm(NetBoxModelForm):
    """Form for creating/editing a WavelengthService."""

    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)
    comments = CommentField()

    fieldsets = (
        FieldSet("name", "status", "wavelength_nm", "tenant", name=_("Service")),
        FieldSet("description", "comments", "tags", name=_("Additional")),
    )

    class Meta:
        model = WavelengthService
        fields = ("name", "status", "wavelength_nm", "tenant", "description", "comments", "tags")


class WavelengthServiceFilterForm(NetBoxModelFilterSetForm):
    """Filter form for WavelengthService."""

    model = WavelengthService

    status = forms.MultipleChoiceField(choices=WavelengthServiceStatusChoices, required=False)
    tenant_id = DynamicModelMultipleChoiceField(
        queryset=Tenant.objects.all(),
        required=False,
        label=_("Tenant"),
    )

    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("status", "tenant_id", name=_("Attributes")),
    )


class WavelengthServiceImportForm(NetBoxModelImportForm):
    """Import form for WavelengthService."""

    status = forms.ChoiceField(choices=WavelengthServiceStatusChoices)

    class Meta:
        model = WavelengthService
        fields = ("name", "status", "wavelength_nm", "description", "comments")
