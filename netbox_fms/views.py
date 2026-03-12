from dcim.models import Device
from django.contrib import messages
from django.db import models, transaction
from django.shortcuts import get_object_or_404, redirect, render
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


class SplicePlanImportFromDeviceView(View):
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
        except Exception as e:
            messages.error(request, str(e))
        return redirect(plan.get_absolute_url())


class SplicePlanApplyView(View):
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
        except Exception as e:
            messages.error(request, str(e))
        return redirect(plan.get_absolute_url())


class SplicePlanExportDrawioView(View):
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
    queryset = ClosureCableEntry.objects.select_related("closure", "fiber_cable", "entrance_port")
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


class ProvisionPortsView(View):
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

        strands = fiber_cable.fiber_strands.select_related("buffer_tube").order_by("position")
        strand_count = strands.count()

        if strand_count == 0:
            messages.error(request, _("This fiber cable has no strands."))
            return render(request, "netbox_fms/provision_ports.html", {"form": form})

        # Check for already provisioned strands on this device
        already = strands.filter(front_port__device=device).exists()
        if already:
            messages.error(request, _("Some strands are already provisioned on this device."))
            return render(request, "netbox_fms/provision_ports.html", {"form": form})

        try:
            self._provision(fiber_cable, device, port_type, strands, strand_count)
            messages.success(
                request,
                _('Provisioned {count} ports for "{cable}" on {device}.').format(
                    count=strand_count, cable=fiber_cable, device=device
                ),
            )
        except Exception as e:
            messages.error(request, str(e))
            return render(request, "netbox_fms/provision_ports.html", {"form": form})

        return redirect(fiber_cable.get_absolute_url())

    @transaction.atomic
    def _provision(self, fiber_cable, device, port_type, strands, strand_count):
        from dcim.models import FrontPort, PortMapping, RearPort

        cable_label = str(fiber_cable.cable) if fiber_cable.cable else f"FiberCable-{fiber_cable.pk}"

        # Create one RearPort with positions = strand_count
        rear_port = RearPort(
            device=device,
            name=cable_label,
            type=port_type,
            positions=strand_count,
            color="",
        )
        rear_port.save()

        # Create FrontPorts and PortMappings
        for strand in strands:
            fp = FrontPort(
                device=device,
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

            strand.front_port = fp
            strand.save(update_fields=["front_port"])


# ---------------------------------------------------------------------------
# Splice Editor
# ---------------------------------------------------------------------------


class SpliceEditorView(View):
    """Visual splice editor for a SplicePlan."""

    def get(self, request, pk):
        plan = get_object_or_404(SplicePlan.objects.select_related("closure"), pk=pk)
        return render(request, "netbox_fms/splice_editor.html", {"object": plan})


# ---------------------------------------------------------------------------
# Device tab: Splice Editor injected on dcim.Device detail pages
# ---------------------------------------------------------------------------


def _device_has_fiber_cables(device):
    """Return True if any FiberCable's dcim.Cable terminates at this device."""
    from dcim.models import CableTermination

    return CableTermination.objects.filter(_device_id=device.pk).exclude(cable__isnull=True).exists()


@register_model_view(Device, "splice_editor", path="splice-editor")
class DeviceSpliceEditorView(View):
    """
    Splice editor tab on a dcim.Device detail page.

    Finds all SplicePlans for this closure device. If none exist,
    creates a default one. Renders the splice editor for the selected plan.
    """

    tab = ViewTab(
        label=_("Splice Editor"),
        visible=_device_has_fiber_cables,
        weight=1500,
    )

    def get(self, request, pk):
        device = get_object_or_404(Device, pk=pk)

        plan = SplicePlan.objects.filter(closure=device).first()

        diff = None
        if plan:
            from .services import get_or_recompute_diff

            diff = get_or_recompute_diff(plan)

        return render(
            request,
            "netbox_fms/device_splice_editor.html",
            {
                "object": device,
                "device": device,
                "plan": plan,
                "diff": diff,
                "tab": self.tab,
            },
        )
