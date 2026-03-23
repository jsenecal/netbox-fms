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
    FiberCircuit,
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


class FiberCableTypeTable(NetBoxTable):
    """Table for displaying FiberCableType objects."""

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
    """Table for displaying BufferTubeTemplate objects."""

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
    """Table for displaying RibbonTemplate objects."""

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
    """Table for displaying CableElementTemplate objects."""

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
    """Table for displaying FiberCable objects."""

    pk = columns.ToggleColumn()
    cable = tables.Column(linkify=True, verbose_name=_("Cable"))
    fiber_cable_type = tables.Column(linkify=True, verbose_name=_("Type"))
    serial_number = tables.Column(verbose_name=_("Serial Number"))
    install_date = tables.DateColumn(verbose_name=_("Install Date"))
    strand_utilization = tables.Column(accessor="pk", orderable=False, verbose_name=_("Utilization"))
    actions = columns.ActionsColumn()

    def render_strand_utilization(self, record):
        total = record.fiber_strands.count()
        if not total:
            return "-"
        active = record.fiber_strands.filter(fiber_circuit_nodes__isnull=False).distinct().count()
        return f"{active}/{total}"

    class Meta(NetBoxTable.Meta):
        model = FiberCable
        fields = (
            "pk",
            "id",
            "cable",
            "fiber_cable_type",
            "serial_number",
            "install_date",
            "strand_utilization",
            "actions",
        )
        default_columns = (
            "pk",
            "cable",
            "fiber_cable_type",
            "serial_number",
            "install_date",
            "strand_utilization",
            "actions",
        )


# ---------------------------------------------------------------------------
# Instance components (used in detail views)
# ---------------------------------------------------------------------------


class BufferTubeTable(NetBoxTable):
    """Table for displaying BufferTube objects."""

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
    """Table for displaying Ribbon objects."""

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
    """Table for displaying FiberStrand objects."""

    pk = columns.ToggleColumn()
    name = tables.Column(linkify=True, verbose_name=_("Name"))
    position = tables.Column(verbose_name=_("Position"))
    color = columns.ColorColumn(verbose_name=_("Color"))
    buffer_tube = tables.Column(linkify=True, verbose_name=_("Buffer Tube"))
    ribbon = tables.Column(linkify=True, verbose_name=_("Ribbon"))
    front_port_a = tables.Column(linkify=True, verbose_name=_("Front Port A"))
    front_port_b = tables.Column(linkify=True, verbose_name=_("Front Port B"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = FiberStrand
        fields = (
            "pk",
            "id",
            "name",
            "position",
            "color",
            "buffer_tube",
            "ribbon",
            "front_port_a",
            "front_port_b",
            "actions",
        )
        default_columns = (
            "pk",
            "name",
            "position",
            "color",
            "buffer_tube",
            "ribbon",
            "front_port_a",
            "front_port_b",
            "actions",
        )


class CableElementTable(NetBoxTable):
    """Table for displaying CableElement objects."""

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
    """Table for displaying SpliceProject objects."""

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
    """Table for displaying SplicePlan objects."""

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
    cable_count = tables.Column(verbose_name=_("Cables"), accessor="cable_count")
    tray_count = tables.Column(verbose_name=_("Trays"), accessor="tray_count")
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
            "cable_count",
            "tray_count",
            "entry_count",
            "description",
            "actions",
        )
        default_columns = (
            "pk",
            "name",
            "project",
            "closure",
            "status",
            "cable_count",
            "tray_count",
            "entry_count",
            "actions",
        )


class SplicePlanEntryTable(NetBoxTable):
    """Table for displaying SplicePlanEntry objects."""

    pk = columns.ToggleColumn()
    plan = tables.Column(linkify=True, verbose_name=_("Plan"))
    tray = tables.Column(linkify=True, verbose_name=_("Tray"))
    fiber_a = tables.Column(linkify=True, verbose_name=_("Fiber A"))
    fiber_b = tables.Column(linkify=True, verbose_name=_("Fiber B"))
    is_express = columns.BooleanColumn(verbose_name=_("Express"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = SplicePlanEntry
        fields = ("pk", "id", "plan", "tray", "fiber_a", "fiber_b", "is_express", "notes", "actions")
        default_columns = ("pk", "plan", "tray", "fiber_a", "fiber_b", "is_express", "actions")


class ClosureCableEntryTable(NetBoxTable):
    """Table for displaying ClosureCableEntry objects."""

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
# TrayProfile / TubeAssignment
# ---------------------------------------------------------------------------


class TrayProfileTable(NetBoxTable):
    """Table for displaying TrayProfile objects."""

    module_type = tables.Column(linkify=True)
    tray_role = tables.Column()

    class Meta(NetBoxTable.Meta):
        model = TrayProfile
        fields = ("pk", "id", "module_type", "tray_role", "description", "actions")
        default_columns = ("module_type", "tray_role", "description")


class TubeAssignmentTable(NetBoxTable):
    """Table for displaying TubeAssignment objects."""

    closure = tables.Column(linkify=True)
    tray = tables.Column(linkify=True)
    buffer_tube = tables.Column(linkify=True)
    position = tables.Column()

    class Meta(NetBoxTable.Meta):
        model = TubeAssignment
        fields = ("pk", "id", "closure", "tray", "buffer_tube", "position", "actions")
        default_columns = ("closure", "tray", "buffer_tube", "position")


# ---------------------------------------------------------------------------
# Slack Loops
# ---------------------------------------------------------------------------


class SlackLoopTable(NetBoxTable):
    """Table for displaying SlackLoop objects."""

    pk = columns.ToggleColumn()
    fiber_cable = tables.Column(linkify=True, verbose_name=_("Fiber Cable"))
    site = tables.Column(linkify=True, verbose_name=_("Site"))
    location = tables.Column(linkify=True, verbose_name=_("Location"))
    start_mark = tables.Column(verbose_name=_("Start Mark"))
    end_mark = tables.Column(verbose_name=_("End Mark"))
    loop_length = tables.Column(accessor="loop_length", orderable=False, verbose_name=_("Loop Length"))
    length_unit = tables.Column(verbose_name=_("Unit"))
    storage_method = tables.Column(verbose_name=_("Storage Method"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = SlackLoop
        fields = (
            "pk",
            "id",
            "fiber_cable",
            "site",
            "location",
            "start_mark",
            "end_mark",
            "loop_length",
            "length_unit",
            "storage_method",
            "actions",
        )
        default_columns = (
            "pk",
            "fiber_cable",
            "site",
            "start_mark",
            "end_mark",
            "loop_length",
            "length_unit",
            "actions",
        )


# ---------------------------------------------------------------------------
# Fiber Circuits
# ---------------------------------------------------------------------------


class FiberCircuitTable(NetBoxTable):
    """Table for displaying FiberCircuit objects."""

    pk = columns.ToggleColumn()
    name = tables.Column(linkify=True, verbose_name=_("Name"))
    cid = tables.Column(verbose_name=_("Circuit ID"))
    status = tables.Column(verbose_name=_("Status"))
    strand_count = tables.Column(verbose_name=_("Strands"))
    tenant = tables.Column(linkify=True, verbose_name=_("Tenant"))
    path_count = tables.Column(verbose_name=_("Paths"), orderable=True)
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = FiberCircuit
        fields = ("pk", "name", "cid", "status", "strand_count", "tenant", "path_count", "actions")
        default_columns = ("pk", "name", "cid", "status", "strand_count", "tenant", "actions")


class FiberCircuitPathTable(NetBoxTable):
    """Table for displaying FiberCircuitPath objects."""

    circuit = tables.Column(linkify=True)
    position = tables.Column()
    origin = tables.Column(linkify=True)
    destination = tables.Column(linkify=True)
    is_complete = columns.BooleanColumn()
    actions = columns.ActionsColumn(
        extra_buttons='<a href="{{ record.get_absolute_url }}#trace" class="btn btn-sm btn-outline-primary" '
        'title="Trace"><i class="mdi mdi-transit-connection-variant"></i></a> ',
    )

    class Meta(NetBoxTable.Meta):
        model = FiberCircuitPath
        fields = (
            "pk",
            "id",
            "circuit",
            "position",
            "origin",
            "destination",
            "is_complete",
            "calculated_loss_db",
            "actual_loss_db",
            "wavelength_nm",
        )
        default_columns = ("circuit", "position", "origin", "destination", "is_complete")


# ---------------------------------------------------------------------------
# WDM Device Type Profile
# ---------------------------------------------------------------------------


class WdmDeviceTypeProfileTable(NetBoxTable):
    """Table for displaying WdmDeviceTypeProfile objects."""

    pk = columns.ToggleColumn()
    device_type = tables.Column(linkify=True, verbose_name=_("Device Type"))
    node_type = tables.Column(verbose_name=_("Node Type"))
    grid = tables.Column(verbose_name=_("Grid"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = WdmDeviceTypeProfile
        fields = ("pk", "id", "device_type", "node_type", "grid", "description", "actions")
        default_columns = ("pk", "device_type", "node_type", "grid", "actions")


class WdmChannelTemplateTable(NetBoxTable):
    """Table for displaying WdmChannelTemplate objects."""

    pk = columns.ToggleColumn()
    profile = tables.Column(linkify=True, verbose_name=_("Profile"))
    grid_position = tables.Column(verbose_name=_("Grid Position"))
    label = tables.Column(verbose_name=_("Label"))
    wavelength_nm = tables.Column(verbose_name=_("Wavelength (nm)"))
    front_port_template = tables.Column(linkify=True, verbose_name=_("Front Port Template"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = WdmChannelTemplate
        fields = ("pk", "id", "profile", "grid_position", "label", "wavelength_nm", "front_port_template", "actions")
        default_columns = ("pk", "profile", "grid_position", "label", "wavelength_nm", "front_port_template", "actions")


# ---------------------------------------------------------------------------
# WDM Node
# ---------------------------------------------------------------------------


class WdmNodeTable(NetBoxTable):
    """Table for displaying WdmNode objects."""

    pk = columns.ToggleColumn()
    device = tables.Column(linkify=True, verbose_name=_("Device"))
    node_type = tables.Column(verbose_name=_("Node Type"))
    grid = tables.Column(verbose_name=_("Grid"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = WdmNode
        fields = ("pk", "id", "device", "node_type", "grid", "description", "actions")
        default_columns = ("pk", "device", "node_type", "grid", "actions")


class WdmTrunkPortTable(NetBoxTable):
    """Table for displaying WdmTrunkPort objects."""

    pk = columns.ToggleColumn()
    wdm_node = tables.Column(linkify=True, verbose_name=_("WDM Node"))
    rear_port = tables.Column(linkify=True, verbose_name=_("Rear Port"))
    direction = tables.Column(verbose_name=_("Direction"))
    position = tables.Column(verbose_name=_("Position"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = WdmTrunkPort
        fields = ("pk", "id", "wdm_node", "rear_port", "direction", "position", "actions")
        default_columns = ("pk", "wdm_node", "rear_port", "direction", "position", "actions")


# ---------------------------------------------------------------------------
# Wavelength Channel
# ---------------------------------------------------------------------------


class WavelengthChannelTable(NetBoxTable):
    """Table for displaying WavelengthChannel objects."""

    pk = columns.ToggleColumn()
    wdm_node = tables.Column(linkify=True, verbose_name=_("WDM Node"))
    grid_position = tables.Column(verbose_name=_("Grid Position"))
    label = tables.Column(verbose_name=_("Label"))
    wavelength_nm = tables.Column(verbose_name=_("Wavelength (nm)"))
    front_port = tables.Column(linkify=True, verbose_name=_("Front Port"))
    status = tables.Column(verbose_name=_("Status"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = WavelengthChannel
        fields = ("pk", "id", "wdm_node", "grid_position", "label", "wavelength_nm", "front_port", "status", "actions")
        default_columns = ("pk", "label", "grid_position", "wavelength_nm", "front_port", "status", "actions")


# ---------------------------------------------------------------------------
# Wavelength Service
# ---------------------------------------------------------------------------


class WavelengthServiceTable(NetBoxTable):
    """Table for displaying WavelengthService objects."""

    pk = columns.ToggleColumn()
    name = tables.Column(linkify=True, verbose_name=_("Name"))
    status = tables.Column(verbose_name=_("Status"))
    wavelength_nm = tables.Column(verbose_name=_("Wavelength (nm)"))
    tenant = tables.Column(linkify=True, verbose_name=_("Tenant"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = WavelengthService
        fields = ("pk", "id", "name", "status", "wavelength_nm", "tenant", "description", "actions")
        default_columns = ("pk", "name", "status", "wavelength_nm", "tenant", "actions")
