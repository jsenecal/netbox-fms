from collections import OrderedDict

from dcim.models import CableTermination, Device, FrontPort, Module, PortMapping, RearPort
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from netbox.api.viewsets import NetBoxModelViewSet
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from ..choices import FiberCircuitStatusChoices
from ..filters import (
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
from ..models import (
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
    WdmChannelTemplate,
    WdmDeviceTypeProfile,
    WdmNode,
    WdmTrunkPort,
)
from ..services import apply_diff, get_or_recompute_diff, import_live_state
from ..trace_hops import build_hops, get_wavelength_service_annotations
from .serializers import (
    BufferTubeSerializer,
    BufferTubeTemplateSerializer,
    CableElementSerializer,
    CableElementTemplateSerializer,
    ClosureCableEntrySerializer,
    FiberCableSerializer,
    FiberCableTypeSerializer,
    FiberCircuitNodeSerializer,
    FiberCircuitPathSerializer,
    FiberCircuitSerializer,
    FiberStrandSerializer,
    ProvisionPortsInputSerializer,
    RibbonSerializer,
    RibbonTemplateSerializer,
    SlackLoopSerializer,
    SplicePlanEntrySerializer,
    SplicePlanSerializer,
    SpliceProjectSerializer,
    TrayProfileSerializer,
    TubeAssignmentSerializer,
    WavelengthChannelSerializer,
    WavelengthServiceSerializer,
    WdmChannelTemplateSerializer,
    WdmDeviceTypeProfileSerializer,
    WdmNodeSerializer,
    WdmTrunkPortSerializer,
)


class FiberCableTypeViewSet(NetBoxModelViewSet):
    """Manage fiber cable type blueprints."""

    queryset = FiberCableType.objects.prefetch_related("manufacturer", "tags").annotate(
        instance_count=Count("instances")
    )
    serializer_class = FiberCableTypeSerializer
    filterset_class = FiberCableTypeFilterSet


class BufferTubeTemplateViewSet(NetBoxModelViewSet):
    """Manage buffer tube templates for fiber cable types."""

    queryset = BufferTubeTemplate.objects.prefetch_related("fiber_cable_type", "tags")
    serializer_class = BufferTubeTemplateSerializer
    filterset_class = BufferTubeTemplateFilterSet


class CableElementTemplateViewSet(NetBoxModelViewSet):
    """Manage cable element templates (e.g., strength members, jackets)."""

    queryset = CableElementTemplate.objects.prefetch_related("fiber_cable_type", "tags")
    serializer_class = CableElementTemplateSerializer
    filterset_class = CableElementTemplateFilterSet


class RibbonTemplateViewSet(NetBoxModelViewSet):
    """Manage ribbon templates for fiber cable types."""

    queryset = RibbonTemplate.objects.prefetch_related("fiber_cable_type", "buffer_tube_template", "tags")
    serializer_class = RibbonTemplateSerializer
    filterset_class = RibbonTemplateFilterSet


class FiberCableViewSet(NetBoxModelViewSet):
    """Manage fiber cable instances linked to dcim cables."""

    queryset = FiberCable.objects.prefetch_related("cable", "fiber_cable_type", "tags")
    serializer_class = FiberCableSerializer
    filterset_class = FiberCableFilterSet


class BufferTubeViewSet(NetBoxModelViewSet):
    """Manage buffer tube instances within fiber cables."""

    queryset = BufferTube.objects.prefetch_related("fiber_cable", "tags")
    serializer_class = BufferTubeSerializer
    filterset_class = BufferTubeFilterSet


class RibbonViewSet(NetBoxModelViewSet):
    """Manage ribbon instances within fiber cables."""

    queryset = Ribbon.objects.prefetch_related("fiber_cable", "buffer_tube", "tags")
    serializer_class = RibbonSerializer
    filterset_class = RibbonFilterSet


class FiberStrandViewSet(NetBoxModelViewSet):
    """Manage individual fiber strand instances."""

    queryset = FiberStrand.objects.prefetch_related("fiber_cable", "buffer_tube", "ribbon", "tags")
    serializer_class = FiberStrandSerializer
    filterset_class = FiberStrandFilterSet


class CableElementViewSet(NetBoxModelViewSet):
    """Manage non-fiber cable elements (e.g., strength members)."""

    queryset = CableElement.objects.prefetch_related("fiber_cable", "tags")
    serializer_class = CableElementSerializer
    filterset_class = CableElementFilterSet


class SlackLoopViewSet(NetBoxModelViewSet):
    """Manage slack loop records for fiber cables."""

    queryset = SlackLoop.objects.prefetch_related("fiber_cable", "site", "location", "tags")
    serializer_class = SlackLoopSerializer
    filterset_class = SlackLoopFilterSet


class SplicePlanEntryViewSet(NetBoxModelViewSet):
    """Manage individual splice plan entries mapping fiber-to-fiber connections."""

    queryset = SplicePlanEntry.objects.prefetch_related("plan", "tray", "fiber_a", "fiber_b", "tags")
    serializer_class = SplicePlanEntrySerializer
    filterset_class = SplicePlanEntryFilterSet


class SpliceProjectViewSet(NetBoxModelViewSet):
    """Manage splice projects that group splice plans."""

    queryset = SpliceProject.objects.prefetch_related("tags").annotate(plan_count=Count("plans"))
    serializer_class = SpliceProjectSerializer
    filterset_class = SpliceProjectFilterSet


class ClosureCableEntryViewSet(NetBoxModelViewSet):
    """Manage cable entry records for closures."""

    queryset = ClosureCableEntry.objects.prefetch_related("closure", "fiber_cable", "tags")
    serializer_class = ClosureCableEntrySerializer
    filterset_class = ClosureCableEntryFilterSet


class TrayProfileViewSet(NetBoxModelViewSet):
    """Manage tray profiles for splice closure module types."""

    queryset = TrayProfile.objects.select_related("module_type")
    serializer_class = TrayProfileSerializer
    filterset_class = TrayProfileFilterSet


class TubeAssignmentViewSet(NetBoxModelViewSet):
    """Manage tube-to-tray assignments within closures."""

    queryset = TubeAssignment.objects.select_related("closure", "tray", "buffer_tube")
    serializer_class = TubeAssignmentSerializer
    filterset_class = TubeAssignmentFilterSet


class SplicePlanViewSet(NetBoxModelViewSet):
    """Manage splice plans and their associated actions (import, apply, diff)."""

    queryset = SplicePlan.objects.prefetch_related("closure", "project", "tags").annotate(entry_count=Count("entries"))
    serializer_class = SplicePlanSerializer
    filterset_class = SplicePlanFilterSet

    @action(detail=True, methods=["post"], url_path="import-from-device")
    def import_from_device(self, request, pk=None):
        """Import live splice state from the closure device into the plan."""
        plan = self.get_object()
        if not request.user.has_perm("netbox_fms.change_spliceplan"):
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            count = import_live_state(plan)
            return Response({"imported": count})
        except (ValueError, ValidationError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="apply")
    def apply_plan(self, request, pk=None):
        """Apply the splice plan diff to create/remove live cable terminations."""
        plan = self.get_object()
        if not request.user.has_perm("netbox_fms.change_spliceplan"):
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )
        # Check for protected splices being modified
        protected = _get_protected_plan_ports(plan)
        if protected:
            names = ", ".join(sorted(set(protected.values())))
            return Response(
                {"error": f"Cannot apply: splices are protected by circuit(s): {names}"},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            result = apply_diff(plan)
            return Response(result)
        except (ValueError, ValidationError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["get"], url_path="diff")
    def get_diff(self, request, pk=None):
        """Return the computed diff between the plan and live splice state."""
        plan = self.get_object()
        if not request.user.has_perm("netbox_fms.view_spliceplan"):
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )
        diff = get_or_recompute_diff(plan)
        return Response(diff)

    @action(detail=True, methods=["post"], url_path="bulk-update")
    def bulk_update_entries(self, request, pk=None):
        """Add and remove splice plan entries in a single atomic operation."""
        plan = self.get_object()
        if not request.user.has_perm("netbox_fms.change_spliceplan"):
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )
        adds = request.data.get("add", [])
        removes = request.data.get("remove", [])

        # Validate payload structure
        for label, items in [("add", adds), ("remove", removes)]:
            if not isinstance(items, list):
                return Response(
                    {"error": f"'{label}' must be a list"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            for i, item in enumerate(items):
                if not isinstance(item, dict) or "fiber_a" not in item or "fiber_b" not in item:
                    return Response(
                        {"error": f"'{label}[{i}]' must have 'fiber_a' and 'fiber_b' keys"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        # Check protection on both removes AND adds (re-splicing a protected fiber)
        all_port_ids = set()
        for item in removes:
            all_port_ids.add(item["fiber_a"])
            all_port_ids.add(item["fiber_b"])
        for item in adds:
            all_port_ids.add(item["fiber_a"])
            all_port_ids.add(item["fiber_b"])

        if all_port_ids:
            protected_nodes = (
                FiberCircuitNode.objects.filter(front_port_id__in=all_port_ids)
                .exclude(path__circuit__status=FiberCircuitStatusChoices.DECOMMISSIONED)
                .select_related("path__circuit")
            )
            protected_names = {n.path.circuit.name for n in protected_nodes}
            if protected_names:
                names = ", ".join(sorted(protected_names))
                return Response(
                    {"error": f"Cannot modify protected splices (circuit(s): {names})"},
                    status=status.HTTP_409_CONFLICT,
                )

        # Validate FrontPorts exist before starting the transaction
        if all_port_ids:
            existing_ids = set(FrontPort.objects.filter(pk__in=all_port_ids).values_list("pk", flat=True))
            missing = all_port_ids - existing_ids
            if missing:
                return Response(
                    {"error": f"FrontPort(s) not found: {sorted(missing)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

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

                # Process adds — remove any conflicting entries first (re-splice case)
                for item in adds:
                    fa_id, fb_id = item["fiber_a"], item["fiber_b"]
                    # Clear any existing entries that use either fiber to avoid unique constraint violations
                    SplicePlanEntry.objects.filter(plan=plan).filter(
                        models.Q(fiber_a_id=fa_id)
                        | models.Q(fiber_b_id=fa_id)
                        | models.Q(fiber_a_id=fb_id)
                        | models.Q(fiber_b_id=fb_id)
                    ).delete()
                    fa = FrontPort.objects.get(pk=fa_id)
                    tray = fa.module
                    if tray is None:
                        return Response(
                            {"error": f"FrontPort {fa_id} has no module (tray). Assign it to a tray first."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    SplicePlanEntry.objects.create(
                        plan=plan,
                        tray=tray,
                        fiber_a_id=fa_id,
                        fiber_b_id=fb_id,
                    )

                plan.diff_stale = True
                plan.save(update_fields=["diff_stale"])

        except IntegrityError as e:
            return Response(
                {"error": f"Database constraint violation: {e}"},
                status=status.HTTP_409_CONFLICT,
            )
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
        """Create a new splice plan without requiring a full form submission."""
        if not request.user.has_perm("netbox_fms.add_spliceplan"):
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = SplicePlanSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Fiber Circuit API views
# ---------------------------------------------------------------------------


class FiberCircuitViewSet(NetBoxModelViewSet):
    """Manage fiber circuits and their paths."""

    queryset = FiberCircuit.objects.prefetch_related("paths", "tags")
    serializer_class = FiberCircuitSerializer
    filterset_class = FiberCircuitFilterSet

    @action(detail=True, methods=["post"])
    def retrace(self, request, pk=None):
        """Retrace all paths belonging to this fiber circuit."""
        circuit = self.get_object()
        for path in circuit.paths.all():
            path.retrace()
        serializer = self.get_serializer(circuit)
        return Response(serializer.data)


class FiberCircuitPathViewSet(NetBoxModelViewSet):
    """Manage fiber circuit paths and provide trace data."""

    queryset = FiberCircuitPath.objects.prefetch_related("tags")
    serializer_class = FiberCircuitPathSerializer
    filterset_class = FiberCircuitPathFilterSet

    @action(detail=True, methods=["get"], url_path="trace")
    def trace(self, request, pk=None):
        """Return the full hop-by-hop trace for this circuit path."""
        path_obj = self.get_object()
        hops = build_hops(path_obj.path)
        data = {
            "circuit_id": path_obj.circuit_id,
            "circuit_name": path_obj.circuit.name,
            "circuit_url": path_obj.circuit.get_absolute_url(),
            "path_position": path_obj.position,
            "is_complete": path_obj.is_complete,
            "total_calculated_loss_db": str(path_obj.calculated_loss_db) if path_obj.calculated_loss_db else None,
            "total_actual_loss_db": str(path_obj.actual_loss_db) if path_obj.actual_loss_db else None,
            "wavelength_nm": path_obj.wavelength_nm,
            "hops": hops,
        }
        data["wavelength_services"] = get_wavelength_service_annotations(path_obj.circuit)
        return Response(data)


class FiberCircuitNodeViewSet(ModelViewSet):
    """Provide read-only access to fiber circuit nodes."""

    queryset = FiberCircuitNode.objects.all()
    serializer_class = FiberCircuitNodeSerializer
    http_method_names = ["get", "head", "options"]


# ---------------------------------------------------------------------------
# WDM API views
# ---------------------------------------------------------------------------


class WdmDeviceTypeProfileViewSet(NetBoxModelViewSet):
    """Manage WDM device type profiles (blueprint-level WDM capabilities)."""

    queryset = WdmDeviceTypeProfile.objects.prefetch_related("device_type", "tags")
    serializer_class = WdmDeviceTypeProfileSerializer
    filterset_class = WdmDeviceTypeProfileFilterSet


class WdmChannelTemplateViewSet(NetBoxModelViewSet):
    """Manage WDM channel templates on device type profiles."""

    queryset = WdmChannelTemplate.objects.prefetch_related("profile", "tags")
    serializer_class = WdmChannelTemplateSerializer
    filterset_class = WdmChannelTemplateFilterSet


def _apply_mapping(wdm_node, desired_mapping: dict[int, int | None]) -> dict:
    """Apply channel-to-port mapping changes for a WDM node.

    Uses bulk operations to avoid O(N*M) query counts.
    """
    channels = {ch.pk: ch for ch in wdm_node.channels.all()}
    trunk_ports = list(wdm_node.trunk_ports.select_related("rear_port").all())

    added = 0
    removed = 0
    changed = 0
    affected_channels = []

    # Collect channels that actually changed
    channels_to_update = []
    old_fp_ids_to_delete = []  # (front_port_id, grid_position) pairs
    new_mappings_to_create = []  # PortMapping instances

    for ch_pk, desired_fp_pk in desired_mapping.items():
        ch = channels.get(ch_pk)
        if ch is None:
            continue

        current_fp_pk = ch.front_port_id
        if current_fp_pk == desired_fp_pk:
            continue

        affected_channels.append(ch)

        # Track old mappings to delete
        if current_fp_pk is not None:
            old_fp_ids_to_delete.append((current_fp_pk, ch.grid_position))

        # Track new mappings to create
        if desired_fp_pk is not None:
            for tp in trunk_ports:
                new_mappings_to_create.append(
                    PortMapping(
                        device=wdm_node.device,
                        front_port_id=desired_fp_pk,
                        rear_port=tp.rear_port,
                        front_port_position=1,
                        rear_port_position=ch.grid_position,
                    )
                )

        # Update channel FK
        ch.front_port_id = desired_fp_pk
        channels_to_update.append(ch)

        # Count
        if current_fp_pk is None and desired_fp_pk is not None:
            added += 1
        elif current_fp_pk is not None and desired_fp_pk is None:
            removed += 1
        else:
            changed += 1

    # Bulk update channels
    if channels_to_update:
        WavelengthChannel.objects.bulk_update(channels_to_update, ["front_port_id"])

    # Bulk delete old PortMappings
    if old_fp_ids_to_delete:
        delete_q = Q()
        for fp_id, grid_pos in old_fp_ids_to_delete:
            for tp in trunk_ports:
                delete_q |= Q(
                    front_port_id=fp_id,
                    rear_port=tp.rear_port,
                    rear_port_position=grid_pos,
                )
        if delete_q:
            PortMapping.objects.filter(delete_q).delete()

    # Bulk create new PortMappings
    if new_mappings_to_create:
        PortMapping.objects.bulk_create(new_mappings_to_create)

    # Retrace affected paths
    if affected_channels:
        _retrace_affected_paths(wdm_node, trunk_ports)

    return {"added": added, "removed": removed, "changed": changed}


def _retrace_affected_paths(wdm_node, trunk_ports):
    """Retrace FiberCircuitPaths that traverse cables connected to the node's trunk ports.

    Args:
        wdm_node: The WdmNode instance.
        trunk_ports: List of WdmTrunkPort instances on this node.
    """
    from dcim.models import CableTermination

    rp_ids = [tp.rear_port_id for tp in trunk_ports]
    if not rp_ids:
        return

    rp_ct = ContentType.objects.get_for_model(RearPort)
    cable_ids = (
        CableTermination.objects.filter(
            termination_type=rp_ct,
            termination_id__in=rp_ids,
        )
        .values_list("cable_id", flat=True)
        .distinct()
    )

    if not cable_ids:
        return

    affected_paths = FiberCircuitPath.objects.filter(
        nodes__cable_id__in=cable_ids,
    ).distinct()

    for path in affected_paths:
        path.retrace()


class WdmNodeViewSet(NetBoxModelViewSet):
    """Manage WDM node instances attached to devices."""

    queryset = WdmNode.objects.prefetch_related("device", "tags")
    serializer_class = WdmNodeSerializer
    filterset_class = WdmNodeFilterSet

    @action(detail=True, methods=["post"], url_path="apply-mapping")
    def apply_mapping(self, request, pk=None):
        """Apply channel-to-port mapping changes atomically."""
        node = self.get_object()

        # Concurrent edit check
        last_updated = request.data.get("last_updated")
        if last_updated and str(node.last_updated) != last_updated:
            return Response(
                {"detail": "Node was modified since editor loaded. Please reload."},
                status=status.HTTP_409_CONFLICT,
            )

        desired = request.data.get("mapping", {})
        desired = {int(k): (int(v) if v else None) for k, v in desired.items()}

        errors = WdmNode.validate_channel_mapping(node, desired)
        if errors:
            return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            result = _apply_mapping(node, desired)

        return Response(result)


class WdmTrunkPortViewSet(NetBoxModelViewSet):
    """Manage WDM trunk port mappings on WDM nodes."""

    queryset = WdmTrunkPort.objects.prefetch_related("wdm_node", "rear_port", "tags")
    serializer_class = WdmTrunkPortSerializer
    filterset_class = WdmTrunkPortFilterSet


class WavelengthChannelViewSet(NetBoxModelViewSet):
    """Manage wavelength channel instances on WDM nodes."""

    queryset = WavelengthChannel.objects.prefetch_related("wdm_node", "tags")
    serializer_class = WavelengthChannelSerializer
    filterset_class = WavelengthChannelFilterSet


class WavelengthServiceViewSet(NetBoxModelViewSet):
    """Manage end-to-end wavelength services spanning fiber circuits."""

    queryset = WavelengthService.objects.prefetch_related("tenant", "tags")
    serializer_class = WavelengthServiceSerializer
    filterset_class = WavelengthServiceFilterSet

    @action(detail=True, methods=["get"], url_path="stitch")
    def stitch(self, request, pk=None):
        """Return the stitched end-to-end wavelength path."""
        service = self.get_object()
        path = service.get_stitched_path()
        return Response(
            {
                "service_id": service.pk,
                "service_name": service.name,
                "wavelength_nm": float(service.wavelength_nm),
                "status": service.status,
                "is_complete": len(path) > 0,
                "hops": path,
            }
        )


class FiberCircuitProtectingAPIView(APIView):
    """Return circuits protecting the given objects."""

    queryset = FiberCircuit.objects.all()

    def get(self, request):
        """Return circuits that protect the specified cables, ports, or strands."""
        filters = models.Q()
        for param, field in [
            ("cable", "paths__nodes__cable_id"),
            ("front_port", "paths__nodes__front_port_id"),
            ("rear_port", "paths__nodes__rear_port_id"),
            ("fiber_strand", "paths__nodes__fiber_strand_id"),
            ("splice_entry", "paths__nodes__splice_entry_id"),
        ]:
            values = request.query_params.get(param)
            if values:
                ids = [int(v) for v in values.split(",")]
                filters |= models.Q(**{f"{field}__in": ids})
        if not filters:
            return Response([])
        circuits = FiberCircuit.objects.filter(filters).distinct()
        serializer = FiberCircuitSerializer(circuits, many=True, context={"request": request})
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Splice toolkit API views
# ---------------------------------------------------------------------------


def _get_protected_plan_ports(plan):
    """Return dict of {front_port_id: circuit_name} for ports in the plan that are protected."""
    fp_ids = set()
    for entry in plan.entries.all():
        fp_ids.add(entry.fiber_a_id)
        fp_ids.add(entry.fiber_b_id)
    if not fp_ids:
        return {}
    protected_nodes = (
        FiberCircuitNode.objects.filter(front_port_id__in=fp_ids)
        .exclude(path__circuit__status=FiberCircuitStatusChoices.DECOMMISSIONED)
        .select_related("path__circuit")
    )
    return {n.front_port_id: n.path.circuit.name for n in protected_nodes}


class ClosureStrandsAPIView(APIView):
    """Return strands grouped by cable/tube for a closure device."""

    permission_classes = [IsAuthenticated]

    def get(self, request, device_id):
        """Return strands grouped by cable and tube for the given closure device."""
        # Build tube assignment lookup: buffer_tube_id -> {tray_id, tray_name}
        tube_assignment_lookup = {}
        for ta in TubeAssignment.objects.filter(closure_id=device_id).select_related("tray"):
            tube_assignment_lookup[ta.buffer_tube_id] = {
                "tray_id": ta.tray_id,
                "tray_name": str(ta.tray),
                "tray_url": ta.get_absolute_url(),
            }

        # Find all FiberCables whose dcim.Cable terminates at this device
        # Get all cables connected to this device
        cable_ids = (
            CableTermination.objects.filter(
                _device_id=device_id,
            )
            .values_list("cable_id", flat=True)
            .distinct()
        )

        fiber_cables = FiberCable.objects.filter(cable_id__in=cable_ids).select_related("cable", "fiber_cable_type")

        # Build far-end device lookup: cable_id -> (device_name, device_url)
        far_end_lookup = {}
        all_terms = CableTermination.objects.filter(cable_id__in=cable_ids).select_related("cable")
        for term in all_terms:
            if term._device_id and term._device_id != device_id:
                try:
                    far_dev = Device.objects.get(pk=term._device_id)
                    far_end_lookup[term.cable_id] = {
                        "id": far_dev.pk,
                        "name": str(far_dev),
                        "url": far_dev.get_absolute_url(),
                    }
                except Device.DoesNotExist:
                    pass

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

        # --- C) Build protection lookup: front_port_id → circuit name ---
        # A front port is "protected" if referenced by a non-decommissioned FiberCircuitNode
        all_tray_fp_ids = set()
        for fc in fiber_cables:
            for s in fc.fiber_strands.all():
                if s.front_port_a_id:
                    all_tray_fp_ids.add(s.front_port_a_id)
                if s.front_port_b_id:
                    all_tray_fp_ids.add(s.front_port_b_id)

        protection_lookup = {}  # front_port_id -> (circuit_name, circuit_url)
        if all_tray_fp_ids:
            protected_nodes = (
                FiberCircuitNode.objects.filter(front_port_id__in=all_tray_fp_ids)
                .exclude(path__circuit__status=FiberCircuitStatusChoices.DECOMMISSIONED)
                .select_related("path__circuit")
            )
            for node in protected_nodes:
                circuit = node.path.circuit
                protection_lookup[node.front_port_id] = (circuit.name, circuit.get_absolute_url())

        # --- D) Build front_port_id → strand_id reverse mapping ---
        fp_to_strand = {}
        for fc in fiber_cables:
            for s in fc.fiber_strands.all():
                if s.front_port_a_id:
                    fp_to_strand[s.front_port_a_id] = s.pk
                if s.front_port_b_id:
                    fp_to_strand[s.front_port_b_id] = s.pk

        cable_groups = []
        for fc in fiber_cables:
            strands = fc.fiber_strands.select_related("buffer_tube", "ribbon").order_by("position")

            # Group strands by tube
            tubes_dict = OrderedDict()
            loose = []
            for s in strands:
                # Use the front_port that belongs to this closure's tray modules
                if s.front_port_a_id and s.front_port_a_id in tray_front_port_ids:
                    local_fp_id = s.front_port_a_id
                elif s.front_port_b_id and s.front_port_b_id in tray_front_port_ids:
                    local_fp_id = s.front_port_b_id
                else:
                    local_fp_id = s.front_port_a_id or s.front_port_b_id
                live_fp = live_lookup.get(local_fp_id)
                live_strand = fp_to_strand.get(live_fp) if live_fp else None
                plan_info = plan_lookup.get(local_fp_id, (None, None))
                plan_strand = fp_to_strand.get(plan_info[1]) if plan_info[1] else None
                circuit_info = protection_lookup.get(local_fp_id)
                circuit_name = circuit_info[0] if circuit_info else None
                circuit_url = circuit_info[1] if circuit_info else None
                strand_data = {
                    "id": s.pk,
                    "name": s.name,
                    "position": s.position,
                    "color": s.color,
                    "tube_color": s.buffer_tube.color if s.buffer_tube else None,
                    "tube_name": s.buffer_tube.name if s.buffer_tube else None,
                    "ribbon_name": s.ribbon.name if s.ribbon else None,
                    "ribbon_color": s.ribbon.color if s.ribbon else None,
                    "front_port_a_id": local_fp_id,
                    "live_spliced_to": live_strand,
                    "plan_entry_id": plan_info[0],
                    "plan_spliced_to": plan_strand,
                    "protected": circuit_name is not None,
                    "circuit_name": circuit_name,
                    "circuit_url": circuit_url,
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
                            "tray_assignment": tube_assignment_lookup.get(s.buffer_tube.pk),
                        }
                    tubes_dict[tube_id]["strand_count"] += 1
                    tubes_dict[tube_id]["strands"].append(strand_data)
                else:
                    loose.append(strand_data)

            far_end = far_end_lookup.get(fc.cable_id)
            cable_groups.append(
                {
                    "fiber_cable_id": fc.pk,
                    "cable_label": str(fc.cable) if fc.cable else f"FiberCable-{fc.pk}",
                    "cable_url": fc.get_absolute_url(),
                    "fiber_type": fc.fiber_cable_type.get_fiber_type_display(),
                    "strand_count": fc.fiber_cable_type.strand_count,
                    "far_device_name": far_end["name"] if far_end else None,
                    "far_device_url": far_end["url"] if far_end else None,
                    "tubes": list(tubes_dict.values()),
                    "loose_strands": loose,
                }
            )

        # Build trays list
        trays = []
        for m in Module.objects.filter(device_id=device_id).select_related("module_type"):
            profile = getattr(m.module_type, "tray_profile", None)
            if profile:
                trays.append(
                    {
                        "id": m.pk,
                        "name": str(m),
                        "role": profile.tray_role,
                        "capacity": FrontPort.objects.filter(module=m).count(),
                    }
                )

        return Response({"cables": cable_groups, "trays": trays})


class ProvisionPortsAPIView(APIView):
    """API endpoint to provision ports for a fiber cable on a device."""

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        """Create rear/front ports on a device and link them to fiber strands."""
        serializer = ProvisionPortsInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

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

            strand.front_port_a = fp
            strand.save(update_fields=["front_port_a"])
            created_ports.append(fp.pk)

        return Response(
            {
                "rear_port_id": rear_port.pk,
                "front_port_ids": created_ports,
                "count": strand_count,
            },
            status=status.HTTP_201_CREATED,
        )
