from collections import OrderedDict

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from netbox.api.viewsets import NetBoxModelViewSet
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..filters import (
    BufferTubeFilterSet,
    BufferTubeTemplateFilterSet,
    CableElementFilterSet,
    CableElementTemplateFilterSet,
    ClosureCableEntryFilterSet,
    FiberCableFilterSet,
    FiberCableTypeFilterSet,
    FiberPathLossFilterSet,
    FiberStrandFilterSet,
    RibbonFilterSet,
    RibbonTemplateFilterSet,
    SplicePlanEntryFilterSet,
    SplicePlanFilterSet,
    SpliceProjectFilterSet,
)
from ..models import (
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
from .serializers import (
    BufferTubeSerializer,
    BufferTubeTemplateSerializer,
    CableElementSerializer,
    CableElementTemplateSerializer,
    ClosureCableEntrySerializer,
    FiberCableSerializer,
    FiberCableTypeSerializer,
    FiberPathLossSerializer,
    FiberStrandSerializer,
    ProvisionPortsInputSerializer,
    RibbonSerializer,
    RibbonTemplateSerializer,
    SplicePlanEntrySerializer,
    SplicePlanSerializer,
    SpliceProjectSerializer,
)


class FiberCableTypeViewSet(NetBoxModelViewSet):
    queryset = FiberCableType.objects.prefetch_related("manufacturer", "tags").annotate(
        instance_count=Count("instances")
    )
    serializer_class = FiberCableTypeSerializer
    filterset_class = FiberCableTypeFilterSet


class BufferTubeTemplateViewSet(NetBoxModelViewSet):
    queryset = BufferTubeTemplate.objects.prefetch_related("fiber_cable_type", "tags")
    serializer_class = BufferTubeTemplateSerializer
    filterset_class = BufferTubeTemplateFilterSet


class CableElementTemplateViewSet(NetBoxModelViewSet):
    queryset = CableElementTemplate.objects.prefetch_related("fiber_cable_type", "tags")
    serializer_class = CableElementTemplateSerializer
    filterset_class = CableElementTemplateFilterSet


class RibbonTemplateViewSet(NetBoxModelViewSet):
    queryset = RibbonTemplate.objects.prefetch_related("fiber_cable_type", "buffer_tube_template", "tags")
    serializer_class = RibbonTemplateSerializer
    filterset_class = RibbonTemplateFilterSet


class FiberCableViewSet(NetBoxModelViewSet):
    queryset = FiberCable.objects.prefetch_related("cable", "fiber_cable_type", "tags")
    serializer_class = FiberCableSerializer
    filterset_class = FiberCableFilterSet


class BufferTubeViewSet(NetBoxModelViewSet):
    queryset = BufferTube.objects.prefetch_related("fiber_cable", "tags")
    serializer_class = BufferTubeSerializer
    filterset_class = BufferTubeFilterSet


class RibbonViewSet(NetBoxModelViewSet):
    queryset = Ribbon.objects.prefetch_related("fiber_cable", "buffer_tube", "tags")
    serializer_class = RibbonSerializer
    filterset_class = RibbonFilterSet


class FiberStrandViewSet(NetBoxModelViewSet):
    queryset = FiberStrand.objects.prefetch_related("fiber_cable", "buffer_tube", "ribbon", "tags")
    serializer_class = FiberStrandSerializer
    filterset_class = FiberStrandFilterSet


class CableElementViewSet(NetBoxModelViewSet):
    queryset = CableElement.objects.prefetch_related("fiber_cable", "tags")
    serializer_class = CableElementSerializer
    filterset_class = CableElementFilterSet


class SplicePlanEntryViewSet(NetBoxModelViewSet):
    queryset = SplicePlanEntry.objects.prefetch_related("plan", "tray", "fiber_a", "fiber_b", "tags")
    serializer_class = SplicePlanEntrySerializer
    filterset_class = SplicePlanEntryFilterSet


class SpliceProjectViewSet(NetBoxModelViewSet):
    queryset = SpliceProject.objects.prefetch_related("tags").annotate(plan_count=Count("plans"))
    serializer_class = SpliceProjectSerializer
    filterset_class = SpliceProjectFilterSet


class ClosureCableEntryViewSet(NetBoxModelViewSet):
    queryset = ClosureCableEntry.objects.prefetch_related("closure", "fiber_cable", "tags")
    serializer_class = ClosureCableEntrySerializer
    filterset_class = ClosureCableEntryFilterSet


class SplicePlanViewSet(NetBoxModelViewSet):
    queryset = SplicePlan.objects.prefetch_related("closure", "project", "tags").annotate(entry_count=Count("entries"))
    serializer_class = SplicePlanSerializer
    filterset_class = SplicePlanFilterSet

    @action(detail=True, methods=["post"], url_path="import-from-device")
    def import_from_device(self, request, pk=None):
        plan = self.get_object()
        if not request.user.has_perm("netbox_fms.change_spliceplan"):
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )
        from ..services import import_live_state

        try:
            count = import_live_state(plan)
            return Response({"imported": count})
        except (ValueError, ValidationError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="apply")
    def apply_plan(self, request, pk=None):
        plan = self.get_object()
        if not request.user.has_perm("netbox_fms.change_spliceplan"):
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )
        from ..services import apply_diff

        try:
            result = apply_diff(plan)
            return Response(result)
        except (ValueError, ValidationError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["get"], url_path="diff")
    def get_diff(self, request, pk=None):
        plan = self.get_object()
        if not request.user.has_perm("netbox_fms.view_spliceplan"):
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )
        from ..services import get_or_recompute_diff

        diff = get_or_recompute_diff(plan)
        return Response(diff)

    @action(detail=True, methods=["post"], url_path="bulk-update")
    def bulk_update_entries(self, request, pk=None):
        plan = self.get_object()
        if not request.user.has_perm("netbox_fms.change_spliceplan"):
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )
        adds = request.data.get("add", [])
        removes = request.data.get("remove", [])

        from dcim.models import FrontPort

        try:
            with transaction.atomic():
                # Process removes
                for item in removes:
                    fa_id, fb_id = item["fiber_a"], item["fiber_b"]
                    SplicePlanEntry.objects.filter(
                        plan=plan,
                    ).filter(
                        models.Q(fiber_a_id=fa_id, fiber_b_id=fb_id) | models.Q(fiber_a_id=fb_id, fiber_b_id=fa_id)
                    ).delete()

                # Process adds
                for item in adds:
                    fa_id, fb_id = item["fiber_a"], item["fiber_b"]
                    fa = FrontPort.objects.get(pk=fa_id)
                    tray = fa.module
                    if tray is None:
                        raise ValueError(f"FrontPort {fa_id} has no module (tray)")
                    SplicePlanEntry.objects.create(
                        plan=plan,
                        tray=tray,
                        fiber_a_id=fa_id,
                        fiber_b_id=fb_id,
                    )

                plan.diff_stale = True
                plan.save(update_fields=["diff_stale"])

        except (FrontPort.DoesNotExist, ValueError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        entries = SplicePlanEntry.objects.filter(plan=plan)
        return Response(
            {
                "entries": [
                    {"id": e.pk, "fiber_a": e.fiber_a_id, "fiber_b": e.fiber_b_id, "tray": e.tray_id} for e in entries
                ]
            }
        )

    @action(detail=False, methods=["post"], url_path="quick-add")
    def quick_add(self, request):
        if not request.user.has_perm("netbox_fms.add_spliceplan"):
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = SplicePlanSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class FiberPathLossViewSet(NetBoxModelViewSet):
    queryset = FiberPathLoss.objects.prefetch_related("cable", "tags")
    serializer_class = FiberPathLossSerializer
    filterset_class = FiberPathLossFilterSet


# ---------------------------------------------------------------------------
# Splice toolkit API views
# ---------------------------------------------------------------------------


class ClosureStrandsAPIView(APIView):
    """Return strands grouped by cable/tube for a closure device."""

    permission_classes = [IsAuthenticated]

    def get(self, request, device_id):
        # Find all FiberCables whose dcim.Cable terminates at this device
        from dcim.models import CableTermination, FrontPort
        from django.contrib.contenttypes.models import ContentType

        # Get all cables connected to this device
        cable_ids = (
            CableTermination.objects.filter(
                _device_id=device_id,
            )
            .values_list("cable_id", flat=True)
            .distinct()
        )

        fiber_cables = FiberCable.objects.filter(cable_id__in=cable_ids).select_related("cable", "fiber_cable_type")

        # --- A) Build LIVE splice lookup (front_port_id → front_port_id) ---
        fp_ct = ContentType.objects.get_for_model(FrontPort)
        tray_front_port_ids = set(
            FrontPort.objects.filter(
                device_id=device_id,
                module__isnull=False,
            ).values_list("pk", flat=True)
        )
        live_lookup = {}  # front_port_id -> front_port_id
        if tray_front_port_ids:
            terms = CableTermination.objects.filter(
                termination_type=fp_ct,
                termination_id__in=tray_front_port_ids,
            ).values_list("cable_id", "termination_id", "cable_end")

            cable_terms = {}
            for cable_id, term_id, cable_end in terms:
                cable_terms.setdefault(cable_id, {})[cable_end] = term_id

            for _cable_id, ends in cable_terms.items():
                if "A" in ends and "B" in ends:
                    a_id, b_id = ends["A"], ends["B"]
                    if a_id in tray_front_port_ids and b_id in tray_front_port_ids:
                        live_lookup[a_id] = b_id
                        live_lookup[b_id] = a_id

        # --- B) Build PLAN splice lookup (optional, when plan_id param provided) ---
        plan_lookup = {}
        plan_id = request.query_params.get("plan_id")
        if plan_id:
            plan_entries = SplicePlanEntry.objects.filter(
                plan_id=plan_id,
            ).values_list("id", "fiber_a_id", "fiber_b_id")
            for entry_id, fa_id, fb_id in plan_entries:
                plan_lookup[fa_id] = (entry_id, fb_id)
                plan_lookup[fb_id] = (entry_id, fa_id)

        # --- C) Build front_port_id → strand_id reverse mapping ---
        fp_to_strand = {}
        for fc in fiber_cables:
            for s in fc.fiber_strands.all():
                if s.front_port_id:
                    fp_to_strand[s.front_port_id] = s.pk

        cable_groups = []
        for fc in fiber_cables:
            strands = fc.fiber_strands.select_related("buffer_tube", "ribbon").order_by("position")

            # Group strands by tube
            tubes_dict = OrderedDict()
            loose = []
            for s in strands:
                live_fp = live_lookup.get(s.front_port_id)
                live_strand = fp_to_strand.get(live_fp) if live_fp else None
                plan_info = plan_lookup.get(s.front_port_id, (None, None))
                plan_strand = fp_to_strand.get(plan_info[1]) if plan_info[1] else None
                strand_data = {
                    "id": s.pk,
                    "name": s.name,
                    "position": s.position,
                    "color": s.color,
                    "tube_color": s.buffer_tube.color if s.buffer_tube else None,
                    "tube_name": s.buffer_tube.name if s.buffer_tube else None,
                    "ribbon_name": s.ribbon.name if s.ribbon else None,
                    "ribbon_color": s.ribbon.color if s.ribbon else None,
                    "front_port_id": s.front_port_id,
                    "live_spliced_to": live_strand,
                    "plan_entry_id": plan_info[0],
                    "plan_spliced_to": plan_strand,
                }
                if s.buffer_tube:
                    tube_id = s.buffer_tube.pk
                    if tube_id not in tubes_dict:
                        tubes_dict[tube_id] = {
                            "id": s.buffer_tube.pk,
                            "name": s.buffer_tube.name,
                            "color": s.buffer_tube.color,
                            "stripe_color": s.buffer_tube.stripe_color,
                            "strand_count": 0,
                            "strands": [],
                        }
                    tubes_dict[tube_id]["strand_count"] += 1
                    tubes_dict[tube_id]["strands"].append(strand_data)
                else:
                    loose.append(strand_data)

            cable_groups.append(
                {
                    "fiber_cable_id": fc.pk,
                    "cable_label": str(fc.cable) if fc.cable else f"FiberCable-{fc.pk}",
                    "fiber_type": fc.fiber_cable_type.get_fiber_type_display(),
                    "strand_count": fc.fiber_cable_type.strand_count,
                    "tubes": list(tubes_dict.values()),
                    "loose_strands": loose,
                }
            )

        return Response(cable_groups)


class ProvisionPortsAPIView(APIView):
    """API endpoint to provision ports for a fiber cable on a device."""

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        serializer = ProvisionPortsInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from dcim.models import Device, FrontPort, PortMapping, RearPort

        fiber_cable = get_object_or_404(FiberCable, pk=serializer.validated_data["fiber_cable_id"])
        device = get_object_or_404(Device, pk=serializer.validated_data["device_id"])
        port_type = serializer.validated_data.get("port_type", "splice")

        strands = fiber_cable.fiber_strands.select_related("buffer_tube").order_by("position")
        strand_count = strands.count()

        if strand_count == 0:
            return Response({"error": "No strands on this fiber cable."}, status=status.HTTP_400_BAD_REQUEST)

        cable_label = str(fiber_cable.cable) if fiber_cable.cable else f"FiberCable-{fiber_cable.pk}"

        rear_port = RearPort(
            device=device,
            name=cable_label,
            type=port_type,
            positions=strand_count,
        )
        rear_port.save()

        created_ports = []
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
            created_ports.append(fp.pk)

        return Response(
            {
                "rear_port_id": rear_port.pk,
                "front_port_ids": created_ports,
                "count": strand_count,
            },
            status=status.HTTP_201_CREATED,
        )
