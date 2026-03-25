"""REST API URL configuration for netbox_fms plugin."""

from django.urls import path
from netbox.api.routers import NetBoxRouter

from . import views

router = NetBoxRouter()
router.register("cable-types", views.FiberCableTypeViewSet)
router.register("buffer-tube-templates", views.BufferTubeTemplateViewSet)
router.register("ribbon-templates", views.RibbonTemplateViewSet)
router.register("cable-element-templates", views.CableElementTemplateViewSet)
router.register("fiber-cables", views.FiberCableViewSet)
router.register("buffer-tubes", views.BufferTubeViewSet)
router.register("ribbons", views.RibbonViewSet)
router.register("fiber-strands", views.FiberStrandViewSet)
router.register("cable-elements", views.CableElementViewSet)
router.register("splice-projects", views.SpliceProjectViewSet)
router.register("splice-plans", views.SplicePlanViewSet)
router.register("splice-plan-entries", views.SplicePlanEntryViewSet)
router.register("closure-cable-entries", views.ClosureCableEntryViewSet)
router.register("tray-profiles", views.TrayProfileViewSet)
router.register("tube-assignments", views.TubeAssignmentViewSet)
router.register("slack-loops", views.SlackLoopViewSet)
router.register("fiber-circuits", views.FiberCircuitViewSet)
router.register("fiber-circuit-paths", views.FiberCircuitPathViewSet)
router.register("fiber-circuit-nodes", views.FiberCircuitNodeViewSet)
urlpatterns = (
    [
        path(
            "fiber-circuits/protecting/", views.FiberCircuitProtectingAPIView.as_view(), name="fibercircuit-protecting"
        ),
    ]
    + router.urls
    + [
        path("closure-strands/<int:device_id>/", views.ClosureStrandsAPIView.as_view(), name="closure_strands"),
        path("closures/<int:device_id>/fiber-claims/", views.FiberClaimsAPIView.as_view(), name="closure_fiber_claims"),
        path("provision-ports/", views.ProvisionPortsAPIView.as_view(), name="provision_ports_api"),
    ]
)
