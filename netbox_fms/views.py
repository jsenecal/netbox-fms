from dcim.models import Cable, CableTermination, Device, FrontPort, PortMapping, RearPort
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views import View
from netbox.object_actions import BulkDelete, BulkEdit, DeleteObject, EditObject
from netbox.views import generic
from utilities.views import ViewTab, register_model_view

from .choices import FiberCircuitStatusChoices
from .export import generate_drawio
from .filters import (
    BufferTubeFilterSet,
    BufferTubeTemplateFilterSet,
    CableElementFilterSet,
    CableElementTemplateFilterSet,
    ClosureCableEntryFilterSet,
    FiberCableFilterSet,
    FiberCableTypeFilterSet,
    FiberCircuitFilterSet,
    FiberCircuitPathFilterSet,
    FiberStrandFilterSet,
    RibbonFilterSet,
    RibbonTemplateFilterSet,
    SlackLoopFilterSet,
    SplicePlanEntryFilterSet,
    SplicePlanFilterSet,
    SpliceProjectFilterSet,
    TrayProfileFilterSet,
    TubeAssignmentFilterSet,
    WavelengthChannelFilterSet,
    WavelengthServiceFilterSet,
    WdmChannelTemplateFilterSet,
    WdmDeviceTypeProfileFilterSet,
    WdmNodeFilterSet,
    WdmTrunkPortFilterSet,
)
from .forms import (
    BufferTubeTemplateBulkEditForm,
    BufferTubeTemplateForm,
    CableElementTemplateBulkEditForm,
    CableElementTemplateForm,
    ClosureCableEntryFilterForm,
    ClosureCableEntryForm,
    FiberCableBulkEditForm,
    FiberCableFilterForm,
    FiberCableForm,
    FiberCableImportForm,
    FiberCableTypeBulkEditForm,
    FiberCableTypeFilterForm,
    FiberCableTypeForm,
    FiberCableTypeImportForm,
    FiberCircuitBulkEditForm,
    FiberCircuitFilterForm,
    FiberCircuitForm,
    FiberCircuitImportForm,
    FiberCircuitPathFilterForm,
    FiberCircuitPathForm,
    InsertSlackLoopForm,
    LinkTopologyForm,
    ProvisionPortsForm,
    RibbonTemplateBulkEditForm,
    RibbonTemplateForm,
    SlackLoopBulkEditForm,
    SlackLoopFilterForm,
    SlackLoopForm,
    SlackLoopImportForm,
    SplicePlanBulkEditForm,
    SplicePlanEntryFilterForm,
    SplicePlanEntryForm,
    SplicePlanFilterForm,
    SplicePlanForm,
    SplicePlanImportForm,
    SpliceProjectFilterForm,
    SpliceProjectForm,
    TrayProfileBulkEditForm,
    TrayProfileFilterForm,
    TrayProfileForm,
    TrayProfileImportForm,
    TubeAssignmentBulkEditForm,
    TubeAssignmentFilterForm,
    TubeAssignmentForm,
    TubeAssignmentImportForm,
    WavelengthChannelBulkEditForm,
    WavelengthChannelFilterForm,
    WavelengthChannelForm,
    WavelengthServiceFilterForm,
    WavelengthServiceForm,
    WavelengthServiceImportForm,
    WdmChannelTemplateForm,
    WdmDeviceTypeProfileFilterForm,
    WdmDeviceTypeProfileForm,
    WdmDeviceTypeProfileImportForm,
    WdmNodeFilterForm,
    WdmNodeForm,
    WdmNodeImportForm,
    WdmTrunkPortForm,
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
    WavelengthChannel,
    WavelengthService,
    WavelengthServiceChannelAssignment,
    WdmChannelTemplate,
    WdmDeviceTypeProfile,
    WdmNode,
    WdmTrunkPort,
)
from .services import (
    NeedsMappingConfirmation,
    apply_diff,
    get_or_recompute_diff,
    import_live_state,
    link_cable_topology,
)
from .tables import (
    BufferTubeTable,
    BufferTubeTemplateTable,
    CableElementTable,
    CableElementTemplateTable,
    ClosureCableEntryTable,
    FiberCableTable,
    FiberCableTypeTable,
    FiberCircuitPathTable,
    FiberCircuitTable,
    FiberStrandTable,
    RibbonTable,
    RibbonTemplateTable,
    SlackLoopTable,
    SplicePlanEntryTable,
    SplicePlanTable,
    SpliceProjectTable,
    TrayProfileTable,
    TubeAssignmentTable,
    WavelengthChannelTable,
    WavelengthServiceTable,
    WdmChannelTemplateTable,
    WdmDeviceTypeProfileTable,
    WdmNodeTable,
    WdmTrunkPortTable,
)

# ---------------------------------------------------------------------------
# FiberCableType
# ---------------------------------------------------------------------------


class FiberCableTypeListView(generic.ObjectListView):
    """List all fiber cable types."""

    queryset = FiberCableType.objects.annotate(instance_count=models.Count("instances"))
    table = FiberCableTypeTable
    filterset = FiberCableTypeFilterSet
    filterset_form = FiberCableTypeFilterForm


@register_model_view(FiberCableType)
class FiberCableTypeView(generic.ObjectView):
    """Display a single fiber cable type."""

    queryset = FiberCableType.objects.all()


class FiberCableTypeEditView(generic.ObjectEditView):
    """Handle fiber cable type creation and editing."""

    queryset = FiberCableType.objects.all()
    form = FiberCableTypeForm


class FiberCableTypeDeleteView(generic.ObjectDeleteView):
    """Delete a fiber cable type."""

    queryset = FiberCableType.objects.all()


class FiberCableTypeBulkImportView(generic.BulkImportView):
    """Bulk import fiber cable types from CSV."""

    queryset = FiberCableType.objects.all()
    model_form = FiberCableTypeImportForm


class FiberCableTypeBulkEditView(generic.BulkEditView):
    """Bulk edit fiber cable types."""

    queryset = FiberCableType.objects.all()
    filterset = FiberCableTypeFilterSet
    table = FiberCableTypeTable
    form = FiberCableTypeBulkEditForm


class FiberCableTypeBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete fiber cable types."""

    queryset = FiberCableType.objects.all()
    filterset = FiberCableTypeFilterSet
    table = FiberCableTypeTable


# ---------------------------------------------------------------------------
# FiberCableType component tab views
# ---------------------------------------------------------------------------


class FiberCableTypeComponentsView(generic.ObjectChildrenView):
    """Base view for fiber cable type component tabs."""

    queryset = FiberCableType.objects.all()
    actions = (EditObject, DeleteObject, BulkEdit, BulkDelete)
    viewname = None

    def get_children(self, request, parent):
        """Return child components filtered by parent fiber cable type."""
        return self.child_model.objects.restrict(request.user, "view").filter(fiber_cable_type=parent)

    def get_extra_context(self, request, instance):
        return {
            "return_url": reverse(self.viewname, kwargs={"pk": instance.pk}),
        }


@register_model_view(FiberCableType, "buffertubes", path="buffer-tubes")
class FiberCableTypeBufferTubesView(FiberCableTypeComponentsView):
    """Display buffer tube templates for a fiber cable type."""

    child_model = BufferTubeTemplate
    table = BufferTubeTemplateTable
    filterset = BufferTubeTemplateFilterSet
    viewname = "plugins:netbox_fms:fibercabletype_buffertubes"
    tab = ViewTab(
        label=_("Buffer Tubes"),
        badge=lambda obj: obj.buffer_tube_template_count,
        permission="netbox_fms.view_buffertubetemplate",
        weight=500,
        hide_if_empty=True,
    )


@register_model_view(FiberCableType, "ribbons", path="ribbons")
class FiberCableTypeRibbonsView(FiberCableTypeComponentsView):
    """Display ribbon templates for a fiber cable type."""

    child_model = RibbonTemplate
    table = RibbonTemplateTable
    filterset = RibbonTemplateFilterSet
    viewname = "plugins:netbox_fms:fibercabletype_ribbons"
    tab = ViewTab(
        label=_("Ribbons"),
        badge=lambda obj: obj.ribbon_template_count,
        permission="netbox_fms.view_ribbontemplate",
        weight=510,
        hide_if_empty=True,
    )


@register_model_view(FiberCableType, "cableelements", path="cable-elements")
class FiberCableTypeCableElementsView(FiberCableTypeComponentsView):
    """Display cable element templates for a fiber cable type."""

    child_model = CableElementTemplate
    table = CableElementTemplateTable
    filterset = CableElementTemplateFilterSet
    viewname = "plugins:netbox_fms:fibercabletype_cableelements"
    tab = ViewTab(
        label=_("Cable Elements"),
        badge=lambda obj: obj.cable_element_template_count,
        permission="netbox_fms.view_cableelementtemplate",
        weight=520,
        hide_if_empty=True,
    )


@register_model_view(FiberCableType, "instances", path="instances")
class FiberCableTypeInstancesView(generic.ObjectChildrenView):
    """Display fiber cable instances of a fiber cable type."""

    queryset = FiberCableType.objects.all()
    child_model = FiberCable
    table = FiberCableTable
    viewname = "plugins:netbox_fms:fibercabletype_instances"
    tab = ViewTab(
        label=_("Instances"),
        badge=lambda obj: FiberCable.objects.filter(fiber_cable_type=obj).count(),
        weight=530,
        hide_if_empty=True,
    )

    def get_children(self, request, parent):
        """Return fiber cable instances for the parent type."""
        return FiberCable.objects.restrict(request.user, "view").filter(fiber_cable_type=parent)

    def get_extra_context(self, request, instance):
        return {
            "return_url": reverse(self.viewname, kwargs={"pk": instance.pk}),
        }


# ---------------------------------------------------------------------------
# FiberCableType component bulk edit/delete views
# ---------------------------------------------------------------------------


class BufferTubeTemplateBulkEditView(generic.BulkEditView):
    """Bulk edit buffer tube templates."""

    queryset = BufferTubeTemplate.objects.all()
    filterset = BufferTubeTemplateFilterSet
    table = BufferTubeTemplateTable
    form = BufferTubeTemplateBulkEditForm


class BufferTubeTemplateBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete buffer tube templates."""

    queryset = BufferTubeTemplate.objects.all()
    filterset = BufferTubeTemplateFilterSet
    table = BufferTubeTemplateTable


class RibbonTemplateBulkEditView(generic.BulkEditView):
    """Bulk edit ribbon templates."""

    queryset = RibbonTemplate.objects.all()
    filterset = RibbonTemplateFilterSet
    table = RibbonTemplateTable
    form = RibbonTemplateBulkEditForm


class RibbonTemplateBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete ribbon templates."""

    queryset = RibbonTemplate.objects.all()
    filterset = RibbonTemplateFilterSet
    table = RibbonTemplateTable


class CableElementTemplateBulkEditView(generic.BulkEditView):
    """Bulk edit cable element templates."""

    queryset = CableElementTemplate.objects.all()
    filterset = CableElementTemplateFilterSet
    table = CableElementTemplateTable
    form = CableElementTemplateBulkEditForm


class CableElementTemplateBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete cable element templates."""

    queryset = CableElementTemplate.objects.all()
    filterset = CableElementTemplateFilterSet
    table = CableElementTemplateTable


# ---------------------------------------------------------------------------
# BufferTubeTemplate
# ---------------------------------------------------------------------------


class BufferTubeTemplateListView(generic.ObjectListView):
    """List all buffer tube templates."""

    queryset = BufferTubeTemplate.objects.select_related("fiber_cable_type")
    table = BufferTubeTemplateTable
    filterset = BufferTubeTemplateFilterSet


class BufferTubeTemplateView(generic.ObjectView):
    """Display a single buffer tube template."""

    queryset = BufferTubeTemplate.objects.all()


class BufferTubeTemplateEditView(generic.ObjectEditView):
    """Handle buffer tube template creation and editing."""

    queryset = BufferTubeTemplate.objects.all()
    form = BufferTubeTemplateForm


class BufferTubeTemplateDeleteView(generic.ObjectDeleteView):
    """Delete a buffer tube template."""

    queryset = BufferTubeTemplate.objects.all()


# ---------------------------------------------------------------------------
# CableElementTemplate
# ---------------------------------------------------------------------------


class CableElementTemplateListView(generic.ObjectListView):
    """List all cable element templates."""

    queryset = CableElementTemplate.objects.all()
    table = CableElementTemplateTable
    filterset = CableElementTemplateFilterSet


class CableElementTemplateView(generic.ObjectView):
    """Display a single cable element template."""

    queryset = CableElementTemplate.objects.all()


class CableElementTemplateEditView(generic.ObjectEditView):
    """Handle cable element template creation and editing."""

    queryset = CableElementTemplate.objects.all()
    form = CableElementTemplateForm


class CableElementTemplateDeleteView(generic.ObjectDeleteView):
    """Delete a cable element template."""

    queryset = CableElementTemplate.objects.all()


# ---------------------------------------------------------------------------
# RibbonTemplate
# ---------------------------------------------------------------------------


class RibbonTemplateListView(generic.ObjectListView):
    """List all ribbon templates."""

    queryset = RibbonTemplate.objects.select_related("fiber_cable_type", "buffer_tube_template")
    table = RibbonTemplateTable
    filterset = RibbonTemplateFilterSet


class RibbonTemplateView(generic.ObjectView):
    """Display a single ribbon template."""

    queryset = RibbonTemplate.objects.all()


class RibbonTemplateEditView(generic.ObjectEditView):
    """Handle ribbon template creation and editing."""

    queryset = RibbonTemplate.objects.all()
    form = RibbonTemplateForm


class RibbonTemplateDeleteView(generic.ObjectDeleteView):
    """Delete a ribbon template."""

    queryset = RibbonTemplate.objects.all()


# ---------------------------------------------------------------------------
# FiberCable (instance)
# ---------------------------------------------------------------------------


class FiberCableListView(generic.ObjectListView):
    """List all fiber cables."""

    queryset = FiberCable.objects.select_related("cable", "fiber_cable_type")
    table = FiberCableTable
    filterset = FiberCableFilterSet
    filterset_form = FiberCableFilterForm


@register_model_view(FiberCable)
class FiberCableView(generic.ObjectView):
    """Display a single fiber cable."""

    queryset = FiberCable.objects.all()

    def get_extra_context(self, request, instance):
        total_strands = instance.fiber_strands.count()
        active_strands = (
            instance.fiber_strands.filter(
                fiber_circuit_nodes__isnull=False,
            )
            .distinct()
            .count()
        )
        available_strands = total_strands - active_strands
        return {
            "strand_stats": {
                "total": total_strands,
                "active": active_strands,
                "available": available_strands,
                "active_pct": round(active_strands / total_strands * 100) if total_strands else 0,
                "available_pct": round(available_strands / total_strands * 100) if total_strands else 0,
            }
        }


class FiberCableEditView(generic.ObjectEditView):
    """Handle fiber cable creation and editing."""

    queryset = FiberCable.objects.all()
    form = FiberCableForm


class FiberCableDeleteView(generic.ObjectDeleteView):
    """Delete a fiber cable."""

    queryset = FiberCable.objects.all()


class FiberCableBulkImportView(generic.BulkImportView):
    """Bulk import fiber cables from CSV."""

    queryset = FiberCable.objects.all()
    model_form = FiberCableImportForm


class FiberCableBulkEditView(generic.BulkEditView):
    """Bulk edit fiber cables."""

    queryset = FiberCable.objects.all()
    filterset = FiberCableFilterSet
    table = FiberCableTable
    form = FiberCableBulkEditForm


class FiberCableBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete fiber cables."""

    queryset = FiberCable.objects.all()
    filterset = FiberCableFilterSet
    table = FiberCableTable


# ---------------------------------------------------------------------------
# FiberCable component tab views
# ---------------------------------------------------------------------------


class FiberCableComponentsView(generic.ObjectChildrenView):
    """Base view for fiber cable component tabs."""

    queryset = FiberCable.objects.all()
    actions = (EditObject, DeleteObject, BulkDelete)
    viewname = None

    def get_children(self, request, parent):
        """Return child components filtered by parent fiber cable."""
        return self.child_model.objects.restrict(request.user, "view").filter(fiber_cable=parent)

    def get_extra_context(self, request, instance):
        return {
            "return_url": reverse(self.viewname, kwargs={"pk": instance.pk}),
        }


@register_model_view(FiberCable, "buffertubes", path="buffer-tubes")
class FiberCableBufferTubesView(FiberCableComponentsView):
    """Display buffer tubes for a fiber cable."""

    child_model = BufferTube
    table = BufferTubeTable
    filterset = BufferTubeFilterSet
    viewname = "plugins:netbox_fms:fibercable_buffertubes"
    tab = ViewTab(
        label=_("Buffer Tubes"),
        badge=lambda obj: obj.buffer_tubes.count(),
        permission="netbox_fms.view_buffertube",
        weight=500,
        hide_if_empty=True,
    )


@register_model_view(FiberCable, "ribbons", path="ribbons")
class FiberCableRibbonsView(FiberCableComponentsView):
    """Display ribbons for a fiber cable."""

    child_model = Ribbon
    table = RibbonTable
    filterset = RibbonFilterSet
    viewname = "plugins:netbox_fms:fibercable_ribbons"
    tab = ViewTab(
        label=_("Ribbons"),
        badge=lambda obj: obj.ribbons.count(),
        permission="netbox_fms.view_ribbon",
        weight=510,
        hide_if_empty=True,
    )


@register_model_view(FiberCable, "strands", path="strands")
class FiberCableStrandsView(FiberCableComponentsView):
    """Display fiber strands for a fiber cable."""

    child_model = FiberStrand
    table = FiberStrandTable
    filterset = FiberStrandFilterSet
    viewname = "plugins:netbox_fms:fibercable_strands"
    tab = ViewTab(
        label=_("Fiber Strands"),
        badge=lambda obj: obj.fiber_strands.count(),
        permission="netbox_fms.view_fiberstrand",
        weight=520,
    )


@register_model_view(FiberCable, "cableelements", path="cable-elements")
class FiberCableCableElementsView(FiberCableComponentsView):
    """Display cable elements for a fiber cable."""

    child_model = CableElement
    table = CableElementTable
    filterset = CableElementFilterSet
    viewname = "plugins:netbox_fms:fibercable_cableelements"
    tab = ViewTab(
        label=_("Cable Elements"),
        badge=lambda obj: obj.cable_elements.count(),
        permission="netbox_fms.view_cableelement",
        weight=530,
        hide_if_empty=True,
    )


@register_model_view(Cable, "fibercircuits", path="fiber-circuits")
class CableFiberCircuitsView(generic.ObjectChildrenView):
    """Display fiber circuit paths passing through a dcim.Cable."""

    queryset = Cable.objects.all()
    child_model = FiberCircuitPath
    table = FiberCircuitPathTable
    filterset = FiberCircuitPathFilterSet
    actions = ()
    tab = ViewTab(
        label=_("Fiber Circuits"),
        badge=lambda obj: FiberCircuitPath.objects.filter(nodes__cable=obj).distinct().count(),
        permission="netbox_fms.view_fibercircuitpath",
        weight=600,
        hide_if_empty=True,
    )

    def get_children(self, request, parent):
        """Return fiber circuit paths that traverse the parent cable."""
        return (
            FiberCircuitPath.objects.restrict(request.user, "view")
            .filter(
                nodes__cable=parent,
            )
            .select_related("circuit", "origin", "destination")
            .distinct()
        )


# ---------------------------------------------------------------------------
# SplicePlan
# ---------------------------------------------------------------------------


class SplicePlanListView(generic.ObjectListView):
    """List all splice plans."""

    queryset = SplicePlan.objects.select_related("project", "closure").annotate(entry_count=models.Count("entries"))
    table = SplicePlanTable
    filterset = SplicePlanFilterSet
    filterset_form = SplicePlanFilterForm


class SplicePlanView(generic.ObjectView):
    """Display a single splice plan with its entries."""

    queryset = SplicePlan.objects.all()

    def get_extra_context(self, request, instance):
        entries_table = SplicePlanEntryTable(instance.entries.all())
        entries_table.configure(request)
        return {
            "entries_table": entries_table,
        }


class SplicePlanEditView(generic.ObjectEditView):
    """Handle splice plan creation and editing."""

    queryset = SplicePlan.objects.all()
    form = SplicePlanForm


class SplicePlanDeleteView(generic.ObjectDeleteView):
    """Delete a splice plan."""

    queryset = SplicePlan.objects.all()


class SplicePlanBulkImportView(generic.BulkImportView):
    """Bulk import splice plans from CSV."""

    queryset = SplicePlan.objects.all()
    model_form = SplicePlanImportForm


class SplicePlanBulkEditView(generic.BulkEditView):
    """Bulk edit splice plans."""

    queryset = SplicePlan.objects.all()
    filterset = SplicePlanFilterSet
    table = SplicePlanTable
    form = SplicePlanBulkEditForm


class SplicePlanBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete splice plans."""

    queryset = SplicePlan.objects.all()
    filterset = SplicePlanFilterSet
    table = SplicePlanTable


class SplicePlanQuickAddFormView(LoginRequiredMixin, View):
    """Return rendered SplicePlanForm HTML for the quick-add modal."""

    def get(self, request):
        """Render the splice plan quick-add form, optionally pre-filled with a closure."""
        closure_id = request.GET.get("closure_id")
        initial = {}
        if closure_id:
            initial["closure"] = closure_id
        form = SplicePlanForm(initial=initial)
        html = render(
            request,
            "netbox_fms/spliceplan_quick_add_form.html",
            {"form": form},
        ).content.decode()
        return HttpResponse(html)


class SplicePlanImportFromDeviceView(LoginRequiredMixin, View):
    """Import current live connections into a splice plan."""

    def post(self, request, pk):
        """Import live device connections into the splice plan."""
        plan = get_object_or_404(SplicePlan, pk=pk)
        try:
            count = import_live_state(plan)
            messages.success(
                request,
                _('Imported {count} connections into "{plan}".').format(count=count, plan=plan),
            )
        except (ValueError, ValidationError) as e:
            messages.error(request, str(e))
        return redirect(plan.get_absolute_url())


class SplicePlanApplyView(LoginRequiredMixin, View):
    """Preview and apply a splice plan's diff to NetBox."""

    def get(self, request, pk):
        """Display the diff preview before applying the splice plan."""
        plan = get_object_or_404(SplicePlan, pk=pk)
        diff = get_or_recompute_diff(plan)
        return render(
            request,
            "netbox_fms/spliceplan_apply_confirm.html",
            {"object": plan, "diff": diff},
        )

    @transaction.atomic
    def post(self, request, pk):
        """Apply the splice plan diff to NetBox, creating and removing connections."""
        plan = get_object_or_404(SplicePlan, pk=pk)

        # Block applying if any splices are protected by fiber circuits
        fp_ids = set()
        for entry in plan.entries.all():
            fp_ids.add(entry.fiber_a_id)
            fp_ids.add(entry.fiber_b_id)
        if fp_ids:
            protected_circuits = set(
                FiberCircuitNode.objects.filter(front_port_id__in=fp_ids)
                .exclude(path__circuit__status=FiberCircuitStatusChoices.DECOMMISSIONED)
                .values_list("path__circuit__name", flat=True)
            )
            if protected_circuits:
                names = ", ".join(sorted(protected_circuits))
                messages.error(
                    request,
                    _("Cannot apply: splices are protected by circuit(s): {names}").format(names=names),
                )
                return redirect(plan.get_absolute_url())

        try:
            result = apply_diff(plan)
            messages.success(
                request,
                _('Applied {added} additions and {removed} removals for "{plan}".').format(
                    added=result["added"], removed=result["removed"], plan=plan
                ),
            )
        except (ValueError, ValidationError, IntegrityError) as e:
            messages.error(request, str(e))
        return redirect(plan.get_absolute_url())


class SplicePlanExportDrawioView(LoginRequiredMixin, View):
    """Export splice plan as draw.io XML."""

    def get(self, request, pk):
        """Generate and return the draw.io XML file as a download."""
        plan = get_object_or_404(SplicePlan, pk=pk)
        xml_content = generate_drawio(plan)
        response = HttpResponse(xml_content, content_type="application/xml")
        response["Content-Disposition"] = f'attachment; filename="{plan.name}.drawio"'
        return response


# ---------------------------------------------------------------------------
# ClosureCableEntry
# ---------------------------------------------------------------------------


class ClosureCableEntryListView(generic.ObjectListView):
    """List all closure cable entries."""

    queryset = ClosureCableEntry.objects.select_related("closure", "fiber_cable")
    table = ClosureCableEntryTable
    filterset = ClosureCableEntryFilterSet
    filterset_form = ClosureCableEntryFilterForm


class ClosureCableEntryView(generic.ObjectView):
    """Display a single closure cable entry with strand linkage info."""

    queryset = ClosureCableEntry.objects.all()

    def get_extra_context(self, request, instance):
        strand_info = None
        if instance.fiber_cable:
            total = instance.fiber_cable.fiber_strands.count()
            linked = instance.fiber_cable.fiber_strands.filter(
                Q(front_port_a__device=instance.closure) | Q(front_port_b__device=instance.closure)
            ).count()
            strand_info = {"linked": linked, "total": total}
        return {"strand_info": strand_info}


class ClosureCableEntryEditView(generic.ObjectEditView):
    """Handle closure cable entry creation and editing."""

    queryset = ClosureCableEntry.objects.all()
    form = ClosureCableEntryForm


class ClosureCableEntryDeleteView(generic.ObjectDeleteView):
    """Delete a closure cable entry."""

    queryset = ClosureCableEntry.objects.all()


class ClosureCableEntryBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete closure cable entries."""

    queryset = ClosureCableEntry.objects.all()
    filterset = ClosureCableEntryFilterSet
    table = ClosureCableEntryTable


# ---------------------------------------------------------------------------
# SplicePlanEntry
# ---------------------------------------------------------------------------


class SplicePlanEntryListView(generic.ObjectListView):
    """List all splice plan entries."""

    queryset = SplicePlanEntry.objects.select_related("plan", "tray", "fiber_a", "fiber_b")
    table = SplicePlanEntryTable
    filterset = SplicePlanEntryFilterSet
    filterset_form = SplicePlanEntryFilterForm


class SplicePlanEntryView(generic.ObjectView):
    """Display a single splice plan entry."""

    queryset = SplicePlanEntry.objects.all()


class SplicePlanEntryEditView(generic.ObjectEditView):
    """Handle splice plan entry creation and editing."""

    queryset = SplicePlanEntry.objects.all()
    form = SplicePlanEntryForm


class SplicePlanEntryDeleteView(generic.ObjectDeleteView):
    """Delete a splice plan entry."""

    queryset = SplicePlanEntry.objects.all()


class SplicePlanEntryBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete splice plan entries."""

    queryset = SplicePlanEntry.objects.all()
    filterset = SplicePlanEntryFilterSet
    table = SplicePlanEntryTable


# ---------------------------------------------------------------------------
# SpliceProject
# ---------------------------------------------------------------------------


class SpliceProjectListView(generic.ObjectListView):
    """List all splice projects."""

    queryset = SpliceProject.objects.prefetch_related("tags").annotate(plan_count=models.Count("plans"))
    table = SpliceProjectTable
    filterset = SpliceProjectFilterSet
    filterset_form = SpliceProjectFilterForm


class SpliceProjectView(generic.ObjectView):
    """Display a single splice project with its plans."""

    queryset = SpliceProject.objects.all()

    def get_extra_context(self, request, instance):
        plans_table = SplicePlanTable(instance.plans.all())
        plans_table.configure(request)
        return {"plans_table": plans_table}


class SpliceProjectEditView(generic.ObjectEditView):
    """Handle splice project creation and editing."""

    queryset = SpliceProject.objects.all()
    form = SpliceProjectForm


class SpliceProjectDeleteView(generic.ObjectDeleteView):
    """Delete a splice project."""

    queryset = SpliceProject.objects.all()


class SpliceProjectBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete splice projects."""

    queryset = SpliceProject.objects.all()
    filterset = SpliceProjectFilterSet
    table = SpliceProjectTable


# ---------------------------------------------------------------------------
# TrayProfile
# ---------------------------------------------------------------------------


class TrayProfileListView(generic.ObjectListView):
    """List all tray profiles."""

    queryset = TrayProfile.objects.select_related("module_type")
    table = TrayProfileTable
    filterset = TrayProfileFilterSet
    filterset_form = TrayProfileFilterForm


@register_model_view(TrayProfile)
class TrayProfileView(generic.ObjectView):
    """Display a single tray profile."""

    queryset = TrayProfile.objects.select_related("module_type")


class TrayProfileEditView(generic.ObjectEditView):
    """Handle tray profile creation and editing."""

    queryset = TrayProfile.objects.all()
    form = TrayProfileForm


class TrayProfileDeleteView(generic.ObjectDeleteView):
    """Handle tray profile deletion."""

    queryset = TrayProfile.objects.all()


class TrayProfileBulkImportView(generic.BulkImportView):
    """Handle bulk import of tray profiles."""

    queryset = TrayProfile.objects.all()
    model_form = TrayProfileImportForm


class TrayProfileBulkEditView(generic.BulkEditView):
    """Handle bulk editing of tray profiles."""

    queryset = TrayProfile.objects.select_related("module_type")
    filterset = TrayProfileFilterSet
    table = TrayProfileTable
    form = TrayProfileBulkEditForm


class TrayProfileBulkDeleteView(generic.BulkDeleteView):
    """Handle bulk deletion of tray profiles."""

    queryset = TrayProfile.objects.select_related("module_type")
    filterset = TrayProfileFilterSet
    table = TrayProfileTable


# ---------------------------------------------------------------------------
# TubeAssignment
# ---------------------------------------------------------------------------


class TubeAssignmentListView(generic.ObjectListView):
    """List all tube assignments."""

    queryset = TubeAssignment.objects.select_related("closure", "tray", "buffer_tube")
    table = TubeAssignmentTable
    filterset = TubeAssignmentFilterSet
    filterset_form = TubeAssignmentFilterForm


@register_model_view(TubeAssignment)
class TubeAssignmentView(generic.ObjectView):
    """Display a single tube assignment."""

    queryset = TubeAssignment.objects.select_related("closure", "tray", "buffer_tube")


class TubeAssignmentEditView(generic.ObjectEditView):
    """Handle tube assignment creation and editing."""

    queryset = TubeAssignment.objects.all()
    form = TubeAssignmentForm


class TubeAssignmentDeleteView(generic.ObjectDeleteView):
    """Handle tube assignment deletion."""

    queryset = TubeAssignment.objects.all()


class TubeAssignmentBulkImportView(generic.BulkImportView):
    """Handle bulk import of tube assignments."""

    queryset = TubeAssignment.objects.all()
    model_form = TubeAssignmentImportForm


class TubeAssignmentBulkEditView(generic.BulkEditView):
    """Handle bulk editing of tube assignments."""

    queryset = TubeAssignment.objects.select_related("closure", "tray", "buffer_tube")
    filterset = TubeAssignmentFilterSet
    table = TubeAssignmentTable
    form = TubeAssignmentBulkEditForm


class TubeAssignmentBulkDeleteView(generic.BulkDeleteView):
    """Handle bulk deletion of tube assignments."""

    queryset = TubeAssignment.objects.select_related("closure", "tray", "buffer_tube")
    filterset = TubeAssignmentFilterSet
    table = TubeAssignmentTable


# ---------------------------------------------------------------------------
# SlackLoop
# ---------------------------------------------------------------------------


class SlackLoopListView(generic.ObjectListView):
    """List all slack loops."""

    queryset = SlackLoop.objects.prefetch_related("fiber_cable", "site", "location", "tags")
    table = SlackLoopTable
    filterset = SlackLoopFilterSet
    filterset_form = SlackLoopFilterForm


@register_model_view(SlackLoop)
class SlackLoopView(generic.ObjectView):
    """Display a single slack loop."""

    queryset = SlackLoop.objects.all()


class SlackLoopEditView(generic.ObjectEditView):
    """Handle slack loop creation and editing."""

    queryset = SlackLoop.objects.all()
    form = SlackLoopForm


class SlackLoopDeleteView(generic.ObjectDeleteView):
    """Delete a slack loop."""

    queryset = SlackLoop.objects.all()


class SlackLoopBulkImportView(generic.BulkImportView):
    """Bulk import slack loops from CSV."""

    queryset = SlackLoop.objects.all()
    model_form = SlackLoopImportForm


class SlackLoopBulkEditView(generic.BulkEditView):
    """Bulk edit slack loops."""

    queryset = SlackLoop.objects.all()
    filterset = SlackLoopFilterSet
    table = SlackLoopTable
    form = SlackLoopBulkEditForm


class SlackLoopBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete slack loops."""

    queryset = SlackLoop.objects.all()
    filterset = SlackLoopFilterSet
    table = SlackLoopTable


# ---------------------------------------------------------------------------
# Insert Slack Loop into Closure
# ---------------------------------------------------------------------------


def insert_slack_loop_into_closure(slack_loop, closure, a_side_rear_ports, b_side_rear_ports, express_strand_positions):
    """Split a cable at a slack loop location and connect both halves through a closure."""
    old_fiber_cable = slack_loop.fiber_cable
    old_cable = old_fiber_cable.cable
    fct = old_fiber_cable.fiber_cable_type
    old_metadata = {
        "serial_number": old_fiber_cable.serial_number,
        "install_date": old_fiber_cable.install_date,
        "notes": old_fiber_cable.notes,
    }

    # Capture actual endpoint objects (survive cable deletion)
    old_a_terms = list(old_cable.a_terminations)
    old_b_terms = list(old_cable.b_terminations)
    old_cable_attrs = {
        "type": old_cable.type,
        "status": old_cable.status,
        "label": old_cable.label,
        "color": old_cable.color,
    }

    with transaction.atomic():
        # Snapshot for change logging
        old_cable.snapshot()

        # Handle FiberCircuitNode references defensively
        rewiring_records = []
        try:
            nodes = FiberCircuitNode.objects.filter(
                models.Q(cable=old_cable) | models.Q(fiber_strand__fiber_cable=old_fiber_cable)
            )
            for node in nodes:
                record = {"path_id": node.path_id, "position": node.position}
                if node.cable_id:
                    record["field"] = "cable"
                elif node.fiber_strand_id:
                    record["field"] = "fiber_strand"
                    record["strand_position"] = node.fiber_strand.position
                rewiring_records.append(record)
            nodes.delete()
        except (ImportError, LookupError):
            pass

        # Delete old cable (cascades FiberCable, strands, etc.)
        old_cable.delete()

        # Create Cable A (original A-side -> closure)
        cable_a = Cable(a_terminations=old_a_terms, b_terminations=a_side_rear_ports, **old_cable_attrs)
        cable_a.save()

        # Create Cable B (closure -> original B-side)
        cable_b = Cable(a_terminations=b_side_rear_ports, b_terminations=old_b_terms, **old_cable_attrs)
        cable_b.save()

        # Create FiberCable instances (auto-instantiates strands)
        fc_a = FiberCable.objects.create(cable=cable_a, fiber_cable_type=fct, **old_metadata)
        fc_b = FiberCable.objects.create(cable=cable_b, fiber_cable_type=fct, **old_metadata)

        # Create/get SplicePlan
        plan, _ = SplicePlan.objects.get_or_create(
            closure=closure,
            defaults={"name": f"Plan for {closure.name}"},
        )

        # Find FrontPorts mapped to our RearPorts via PortMapping
        a_front_ports = list(
            FrontPort.objects.filter(mappings__rear_port__in=a_side_rear_ports).order_by("mappings__rear_port_position")
        )
        b_front_ports = list(
            FrontPort.objects.filter(mappings__rear_port__in=b_side_rear_ports).order_by("mappings__rear_port_position")
        )

        # Create SplicePlanEntries
        tray = a_front_ports[0].module if a_front_ports and a_front_ports[0].module else None
        entries = []
        for i, (fp_a, fp_b) in enumerate(zip(a_front_ports, b_front_ports, strict=False)):
            strand_pos = i + 1
            entry_tray = fp_a.module or tray
            entries.append(
                SplicePlanEntry(
                    plan=plan,
                    tray=entry_tray,
                    fiber_a=fp_a,
                    fiber_b=fp_b,
                    is_express=strand_pos in express_strand_positions,
                )
            )
        SplicePlanEntry.objects.bulk_create(entries)

        # Create ClosureCableEntry records
        ClosureCableEntry.objects.create(closure=closure, fiber_cable=fc_a)
        ClosureCableEntry.objects.create(closure=closure, fiber_cable=fc_b)

        # Re-wire FiberCircuitNodes
        if rewiring_records:
            try:
                for record in rewiring_records:
                    kwargs = {"path_id": record["path_id"], "position": record["position"]}
                    if record["field"] == "cable":
                        kwargs["cable"] = cable_a
                    elif record["field"] == "fiber_strand":
                        strand_pos = record["strand_position"]
                        strand = fc_a.fiber_strands.filter(position=strand_pos).first()
                        if not strand:
                            strand = fc_b.fiber_strands.filter(position=strand_pos).first()
                        if strand:
                            kwargs["fiber_strand"] = strand
                        else:
                            continue
                    FiberCircuitNode.objects.create(**kwargs)
            except (ImportError, LookupError):
                pass

        # Delete the SlackLoop
        slack_loop.delete()

    return cable_a, cable_b, fc_a, fc_b, plan


class SlackLoopInsertView(LoginRequiredMixin, View):
    """Insert a slack loop into a splice closure by splitting the cable."""

    def get(self, request, pk):
        """Render the slack loop insertion form."""
        slack_loop = get_object_or_404(SlackLoop, pk=pk)
        form = InsertSlackLoopForm()
        return render(request, "netbox_fms/slackloop_insert.html", {"object": slack_loop, "form": form})

    def post(self, request, pk):
        """Process the slack loop insertion, splitting the cable at the closure."""
        slack_loop = get_object_or_404(SlackLoop, pk=pk)
        form = InsertSlackLoopForm(request.POST)
        if form.is_valid():
            try:
                cable_a, cable_b, fc_a, fc_b, plan = insert_slack_loop_into_closure(
                    slack_loop=slack_loop,
                    closure=form.cleaned_data["closure"],
                    a_side_rear_ports=list(form.cleaned_data["a_side_rear_ports"]),
                    b_side_rear_ports=list(form.cleaned_data["b_side_rear_ports"]),
                    express_strand_positions=form.cleaned_data["express_strand_positions"],
                )
                messages.success(request, f"Slack loop inserted into {form.cleaned_data['closure']}.")
                return redirect(plan.get_absolute_url())
            except Exception as e:
                messages.error(request, f"Failed to insert slack loop: {e}")
        return render(request, "netbox_fms/slackloop_insert.html", {"object": slack_loop, "form": form})


# ---------------------------------------------------------------------------
# FiberCircuit
# ---------------------------------------------------------------------------


class FiberCircuitListView(generic.ObjectListView):
    """List all fiber circuits."""

    queryset = FiberCircuit.objects.select_related("tenant").annotate(path_count=Count("paths"))
    table = FiberCircuitTable
    filterset = FiberCircuitFilterSet
    filterset_form = FiberCircuitFilterForm


class FiberCircuitView(generic.ObjectView):
    """Display a single fiber circuit with its paths."""

    queryset = FiberCircuit.objects.all()

    def get_extra_context(self, request, instance):
        return {"paths": instance.paths.all()}


class FiberCircuitEditView(generic.ObjectEditView):
    """Handle fiber circuit creation and editing."""

    queryset = FiberCircuit.objects.all()
    form = FiberCircuitForm


class FiberCircuitDeleteView(generic.ObjectDeleteView):
    """Delete a fiber circuit."""

    queryset = FiberCircuit.objects.all()


class FiberCircuitBulkImportView(generic.BulkImportView):
    """Bulk import fiber circuits from CSV."""

    queryset = FiberCircuit.objects.all()
    model_form = FiberCircuitImportForm


class FiberCircuitBulkEditView(generic.BulkEditView):
    """Bulk edit fiber circuits."""

    queryset = FiberCircuit.objects.all()
    filterset = FiberCircuitFilterSet
    table = FiberCircuitTable
    form = FiberCircuitBulkEditForm


class FiberCircuitBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete fiber circuits."""

    queryset = FiberCircuit.objects.all()
    filterset = FiberCircuitFilterSet
    table = FiberCircuitTable


# ---------------------------------------------------------------------------
# FiberCircuitPath
# ---------------------------------------------------------------------------


class FiberCircuitPathListView(generic.ObjectListView):
    """List all fiber circuit paths."""

    queryset = FiberCircuitPath.objects.select_related("circuit", "origin", "destination")
    table = FiberCircuitPathTable
    filterset = FiberCircuitPathFilterSet
    filterset_form = FiberCircuitPathFilterForm


class FiberCircuitPathView(generic.ObjectView):
    """Display a single fiber circuit path."""

    queryset = FiberCircuitPath.objects.select_related("circuit", "origin", "destination")


class FiberCircuitPathEditView(generic.ObjectEditView):
    """Handle fiber circuit path creation and editing."""

    queryset = FiberCircuitPath.objects.all()
    form = FiberCircuitPathForm


class FiberCircuitPathDeleteView(generic.ObjectDeleteView):
    """Delete a fiber circuit path."""

    queryset = FiberCircuitPath.objects.all()


# ---------------------------------------------------------------------------
# Provision Ports
# ---------------------------------------------------------------------------


@transaction.atomic
def provision_strands(fiber_cable, device, port_type, module=None):
    """
    Provision dcim FrontPort/RearPort/PortMapping for a FiberCable on a Device.
    If module is provided, all ports are created on that module (in addition to device).
    """
    strands = fiber_cable.fiber_strands.select_related("buffer_tube").order_by("position")
    strand_count = strands.count()
    if strand_count == 0:
        raise ValueError("This fiber cable has no strands.")

    cable_label = str(fiber_cable.cable) if fiber_cable.cable else f"FiberCable-{fiber_cable.pk}"

    # PortMapping only has device, front_port, rear_port — no module field.
    component_kwargs = {"device": device}
    if module is not None:
        component_kwargs["module"] = module

    rear_port = RearPort(
        **component_kwargs,
        name=cable_label,
        type=port_type,
        positions=strand_count,
        color="",
    )
    rear_port.save()

    for strand in strands:
        fp = FrontPort(
            **component_kwargs,
            name=strand.name,
            type=port_type,
            color=strand.color,
        )
        fp.save()

        PortMapping.objects.create(
            device=device,
            front_port=fp,
            rear_port=rear_port,
            front_port_position=1,
            rear_port_position=strand.position,
        )

        strand.front_port_a = fp
        strand.save(update_fields=["front_port_a"])


class ProvisionPortsView(LoginRequiredMixin, View):
    """Provision dcim FrontPort/RearPort/PortMapping for a FiberCable on a Device."""

    def get(self, request):
        """Render the port provisioning form."""
        form = ProvisionPortsForm(initial=request.GET)
        return render(request, "netbox_fms/provision_ports.html", {"form": form})

    def post(self, request):
        """Create FrontPort/RearPort/PortMapping for the selected fiber cable and device."""
        form = ProvisionPortsForm(request.POST)
        if not form.is_valid():
            return render(request, "netbox_fms/provision_ports.html", {"form": form})

        fiber_cable = form.cleaned_data["fiber_cable"]
        device = form.cleaned_data["device"]
        port_type = form.cleaned_data["port_type"]

        # Check for already provisioned strands on this device
        already = fiber_cable.fiber_strands.filter(
            Q(front_port_a__device=device) | Q(front_port_b__device=device)
        ).exists()
        if already:
            messages.error(request, _("Some strands are already provisioned on this device."))
            return render(request, "netbox_fms/provision_ports.html", {"form": form})

        try:
            provision_strands(fiber_cable, device, port_type)
            strand_count = fiber_cable.fiber_strands.count()
            messages.success(
                request,
                _('Provisioned {count} ports for "{cable}" on {device}.').format(
                    count=strand_count, cable=fiber_cable, device=device
                ),
            )
        except ValueError as e:
            messages.error(request, str(e))
            return render(request, "netbox_fms/provision_ports.html", {"form": form})

        return redirect(fiber_cable.get_absolute_url())


# ---------------------------------------------------------------------------
# Splice Editor
# ---------------------------------------------------------------------------


class SpliceEditorView(LoginRequiredMixin, View):
    """Visual splice editor for a SplicePlan."""

    def get(self, request, pk):
        """Render the visual splice editor for the given plan."""
        plan = get_object_or_404(SplicePlan.objects.select_related("closure"), pk=pk)
        return render(
            request,
            "netbox_fms/splice_editor.html",
            {
                "object": plan,
                "context_mode": "plan-edit",
            },
        )


# ---------------------------------------------------------------------------
# Device tab: Splice Editor injected on dcim.Device detail pages
# ---------------------------------------------------------------------------


def _device_has_modules_or_fiber_cables(device):
    """Return True if device has modules (trays) or FiberCable terminations."""
    if device.modules.exists():
        return True
    cable_ids = (
        CableTermination.objects.filter(_device_id=device.pk)
        .exclude(cable__isnull=True)
        .values_list("cable_id", flat=True)
        .distinct()
    )
    return FiberCable.objects.filter(cable_id__in=cable_ids).exists()


def _build_cable_rows(device):
    """Build context dicts for Fiber Overview, grouped by cable."""
    cable_ids = (
        CableTermination.objects.filter(_device_id=device.pk)
        .exclude(cable__isnull=True)
        .values_list("cable_id", flat=True)
        .distinct()
    )

    cables = Cable.objects.filter(pk__in=cable_ids).order_by("pk")
    fc_by_cable = {
        fc.cable_id: fc for fc in FiberCable.objects.filter(cable_id__in=cable_ids).select_related("fiber_cable_type")
    }

    fiber_cable_ids = [fc.pk for fc in fc_by_cable.values()]
    strand_totals = {}
    strand_linked = {}
    if fiber_cable_ids:
        totals = (
            FiberStrand.objects.filter(fiber_cable_id__in=fiber_cable_ids)
            .values("fiber_cable_id")
            .annotate(
                total=Count("pk"),
                linked=Count("pk", filter=Q(front_port_a__device=device) | Q(front_port_b__device=device)),
            )
        )
        for row in totals:
            strand_totals[row["fiber_cable_id"]] = row["total"]
            strand_linked[row["fiber_cable_id"]] = row["linked"]

    gland_by_fc = {}
    if fiber_cable_ids:
        for entry in ClosureCableEntry.objects.filter(closure=device, fiber_cable_id__in=fiber_cable_ids):
            gland_by_fc[entry.fiber_cable_id] = entry

    rows = []
    for cable in cables:
        fc = fc_by_cable.get(cable.pk)
        strand_info = None
        gland_entry = None
        if fc:
            strand_info = {
                "linked": strand_linked.get(fc.pk, 0),
                "total": strand_totals.get(fc.pk, 0),
            }
            gland_entry = gland_by_fc.get(fc.pk)
        rows.append(
            {
                "cable": cable,
                "fiber_cable": fc,
                "strand_info": strand_info,
                "gland_entry": gland_entry,
            }
        )
    return rows


def _device_has_splice_plan_or_fiber_cables(device):
    """Return True if this device has a splice plan or FiberCable terminations."""
    if SplicePlan.objects.filter(closure=device).exists():
        return True
    cable_ids = (
        CableTermination.objects.filter(_device_id=device.pk)
        .exclude(cable__isnull=True)
        .values_list("cable_id", flat=True)
        .distinct()
    )
    return FiberCable.objects.filter(cable_id__in=cable_ids).exists()


@register_model_view(Device, "fiber_overview", path="fiber-overview")
class DeviceFiberOverviewView(View):
    """Fiber Overview tab on a dcim.Device detail page."""

    tab = ViewTab(
        label=_("Fiber Overview"),
        visible=_device_has_modules_or_fiber_cables,
        weight=1400,
    )

    def get(self, request, pk):
        """Render the fiber overview tab with cable rows and statistics."""
        device = get_object_or_404(Device, pk=pk)
        cable_rows = _build_cable_rows(device)
        plan = SplicePlan.objects.filter(closure=device).first()
        stats = {
            "tray_count": device.modules.count(),
            "cable_count": len(cable_rows),
            "fiber_cable_count": sum(1 for r in cable_rows if r["fiber_cable"]),
            "strand_linked": sum(r["strand_info"]["linked"] for r in cable_rows if r["strand_info"]),
            "strand_total": sum(r["strand_info"]["total"] for r in cable_rows if r["strand_info"]),
        }
        # Conditionally provide a "Show on Map" URL if netbox-pathways is installed
        show_on_map_url = None
        try:
            import netbox_pathways  # noqa: F401

            if device.site_id:
                show_on_map_url = f"/plugins/pathways/map/#site={device.site_id}"
        except ImportError:
            pass

        return render(
            request,
            "netbox_fms/device_fiber_overview.html",
            {
                "object": device,
                "device": device,
                "cable_rows": cable_rows,
                "plan": plan,
                "stats": stats,
                "show_on_map_url": show_on_map_url,
                "tab": self.tab,
            },
        )


@register_model_view(Device, "splice_editor", path="splice-editor")
class DeviceSpliceEditorView(View):
    """
    Splice editor tab on a dcim.Device detail page.

    Finds all SplicePlans for this closure device. If none exist,
    creates a default one. Renders the splice editor for the selected plan.
    """

    tab = ViewTab(
        label=_("Splice Editor"),
        visible=_device_has_splice_plan_or_fiber_cables,
        weight=1500,
    )

    def get(self, request, pk):
        """Render the splice editor tab for a device, creating a default plan if needed."""
        device = get_object_or_404(Device, pk=pk)
        plan = SplicePlan.objects.filter(closure=device).first()
        context_mode = "edit" if plan else "view"

        return render(
            request,
            "netbox_fms/device_splice_editor.html",
            {
                "object": device,
                "device": device,
                "plan": plan,
                "context_mode": context_mode,
                "tab": self.tab,
            },
        )


# ---------------------------------------------------------------------------
# Fiber Overview HTMX action views (placeholders)
# ---------------------------------------------------------------------------


class UpdateGlandLabelView(LoginRequiredMixin, View):
    """Edit the entrance/gland label for a closure cable entry via HTMX modal."""

    def get(self, request, pk):
        if not request.user.has_perm("netbox_fms.change_closurecableentry") and not request.user.has_perm(
            "netbox_fms.add_closurecableentry"
        ):
            return HttpResponse("Permission denied", status=403)
        device = get_object_or_404(Device, pk=pk)
        fiber_cable_id = request.GET.get("fiber_cable_id")
        fiber_cable = get_object_or_404(FiberCable, pk=fiber_cable_id)

        entry = ClosureCableEntry.objects.filter(closure=device, fiber_cable=fiber_cable).first()
        current_label = entry.entrance_label if entry else ""

        return render(
            request,
            "netbox_fms/htmx/edit_gland_modal.html",
            {
                "device": device,
                "fiber_cable": fiber_cable,
                "current_label": current_label,
                "post_url": reverse("plugins:netbox_fms:fiber_overview_update_gland", kwargs={"pk": pk}),
            },
        )

    def post(self, request, pk):
        if not request.user.has_perm("netbox_fms.change_closurecableentry") and not request.user.has_perm(
            "netbox_fms.add_closurecableentry"
        ):
            return HttpResponse("Permission denied", status=403)
        device = get_object_or_404(Device, pk=pk)
        fiber_cable_id = request.POST.get("fiber_cable_id")
        fiber_cable = get_object_or_404(FiberCable, pk=fiber_cable_id)
        entrance_label = request.POST.get("entrance_label", "").strip()

        ClosureCableEntry.objects.update_or_create(
            closure=device,
            fiber_cable=fiber_cable,
            defaults={"entrance_label": entrance_label},
        )

        redirect_url = reverse("dcim:device", kwargs={"pk": pk}) + "fiber-overview/"
        response = HttpResponse(status=200)
        response["HX-Redirect"] = redirect_url
        return response


class LinkTopologyView(LoginRequiredMixin, View):
    """Link a dcim.Cable to a FiberCableType — creates FiberCable and links strands."""

    def get(self, request, pk):
        """Render the link topology modal for associating a cable with a fiber cable type."""
        if not request.user.has_perm("netbox_fms.add_fibercable"):
            return HttpResponse("Permission denied", status=403)
        device = get_object_or_404(Device, pk=pk)
        cable_id = request.GET.get("cable_id")
        cable = get_object_or_404(Cable, pk=cable_id)

        rp_ct = ContentType.objects.get_for_model(RearPort)
        has_existing = CableTermination.objects.filter(
            cable=cable,
            termination_type=rp_ct,
            termination_id__in=RearPort.objects.filter(device=device).values("pk"),
        ).exists()

        form = LinkTopologyForm()
        return render(
            request,
            "netbox_fms/htmx/link_topology_modal.html",
            {
                "device": device,
                "cable": cable,
                "form": form,
                "show_port_type": not has_existing,
                "post_url": reverse("plugins:netbox_fms:fiber_overview_link_topology", kwargs={"pk": pk}),
            },
        )

    def post(self, request, pk):
        """Create a FiberCable and link strands to ports, with optional mapping confirmation."""
        if not request.user.has_perm("netbox_fms.add_fibercable"):
            return HttpResponse("Permission denied", status=403)
        device = get_object_or_404(Device, pk=pk)

        if request.POST.get("confirm_mapping"):
            cable = get_object_or_404(Cable, pk=request.POST.get("cable_id"))
            fct = get_object_or_404(FiberCableType, pk=request.POST.get("fiber_cable_type_id"))
            port_mapping = {}
            for key, value in request.POST.items():
                if key.startswith("mapping_"):
                    port_mapping[int(key.split("_")[1])] = int(value)
            fc, warnings = link_cable_topology(cable, fct, device, port_mapping=port_mapping)
            redirect_url = reverse("dcim:device", kwargs={"pk": pk}) + "fiber-overview/"
            response = HttpResponse(status=200)
            response["HX-Redirect"] = redirect_url
            return response

        form = LinkTopologyForm(request.POST)
        if not form.is_valid():
            cable = get_object_or_404(Cable, pk=request.POST.get("cable_id"))
            return render(
                request,
                "netbox_fms/htmx/link_topology_modal.html",
                {
                    "device": device,
                    "cable": cable,
                    "form": form,
                    "show_port_type": True,
                    "post_url": reverse("plugins:netbox_fms:fiber_overview_link_topology", kwargs={"pk": pk}),
                },
            )

        cable = get_object_or_404(Cable, pk=request.POST.get("cable_id"))
        fct = form.cleaned_data["fiber_cable_type"]
        port_type = form.cleaned_data.get("port_type") or "splice"

        try:
            fc, warnings = link_cable_topology(cable, fct, device, port_type=port_type)
        except NeedsMappingConfirmation as exc:
            mapping_entries = []
            for pos in range(1, fct.strand_count + 1):
                fp_id = exc.proposed_mapping.get(pos)
                fp_name = None
                if fp_id:
                    fp = FrontPort.objects.filter(pk=fp_id).first()
                    fp_name = fp.name if fp else None
                mapping_entries.append(
                    {
                        "position": pos,
                        "frontport_id": fp_id,
                        "frontport_name": fp_name,
                    }
                )
            return render(
                request,
                "netbox_fms/htmx/link_topology_confirm.html",
                {
                    "cable_id": cable.pk,
                    "fiber_cable_type_id": fct.pk,
                    "mapping_entries": mapping_entries,
                    "warnings": exc.warnings,
                    "post_url": reverse("plugins:netbox_fms:fiber_overview_link_topology", kwargs={"pk": pk}),
                },
            )

        redirect_url = reverse("dcim:device", kwargs={"pk": pk}) + "fiber-overview/"
        response = HttpResponse(status=200)
        response["HX-Redirect"] = redirect_url
        return response


class TraceDetailView(LoginRequiredMixin, View):
    """HTMX partial view for trace sidebar detail panels."""

    def get(self, request, pk, node_type, object_id):
        """Return an HTMX partial for the specified node type (device, cable, port, or splice)."""
        if not request.user.has_perm("netbox_fms.view_fibercircuitpath"):
            return HttpResponse("Permission denied", status=403)

        path_obj = get_object_or_404(FiberCircuitPath, pk=pk)

        if node_type == "device":
            device = get_object_or_404(Device, pk=object_id)
            has_splice_plans = SplicePlan.objects.filter(closure=device).exists()
            return render(
                request,
                "netbox_fms/htmx/trace_device_detail.html",
                {
                    "device": device,
                    "path": path_obj,
                    "has_splice_plans": has_splice_plans,
                },
            )

        elif node_type == "cable":
            cable = get_object_or_404(Cable, pk=object_id)
            fiber_cable = FiberCable.objects.filter(cable=cable).select_related("fiber_cable_type").first()
            return render(
                request,
                "netbox_fms/htmx/trace_cable_detail.html",
                {
                    "cable": cable,
                    "fiber_cable": fiber_cable,
                    "path": path_obj,
                },
            )

        elif node_type == "port":
            port = get_object_or_404(FrontPort, pk=object_id)
            strand = (
                FiberStrand.objects.filter(models.Q(front_port_a=port) | models.Q(front_port_b=port))
                .select_related("buffer_tube")
                .first()
            )
            return render(
                request,
                "netbox_fms/htmx/trace_port_detail.html",
                {
                    "port": port,
                    "strand": strand,
                    "path": path_obj,
                },
            )

        elif node_type == "splice":
            splice_entry = get_object_or_404(
                SplicePlanEntry.objects.select_related("plan", "tray", "fiber_a", "fiber_b"),
                pk=object_id,
            )
            return render(
                request,
                "netbox_fms/htmx/trace_splice_detail.html",
                {
                    "splice_entry": splice_entry,
                    "path": path_obj,
                },
            )

        return HttpResponse("Unknown node type", status=400)


# ---------------------------------------------------------------------------
# WDM Device Type Profile
# ---------------------------------------------------------------------------


class WdmDeviceTypeProfileListView(generic.ObjectListView):
    """List all WDM device type profiles."""

    queryset = WdmDeviceTypeProfile.objects.select_related("device_type")
    table = WdmDeviceTypeProfileTable
    filterset = WdmDeviceTypeProfileFilterSet
    filterset_form = WdmDeviceTypeProfileFilterForm


@register_model_view(WdmDeviceTypeProfile)
class WdmDeviceTypeProfileView(generic.ObjectView):
    """Display a single WDM device type profile."""

    queryset = WdmDeviceTypeProfile.objects.all()


class WdmDeviceTypeProfileEditView(generic.ObjectEditView):
    """Handle WDM device type profile creation and editing."""

    queryset = WdmDeviceTypeProfile.objects.all()
    form = WdmDeviceTypeProfileForm


class WdmDeviceTypeProfileDeleteView(generic.ObjectDeleteView):
    """Delete a WDM device type profile."""

    queryset = WdmDeviceTypeProfile.objects.all()


class WdmDeviceTypeProfileBulkImportView(generic.BulkImportView):
    """Bulk import WDM device type profiles from CSV."""

    queryset = WdmDeviceTypeProfile.objects.all()
    model_form = WdmDeviceTypeProfileImportForm


class WdmDeviceTypeProfileBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete WDM device type profiles."""

    queryset = WdmDeviceTypeProfile.objects.all()
    filterset = WdmDeviceTypeProfileFilterSet
    table = WdmDeviceTypeProfileTable


# ---------------------------------------------------------------------------
# WDM Device Type Profile component tab views
# ---------------------------------------------------------------------------


@register_model_view(WdmDeviceTypeProfile, "channel_templates", path="channel-templates")
class WdmDeviceTypeProfileChannelTemplatesView(generic.ObjectChildrenView):
    """Display channel templates for a WDM device type profile."""

    queryset = WdmDeviceTypeProfile.objects.all()
    child_model = WdmChannelTemplate
    table = WdmChannelTemplateTable
    filterset = WdmChannelTemplateFilterSet
    actions = (EditObject, DeleteObject, BulkDelete)
    tab = ViewTab(
        label=_("Channel Templates"),
        badge=lambda obj: obj.channel_templates.count(),
        permission="netbox_fms.view_wdmchanneltemplate",
        weight=500,
    )

    def get_children(self, request, parent):
        """Return channel templates filtered by parent profile."""
        return self.child_model.objects.restrict(request.user, "view").filter(profile=parent)


# ---------------------------------------------------------------------------
# WDM Channel Template
# ---------------------------------------------------------------------------


@register_model_view(WdmChannelTemplate)
class WdmChannelTemplateView(generic.ObjectView):
    """Display a single WDM channel template."""

    queryset = WdmChannelTemplate.objects.all()


class WdmChannelTemplateEditView(generic.ObjectEditView):
    """Handle WDM channel template creation and editing."""

    queryset = WdmChannelTemplate.objects.all()
    form = WdmChannelTemplateForm


class WdmChannelTemplateDeleteView(generic.ObjectDeleteView):
    """Delete a WDM channel template."""

    queryset = WdmChannelTemplate.objects.all()


# ---------------------------------------------------------------------------
# WDM Node
# ---------------------------------------------------------------------------


class WdmNodeListView(generic.ObjectListView):
    """List all WDM nodes."""

    queryset = WdmNode.objects.select_related("device")
    table = WdmNodeTable
    filterset = WdmNodeFilterSet
    filterset_form = WdmNodeFilterForm


@register_model_view(WdmNode)
class WdmNodeView(generic.ObjectView):
    """Display a single WDM node with channel and trunk port counts."""

    queryset = WdmNode.objects.all()

    def get_extra_context(self, request, instance):
        """Return channel and trunk port counts and utilization stats for the WDM node."""
        channels = instance.channels.all()
        total = channels.count()
        lit = channels.filter(status="lit").count()
        reserved = channels.filter(status="reserved").count()
        available = channels.filter(status="available").count()
        return {
            "channel_count": total,
            "trunk_port_count": instance.trunk_ports.count(),
            "channel_stats": {
                "total": total,
                "lit": lit,
                "reserved": reserved,
                "available": available,
                "lit_pct": round(lit / total * 100) if total else 0,
                "reserved_pct": round(reserved / total * 100) if total else 0,
                "available_pct": round(available / total * 100) if total else 0,
            },
        }


class WdmNodeEditView(generic.ObjectEditView):
    """Handle WDM node creation and editing."""

    queryset = WdmNode.objects.all()
    form = WdmNodeForm


class WdmNodeDeleteView(generic.ObjectDeleteView):
    """Delete a WDM node."""

    queryset = WdmNode.objects.all()


class WdmNodeBulkImportView(generic.BulkImportView):
    """Bulk import WDM nodes from CSV."""

    queryset = WdmNode.objects.all()
    model_form = WdmNodeImportForm


class WdmNodeBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete WDM nodes."""

    queryset = WdmNode.objects.all()
    filterset = WdmNodeFilterSet
    table = WdmNodeTable


# ---------------------------------------------------------------------------
# WDM Node component tab views
# ---------------------------------------------------------------------------


@register_model_view(WdmNode, "channels", path="channels")
class WdmNodeChannelsView(generic.ObjectChildrenView):
    """Display wavelength channels for a WDM node."""

    queryset = WdmNode.objects.all()
    child_model = WavelengthChannel
    table = WavelengthChannelTable
    filterset = WavelengthChannelFilterSet
    actions = (EditObject, DeleteObject, BulkDelete)
    tab = ViewTab(
        label=_("Channels"),
        badge=lambda obj: obj.channels.count(),
        permission="netbox_fms.view_wavelengthchannel",
        weight=500,
    )

    def get_children(self, request, parent):
        """Return channels filtered by parent WDM node."""
        return self.child_model.objects.restrict(request.user, "view").filter(wdm_node=parent)


@register_model_view(WdmNode, "trunk_ports", path="trunk-ports")
class WdmNodeTrunkPortsView(generic.ObjectChildrenView):
    """Display trunk ports for a WDM node."""

    queryset = WdmNode.objects.all()
    child_model = WdmTrunkPort
    table = WdmTrunkPortTable
    filterset = WdmTrunkPortFilterSet
    actions = (EditObject, DeleteObject, BulkDelete)
    tab = ViewTab(
        label=_("Trunk Ports"),
        badge=lambda obj: obj.trunk_ports.count(),
        permission="netbox_fms.view_wdmtrunkport",
        weight=510,
    )

    def get_children(self, request, parent):
        """Return trunk ports filtered by parent WDM node."""
        return self.child_model.objects.restrict(request.user, "view").filter(wdm_node=parent)


@register_model_view(WdmNode, "wavelength_editor", path="wavelength-editor")
class WdmNodeWavelengthEditorView(generic.ObjectView):
    """Live wavelength channel editor for ROADM nodes."""

    queryset = WdmNode.objects.all()
    tab = ViewTab(
        label=_("Wavelength Editor"),
        permission="netbox_fms.change_wavelengthchannel",
        weight=600,
    )

    def get_template_name(self):
        """Return the wavelength editor template."""
        return "netbox_fms/wdmnode_wavelength_editor.html"

    def get_extra_context(self, request, instance):
        """Build JSON config for the wavelength editor frontend."""
        import json

        channels = instance.channels.select_related("front_port").order_by("grid_position")
        # Available ports = device FrontPorts not already assigned to a channel
        assigned_fp_ids = set(
            instance.channels.exclude(front_port__isnull=True).values_list("front_port_id", flat=True)
        )
        available_ports = FrontPort.objects.filter(device=instance.device).exclude(pk__in=assigned_fp_ids)

        channel_data = []
        for ch in channels:
            svc_name = None
            svc_assignment = (
                WavelengthServiceChannelAssignment.objects.filter(channel=ch).select_related("service").first()
            )
            if svc_assignment:
                svc_name = svc_assignment.service.name
            channel_data.append(
                {
                    "id": ch.pk,
                    "grid_position": ch.grid_position,
                    "wavelength_nm": float(ch.wavelength_nm),
                    "label": ch.label,
                    "front_port_id": ch.front_port_id,
                    "front_port_name": ch.front_port.name if ch.front_port else None,
                    "status": ch.status,
                    "service_name": svc_name,
                }
            )

        port_data = [{"id": p.pk, "name": p.name} for p in available_ports]

        config = {
            "nodeId": instance.pk,
            "nodeType": instance.node_type,
            "lastUpdated": str(instance.last_updated),
            "applyUrl": reverse("plugins-api:netbox_fms-api:wdmnode-apply-mapping", args=[instance.pk]),
            "channels": channel_data,
            "availablePorts": port_data,
        }
        return {"editor_config_json": json.dumps(config)}


# ---------------------------------------------------------------------------
# WDM Trunk Port
# ---------------------------------------------------------------------------


@register_model_view(WdmTrunkPort)
class WdmTrunkPortView(generic.ObjectView):
    """Display a single WDM trunk port."""

    queryset = WdmTrunkPort.objects.all()


class WdmTrunkPortEditView(generic.ObjectEditView):
    """Handle WDM trunk port creation and editing."""

    queryset = WdmTrunkPort.objects.all()
    form = WdmTrunkPortForm


class WdmTrunkPortDeleteView(generic.ObjectDeleteView):
    """Delete a WDM trunk port."""

    queryset = WdmTrunkPort.objects.all()


# ---------------------------------------------------------------------------
# Wavelength Channel
# ---------------------------------------------------------------------------


class WavelengthChannelListView(generic.ObjectListView):
    """List all wavelength channels."""

    queryset = WavelengthChannel.objects.select_related("wdm_node", "front_port")
    table = WavelengthChannelTable
    filterset = WavelengthChannelFilterSet
    filterset_form = WavelengthChannelFilterForm


@register_model_view(WavelengthChannel)
class WavelengthChannelView(generic.ObjectView):
    """Display a single wavelength channel."""

    queryset = WavelengthChannel.objects.all()


class WavelengthChannelEditView(generic.ObjectEditView):
    """Handle wavelength channel creation and editing."""

    queryset = WavelengthChannel.objects.all()
    form = WavelengthChannelForm


class WavelengthChannelDeleteView(generic.ObjectDeleteView):
    """Delete a wavelength channel."""

    queryset = WavelengthChannel.objects.all()


class WavelengthChannelBulkEditView(generic.BulkEditView):
    """Bulk edit wavelength channels."""

    queryset = WavelengthChannel.objects.all()
    filterset = WavelengthChannelFilterSet
    table = WavelengthChannelTable
    form = WavelengthChannelBulkEditForm


class WavelengthChannelBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete wavelength channels."""

    queryset = WavelengthChannel.objects.all()
    filterset = WavelengthChannelFilterSet
    table = WavelengthChannelTable


# ---------------------------------------------------------------------------
# Wavelength Service
# ---------------------------------------------------------------------------


class WavelengthServiceListView(generic.ObjectListView):
    """List all wavelength services."""

    queryset = WavelengthService.objects.select_related("tenant")
    table = WavelengthServiceTable
    filterset = WavelengthServiceFilterSet
    filterset_form = WavelengthServiceFilterForm


@register_model_view(WavelengthService)
class WavelengthServiceView(generic.ObjectView):
    """Display a single wavelength service."""

    queryset = WavelengthService.objects.all()


@register_model_view(WavelengthService, "trace", path="trace")
class WavelengthServiceTraceView(generic.ObjectView):
    """Stitched wavelength path trace visualization."""

    queryset = WavelengthService.objects.all()
    tab = ViewTab(
        label=_("Trace"),
        permission="netbox_fms.view_wavelengthservice",
        weight=500,
    )

    def get_template_name(self):
        """Return the trace tab template."""
        return "netbox_fms/wavelengthservice_trace_tab.html"

    def get_extra_context(self, request, instance):
        """Return the stitched path for the trace tab."""
        return {"stitched_path": instance.get_stitched_path()}


class WavelengthServiceEditView(generic.ObjectEditView):
    """Handle wavelength service creation and editing."""

    queryset = WavelengthService.objects.all()
    form = WavelengthServiceForm


class WavelengthServiceDeleteView(generic.ObjectDeleteView):
    """Delete a wavelength service."""

    queryset = WavelengthService.objects.all()


class WavelengthServiceBulkImportView(generic.BulkImportView):
    """Bulk import wavelength services from CSV."""

    queryset = WavelengthService.objects.all()
    model_form = WavelengthServiceImportForm


class WavelengthServiceBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete wavelength services."""

    queryset = WavelengthService.objects.all()
    filterset = WavelengthServiceFilterSet
    table = WavelengthServiceTable
