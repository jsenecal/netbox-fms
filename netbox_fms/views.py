from dcim.models import Cable, Device, Module
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views import View
from netbox.views import generic
from utilities.views import ViewTab, register_model_view

from .filters import (
    BufferTubeTemplateFilterSet,
    CableElementTemplateFilterSet,
    ClosureCableEntryFilterSet,
    FiberCableFilterSet,
    FiberCableTypeFilterSet,
    FiberPathLossFilterSet,
    RibbonTemplateFilterSet,
    SplicePlanEntryFilterSet,
    SplicePlanFilterSet,
    SpliceProjectFilterSet,
)
from .forms import (
    BufferTubeTemplateForm,
    CableElementTemplateForm,
    ClosureCableEntryFilterForm,
    ClosureCableEntryForm,
    CreateFiberCableFromCableForm,
    FiberCableBulkEditForm,
    FiberCableFilterForm,
    FiberCableForm,
    FiberCableImportForm,
    FiberCableTypeBulkEditForm,
    FiberCableTypeFilterForm,
    FiberCableTypeForm,
    FiberCableTypeImportForm,
    FiberPathLossFilterForm,
    FiberPathLossForm,
    ProvisionPortsForm,
    ProvisionStrandsFromOverviewForm,
    RibbonTemplateForm,
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
    BufferTubeTemplate,
    CableElementTemplate,
    ClosureCableEntry,
    FiberCable,
    FiberCableType,
    FiberPathLoss,
    RibbonTemplate,
    SplicePlan,
    SplicePlanEntry,
    SpliceProject,
)
from .tables import (
    BufferTubeTable,
    BufferTubeTemplateTable,
    CableElementTable,
    CableElementTemplateTable,
    ClosureCableEntryTable,
    FiberCableTable,
    FiberCableTypeTable,
    FiberPathLossTable,
    FiberStrandTable,
    RibbonTable,
    RibbonTemplateTable,
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


class FiberCableTypeView(generic.ObjectView):
    queryset = FiberCableType.objects.all()

    def get_extra_context(self, request, instance):
        tubes_table = BufferTubeTemplateTable(instance.buffer_tube_templates.all())
        tubes_table.configure(request)
        ribbons_table = RibbonTemplateTable(instance.ribbon_templates.all())
        ribbons_table.configure(request)
        elements_table = CableElementTemplateTable(instance.cable_element_templates.all())
        elements_table.configure(request)
        return {
            "tubes_table": tubes_table,
            "ribbons_table": ribbons_table,
            "elements_table": elements_table,
        }


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


class FiberCableView(generic.ObjectView):
    queryset = FiberCable.objects.all()

    def get_extra_context(self, request, instance):
        tubes_table = BufferTubeTable(instance.buffer_tubes.all())
        tubes_table.configure(request)
        ribbons_table = RibbonTable(instance.ribbons.all())
        ribbons_table.configure(request)
        strands_table = FiberStrandTable(instance.fiber_strands.all())
        strands_table.configure(request)
        elements_table = CableElementTable(instance.cable_elements.all())
        elements_table.configure(request)
        return {
            "tubes_table": tubes_table,
            "ribbons_table": ribbons_table,
            "strands_table": strands_table,
            "elements_table": elements_table,
        }


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
# FiberPathLoss
# ---------------------------------------------------------------------------


class FiberPathLossListView(generic.ObjectListView):
    queryset = FiberPathLoss.objects.all()
    table = FiberPathLossTable
    filterset = FiberPathLossFilterSet
    filterset_form = FiberPathLossFilterForm


class FiberPathLossView(generic.ObjectView):
    queryset = FiberPathLoss.objects.all()


class FiberPathLossEditView(generic.ObjectEditView):
    queryset = FiberPathLoss.objects.all()
    form = FiberPathLossForm


class FiberPathLossDeleteView(generic.ObjectDeleteView):
    queryset = FiberPathLoss.objects.all()


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


def _build_cable_rows(device, rearports):
    """Build context dicts for all cable rows in one batch — avoids N+1 queries."""
    from dcim.models import CableTermination, RearPort
    from django.contrib.contenttypes.models import ContentType

    if not rearports:
        return []

    rp_ct = ContentType.objects.get_for_model(RearPort)
    rp_ids = [rp.pk for rp in rearports]

    terms = CableTermination.objects.filter(
        termination_type=rp_ct,
        termination_id__in=rp_ids,
    ).select_related("cable")
    term_by_rp = {t.termination_id: t for t in terms}

    cable_ids = [t.cable_id for t in terms if t.cable_id]
    fc_by_cable = {}
    if cable_ids:
        for fc in FiberCable.objects.filter(cable_id__in=cable_ids).select_related("cable", "fiber_cable_type"):
            fc_by_cable[fc.cable_id] = fc

    fiber_cable_ids = [fc.pk for fc in fc_by_cable.values()]
    strand_totals = {}
    strand_provisioned = {}
    if fiber_cable_ids:
        from django.db.models import Count, Q

        from .models import FiberStrand

        totals = (
            FiberStrand.objects.filter(fiber_cable_id__in=fiber_cable_ids)
            .values("fiber_cable_id")
            .annotate(
                total=Count("pk"),
                provisioned=Count("pk", filter=Q(front_port_a__device=device) | Q(front_port_b__device=device)),
            )
        )
        for row in totals:
            strand_totals[row["fiber_cable_id"]] = row["total"]
            strand_provisioned[row["fiber_cable_id"]] = row["provisioned"]

    gland_by_fc = {}
    if fiber_cable_ids:
        for entry in ClosureCableEntry.objects.filter(closure=device, fiber_cable_id__in=fiber_cable_ids):
            gland_by_fc[entry.fiber_cable_id] = entry

    rows = []
    for rp in rearports:
        term = term_by_rp.get(rp.pk)
        cable = term.cable if term else None
        fiber_cable = fc_by_cable.get(cable.pk) if cable else None

        strand_info = None
        gland_entry = None
        if fiber_cable:
            strand_info = {
                "provisioned": strand_provisioned.get(fiber_cable.pk, 0),
                "total": strand_totals.get(fiber_cable.pk, 0),
            }
            gland_entry = gland_by_fc.get(fiber_cable.pk)

        rows.append(
            {
                "rearport": rp,
                "cable": cable,
                "fiber_cable": fiber_cable,
                "strand_info": strand_info,
                "gland_entry": gland_entry,
            }
        )

    return rows


def _build_cable_row(device, rearport):
    """Build context dict for a single cable row (used by HTMX row-swap endpoints)."""
    rows = _build_cable_rows(device, [rearport])
    return rows[0] if rows else {}


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

        from dcim.models import RearPort

        module_rearports = list(RearPort.objects.filter(device=device, module__isnull=False).select_related("module"))

        cable_rows = _build_cable_rows(device, module_rearports)

        plan = SplicePlan.objects.filter(closure=device).first()

        stats = {
            "tray_count": device.modules.count(),
            "cable_count": sum(1 for r in cable_rows if r["cable"]),
            "fiber_cable_count": sum(1 for r in cable_rows if r["fiber_cable"]),
            "strand_provisioned": sum(r["strand_info"]["provisioned"] for r in cable_rows if r["strand_info"]),
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


class CreateFiberCableFromCableView(LoginRequiredMixin, View):
    def get(self, request, pk):
        if not request.user.has_perm("netbox_fms.add_fibercable"):
            return HttpResponse("Permission denied", status=403)
        device = get_object_or_404(Device, pk=pk)
        cable_id = request.GET.get("cable_id")
        cable = get_object_or_404(Cable, pk=cable_id)

        already_exists = FiberCable.objects.filter(cable=cable).exists()

        form = None
        if not already_exists:
            form = CreateFiberCableFromCableForm()

        return render(
            request,
            "netbox_fms/htmx/create_fiber_cable_modal.html",
            {
                "device": device,
                "cable": cable,
                "already_exists": already_exists,
                "form": form,
                "post_url": reverse("plugins:netbox_fms:fiber_overview_create_fibercable", kwargs={"pk": pk}),
            },
        )

    @transaction.atomic
    def post(self, request, pk):
        if not request.user.has_perm("netbox_fms.add_fibercable"):
            return HttpResponse("Permission denied", status=403)
        device = get_object_or_404(Device, pk=pk)
        form = CreateFiberCableFromCableForm(request.POST)
        if not form.is_valid():
            cable = get_object_or_404(Cable, pk=request.POST.get("cable_id"))
            return render(
                request,
                "netbox_fms/htmx/create_fiber_cable_modal.html",
                {
                    "device": device,
                    "cable": cable,
                    "already_exists": False,
                    "form": form,
                    "post_url": reverse("plugins:netbox_fms:fiber_overview_create_fibercable", kwargs={"pk": pk}),
                },
            )

        cable = get_object_or_404(Cable, pk=form.cleaned_data["cable_id"])

        from dcim.models import CableTermination

        if not CableTermination.objects.filter(cable=cable, _device_id=device.pk).exists():
            return HttpResponse("Cable does not terminate on this device", status=400)

        FiberCable.objects.create(
            cable=cable,
            fiber_cable_type=form.cleaned_data["fiber_cable_type"],
        )

        redirect_url = reverse("dcim:device", kwargs={"pk": pk}) + "fiber-overview/"
        response = HttpResponse(status=200)
        response["HX-Redirect"] = redirect_url
        return response


class ProvisionStrandsFromOverviewView(LoginRequiredMixin, View):
    def get(self, request, pk):
        if not request.user.has_perm("dcim.add_frontport"):
            return HttpResponse("Permission denied", status=403)
        device = get_object_or_404(Device, pk=pk)
        fiber_cable_id = request.GET.get("fiber_cable_id")
        fiber_cable = get_object_or_404(FiberCable, pk=fiber_cable_id)

        initial = {"fiber_cable_id": fiber_cable.pk}
        if fiber_cable.cable:
            from dcim.models import CableTermination, RearPort
            from django.contrib.contenttypes.models import ContentType

            rp_ct = ContentType.objects.get_for_model(RearPort)
            term = CableTermination.objects.filter(
                cable=fiber_cable.cable,
                termination_type=rp_ct,
            ).first()
            if term:
                rp = RearPort.objects.filter(pk=term.termination_id).select_related("module").first()
                if rp and rp.module:
                    initial["target_module"] = rp.module.pk

        form = ProvisionStrandsFromOverviewForm(initial=initial)
        form.fields["target_module"].queryset = Module.objects.filter(device=device)

        return render(
            request,
            "netbox_fms/htmx/provision_strands_modal.html",
            {
                "device": device,
                "fiber_cable": fiber_cable,
                "form": form,
                "post_url": reverse("plugins:netbox_fms:fiber_overview_provision_strands", kwargs={"pk": pk}),
            },
        )

    def post(self, request, pk):
        if not request.user.has_perm("dcim.add_frontport"):
            return HttpResponse("Permission denied", status=403)
        device = get_object_or_404(Device, pk=pk)
        form = ProvisionStrandsFromOverviewForm(request.POST)
        form.fields["target_module"].queryset = Module.objects.filter(device=device)

        fiber_cable_id = request.POST.get("fiber_cable_id")
        fiber_cable = get_object_or_404(FiberCable, pk=fiber_cable_id)

        from dcim.models import CableTermination

        if (
            fiber_cable.cable
            and not CableTermination.objects.filter(cable=fiber_cable.cable, _device_id=device.pk).exists()
        ):
            return HttpResponse("Fiber cable does not terminate on this device", status=400)

        if not form.is_valid():
            return render(
                request,
                "netbox_fms/htmx/provision_strands_modal.html",
                {
                    "device": device,
                    "fiber_cable": fiber_cable,
                    "form": form,
                    "post_url": reverse("plugins:netbox_fms:fiber_overview_provision_strands", kwargs={"pk": pk}),
                },
            )

        module = form.cleaned_data["target_module"]
        port_type = form.cleaned_data["port_type"]

        already = fiber_cable.fiber_strands.filter(
            Q(front_port_a__device=device) | Q(front_port_b__device=device)
        ).exists()
        if already:
            return render(
                request,
                "netbox_fms/htmx/provision_strands_modal.html",
                {
                    "device": device,
                    "fiber_cable": fiber_cable,
                    "form": form,
                    "error_message": _("Strands are already provisioned on this device."),
                    "post_url": reverse("plugins:netbox_fms:fiber_overview_provision_strands", kwargs={"pk": pk}),
                },
            )

        try:
            provision_strands(fiber_cable, device, port_type, module=module)
        except ValueError as e:
            return render(
                request,
                "netbox_fms/htmx/provision_strands_modal.html",
                {
                    "device": device,
                    "fiber_cable": fiber_cable,
                    "form": form,
                    "error_message": str(e),
                    "post_url": reverse("plugins:netbox_fms:fiber_overview_provision_strands", kwargs={"pk": pk}),
                },
            )

        redirect_url = reverse("dcim:device", kwargs={"pk": pk}) + "fiber-overview/"
        response = HttpResponse(status=200)
        response["HX-Redirect"] = redirect_url
        return response


class UpdateGlandLabelView(LoginRequiredMixin, View):
    def get(self, request, pk):
        if not request.user.has_perm("netbox_fms.change_closurecableentry") and not request.user.has_perm(
            "netbox_fms.add_closurecableentry"
        ):
            return HttpResponse("Permission denied", status=403)
        device = get_object_or_404(Device, pk=pk)
        fiber_cable_id = request.GET.get("fiber_cable_id")
        fiber_cable = get_object_or_404(FiberCable, pk=fiber_cable_id)
        rearport_id = request.GET.get("rearport_id")

        entry = ClosureCableEntry.objects.filter(closure=device, fiber_cable=fiber_cable).first()
        current_label = entry.entrance_label if entry else ""

        return render(
            request,
            "netbox_fms/htmx/edit_gland_modal.html",
            {
                "device": device,
                "fiber_cable": fiber_cable,
                "rearport_id": rearport_id,
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
        rearport_id = request.POST.get("rearport_id")
        entrance_label = request.POST.get("entrance_label", "").strip()

        entry, _created = ClosureCableEntry.objects.update_or_create(
            closure=device,
            fiber_cable=fiber_cable,
            defaults={"entrance_label": entrance_label},
        )

        from dcim.models import RearPort

        rearport = get_object_or_404(RearPort, pk=rearport_id)
        row = _build_cable_row(device, rearport)

        response = render(
            request,
            "netbox_fms/htmx/fiber_overview_row.html",
            {
                "device": device,
                "row": row,
            },
        )
        response["HX-Trigger"] = "modalClose"
        return response
