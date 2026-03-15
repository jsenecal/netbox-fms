import django_tables2 as tables
from django.utils.translation import gettext_lazy as _
from netbox.tables import NetBoxTable, columns

from .models import (
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

# ---------------------------------------------------------------------------
# FiberCableType
# ---------------------------------------------------------------------------


class FiberCableTypeTable(NetBoxTable):
    pk = columns.ToggleColumn()
    model = tables.Column(linkify=True, verbose_name=_("Model"))
    manufacturer = tables.Column(linkify=True, verbose_name=_("Manufacturer"))
    construction = tables.Column(verbose_name=_("Construction"))
    fiber_type = tables.Column(verbose_name=_("Fiber Type"))
    strand_count = tables.Column(verbose_name=_("Strands"))
    jacket_color = columns.ColorColumn(verbose_name=_("Jacket Color"))
    sheath_material = tables.Column(verbose_name=_("Sheath"))
    is_armored = columns.BooleanColumn(verbose_name=_("Armored"))
    deployment = tables.Column(verbose_name=_("Deployment"))
    fire_rating = tables.Column(verbose_name=_("Fire Rating"))
    instance_count = columns.LinkedCountColumn(
        viewname="plugins:netbox_fms:fibercable_list",
        url_params={"fiber_cable_type_id": "pk"},
        verbose_name=_("Instances"),
    )
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = FiberCableType
        fields = (
            "pk",
            "id",
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
            "instance_count",
            "actions",
        )
        default_columns = (
            "pk",
            "manufacturer",
            "model",
            "construction",
            "fiber_type",
            "strand_count",
            "deployment",
            "instance_count",
            "actions",
        )


# ---------------------------------------------------------------------------
# BufferTubeTemplate / CableElementTemplate
# ---------------------------------------------------------------------------


class BufferTubeTemplateTable(NetBoxTable):
    pk = columns.ToggleColumn()
    name = tables.Column(linkify=True, verbose_name=_("Name"))
    fiber_cable_type = tables.Column(linkify=True, verbose_name=_("Cable Type"))
    position = tables.Column(verbose_name=_("Position"))
    color = columns.ColorColumn(verbose_name=_("Color"))
    stripe_color = columns.ColorColumn(verbose_name=_("Stripe"))
    fiber_count = tables.Column(verbose_name=_("Fiber Count"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = BufferTubeTemplate
        fields = (
            "pk",
            "id",
            "fiber_cable_type",
            "name",
            "position",
            "color",
            "stripe_color",
            "fiber_count",
            "description",
            "actions",
        )
        default_columns = (
            "pk",
            "fiber_cable_type",
            "name",
            "position",
            "color",
            "stripe_color",
            "fiber_count",
            "actions",
        )


class RibbonTemplateTable(NetBoxTable):
    pk = columns.ToggleColumn()
    name = tables.Column(linkify=True, verbose_name=_("Name"))
    fiber_cable_type = tables.Column(linkify=True, verbose_name=_("Cable Type"))
    buffer_tube_template = tables.Column(linkify=True, verbose_name=_("Buffer Tube"))
    position = tables.Column(verbose_name=_("Position"))
    color = columns.ColorColumn(verbose_name=_("Color"))
    stripe_color = columns.ColorColumn(verbose_name=_("Stripe"))
    fiber_count = tables.Column(verbose_name=_("Fiber Count"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = RibbonTemplate
        fields = (
            "pk",
            "id",
            "fiber_cable_type",
            "buffer_tube_template",
            "name",
            "position",
            "color",
            "stripe_color",
            "fiber_count",
            "description",
            "actions",
        )
        default_columns = (
            "pk",
            "fiber_cable_type",
            "buffer_tube_template",
            "name",
            "position",
            "color",
            "stripe_color",
            "fiber_count",
            "actions",
        )


class CableElementTemplateTable(NetBoxTable):
    pk = columns.ToggleColumn()
    name = tables.Column(linkify=True, verbose_name=_("Name"))
    fiber_cable_type = tables.Column(linkify=True, verbose_name=_("Cable Type"))
    element_type = tables.Column(verbose_name=_("Type"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = CableElementTemplate
        fields = ("pk", "id", "fiber_cable_type", "name", "element_type", "description", "actions")
        default_columns = ("pk", "fiber_cable_type", "name", "element_type", "actions")


# ---------------------------------------------------------------------------
# FiberCable (instance)
# ---------------------------------------------------------------------------


class FiberCableTable(NetBoxTable):
    pk = columns.ToggleColumn()
    cable = tables.Column(linkify=True, verbose_name=_("Cable"))
    fiber_cable_type = tables.Column(linkify=True, verbose_name=_("Type"))
    serial_number = tables.Column(verbose_name=_("Serial Number"))
    install_date = tables.DateColumn(verbose_name=_("Install Date"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = FiberCable
        fields = ("pk", "id", "cable", "fiber_cable_type", "serial_number", "install_date", "actions")
        default_columns = ("pk", "cable", "fiber_cable_type", "serial_number", "install_date", "actions")


# ---------------------------------------------------------------------------
# Instance components (used in detail views)
# ---------------------------------------------------------------------------


class BufferTubeTable(NetBoxTable):
    pk = columns.ToggleColumn()
    name = tables.Column(linkify=True, verbose_name=_("Name"))
    position = tables.Column(verbose_name=_("Position"))
    color = columns.ColorColumn(verbose_name=_("Color"))
    stripe_color = columns.ColorColumn(verbose_name=_("Stripe"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = BufferTube
        fields = ("pk", "id", "name", "position", "color", "stripe_color", "actions")
        default_columns = ("pk", "name", "position", "color", "stripe_color", "actions")


class RibbonTable(NetBoxTable):
    pk = columns.ToggleColumn()
    name = tables.Column(linkify=True, verbose_name=_("Name"))
    position = tables.Column(verbose_name=_("Position"))
    color = columns.ColorColumn(verbose_name=_("Color"))
    stripe_color = columns.ColorColumn(verbose_name=_("Stripe"))
    buffer_tube = tables.Column(linkify=True, verbose_name=_("Buffer Tube"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = Ribbon
        fields = ("pk", "id", "name", "position", "color", "stripe_color", "buffer_tube", "actions")
        default_columns = ("pk", "name", "position", "color", "stripe_color", "buffer_tube", "actions")


class FiberStrandTable(NetBoxTable):
    pk = columns.ToggleColumn()
    name = tables.Column(linkify=True, verbose_name=_("Name"))
    position = tables.Column(verbose_name=_("Position"))
    color = columns.ColorColumn(verbose_name=_("Color"))
    buffer_tube = tables.Column(linkify=True, verbose_name=_("Buffer Tube"))
    ribbon = tables.Column(linkify=True, verbose_name=_("Ribbon"))
    front_port = tables.Column(linkify=True, verbose_name=_("Front Port"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = FiberStrand
        fields = ("pk", "id", "name", "position", "color", "buffer_tube", "ribbon", "front_port", "actions")
        default_columns = ("pk", "name", "position", "color", "buffer_tube", "ribbon", "front_port", "actions")


class CableElementTable(NetBoxTable):
    pk = columns.ToggleColumn()
    name = tables.Column(linkify=True, verbose_name=_("Name"))
    element_type = tables.Column(verbose_name=_("Type"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = CableElement
        fields = ("pk", "id", "name", "element_type", "actions")
        default_columns = ("pk", "name", "element_type", "actions")


# ---------------------------------------------------------------------------
# Splice planning
# ---------------------------------------------------------------------------


class SpliceProjectTable(NetBoxTable):
    pk = columns.ToggleColumn()
    name = tables.Column(linkify=True, verbose_name=_("Name"))
    description = tables.Column(verbose_name=_("Description"))
    plan_count = columns.LinkedCountColumn(
        viewname="plugins:netbox_fms:spliceplan_list",
        url_params={"project_id": "pk"},
        verbose_name=_("Plans"),
    )
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = SpliceProject
        fields = ("pk", "id", "name", "description", "plan_count", "actions")
        default_columns = ("pk", "name", "plan_count", "actions")


class SplicePlanTable(NetBoxTable):
    pk = columns.ToggleColumn()
    name = tables.Column(linkify=True, verbose_name=_("Name"))
    project = tables.Column(linkify=True, verbose_name=_("Project"))
    closure = tables.Column(linkify=True, verbose_name=_("Closure"))
    status = tables.Column(verbose_name=_("Status"))
    entry_count = columns.LinkedCountColumn(
        viewname="plugins:netbox_fms:spliceplanentry_list",
        url_params={"plan_id": "pk"},
        verbose_name=_("Entries"),
    )
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = SplicePlan
        fields = (
            "pk",
            "id",
            "name",
            "project",
            "closure",
            "status",
            "entry_count",
            "description",
            "actions",
        )
        default_columns = ("pk", "name", "project", "closure", "status", "entry_count", "actions")


class SplicePlanEntryTable(NetBoxTable):
    pk = columns.ToggleColumn()
    plan = tables.Column(linkify=True, verbose_name=_("Plan"))
    tray = tables.Column(linkify=True, verbose_name=_("Tray"))
    fiber_a = tables.Column(linkify=True, verbose_name=_("Fiber A"))
    fiber_b = tables.Column(linkify=True, verbose_name=_("Fiber B"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = SplicePlanEntry
        fields = ("pk", "id", "plan", "tray", "fiber_a", "fiber_b", "notes", "actions")
        default_columns = ("pk", "plan", "tray", "fiber_a", "fiber_b", "actions")


class ClosureCableEntryTable(NetBoxTable):
    pk = columns.ToggleColumn()
    closure = tables.Column(linkify=True, verbose_name=_("Closure"))
    fiber_cable = tables.Column(linkify=True, verbose_name=_("Fiber Cable"))
    entrance_label = tables.Column(verbose_name=_("Entrance Label"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = ClosureCableEntry
        fields = ("pk", "id", "closure", "fiber_cable", "entrance_label", "notes", "actions")
        default_columns = ("pk", "closure", "fiber_cable", "entrance_label", "actions")


# ---------------------------------------------------------------------------
# Loss budget
# ---------------------------------------------------------------------------


class FiberPathLossTable(NetBoxTable):
    pk = columns.ToggleColumn()
    cable = tables.Column(linkify=True, verbose_name=_("Cable"))
    wavelength_nm = tables.Column(verbose_name=_("Wavelength (nm)"))
    measured_loss_db = tables.Column(verbose_name=_("Measured Loss (dB)"))
    calculated_loss_db = tables.Column(verbose_name=_("Calculated Loss (dB)"))
    test_date = tables.DateColumn(verbose_name=_("Test Date"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = FiberPathLoss
        fields = (
            "pk",
            "id",
            "cable",
            "wavelength_nm",
            "measured_loss_db",
            "calculated_loss_db",
            "test_date",
            "actions",
        )
        default_columns = (
            "pk",
            "cable",
            "wavelength_nm",
            "measured_loss_db",
            "calculated_loss_db",
            "test_date",
            "actions",
        )
