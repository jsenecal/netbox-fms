from django.urls import include, path
from utilities.urls import get_model_urls

from . import views

# Model routes come from @register_model_view; each model mounts its list-level
# and object-level views under one URL prefix.
MODEL_PREFIXES = (
    ("cable-types", "fibercabletype"),
    ("attenuation-specs", "fiberattenuationspec"),
    ("buffer-tube-templates", "buffertubetemplate"),
    ("ribbon-templates", "ribbontemplate"),
    ("cable-element-templates", "cableelementtemplate"),
    ("fiber-cables", "fibercable"),
    ("cable-elements", "cableelement"),
    ("splice-plans", "spliceplan"),
    ("splice-plan-entries", "spliceplanentry"),
    ("splice-projects", "spliceproject"),
    ("closure-cable-entries", "closurecableentry"),
    ("tray-profiles", "trayprofile"),
    ("tube-assignments", "tubeassignment"),
    ("slack-loops", "slackloop"),
    ("faults", "fiberfault"),
    ("fiber-circuits", "fibercircuit"),
    ("fiber-circuit-paths", "fibercircuitpath"),
    ("fiber-paths", "fiberstrandpath"),
    ("path-anomalies", "pathanomaly"),
    ("path-analysis-queue", "pathanalysisqueue"),
)

urlpatterns = [
    # Splice Closure wizard
    path("splice-closures/add/", views.SpliceClosureCreateView.as_view(), name="spliceclosure_add"),
    path("faults/map-segments/", views.FiberFaultMapSegmentsView.as_view(), name="fiberfault_map_segments"),
    # Fiber Overview HTMX actions
    path(
        "fiber-overview/<int:pk>/update-gland/",
        views.UpdateGlandLabelView.as_view(),
        name="fiber_overview_update_gland",
    ),
    path(
        "fiber-overview/<int:pk>/link-topology/",
        views.LinkTopologyView.as_view(),
        name="fiber_overview_link_topology",
    ),
    path(
        "fiber-overview/<int:pk>/add-cable/",
        views.ClosureCableWizardView.as_view(),
        name="fiber_overview_add_cable",
    ),
    path(
        "fiber-overview/<int:pk>/tray-assignments/",
        views.TrayAssignmentsSectionView.as_view(),
        name="fiber_overview_tray_section",
    ),
    path(
        "fiber-overview/<int:pk>/assign-tube/",
        views.AssignTubeView.as_view(),
        name="fiber_overview_assign_tube",
    ),
    path(
        "fiber-overview/<int:pk>/unassign-tube/",
        views.UnassignTubeView.as_view(),
        name="fiber_overview_unassign_tube",
    ),
    path(
        "fiber-overview/<int:pk>/auto-assign/",
        views.AutoAssignTubesView.as_view(),
        name="fiber_overview_auto_assign",
    ),
]

for prefix, model_name in MODEL_PREFIXES:
    urlpatterns += [
        path(f"{prefix}/", include(get_model_urls("netbox_fms", model_name, detail=False))),
        path(f"{prefix}/<int:pk>/", include(get_model_urls("netbox_fms", model_name))),
    ]
