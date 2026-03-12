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
router.register("splice-plans", views.SplicePlanViewSet)
router.register("splice-plan-entries", views.SplicePlanEntryViewSet)
router.register("fiber-path-losses", views.FiberPathLossViewSet)

urlpatterns = router.urls + [
    path("closure-strands/<int:device_id>/", views.ClosureStrandsAPIView.as_view(), name="closure_strands"),
    path("provision-ports/", views.ProvisionPortsAPIView.as_view(), name="provision_ports_api"),
]
