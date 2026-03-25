from dcim.models import Cable, CableTermination, Device, FrontPort, Module, PortMapping, RearPort
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

from .choices import FiberCircuitStatusChoices, SplicePlanStatusChoices, TrayRoleChoices
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
    actions = ()
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


class CableElementView(generic.ObjectView):
    """Detail view for a single CableElement."""

    queryset = CableElement.objects.all()


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

    queryset = SplicePlan.objects.select_related("project", "closure", "submitted_by").with_counts()
    table = SplicePlanTable
    filterset = SplicePlanFilterSet
    filterset_form = SplicePlanFilterForm


class SplicePlanView(generic.ObjectView):
    """Display a single splice plan with its entries."""

    queryset = SplicePlan.objects.all()

    def get_extra_context(self, request, instance):
        entries_table = SplicePlanEntryTable(
            instance.entries.select_related("tray").prefetch_related(
                "fiber_a__fiber_strands_a__fiber_cable__cable",
                "fiber_a__fiber_strands_b__fiber_cable__cable",
                "fiber_b__fiber_strands_a__fiber_cable__cable",
                "fiber_b__fiber_strands_b__fiber_cable__cable",
            )
        )
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


def _build_enriched_diff(plan):
    """Build an enriched diff with readable names for the apply preview."""
    raw_diff = get_or_recompute_diff(plan)

    all_fp_ids = set()
    tray_ids = set()
    for tray_id, tray_diff in raw_diff.items():
        tray_ids.add(tray_id)
        for pair in tray_diff.get("add", []) + tray_diff.get("remove", []) + tray_diff.get("unchanged", []):
            all_fp_ids.update(pair)

    fp_lookup = {}
    if all_fp_ids:
        for fp in FrontPort.objects.filter(pk__in=all_fp_ids).select_related("module"):
            fp_lookup[fp.pk] = str(fp)

    tray_lookup = {}
    if tray_ids:
        for m in Module.objects.filter(pk__in=tray_ids).select_related("module_type"):
            tray_lookup[m.pk] = str(m)

    def _enrich_pairs(pairs):
        return [
            {
                "fp_a": p[0],
                "fp_b": p[1],
                "name_a": fp_lookup.get(p[0], str(p[0])),
                "name_b": fp_lookup.get(p[1], str(p[1])),
            }
            for p in pairs
        ]

    diff = []
    total_add = 0
    total_remove = 0
    total_unchanged = 0
    for tray_id, tray_diff in raw_diff.items():
        adds = _enrich_pairs(tray_diff.get("add", []))
        removes = _enrich_pairs(tray_diff.get("remove", []))
        unchanged = _enrich_pairs(tray_diff.get("unchanged", []))
        total_add += len(adds)
        total_remove += len(removes)
        total_unchanged += len(unchanged)
        if adds or removes or unchanged:
            diff.append(
                {
                    "tray_id": tray_id,
                    "tray_name": tray_lookup.get(tray_id, f"Tray #{tray_id}"),
                    "add": adds,
                    "remove": removes,
                    "unchanged": unchanged,
                }
            )

    return diff, total_add, total_remove, total_unchanged


def _splice_plan_has_changes(instance):
    """Return True if the splice plan diff has pending additions or removals."""
    try:
        raw_diff = get_or_recompute_diff(instance)
        for tray_diff in raw_diff.values():
            if tray_diff.get("add") or tray_diff.get("remove"):
                return True
    except Exception:  # noqa: S110
        return False
    return False


@register_model_view(SplicePlan, "apply", path="apply")
class SplicePlanApplyView(generic.ObjectView):
    """Read-only preview tab on a SplicePlan — shows diff of what this plan would contribute."""

    queryset = SplicePlan.objects.all()
    tab = ViewTab(
        label=_("Pending Changes"),
        weight=600,
        visible=_splice_plan_has_changes,
    )

    def get_template_name(self):
        return "netbox_fms/spliceplan_apply_confirm.html"

    def get_extra_context(self, request, instance):
        diff, total_add, total_remove, total_unchanged = _build_enriched_diff(instance)

        # Detect invalid entries (tray not on this closure device)
        local_module_ids = set(Module.objects.filter(device=instance.closure).values_list("pk", flat=True))
        invalid_entries = []
        for entry in instance.entries.select_related("tray", "fiber_a", "fiber_b"):
            if entry.tray_id not in local_module_ids:
                invalid_entries.append(
                    {
                        "id": entry.pk,
                        "fiber_a": str(entry.fiber_a),
                        "fiber_b": str(entry.fiber_b),
                        "tray": str(entry.tray),
                    }
                )

        # Fetch recent changelog messages for this plan (with non-empty messages)
        from core.models import ObjectChange
        from django.contrib.contenttypes.models import ContentType
        from django.db.models import Q

        plan_ct = ContentType.objects.get_for_model(SplicePlan)
        recent_changes = (
            ObjectChange.objects.filter(
                Q(changed_object_type=plan_ct, changed_object_id=instance.pk)
                | Q(related_object_type=plan_ct, related_object_id=instance.pk)
            )
            .exclude(message="")
            .order_by("-time")[:10]
            .values_list("time", "user_name", "message")
        )
        changelog_messages = [{"time": t, "user": u, "message": m} for t, u, m in recent_changes]

        return {
            "diff": diff,
            "total_add": total_add,
            "total_remove": total_remove,
            "total_unchanged": total_unchanged,
            "invalid_entries": invalid_entries,
            "changelog_messages": changelog_messages,
        }


class SplicePlanExportDrawioView(LoginRequiredMixin, View):
    """Export splice plan as draw.io XML."""

    def get(self, request, pk):
        """Generate and return the draw.io XML file as a download."""
        plan = get_object_or_404(SplicePlan, pk=pk)
        xml_content = generate_drawio(plan)
        response = HttpResponse(xml_content, content_type="application/xml")
        response["Content-Disposition"] = f'attachment; filename="{plan.name}.drawio"'
        return response


class SplicePlanTransitionView(LoginRequiredMixin, View):
    """Handle splice plan status transitions via POST."""

    def post(self, request, pk):
        plan = get_object_or_404(SplicePlan, pk=pk)
        action = request.POST.get("action")

        if action == "submit":
            if plan.status != SplicePlanStatusChoices.DRAFT:
                messages.error(request, _("Only draft plans can be submitted."))
                return redirect(plan.get_absolute_url())
            if not request.user.has_perm("netbox_fms.change_spliceplan"):
                messages.error(request, _("You do not have permission to submit plans."))
                return redirect(plan.get_absolute_url())
            plan.status = SplicePlanStatusChoices.PENDING_APPROVAL
            plan.submitted_by = request.user
            plan.full_clean()
            plan.save()
            messages.success(request, _('Plan "{plan}" submitted for approval.').format(plan=plan))

        elif action == "approve":
            if plan.status != SplicePlanStatusChoices.PENDING_APPROVAL:
                messages.error(request, _("Only plans pending approval can be approved."))
                return redirect(plan.get_absolute_url())
            if not request.user.has_perm("netbox_fms.approve_spliceplan"):
                messages.error(request, _("You do not have permission to approve plans."))
                return redirect(plan.get_absolute_url())
            plan.status = SplicePlanStatusChoices.APPROVED
            plan.full_clean()
            plan.save()
            messages.success(request, _('Plan "{plan}" approved.').format(plan=plan))

        elif action == "reject":
            if plan.status != SplicePlanStatusChoices.PENDING_APPROVAL:
                messages.error(request, _("Only plans pending approval can be rejected."))
                return redirect(plan.get_absolute_url())
            if not request.user.has_perm("netbox_fms.approve_spliceplan"):
                messages.error(request, _("You do not have permission to reject plans."))
                return redirect(plan.get_absolute_url())
            plan.status = SplicePlanStatusChoices.DRAFT
            plan.full_clean()
            plan.save()
            messages.success(request, _('Plan "{plan}" rejected, returned to draft.').format(plan=plan))

        elif action == "withdraw":
            if plan.status != SplicePlanStatusChoices.PENDING_APPROVAL:
                messages.error(request, _("Only plans pending approval can be withdrawn."))
                return redirect(plan.get_absolute_url())
            if plan.submitted_by != request.user:
                messages.error(request, _("Only the submitter can withdraw this plan."))
                return redirect(plan.get_absolute_url())
            plan.status = SplicePlanStatusChoices.DRAFT
            plan.full_clean()
            plan.save()
            messages.success(request, _('Plan "{plan}" withdrawn, returned to draft.').format(plan=plan))

        elif action == "reopen":
            if plan.status != SplicePlanStatusChoices.APPROVED:
                messages.error(request, _("Only approved plans can be reopened."))
                return redirect(plan.get_absolute_url())
            if not request.user.has_perm("netbox_fms.approve_spliceplan"):
                messages.error(request, _("You do not have permission to reopen plans."))
                return redirect(plan.get_absolute_url())
            plan.status = SplicePlanStatusChoices.DRAFT
            plan.full_clean()
            plan.save()
            messages.success(request, _('Plan "{plan}" reopened as draft.').format(plan=plan))

        elif action == "archive":
            if plan.status == SplicePlanStatusChoices.ARCHIVED:
                messages.error(request, _("Plan is already archived."))
                return redirect(plan.get_absolute_url())
            if plan.status == SplicePlanStatusChoices.DRAFT:
                if not request.user.has_perm("netbox_fms.change_spliceplan"):
                    messages.error(request, _("You do not have permission."))
                    return redirect(plan.get_absolute_url())
            else:
                if not request.user.has_perm("netbox_fms.approve_spliceplan"):
                    messages.error(request, _("You do not have permission to archive this plan."))
                    return redirect(plan.get_absolute_url())
            plan.status = SplicePlanStatusChoices.ARCHIVED
            plan.full_clean()
            plan.save()
            messages.success(request, _('Plan "{plan}" archived.').format(plan=plan))

        else:
            messages.error(request, _("Unknown action."))

        return redirect(plan.get_absolute_url())


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

    queryset = SplicePlanEntry.objects.select_related("plan", "tray", "fiber_a", "fiber_b").prefetch_related(
        "fiber_a__fiber_strands_a__fiber_cable__cable",
        "fiber_a__fiber_strands_b__fiber_cable__cable",
        "fiber_b__fiber_strands_a__fiber_cable__cable",
        "fiber_b__fiber_strands_b__fiber_cable__cable",
    )
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
        plans_table = SplicePlanTable(instance.plans.select_related("project", "closure").with_counts())
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

    from .signals import fms_portmapping_bypass

    with fms_portmapping_bypass():
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
    """Provision dcim FrontPort/RearPort/PortMapping for a FiberCable on a Device (htmx modal)."""

    def _get_context(self, request, form=None):
        fiber_cable = get_object_or_404(
            FiberCable, pk=request.GET.get("fiber_cable") or request.POST.get("fiber_cable")
        )
        if form is None:
            form = ProvisionPortsForm(initial={"fiber_cable": fiber_cable.pk})
        return {"form": form, "fiber_cable": fiber_cable}

    def get(self, request):
        """Render the provision ports form inside the htmx modal."""
        ctx = self._get_context(request)
        return render(request, "netbox_fms/provision_ports_modal.html", ctx)

    def post(self, request):
        """Create FrontPort/RearPort/PortMapping for the selected fiber cable and device."""
        form = ProvisionPortsForm(request.POST)
        ctx = self._get_context(request, form)
        fiber_cable = ctx["fiber_cable"]
        template = "netbox_fms/provision_ports_modal.html"

        if not form.is_valid():
            return render(request, template, ctx)

        device = form.cleaned_data["device"]
        port_type = form.cleaned_data["port_type"]

        # Check for already provisioned strands on this device
        already = fiber_cable.fiber_strands.filter(
            Q(front_port_a__device=device) | Q(front_port_b__device=device)
        ).exists()
        if already:
            messages.error(request, _("Some strands are already provisioned on this device."))
            return render(request, template, ctx)

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
            return render(request, template, ctx)

        response = HttpResponse(status=204)
        response["HX-Redirect"] = fiber_cable.get_absolute_url()
        return response


# ---------------------------------------------------------------------------
# Splice Editor
# ---------------------------------------------------------------------------


@register_model_view(SplicePlan, "splice_editor", path="editor")
class SpliceEditorView(generic.ObjectView):
    """Visual splice editor tab on a SplicePlan detail page."""

    queryset = SplicePlan.objects.all()
    tab = ViewTab(
        label=_("Visual Editor"),
        weight=500,
    )

    def get_template_name(self):
        """Return the splice editor template."""
        return "netbox_fms/splice_editor.html"

    def get_extra_context(self, request, instance):
        """Return context for the splice editor."""
        return {
            "context_mode": "plan-edit",
        }


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


def _build_tray_assignment_data(device):
    """Build tray assignment context for the Fiber Overview tab."""
    modules = Module.objects.filter(device=device).select_related("module_type__tray_profile")
    tube_assignments = TubeAssignment.objects.filter(closure=device).select_related(
        "tray", "buffer_tube__fiber_cable__fiber_cable_type"
    )

    assignment_map = {}
    for ta in tube_assignments:
        assignment_map.setdefault(ta.tray_id, []).append(ta)

    splice_trays = []
    express_baskets = []

    for module in modules:
        profile = getattr(module.module_type, "tray_profile", None)
        if not profile:
            continue

        assigned_tubes = assignment_map.get(module.pk, [])
        fiber_count = sum(t.buffer_tube.fiber_strands.count() for t in assigned_tubes)

        entry = {
            "module": module,
            "profile": profile,
            "assigned_tubes": assigned_tubes,
            "fiber_count": fiber_count,
            "capacity": profile.max_fibers,
        }

        if profile.tray_role == TrayRoleChoices.SPLICE_TRAY:
            splice_trays.append(entry)
        else:
            express_baskets.append(entry)

    assigned_tube_ids = set(tube_assignments.values_list("buffer_tube_id", flat=True))
    cable_entry_fc_ids = ClosureCableEntry.objects.filter(closure=device).values_list("fiber_cable_id", flat=True)
    unassigned_tubes = (
        BufferTube.objects.filter(
            fiber_cable_id__in=cable_entry_fc_ids,
        )
        .exclude(pk__in=assigned_tube_ids)
        .select_related("fiber_cable__fiber_cable_type")
    )

    return {
        "splice_trays": splice_trays,
        "express_baskets": express_baskets,
        "unassigned_tubes": list(unassigned_tubes),
        "has_trays": bool(splice_trays or express_baskets),
    }


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

        tray_data = _build_tray_assignment_data(device)

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
                "tray_data": tray_data,
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


def _device_has_approved_plans(device):
    """Return True if the device (closure) has at least one approved splice plan."""
    return SplicePlan.objects.filter(
        closure=device,
        status=SplicePlanStatusChoices.APPROVED,
    ).exists()


@register_model_view(Device, "pending_work", path="pending-work")
class DevicePendingWorkView(generic.ObjectView):
    """Closure-level view showing combined changes from all approved splice plans."""

    queryset = Device.objects.all()
    tab = ViewTab(
        label=_("Pending Work"),
        visible=_device_has_approved_plans,
        weight=1600,
    )

    def get_template_name(self):
        return "netbox_fms/device_pending_work.html"

    def get_extra_context(self, request, instance):
        approved_plans = SplicePlan.objects.filter(
            closure=instance,
            status=SplicePlanStatusChoices.APPROVED,
        ).select_related("project")

        # Build combined diff from all approved plans
        combined_diff = []
        total_add = 0
        total_remove = 0
        total_unchanged = 0

        for plan in approved_plans:
            plan_diff, p_add, p_remove, p_unchanged = _build_enriched_diff(plan)
            for tray_data in plan_diff:
                for action_key in ("add", "remove", "unchanged"):
                    for pair in tray_data.get(action_key, []):
                        pair["plan_name"] = plan.name
                        pair["project_name"] = plan.project.name if plan.project else ""
            combined_diff.extend(plan_diff)
            total_add += p_add
            total_remove += p_remove
            total_unchanged += p_unchanged

        return {
            "diff": combined_diff,
            "total_add": total_add,
            "total_remove": total_remove,
            "total_unchanged": total_unchanged,
            "approved_plans": approved_plans,
        }

    def post(self, request, pk):
        """Apply all approved plans atomically."""
        device = get_object_or_404(Device, pk=pk)

        approved_plans = list(
            SplicePlan.objects.filter(
                closure=device,
                status=SplicePlanStatusChoices.APPROVED,
            ).select_for_update()
        )

        if not approved_plans:
            messages.error(request, _("No approved plans to apply."))
            return redirect(device.get_absolute_url())

        # Verify all are still approved (race condition guard)
        if any(p.status != SplicePlanStatusChoices.APPROVED for p in approved_plans):
            messages.error(request, _("Some plans are no longer approved. Please review."))
            return redirect(device.get_absolute_url())

        # Block applying if any splices are protected by active fiber circuits
        fp_ids = set()
        for plan in approved_plans:
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
                return redirect(device.get_absolute_url())

        try:
            with transaction.atomic():
                total_added = 0
                total_removed = 0

                for plan in approved_plans:
                    # Clean up invalid entries before applying (tray not on this closure)
                    local_module_ids = set(Module.objects.filter(device=plan.closure).values_list("pk", flat=True))
                    plan.entries.exclude(tray_id__in=local_module_ids).delete()

                    result = apply_diff(plan)
                    total_added += result["added"]
                    total_removed += result["removed"]

                    # Archive the plan
                    plan.status = SplicePlanStatusChoices.ARCHIVED
                    plan.cached_diff = None
                    plan.diff_stale = True
                    plan.save(update_fields=["status", "cached_diff", "diff_stale"])

            msg = _("Applied {added} additions and {removed} removals from {count} plan(s).").format(
                added=total_added,
                removed=total_removed,
                count=len(approved_plans),
            )
            messages.success(request, msg)
        except (ValueError, ValidationError, IntegrityError) as e:
            messages.error(request, str(e))

        return redirect(device.get_absolute_url())


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
# Tray Assignment HTMX views
# ---------------------------------------------------------------------------


class TrayAssignmentsSectionView(LoginRequiredMixin, View):
    """Return the tray assignments HTML fragment for HTMX refresh."""

    def get(self, request, pk):
        device = get_object_or_404(Device, pk=pk)
        tray_data = _build_tray_assignment_data(device)
        return render(
            request,
            "netbox_fms/htmx/tray_assignments_card.html",
            {"device": device, "tray_data": tray_data},
        )


class AssignTubeView(LoginRequiredMixin, View):
    """HTMX modal for assigning a buffer tube to a tray."""

    def get(self, request, pk):
        if not request.user.has_perm("netbox_fms.add_tubeassignment"):
            return HttpResponse("Permission denied", status=403)
        device = get_object_or_404(Device, pk=pk)
        tube_id = request.GET.get("tube_id")
        tube = get_object_or_404(BufferTube, pk=tube_id)

        available_trays = Module.objects.filter(
            device=device,
            module_type__tray_profile__tray_role=TrayRoleChoices.SPLICE_TRAY,
        ).select_related("module_type")

        return render(
            request,
            "netbox_fms/htmx/assign_tube_modal.html",
            {
                "device": device,
                "tube": tube,
                "available_trays": available_trays,
                "post_url": reverse("plugins:netbox_fms:fiber_overview_assign_tube", kwargs={"pk": pk}),
            },
        )

    def post(self, request, pk):
        if not request.user.has_perm("netbox_fms.add_tubeassignment"):
            return HttpResponse("Permission denied", status=403)
        device = get_object_or_404(Device, pk=pk)
        tube_id = request.POST.get("tube_id")
        tray_id = request.POST.get("tray_id")
        tube = get_object_or_404(BufferTube, pk=tube_id)
        tray = get_object_or_404(Module, pk=tray_id)

        ta = TubeAssignment(closure=device, tray=tray, buffer_tube=tube)
        ta.full_clean()
        ta.save()

        return self._respond(request, device)

    @staticmethod
    def _respond(request, device):
        """Return refreshed tray card (HTMX) or redirect (plain form)."""
        if request.headers.get("HX-Request"):
            tray_data = _build_tray_assignment_data(device)
            response = render(
                request, "netbox_fms/htmx/tray_assignments_card.html", {"device": device, "tray_data": tray_data}
            )
            response["HX-Trigger"] = "fmsCloseModal"
            return response
        return redirect(reverse("dcim:device", kwargs={"pk": device.pk}) + "fiber-overview/")


class UnassignTubeView(LoginRequiredMixin, View):
    """Remove a tube assignment via HTMX POST."""

    def post(self, request, pk):
        if not request.user.has_perm("netbox_fms.delete_tubeassignment"):
            return HttpResponse("Permission denied", status=403)
        device = get_object_or_404(Device, pk=pk)
        tube_id = request.POST.get("tube_id")
        TubeAssignment.objects.filter(closure=device, buffer_tube_id=tube_id).delete()

        if request.headers.get("HX-Request"):
            tray_data = _build_tray_assignment_data(device)
            return render(
                request, "netbox_fms/htmx/tray_assignments_card.html", {"device": device, "tray_data": tray_data}
            )
        return redirect(reverse("dcim:device", kwargs={"pk": device.pk}) + "fiber-overview/")


class AutoAssignTubesView(LoginRequiredMixin, View):
    """Auto-assign unassigned tubes to splice trays, pairing by tube position.

    Tubes at the same position across cables (e.g. T1 from Cable A and T1
    from Cable B) are assigned to the same tray when capacity allows.
    """

    def post(self, request, pk):
        if not request.user.has_perm("netbox_fms.add_tubeassignment"):
            return HttpResponse("Permission denied", status=403)
        device = get_object_or_404(Device, pk=pk)

        trays = list(
            Module.objects.filter(
                device=device,
                module_type__tray_profile__tray_role=TrayRoleChoices.SPLICE_TRAY,
            ).select_related("module_type__tray_profile")
        )

        # Build tray capacity: max_fibers minus already-assigned fiber count
        tray_remaining = {}
        for tray in trays:
            profile = tray.module_type.tray_profile
            used = sum(
                ta.buffer_tube.fiber_strands.count()
                for ta in TubeAssignment.objects.filter(tray=tray).select_related("buffer_tube")
            )
            tray_remaining[tray.pk] = {"tray": tray, "remaining": profile.max_fibers - used}

        assigned_tube_ids = set(TubeAssignment.objects.filter(closure=device).values_list("buffer_tube_id", flat=True))
        cable_fc_ids = ClosureCableEntry.objects.filter(closure=device).values_list("fiber_cable_id", flat=True)
        unassigned_tubes = (
            BufferTube.objects.filter(fiber_cable_id__in=cable_fc_ids)
            .exclude(pk__in=assigned_tube_ids)
            .select_related("fiber_cable")
            .order_by("position", "fiber_cable__pk")
        )

        # Group unassigned tubes by position so same-position tubes get the same tray
        from collections import defaultdict

        by_position = defaultdict(list)
        for tube in unassigned_tubes:
            by_position[tube.position].append(tube)

        # Assign each position group to a tray, ordered by position
        tray_list = sorted(tray_remaining.values(), key=lambda t: t["tray"].pk)
        tray_idx = 0

        for position in sorted(by_position.keys()):
            tubes = by_position[position]
            total_fibers = sum(t.fiber_strands.count() for t in tubes)

            # Find a tray with enough capacity, starting from where we left off
            assigned = False
            for offset in range(len(tray_list)):
                idx = (tray_idx + offset) % len(tray_list)
                info = tray_list[idx]
                if info["remaining"] >= total_fibers:
                    for tube in tubes:
                        TubeAssignment.objects.create(closure=device, tray=info["tray"], buffer_tube=tube)
                    info["remaining"] -= total_fibers
                    tray_idx = idx + 1
                    assigned = True
                    break

            if not assigned:
                # Fall back: assign tubes individually to any tray with space
                for tube in tubes:
                    fiber_count = tube.fiber_strands.count()
                    for info in tray_list:
                        if info["remaining"] >= fiber_count:
                            TubeAssignment.objects.create(closure=device, tray=info["tray"], buffer_tube=tube)
                            info["remaining"] -= fiber_count
                            break

        if request.headers.get("HX-Request"):
            tray_data = _build_tray_assignment_data(device)
            return render(
                request, "netbox_fms/htmx/tray_assignments_card.html", {"device": device, "tray_data": tray_data}
            )
        return redirect(reverse("dcim:device", kwargs={"pk": pk}) + "fiber-overview/")
