from dcim.models import Cable, Device, FrontPort
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
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
)
from .services import NeedsMappingConfirmation, link_cable_topology
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
)

# ---------------------------------------------------------------------------
# FiberCableType
# ---------------------------------------------------------------------------


class FiberCableTypeListView(generic.ObjectListView):
    queryset = FiberCableType.objects.annotate(instance_count=models.Count("instances"))
    table = FiberCableTypeTable
    filterset = FiberCableTypeFilterSet
    filterset_form = FiberCableTypeFilterForm


@register_model_view(FiberCableType)
class FiberCableTypeView(generic.ObjectView):
    queryset = FiberCableType.objects.all()


class FiberCableTypeEditView(generic.ObjectEditView):
    queryset = FiberCableType.objects.all()
    form = FiberCableTypeForm


class FiberCableTypeDeleteView(generic.ObjectDeleteView):
    queryset = FiberCableType.objects.all()


class FiberCableTypeBulkImportView(generic.BulkImportView):
    queryset = FiberCableType.objects.all()
    model_form = FiberCableTypeImportForm


class FiberCableTypeBulkEditView(generic.BulkEditView):
    queryset = FiberCableType.objects.all()
    filterset = FiberCableTypeFilterSet
    table = FiberCableTypeTable
    form = FiberCableTypeBulkEditForm


class FiberCableTypeBulkDeleteView(generic.BulkDeleteView):
    queryset = FiberCableType.objects.all()
    filterset = FiberCableTypeFilterSet
    table = FiberCableTypeTable


# ---------------------------------------------------------------------------
# FiberCableType component tab views
# ---------------------------------------------------------------------------


class FiberCableTypeComponentsView(generic.ObjectChildrenView):
    queryset = FiberCableType.objects.all()
    actions = (EditObject, DeleteObject, BulkEdit, BulkDelete)
    viewname = None

    def get_children(self, request, parent):
        return self.child_model.objects.restrict(request.user, "view").filter(fiber_cable_type=parent)

    def get_extra_context(self, request, instance):
        return {
            "return_url": reverse(self.viewname, kwargs={"pk": instance.pk}),
        }


@register_model_view(FiberCableType, "buffertubes", path="buffer-tubes")
class FiberCableTypeBufferTubesView(FiberCableTypeComponentsView):
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
        return FiberCable.objects.restrict(request.user, "view").filter(fiber_cable_type=parent)

    def get_extra_context(self, request, instance):
        return {
            "return_url": reverse(self.viewname, kwargs={"pk": instance.pk}),
        }


# ---------------------------------------------------------------------------
# FiberCableType component bulk edit/delete views
# ---------------------------------------------------------------------------


class BufferTubeTemplateBulkEditView(generic.BulkEditView):
    queryset = BufferTubeTemplate.objects.all()
    filterset = BufferTubeTemplateFilterSet
    table = BufferTubeTemplateTable
    form = BufferTubeTemplateBulkEditForm


class BufferTubeTemplateBulkDeleteView(generic.BulkDeleteView):
    queryset = BufferTubeTemplate.objects.all()
    filterset = BufferTubeTemplateFilterSet
    table = BufferTubeTemplateTable


class RibbonTemplateBulkEditView(generic.BulkEditView):
    queryset = RibbonTemplate.objects.all()
    filterset = RibbonTemplateFilterSet
    table = RibbonTemplateTable
    form = RibbonTemplateBulkEditForm


class RibbonTemplateBulkDeleteView(generic.BulkDeleteView):
    queryset = RibbonTemplate.objects.all()
    filterset = RibbonTemplateFilterSet
    table = RibbonTemplateTable


class CableElementTemplateBulkEditView(generic.BulkEditView):
    queryset = CableElementTemplate.objects.all()
    filterset = CableElementTemplateFilterSet
    table = CableElementTemplateTable
    form = CableElementTemplateBulkEditForm


class CableElementTemplateBulkDeleteView(generic.BulkDeleteView):
    queryset = CableElementTemplate.objects.all()
    filterset = CableElementTemplateFilterSet
    table = CableElementTemplateTable


# ---------------------------------------------------------------------------
# BufferTubeTemplate
# ---------------------------------------------------------------------------


class BufferTubeTemplateListView(generic.ObjectListView):
    queryset = BufferTubeTemplate.objects.all()
    table = BufferTubeTemplateTable
    filterset = BufferTubeTemplateFilterSet


class BufferTubeTemplateView(generic.ObjectView):
    queryset = BufferTubeTemplate.objects.all()


class BufferTubeTemplateEditView(generic.ObjectEditView):
    queryset = BufferTubeTemplate.objects.all()
    form = BufferTubeTemplateForm


class BufferTubeTemplateDeleteView(generic.ObjectDeleteView):
    queryset = BufferTubeTemplate.objects.all()


# ---------------------------------------------------------------------------
# CableElementTemplate
# ---------------------------------------------------------------------------


class CableElementTemplateListView(generic.ObjectListView):
    queryset = CableElementTemplate.objects.all()
    table = CableElementTemplateTable
    filterset = CableElementTemplateFilterSet


class CableElementTemplateView(generic.ObjectView):
    queryset = CableElementTemplate.objects.all()


class CableElementTemplateEditView(generic.ObjectEditView):
    queryset = CableElementTemplate.objects.all()
    form = CableElementTemplateForm


class CableElementTemplateDeleteView(generic.ObjectDeleteView):
    queryset = CableElementTemplate.objects.all()


# ---------------------------------------------------------------------------
# RibbonTemplate
# ---------------------------------------------------------------------------


class RibbonTemplateListView(generic.ObjectListView):
    queryset = RibbonTemplate.objects.all()
    table = RibbonTemplateTable
    filterset = RibbonTemplateFilterSet


class RibbonTemplateView(generic.ObjectView):
    queryset = RibbonTemplate.objects.all()


class RibbonTemplateEditView(generic.ObjectEditView):
    queryset = RibbonTemplate.objects.all()
    form = RibbonTemplateForm


class RibbonTemplateDeleteView(generic.ObjectDeleteView):
    queryset = RibbonTemplate.objects.all()


# ---------------------------------------------------------------------------
# FiberCable (instance)
# ---------------------------------------------------------------------------


class FiberCableListView(generic.ObjectListView):
    queryset = FiberCable.objects.select_related("cable", "fiber_cable_type")
    table = FiberCableTable
    filterset = FiberCableFilterSet
    filterset_form = FiberCableFilterForm


@register_model_view(FiberCable)
class FiberCableView(generic.ObjectView):
    queryset = FiberCable.objects.all()


class FiberCableEditView(generic.ObjectEditView):
    queryset = FiberCable.objects.all()
    form = FiberCableForm


class FiberCableDeleteView(generic.ObjectDeleteView):
    queryset = FiberCable.objects.all()


class FiberCableBulkImportView(generic.BulkImportView):
    queryset = FiberCable.objects.all()
    model_form = FiberCableImportForm


class FiberCableBulkEditView(generic.BulkEditView):
    queryset = FiberCable.objects.all()
    filterset = FiberCableFilterSet
    table = FiberCableTable
    form = FiberCableBulkEditForm


class FiberCableBulkDeleteView(generic.BulkDeleteView):
    queryset = FiberCable.objects.all()
    filterset = FiberCableFilterSet
    table = FiberCableTable


# ---------------------------------------------------------------------------
# FiberCable component tab views
# ---------------------------------------------------------------------------


class FiberCableComponentsView(generic.ObjectChildrenView):
    queryset = FiberCable.objects.all()
    actions = (EditObject, DeleteObject, BulkDelete)
    viewname = None

    def get_children(self, request, parent):
        return self.child_model.objects.restrict(request.user, "view").filter(fiber_cable=parent)

    def get_extra_context(self, request, instance):
        return {
            "return_url": reverse(self.viewname, kwargs={"pk": instance.pk}),
        }


@register_model_view(FiberCable, "buffertubes", path="buffer-tubes")
class FiberCableBufferTubesView(FiberCableComponentsView):
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


# ---------------------------------------------------------------------------
# SplicePlan
# ---------------------------------------------------------------------------


class SplicePlanListView(generic.ObjectListView):
    queryset = SplicePlan.objects.annotate(entry_count=models.Count("entries"))
    table = SplicePlanTable
    filterset = SplicePlanFilterSet
    filterset_form = SplicePlanFilterForm


class SplicePlanView(generic.ObjectView):
    queryset = SplicePlan.objects.all()

    def get_extra_context(self, request, instance):
        entries_table = SplicePlanEntryTable(instance.entries.all())
        entries_table.configure(request)
        return {
            "entries_table": entries_table,
        }


class SplicePlanEditView(generic.ObjectEditView):
    queryset = SplicePlan.objects.all()
    form = SplicePlanForm


class SplicePlanDeleteView(generic.ObjectDeleteView):
    queryset = SplicePlan.objects.all()


class SplicePlanBulkImportView(generic.BulkImportView):
    queryset = SplicePlan.objects.all()
    model_form = SplicePlanImportForm


class SplicePlanBulkEditView(generic.BulkEditView):
    queryset = SplicePlan.objects.all()
    filterset = SplicePlanFilterSet
    table = SplicePlanTable
    form = SplicePlanBulkEditForm


class SplicePlanBulkDeleteView(generic.BulkDeleteView):
    queryset = SplicePlan.objects.all()
    filterset = SplicePlanFilterSet
    table = SplicePlanTable


class SplicePlanQuickAddFormView(LoginRequiredMixin, View):
    """Return rendered SplicePlanForm HTML for the quick-add modal."""

    def get(self, request):
        from django.http import HttpResponse

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
        plan = get_object_or_404(SplicePlan, pk=pk)
        from .services import import_live_state

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
        plan = get_object_or_404(SplicePlan, pk=pk)
        from .services import get_or_recompute_diff

        diff = get_or_recompute_diff(plan)
        return render(
            request,
            "netbox_fms/spliceplan_apply_confirm.html",
            {"object": plan, "diff": diff},
        )

    @transaction.atomic
    def post(self, request, pk):
        plan = get_object_or_404(SplicePlan, pk=pk)

        # Block applying if any splices are protected by fiber circuits
        from .choices import FiberCircuitStatusChoices
        from .models import FiberCircuitNode

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

        from .services import apply_diff

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
        from django.http import HttpResponse

        from .export import generate_drawio

        plan = get_object_or_404(SplicePlan, pk=pk)
        xml_content = generate_drawio(plan)
        response = HttpResponse(xml_content, content_type="application/xml")
        response["Content-Disposition"] = f'attachment; filename="{plan.name}.drawio"'
        return response


# ---------------------------------------------------------------------------
# ClosureCableEntry
# ---------------------------------------------------------------------------


class ClosureCableEntryListView(generic.ObjectListView):
    queryset = ClosureCableEntry.objects.select_related("closure", "fiber_cable")
    table = ClosureCableEntryTable
    filterset = ClosureCableEntryFilterSet
    filterset_form = ClosureCableEntryFilterForm


class ClosureCableEntryView(generic.ObjectView):
    queryset = ClosureCableEntry.objects.all()

    def get_extra_context(self, request, instance):
        strand_info = None
        if instance.fiber_cable:
            from django.db.models import Q

            total = instance.fiber_cable.fiber_strands.count()
            linked = instance.fiber_cable.fiber_strands.filter(
                Q(front_port_a__device=instance.closure) | Q(front_port_b__device=instance.closure)
            ).count()
            strand_info = {"linked": linked, "total": total}
        return {"strand_info": strand_info}


class ClosureCableEntryEditView(generic.ObjectEditView):
    queryset = ClosureCableEntry.objects.all()
    form = ClosureCableEntryForm


class ClosureCableEntryDeleteView(generic.ObjectDeleteView):
    queryset = ClosureCableEntry.objects.all()


class ClosureCableEntryBulkDeleteView(generic.BulkDeleteView):
    queryset = ClosureCableEntry.objects.all()
    filterset = ClosureCableEntryFilterSet
    table = ClosureCableEntryTable


# ---------------------------------------------------------------------------
# SplicePlanEntry
# ---------------------------------------------------------------------------


class SplicePlanEntryListView(generic.ObjectListView):
    queryset = SplicePlanEntry.objects.all()
    table = SplicePlanEntryTable
    filterset = SplicePlanEntryFilterSet
    filterset_form = SplicePlanEntryFilterForm


class SplicePlanEntryView(generic.ObjectView):
    queryset = SplicePlanEntry.objects.all()


class SplicePlanEntryEditView(generic.ObjectEditView):
    queryset = SplicePlanEntry.objects.all()
    form = SplicePlanEntryForm


class SplicePlanEntryDeleteView(generic.ObjectDeleteView):
    queryset = SplicePlanEntry.objects.all()


class SplicePlanEntryBulkDeleteView(generic.BulkDeleteView):
    queryset = SplicePlanEntry.objects.all()
    filterset = SplicePlanEntryFilterSet
    table = SplicePlanEntryTable


# ---------------------------------------------------------------------------
# SpliceProject
# ---------------------------------------------------------------------------


class SpliceProjectListView(generic.ObjectListView):
    queryset = SpliceProject.objects.annotate(plan_count=models.Count("plans"))
    table = SpliceProjectTable
    filterset = SpliceProjectFilterSet
    filterset_form = SpliceProjectFilterForm


class SpliceProjectView(generic.ObjectView):
    queryset = SpliceProject.objects.all()

    def get_extra_context(self, request, instance):
        plans_table = SplicePlanTable(instance.plans.all())
        plans_table.configure(request)
        return {"plans_table": plans_table}


class SpliceProjectEditView(generic.ObjectEditView):
    queryset = SpliceProject.objects.all()
    form = SpliceProjectForm


class SpliceProjectDeleteView(generic.ObjectDeleteView):
    queryset = SpliceProject.objects.all()


class SpliceProjectBulkDeleteView(generic.BulkDeleteView):
    queryset = SpliceProject.objects.all()
    filterset = SpliceProjectFilterSet
    table = SpliceProjectTable


# ---------------------------------------------------------------------------
# SlackLoop
# ---------------------------------------------------------------------------


class SlackLoopListView(generic.ObjectListView):
    queryset = SlackLoop.objects.prefetch_related("fiber_cable", "site", "location", "tags")
    table = SlackLoopTable
    filterset = SlackLoopFilterSet
    filterset_form = SlackLoopFilterForm


@register_model_view(SlackLoop)
class SlackLoopView(generic.ObjectView):
    queryset = SlackLoop.objects.all()


class SlackLoopEditView(generic.ObjectEditView):
    queryset = SlackLoop.objects.all()
    form = SlackLoopForm


class SlackLoopDeleteView(generic.ObjectDeleteView):
    queryset = SlackLoop.objects.all()


class SlackLoopBulkImportView(generic.BulkImportView):
    queryset = SlackLoop.objects.all()
    model_form = SlackLoopImportForm


class SlackLoopBulkEditView(generic.BulkEditView):
    queryset = SlackLoop.objects.all()
    filterset = SlackLoopFilterSet
    table = SlackLoopTable
    form = SlackLoopBulkEditForm


class SlackLoopBulkDeleteView(generic.BulkDeleteView):
    queryset = SlackLoop.objects.all()
    filterset = SlackLoopFilterSet
    table = SlackLoopTable


# ---------------------------------------------------------------------------
# Insert Slack Loop into Closure
# ---------------------------------------------------------------------------


def insert_slack_loop_into_closure(slack_loop, closure, a_side_rear_ports, b_side_rear_ports, express_strand_positions):
    """Split a cable at a slack loop location and connect both halves through a closure."""
    from dcim.models import FrontPort as DcimFrontPort

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
            from .models import FiberCircuitNode

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
            DcimFrontPort.objects.filter(mappings__rear_port__in=a_side_rear_ports).order_by(
                "mappings__rear_port_position"
            )
        )
        b_front_ports = list(
            DcimFrontPort.objects.filter(mappings__rear_port__in=b_side_rear_ports).order_by(
                "mappings__rear_port_position"
            )
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
                from .models import FiberCircuitNode

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
        slack_loop = get_object_or_404(SlackLoop, pk=pk)
        form = InsertSlackLoopForm()
        return render(request, "netbox_fms/slackloop_insert.html", {"object": slack_loop, "form": form})

    def post(self, request, pk):
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
    queryset = FiberCircuit.objects.annotate(path_count=Count("paths"))
    table = FiberCircuitTable
    filterset = FiberCircuitFilterSet
    filterset_form = FiberCircuitFilterForm


class FiberCircuitView(generic.ObjectView):
    queryset = FiberCircuit.objects.all()

    def get_extra_context(self, request, instance):
        return {"paths": instance.paths.all()}


class FiberCircuitEditView(generic.ObjectEditView):
    queryset = FiberCircuit.objects.all()
    form = FiberCircuitForm


class FiberCircuitDeleteView(generic.ObjectDeleteView):
    queryset = FiberCircuit.objects.all()


class FiberCircuitBulkImportView(generic.BulkImportView):
    queryset = FiberCircuit.objects.all()
    model_form = FiberCircuitImportForm


class FiberCircuitBulkEditView(generic.BulkEditView):
    queryset = FiberCircuit.objects.all()
    filterset = FiberCircuitFilterSet
    table = FiberCircuitTable
    form = FiberCircuitBulkEditForm


class FiberCircuitBulkDeleteView(generic.BulkDeleteView):
    queryset = FiberCircuit.objects.all()
    filterset = FiberCircuitFilterSet
    table = FiberCircuitTable


# ---------------------------------------------------------------------------
# FiberCircuitPath
# ---------------------------------------------------------------------------


class FiberCircuitPathListView(generic.ObjectListView):
    queryset = FiberCircuitPath.objects.select_related("circuit", "origin", "destination")
    table = FiberCircuitPathTable
    filterset = FiberCircuitPathFilterSet
    filterset_form = FiberCircuitPathFilterForm


class FiberCircuitPathView(generic.ObjectView):
    queryset = FiberCircuitPath.objects.select_related("circuit", "origin", "destination")


class FiberCircuitPathEditView(generic.ObjectEditView):
    queryset = FiberCircuitPath.objects.all()
    form = FiberCircuitPathForm


class FiberCircuitPathDeleteView(generic.ObjectDeleteView):
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
    from dcim.models import FrontPort, PortMapping, RearPort

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
        form = ProvisionPortsForm(initial=request.GET)
        return render(request, "netbox_fms/provision_ports.html", {"form": form})

    def post(self, request):
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
    from dcim.models import CableTermination

    cable_ids = (
        CableTermination.objects.filter(_device_id=device.pk)
        .exclude(cable__isnull=True)
        .values_list("cable_id", flat=True)
        .distinct()
    )
    return FiberCable.objects.filter(cable_id__in=cable_ids).exists()


def _build_cable_rows(device):
    """Build context dicts for Fiber Overview, grouped by cable."""
    from dcim.models import CableTermination
    from django.db.models import Count, Q

    from .models import FiberStrand

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
    from dcim.models import CableTermination

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
        return render(
            request,
            "netbox_fms/device_fiber_overview.html",
            {
                "object": device,
                "device": device,
                "cable_rows": cable_rows,
                "plan": plan,
                "stats": stats,
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
        if not request.user.has_perm("netbox_fms.add_fibercable"):
            return HttpResponse("Permission denied", status=403)
        device = get_object_or_404(Device, pk=pk)
        cable_id = request.GET.get("cable_id")
        cable = get_object_or_404(Cable, pk=cable_id)

        from dcim.models import CableTermination, RearPort
        from django.contrib.contenttypes.models import ContentType

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
            from dcim.models import FrontPort

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
