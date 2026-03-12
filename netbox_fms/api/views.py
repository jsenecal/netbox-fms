from collections import OrderedDict

from django.db import transaction
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
    FiberCableFilterSet,
    FiberCableTypeFilterSet,
    FiberPathLossFilterSet,
    FiberStrandFilterSet,
    RibbonFilterSet,
    RibbonTemplateFilterSet,
    SplicePlanEntryFilterSet,
    SplicePlanFilterSet,
)
from ..models import (
    BufferTube,
    BufferTubeTemplate,
    CableElement,
    CableElementTemplate,
    FiberCable,
    FiberCableType,
    FiberPathLoss,
    FiberStrand,
    Ribbon,
    RibbonTemplate,
    SplicePlan,
    SplicePlanEntry,
)
from .serializers import (
    BufferTubeSerializer,
    BufferTubeTemplateSerializer,
    BulkSpliceInputSerializer,
    CableElementSerializer,
    CableElementTemplateSerializer,
    FiberCableSerializer,
    FiberCableTypeSerializer,
    FiberPathLossSerializer,
    FiberStrandSerializer,
    ProvisionPortsInputSerializer,
    RibbonSerializer,
    RibbonTemplateSerializer,
    SplicePlanEntrySerializer,
    SplicePlanSerializer,
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
    queryset = SplicePlanEntry.objects.prefetch_related("plan", "fiber_a", "fiber_b", "cable", "tags")
    serializer_class = SplicePlanEntrySerializer
    filterset_class = SplicePlanEntryFilterSet


class SplicePlanViewSet(NetBoxModelViewSet):
    queryset = SplicePlan.objects.prefetch_related("closure", "tags").annotate(entry_count=Count("entries"))
    serializer_class = SplicePlanSerializer
    filterset_class = SplicePlanFilterSet

    @action(detail=True, methods=["post", "delete"], url_path="bulk-splice")
    def bulk_splice(self, request, pk=None):
        plan = self.get_object()

        if request.method == "POST":
            serializer = BulkSpliceInputSerializer(data=request.data, many=True)
            serializer.is_valid(raise_exception=True)
            created = []
            for item in serializer.validated_data:
                entry = SplicePlanEntry.objects.create(
                    plan=plan,
                    fiber_a_id=item["fiber_a"],
                    fiber_b_id=item["fiber_b"],
                )
                created.append(entry.pk)
            return Response({"created": created}, status=status.HTTP_201_CREATED)

        if request.method == "DELETE":
            entry_ids = request.data.get("entry_ids", [])
            if entry_ids:
                deleted, _ = plan.entries.filter(pk__in=entry_ids).delete()
            else:
                deleted, _ = plan.entries.all().delete()
            return Response({"deleted": deleted})


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
        from dcim.models import CableTermination

        # Get all cables connected to this device
        cable_ids = (
            CableTermination.objects.filter(
                _device_id=device_id,
            )
            .values_list("cable_id", flat=True)
            .distinct()
        )

        fiber_cables = FiberCable.objects.filter(cable_id__in=cable_ids).select_related("cable", "fiber_cable_type")

        # Build splice entry lookup: strand_id → (entry_id, spliced_to_id)
        splice_lookup = {}
        all_plan_entries = SplicePlanEntry.objects.filter(
            plan__closure_id=device_id,
        ).values_list("id", "fiber_a_id", "fiber_b_id")
        for entry_id, fa_id, fb_id in all_plan_entries:
            splice_lookup[fa_id] = (entry_id, fb_id)
            splice_lookup[fb_id] = (entry_id, fa_id)

        cable_groups = []
        for fc in fiber_cables:
            strands = fc.fiber_strands.select_related("buffer_tube", "ribbon").order_by("position")

            # Group strands by tube
            tubes_dict = OrderedDict()
            loose = []
            for s in strands:
                entry_info = splice_lookup.get(s.pk, (None, None))
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
                    "splice_entry_id": entry_info[0],
                    "spliced_to": entry_info[1],
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
