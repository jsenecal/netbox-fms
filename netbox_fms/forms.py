from dcim.choices import (
    CableLengthUnitChoices,
    CableTypeChoices,
    DeviceStatusChoices,
    LinkStatusChoices,
    PortTypeChoices,
)
from dcim.models import (
    Cable,
    Device,
    DeviceRole,
    DeviceType,
    FrontPort,
    Location,
    Manufacturer,
    Module,
    ModuleType,
    RearPort,
    Site,
)
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from netbox.forms import (
    NetBoxModelBulkEditForm,
    NetBoxModelFilterSetForm,
    NetBoxModelForm,
    NetBoxModelImportForm,
)
from tenancy.models import Tenant
from utilities.choices import unpack_grouped_choices
from utilities.forms.fields import (
    ColorField,
    CommentField,
    CSVChoiceField,
    CSVModelChoiceField,
    DynamicModelChoiceField,
    DynamicModelMultipleChoiceField,
)
from utilities.forms.rendering import FieldSet
from utilities.forms.utils import add_blank_choice

from .choices import (
    CableElementTypeChoices,
    ConstructionChoices,
    DeploymentChoices,
    FiberCircuitStatusChoices,
    FiberColorSchemeChoices,
    FireRatingChoices,
    MarkerTypeChoices,
    SheathMaterialChoices,
    SplicePlanStatusChoices,
    StorageMethodChoices,
    TrayRoleChoices,
)
from .constants import FIBER_CABLE_TYPES, get_grouped_color_choices
from .models import (
    BufferTube,
    BufferTubeTemplate,
    CableElementTemplate,
    ClosureCableEntry,
    FiberAttenuationSpec,
    FiberCable,
    FiberCableType,
    FiberCircuit,
    FiberCircuitPath,
    RibbonTemplate,
    SlackLoop,
    SplicePlan,
    SplicePlanEntry,
    SpliceProject,
    TrayProfile,
    TubeAssignment,
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
    strand_marker_color = ColorField(required=False)
    comments = CommentField()

    fieldsets = (
        FieldSet("manufacturer", "model", "part_number", name=_("Cable Type")),
        FieldSet("construction", "strand_count", "color_scheme", name=_("Cable Construction")),
        FieldSet("outer_diameter", "twist_factor_ratio", "mark_unit", name=_("Physical")),
        FieldSet("sheath_material", "jacket_color", name=_("Sheath / Jacket")),
        FieldSet("is_armored", "armor_type", name=_("Armor")),
        FieldSet("deployment", "fire_rating", name=_("Deployment & Rating")),
        FieldSet(
            "strand_marker_interval",
            "strand_marker_color",
            "strand_marker_type",
            name=_("Strand Markers (Tight Buffer)"),
        ),
        FieldSet("construction_image", "notes", "tags", name=_("Additional")),
    )

    class Meta:
        model = FiberCableType
        fields = (
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
            "construction_image",
            "notes",
            "tags",
        )


class FiberCableTypeImportForm(NetBoxModelImportForm):
    """Import form for FiberCableType."""

    manufacturer = DynamicModelChoiceField(queryset=Manufacturer.objects.all())
    construction = CSVChoiceField(choices=ConstructionChoices)
    color_scheme = CSVChoiceField(choices=FiberColorSchemeChoices, required=False)

    def clean_color_scheme(self):
        return self.cleaned_data.get("color_scheme") or FiberColorSchemeChoices.EIA_598

    class Meta:
        model = FiberCableType
        fields = (
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
            "notes",
            "tags",
        )


class FiberCableTypeBulkEditForm(NetBoxModelBulkEditForm):
    """Bulk edit form for FiberCableType."""

    model = FiberCableType

    manufacturer = DynamicModelChoiceField(queryset=Manufacturer.objects.all(), required=False)
    construction = forms.ChoiceField(choices=add_blank_choice(ConstructionChoices), required=False)
    color_scheme = forms.ChoiceField(choices=add_blank_choice(FiberColorSchemeChoices), required=False)
    sheath_material = forms.ChoiceField(choices=add_blank_choice(SheathMaterialChoices), required=False)
    deployment = forms.ChoiceField(choices=add_blank_choice(DeploymentChoices), required=False)
    fire_rating = forms.ChoiceField(choices=add_blank_choice(FireRatingChoices), required=False)
    outer_diameter = forms.FloatField(required=False, label=_("Outer diameter (mm)"))
    twist_factor_ratio = forms.FloatField(required=False, label=_("Twist factor ratio"))
    mark_unit = forms.ChoiceField(choices=add_blank_choice(CableLengthUnitChoices), required=False)

    fieldsets = (
        FieldSet("manufacturer", "construction", "color_scheme"),
        FieldSet("outer_diameter", "twist_factor_ratio", "mark_unit", name=_("Physical")),
        FieldSet("sheath_material", "deployment", "fire_rating"),
    )
    nullable_fields = (
        "sheath_material",
        "deployment",
        "fire_rating",
        "outer_diameter",
        "twist_factor_ratio",
        "mark_unit",
    )


class FiberCableTypeFilterForm(NetBoxModelFilterSetForm):
    """Filter form for FiberCableType."""

    model = FiberCableType

    manufacturer_id = DynamicModelMultipleChoiceField(
        queryset=Manufacturer.objects.all(),
        required=False,
        label=_("Manufacturer"),
    )
    construction = forms.MultipleChoiceField(choices=ConstructionChoices, required=False)
    color_scheme = forms.MultipleChoiceField(choices=FiberColorSchemeChoices, required=False)
    sheath_material = forms.MultipleChoiceField(choices=SheathMaterialChoices, required=False)
    is_armored = forms.NullBooleanField(required=False, label=_("Armored"))
    deployment = forms.MultipleChoiceField(choices=DeploymentChoices, required=False)
    fire_rating = forms.MultipleChoiceField(choices=FireRatingChoices, required=False)

    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("manufacturer_id", "construction", "color_scheme", name=_("Properties")),
        FieldSet("sheath_material", "is_armored", "deployment", "fire_rating", name=_("Physical")),
    )


# ---------------------------------------------------------------------------
# FiberAttenuationSpec
# ---------------------------------------------------------------------------


class FiberAttenuationSpecForm(NetBoxModelForm):
    """Form for creating/editing a FiberAttenuationSpec."""

    fiber_cable_type = DynamicModelChoiceField(
        queryset=FiberCableType.objects.all(),
        label=_("Fiber Cable Type"),
    )

    fieldsets = (
        FieldSet("fiber_cable_type", "wavelength_nm", "max_loss_db_per_km", name=_("Attenuation Spec")),
        FieldSet("tags", name=_("Additional")),
    )

    class Meta:
        model = FiberAttenuationSpec
        fields = ("fiber_cable_type", "wavelength_nm", "max_loss_db_per_km", "tags")


class FiberAttenuationSpecImportForm(NetBoxModelImportForm):
    """Import form for FiberAttenuationSpec."""

    fiber_cable_type = DynamicModelChoiceField(queryset=FiberCableType.objects.all())

    class Meta:
        model = FiberAttenuationSpec
        fields = ("fiber_cable_type", "wavelength_nm", "max_loss_db_per_km", "tags")


class FiberAttenuationSpecBulkEditForm(NetBoxModelBulkEditForm):
    """Bulk edit form for FiberAttenuationSpec."""

    model = FiberAttenuationSpec

    max_loss_db_per_km = forms.DecimalField(max_digits=6, decimal_places=4, required=False, label=_("Max loss (dB/km)"))

    fieldsets = (FieldSet("max_loss_db_per_km"),)


class FiberAttenuationSpecFilterForm(NetBoxModelFilterSetForm):
    """Filter form for FiberAttenuationSpec."""

    model = FiberAttenuationSpec

    fiber_cable_type_id = DynamicModelMultipleChoiceField(
        queryset=FiberCableType.objects.all(),
        required=False,
        label=_("Fiber Cable Type"),
    )
    wavelength_nm = forms.IntegerField(required=False, label=_("Wavelength (nm)"))

    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("fiber_cable_type_id", "wavelength_nm", name=_("Spec")),
    )


# ---------------------------------------------------------------------------
# BufferTubeTemplate
# ---------------------------------------------------------------------------


def _apply_scheme_color_choices(form):
    """
    Rebuild the form's ``color`` picker around the parent cable type's
    color scheme. Falls back to showing every known scheme when the parent
    cannot be resolved, and always appends the current off-palette value
    so existing data stays selectable.
    """
    fct = None
    if form.instance.pk:
        fct = form.instance.fiber_cable_type
    else:
        raw = form.data.get("fiber_cable_type") or form.initial.get("fiber_cable_type")
        if raw:
            try:
                fct = FiberCableType.objects.filter(pk=int(getattr(raw, "pk", raw))).first()
            except (TypeError, ValueError):
                fct = None
    choices = get_grouped_color_choices(fct.color_scheme if fct else None)
    current = form["color"].value()
    known = {value for _label, options in choices for value, _l in options}
    if current and current not in known:
        choices.append((_("Current"), [(current, f"#{current}")]))
    form.fields["color"].widget.choices = add_blank_choice(choices)


class BufferTubeTemplateForm(NetBoxModelForm):
    """Form for creating/editing a BufferTubeTemplate."""

    fiber_cable_type = DynamicModelChoiceField(
        queryset=FiberCableType.objects.all(),
        label=_("Fiber Cable Type"),
    )
    color = ColorField(required=False)
    marker_color = ColorField(required=False)
    strand_marker_color = ColorField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_scheme_color_choices(self)

    fieldsets = (
        FieldSet(
            "fiber_cable_type",
            "name",
            "position",
            "color",
            "marker_count",
            "marker_color",
            "marker_type",
            "fiber_count",
            "description",
            name=_("Buffer Tube"),
        ),
        FieldSet(
            "strand_marker_interval",
            "strand_marker_color",
            "strand_marker_type",
            name=_("Strand Markers"),
        ),
        FieldSet("tags", name=_("Additional")),
    )

    class Meta:
        model = BufferTubeTemplate
        fields = (
            "fiber_cable_type",
            "name",
            "position",
            "color",
            "marker_count",
            "marker_color",
            "marker_type",
            "fiber_count",
            "strand_marker_interval",
            "strand_marker_color",
            "strand_marker_type",
            "description",
            "tags",
        )


class BufferTubeTemplateBulkEditForm(NetBoxModelBulkEditForm):
    """Bulk edit form for BufferTubeTemplate."""

    model = BufferTubeTemplate

    color = ColorField(required=False)
    marker_count = forms.IntegerField(required=False)
    marker_color = ColorField(required=False)
    marker_type = forms.ChoiceField(choices=add_blank_choice(MarkerTypeChoices), required=False)
    fiber_count = forms.IntegerField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["color"].widget.choices = add_blank_choice(get_grouped_color_choices())

    fieldsets = (FieldSet("color", "marker_count", "marker_color", "marker_type", "fiber_count"),)
    nullable_fields = ("color", "marker_color", "marker_type")


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
    marker_color = ColorField(required=False)
    strand_marker_color = ColorField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_scheme_color_choices(self)

    fieldsets = (
        FieldSet(
            "fiber_cable_type",
            "buffer_tube_template",
            "name",
            "position",
            "color",
            "marker_count",
            "marker_color",
            "marker_type",
            "fiber_count",
            "description",
            name=_("Ribbon Template"),
        ),
        FieldSet(
            "strand_marker_interval",
            "strand_marker_color",
            "strand_marker_type",
            name=_("Strand Markers"),
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
            "marker_count",
            "marker_color",
            "marker_type",
            "fiber_count",
            "strand_marker_interval",
            "strand_marker_color",
            "strand_marker_type",
            "description",
            "tags",
        )


class RibbonTemplateBulkEditForm(NetBoxModelBulkEditForm):
    """Bulk edit form for RibbonTemplate."""

    model = RibbonTemplate

    color = ColorField(required=False)
    marker_count = forms.IntegerField(required=False)
    marker_color = ColorField(required=False)
    marker_type = forms.ChoiceField(choices=add_blank_choice(MarkerTypeChoices), required=False)
    fiber_count = forms.IntegerField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["color"].widget.choices = add_blank_choice(get_grouped_color_choices())

    fieldsets = (FieldSet("color", "marker_count", "marker_color", "marker_type", "fiber_count"),)
    nullable_fields = ("color", "marker_color", "marker_type")


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

    element_type = forms.ChoiceField(choices=add_blank_choice(CableElementTypeChoices), required=False)

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
    installed_by = DynamicModelChoiceField(
        queryset=Tenant.objects.all(),
        required=False,
        label=_("Installed by"),
        help_text=_("Contractor or workforce that physically installed this cable."),
    )
    comments = CommentField()

    fieldsets = (
        FieldSet("cable", "fiber_cable_type", name=_("Fiber Cable")),
        FieldSet("serial_number", "install_date", "installed_by", name=_("Identification")),
        FieldSet("start_mark", "end_mark", name=_("Sheath Marks")),
        FieldSet("notes", "tags", name=_("Additional")),
    )

    class Meta:
        model = FiberCable
        fields = (
            "cable",
            "fiber_cable_type",
            "serial_number",
            "install_date",
            "installed_by",
            "start_mark",
            "end_mark",
            "notes",
            "tags",
        )


class FiberCableImportForm(NetBoxModelImportForm):
    """Import form for FiberCable."""

    cable = DynamicModelChoiceField(queryset=Cable.objects.all())
    fiber_cable_type = DynamicModelChoiceField(queryset=FiberCableType.objects.all())
    installed_by = CSVModelChoiceField(
        queryset=Tenant.objects.all(),
        to_field_name="name",
        required=False,
        help_text=_("Installer tenant name."),
    )

    class Meta:
        model = FiberCable
        fields = (
            "cable",
            "fiber_cable_type",
            "serial_number",
            "install_date",
            "installed_by",
            "start_mark",
            "end_mark",
            "notes",
            "tags",
        )


class FiberCableBulkEditForm(NetBoxModelBulkEditForm):
    """Bulk edit form for FiberCable."""

    model = FiberCable

    fiber_cable_type = DynamicModelChoiceField(queryset=FiberCableType.objects.all(), required=False)
    install_date = forms.DateField(required=False)
    installed_by = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)

    fieldsets = (FieldSet("fiber_cable_type", "install_date", "installed_by"),)
    nullable_fields = ("install_date", "installed_by")


class FiberCableFilterForm(NetBoxModelFilterSetForm):
    """Filter form for FiberCable."""

    model = FiberCable

    fiber_cable_type_id = DynamicModelMultipleChoiceField(
        queryset=FiberCableType.objects.all(),
        required=False,
        label=_("Fiber Cable Type"),
    )
    installed_by_id = DynamicModelMultipleChoiceField(
        queryset=Tenant.objects.all(),
        required=False,
        label=_("Installed by"),
    )

    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("fiber_cable_type_id", "installed_by_id", name=_("Attributes")),
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
        FieldSet("tags", name=_("Additional")),
    )

    class Meta:
        model = SplicePlan
        fields = ("closure", "name", "description", "project", "tags")


class SplicePlanImportForm(NetBoxModelImportForm):
    """Import form for SplicePlan."""

    closure = DynamicModelChoiceField(queryset=Device.objects.all())

    class Meta:
        model = SplicePlan
        fields = ("closure", "name", "description", "tags")


class SplicePlanBulkEditForm(NetBoxModelBulkEditForm):
    """Bulk edit form for SplicePlan."""

    model = SplicePlan
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
        FieldSet("start_mark", "end_mark", name=_("Position")),
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
            "storage_method",
            "notes",
            "tags",
        )


class SlackLoopImportForm(NetBoxModelImportForm):
    """Import form for SlackLoop."""

    fiber_cable = DynamicModelChoiceField(queryset=FiberCable.objects.all())
    storage_method = CSVChoiceField(choices=StorageMethodChoices, required=False)

    class Meta:
        model = SlackLoop
        fields = (
            "fiber_cable",
            "site",
            "location",
            "start_mark",
            "end_mark",
            "storage_method",
            "notes",
        )


class SlackLoopBulkEditForm(NetBoxModelBulkEditForm):
    """Bulk edit form for SlackLoop."""

    model = SlackLoop

    site = DynamicModelChoiceField(queryset=Site.objects.all(), required=False)
    location = DynamicModelChoiceField(queryset=Location.objects.all(), required=False)
    storage_method = forms.ChoiceField(choices=add_blank_choice(StorageMethodChoices), required=False)

    fieldsets = (FieldSet("site", "location", "storage_method"),)
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
    storage_method = forms.MultipleChoiceField(choices=StorageMethodChoices, required=False)

    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("fiber_cable_id", "site_id", "location_id", name=_("Location")),
        FieldSet("storage_method", name=_("Attributes")),
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

    status = forms.ChoiceField(choices=add_blank_choice(FiberCircuitStatusChoices), required=False)
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
        FieldSet("actual_loss_db", "wavelength_nm", name=_("Optical Parameters")),
        FieldSet("tags", name=_("Additional")),
    )

    class Meta:
        model = FiberCircuitPath
        fields = (
            "circuit",
            "position",
            "origin",
            "destination",
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
# Circuit Wizard
# ---------------------------------------------------------------------------


class CircuitWizardStep1Form(forms.Form):
    """Step 1: Circuit basics."""

    name = forms.CharField(max_length=200, label=_("Circuit Name"))
    cid = forms.CharField(max_length=200, required=False, label=_("Circuit ID"))
    strand_count = forms.IntegerField(min_value=1, initial=1, label=_("Strand Count"))
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False, label=_("Tenant"))


class CircuitWizardStep2Form(forms.Form):
    """Step 2: Select origin and destination devices."""

    origin_device = DynamicModelChoiceField(queryset=Device.objects.all(), label=_("Origin Device"))
    destination_device = DynamicModelChoiceField(queryset=Device.objects.all(), label=_("Destination Device"))

    def clean(self):
        super().clean()
        origin = self.cleaned_data.get("origin_device")
        destination = self.cleaned_data.get("destination_device")
        if origin and destination and origin == destination:
            raise ValidationError(_("Origin and destination must be different devices."))
        return self.cleaned_data


class CircuitWizardStep3Form(forms.Form):
    """Step 3: Pick a route proposal."""

    selected_proposal = forms.IntegerField(widget=forms.RadioSelect, label=_("Select Route"))


class CircuitWizardStep4Form(forms.Form):
    """Step 4: Splice project selection (only when new splices needed)."""

    splice_project = DynamicModelChoiceField(
        queryset=SpliceProject.objects.all(),
        required=False,
        label=_("Existing Splice Project"),
    )
    new_project_name = forms.CharField(
        max_length=100,
        required=False,
        label=_("Or Create New Project"),
        help_text=_("Enter a name to create a new splice project."),
    )


# ---------------------------------------------------------------------------
# Link Topology
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
# TrayProfile
# ---------------------------------------------------------------------------


class TrayProfileForm(NetBoxModelForm):
    """Form for creating/editing a TrayProfile."""

    module_type = DynamicModelChoiceField(queryset=ModuleType.objects.all(), label=_("Module Type"))

    fieldsets = (FieldSet("module_type", "tray_role", "max_fibers", "description", "tags", name=_("Tray Profile")),)

    class Meta:
        model = TrayProfile
        fields = ("module_type", "tray_role", "max_fibers", "description", "tags")


class TrayProfileImportForm(NetBoxModelImportForm):
    """Import form for TrayProfile."""

    class Meta:
        model = TrayProfile
        fields = ("module_type", "tray_role", "description", "tags")


class TrayProfileBulkEditForm(NetBoxModelBulkEditForm):
    """Bulk edit form for TrayProfile."""

    model = TrayProfile
    tray_role = forms.ChoiceField(choices=add_blank_choice(TrayRoleChoices), required=False, label=_("Tray Role"))
    description = forms.CharField(required=False, label=_("Description"))


class TrayProfileFilterForm(NetBoxModelFilterSetForm):
    """Filter form for TrayProfile."""

    model = TrayProfile
    tray_role = forms.MultipleChoiceField(choices=TrayRoleChoices, required=False, label=_("Tray Role"))

    fieldsets = (FieldSet("q", "tray_role", "tag", name=_("Filters")),)


# ---------------------------------------------------------------------------
# TubeAssignment
# ---------------------------------------------------------------------------


class TubeAssignmentForm(NetBoxModelForm):
    """Form for creating/editing a TubeAssignment."""

    closure = DynamicModelChoiceField(queryset=Device.objects.all(), label=_("Closure"))
    tray = DynamicModelChoiceField(
        queryset=Module.objects.all(), label=_("Tray"), query_params={"device_id": "$closure"}
    )
    buffer_tube = DynamicModelChoiceField(
        queryset=BufferTube.objects.all(),
        label=_("Buffer Tube"),
        query_params={"closure_id": "$closure"},
    )

    fieldsets = (FieldSet("closure", "tray", "buffer_tube", "position", "notes", "tags", name=_("Tube Assignment")),)

    class Meta:
        model = TubeAssignment
        fields = ("closure", "tray", "buffer_tube", "position", "notes", "tags")


class TubeAssignmentImportForm(NetBoxModelImportForm):
    """Import form for TubeAssignment."""

    class Meta:
        model = TubeAssignment
        fields = ("closure", "tray", "buffer_tube", "position", "notes", "tags")


class TubeAssignmentBulkEditForm(NetBoxModelBulkEditForm):
    """Bulk edit form for TubeAssignment."""

    model = TubeAssignment
    tray = DynamicModelChoiceField(queryset=Module.objects.all(), required=False, label=_("Tray"))
    position = forms.IntegerField(required=False, label=_("Position"))


class TubeAssignmentFilterForm(NetBoxModelFilterSetForm):
    """Filter form for TubeAssignment."""

    model = TubeAssignment
    closure_id = DynamicModelChoiceField(queryset=Device.objects.all(), required=False, label=_("Closure"))

    fieldsets = (FieldSet("q", "closure_id", "tag", name=_("Filters")),)


class SpliceClosureCreateForm(forms.Form):
    """Guided creation of a splice closure: device + tray/basket modules.

    Tray/basket type fields are plain ModelChoiceFields (not Dynamic): the
    dcim REST API cannot filter ModuleTypes by the plugin's TrayProfile role.
    """

    name = forms.CharField(label=_("Name"), max_length=64)
    site = DynamicModelChoiceField(queryset=Site.objects.all(), label=_("Site"))
    location = DynamicModelChoiceField(
        queryset=Location.objects.all(),
        label=_("Location"),
        required=False,
        query_params={"site_id": "$site"},
    )
    device_type = DynamicModelChoiceField(queryset=DeviceType.objects.all(), label=_("Device type"))
    role = DynamicModelChoiceField(queryset=DeviceRole.objects.all(), label=_("Role"))
    status = forms.ChoiceField(
        choices=DeviceStatusChoices,
        initial=DeviceStatusChoices.STATUS_ACTIVE,
        label=_("Status"),
    )
    tray_module_type = forms.ModelChoiceField(
        queryset=ModuleType.objects.filter(tray_profile__tray_role=TrayRoleChoices.SPLICE_TRAY),
        label=_("Splice tray type"),
        help_text=_("Module types marked as splice trays via a Tray Profile."),
    )
    tray_count = forms.IntegerField(min_value=1, initial=1, label=_("Tray count"))
    basket_module_type = forms.ModelChoiceField(
        queryset=ModuleType.objects.filter(tray_profile__tray_role=TrayRoleChoices.EXPRESS_BASKET),
        label=_("Express basket type"),
        required=False,
    )
    basket_count = forms.IntegerField(min_value=1, initial=1, required=False, label=_("Basket count"))


def _fiber_type_choices():
    """dcim CableTypeChoices restricted to the fiber subset the plugin accepts."""
    fiber = [
        (value, label)
        for value, label in unpack_grouped_choices(CableTypeChoices.CHOICES)
        if value in FIBER_CABLE_TYPES
    ]
    return add_blank_choice(fiber)


class ClosureCableWizardStep1Form(forms.Form):
    """Closure cable wizard step 1: FMS scope."""

    far_end_device = DynamicModelChoiceField(
        queryset=Device.objects.all(),
        label=_("Far end device"),
        help_text=_("The closure or device at the other end of the cable."),
    )
    fiber_cable_type = DynamicModelChoiceField(
        queryset=FiberCableType.objects.all(),
        label=_("Fiber cable type"),
    )
    port_type = forms.ChoiceField(
        choices=PortTypeChoices,
        initial="splice",
        label=_("Port type"),
        help_text=_("Defaults to Splice. Override for special cases like MPO cassettes."),
    )

    def __init__(self, *args, near_device=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.near_device = near_device

    def clean_far_end_device(self):
        far_device = self.cleaned_data["far_end_device"]
        if self.near_device is not None and far_device == self.near_device:
            raise ValidationError(_("Far end must be a different device."))
        return far_device


class ClosureCableWizardStep2Form(forms.Form):
    """Closure cable wizard step 2: native dcim.Cable attributes.

    A plain Form, not a ModelForm -- a create-ModelForm over Cable would
    trip Cable.clean()'s both-ends-required check in _post_clean() before
    any ports exist.
    """

    type = forms.ChoiceField(choices=_fiber_type_choices, required=False, label=_("Type"))
    status = forms.ChoiceField(
        choices=LinkStatusChoices,
        initial=LinkStatusChoices.STATUS_CONNECTED,
        label=_("Status"),
    )
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False, label=_("Tenant"))
    label = forms.CharField(max_length=100, required=False, label=_("Label"))
    color = ColorField(required=False, label=_("Color"))
    length = forms.DecimalField(max_digits=8, decimal_places=2, min_value=0, required=False, label=_("Length"))
    length_unit = forms.ChoiceField(
        choices=add_blank_choice(CableLengthUnitChoices),
        required=False,
        label=_("Length unit"),
    )
    description = forms.CharField(max_length=200, required=False, label=_("Description"))

    def clean(self):
        super().clean()
        if self.cleaned_data.get("length") is not None and not self.cleaned_data.get("length_unit"):
            raise ValidationError({"length_unit": _("Must specify a unit when setting a cable length.")})
        return self.cleaned_data
