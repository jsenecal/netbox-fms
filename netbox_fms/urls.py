from django.urls import include, path
from utilities.urls import get_model_urls

from . import views

urlpatterns = [
    # FiberCableType
    path("cable-types/", views.FiberCableTypeListView.as_view(), name="fibercabletype_list"),
    path("cable-types/add/", views.FiberCableTypeEditView.as_view(), name="fibercabletype_add"),
    path("cable-types/import/", views.FiberCableTypeBulkImportView.as_view(), name="fibercabletype_import"),
    path("cable-types/edit/", views.FiberCableTypeBulkEditView.as_view(), name="fibercabletype_bulk_edit"),
    path("cable-types/delete/", views.FiberCableTypeBulkDeleteView.as_view(), name="fibercabletype_bulk_delete"),
    path("cable-types/<int:pk>/", include(get_model_urls("netbox_fms", "fibercabletype"))),
    path("cable-types/<int:pk>/", views.FiberCableTypeView.as_view(), name="fibercabletype"),
    path("cable-types/<int:pk>/edit/", views.FiberCableTypeEditView.as_view(), name="fibercabletype_edit"),
    path("cable-types/<int:pk>/delete/", views.FiberCableTypeDeleteView.as_view(), name="fibercabletype_delete"),
    # BufferTubeTemplate
    path("buffer-tube-templates/", views.BufferTubeTemplateListView.as_view(), name="buffertubetemplate_list"),
    path("buffer-tube-templates/add/", views.BufferTubeTemplateEditView.as_view(), name="buffertubetemplate_add"),
    path(
        "buffer-tube-templates/edit/",
        views.BufferTubeTemplateBulkEditView.as_view(),
        name="buffertubetemplate_bulk_edit",
    ),
    path(
        "buffer-tube-templates/delete/",
        views.BufferTubeTemplateBulkDeleteView.as_view(),
        name="buffertubetemplate_bulk_delete",
    ),
    path("buffer-tube-templates/<int:pk>/", include(get_model_urls("netbox_fms", "buffertubetemplate"))),
    path("buffer-tube-templates/<int:pk>/", views.BufferTubeTemplateView.as_view(), name="buffertubetemplate"),
    path(
        "buffer-tube-templates/<int:pk>/edit/",
        views.BufferTubeTemplateEditView.as_view(),
        name="buffertubetemplate_edit",
    ),
    path(
        "buffer-tube-templates/<int:pk>/delete/",
        views.BufferTubeTemplateDeleteView.as_view(),
        name="buffertubetemplate_delete",
    ),
    # RibbonTemplate
    path("ribbon-templates/", views.RibbonTemplateListView.as_view(), name="ribbontemplate_list"),
    path("ribbon-templates/add/", views.RibbonTemplateEditView.as_view(), name="ribbontemplate_add"),
    path("ribbon-templates/edit/", views.RibbonTemplateBulkEditView.as_view(), name="ribbontemplate_bulk_edit"),
    path("ribbon-templates/delete/", views.RibbonTemplateBulkDeleteView.as_view(), name="ribbontemplate_bulk_delete"),
    path("ribbon-templates/<int:pk>/", include(get_model_urls("netbox_fms", "ribbontemplate"))),
    path("ribbon-templates/<int:pk>/", views.RibbonTemplateView.as_view(), name="ribbontemplate"),
    path("ribbon-templates/<int:pk>/edit/", views.RibbonTemplateEditView.as_view(), name="ribbontemplate_edit"),
    path("ribbon-templates/<int:pk>/delete/", views.RibbonTemplateDeleteView.as_view(), name="ribbontemplate_delete"),
    # CableElementTemplate
    path("cable-element-templates/", views.CableElementTemplateListView.as_view(), name="cableelementtemplate_list"),
    path("cable-element-templates/add/", views.CableElementTemplateEditView.as_view(), name="cableelementtemplate_add"),
    path(
        "cable-element-templates/edit/",
        views.CableElementTemplateBulkEditView.as_view(),
        name="cableelementtemplate_bulk_edit",
    ),
    path(
        "cable-element-templates/delete/",
        views.CableElementTemplateBulkDeleteView.as_view(),
        name="cableelementtemplate_bulk_delete",
    ),
    path("cable-element-templates/<int:pk>/", include(get_model_urls("netbox_fms", "cableelementtemplate"))),
    path("cable-element-templates/<int:pk>/", views.CableElementTemplateView.as_view(), name="cableelementtemplate"),
    path(
        "cable-element-templates/<int:pk>/edit/",
        views.CableElementTemplateEditView.as_view(),
        name="cableelementtemplate_edit",
    ),
    path(
        "cable-element-templates/<int:pk>/delete/",
        views.CableElementTemplateDeleteView.as_view(),
        name="cableelementtemplate_delete",
    ),
    # FiberCable (instance)
    path("fiber-cables/", views.FiberCableListView.as_view(), name="fibercable_list"),
    path("fiber-cables/add/", views.FiberCableEditView.as_view(), name="fibercable_add"),
    path("fiber-cables/import/", views.FiberCableBulkImportView.as_view(), name="fibercable_import"),
    path("fiber-cables/edit/", views.FiberCableBulkEditView.as_view(), name="fibercable_bulk_edit"),
    path("fiber-cables/delete/", views.FiberCableBulkDeleteView.as_view(), name="fibercable_bulk_delete"),
    path("fiber-cables/<int:pk>/", include(get_model_urls("netbox_fms", "fibercable"))),
    path("fiber-cables/<int:pk>/", views.FiberCableView.as_view(), name="fibercable"),
    path("fiber-cables/<int:pk>/edit/", views.FiberCableEditView.as_view(), name="fibercable_edit"),
    path("fiber-cables/<int:pk>/delete/", views.FiberCableDeleteView.as_view(), name="fibercable_delete"),
    # SplicePlan
    path("splice-plans/", views.SplicePlanListView.as_view(), name="spliceplan_list"),
    path(
        "splice-plans/quick-add-form/",
        views.SplicePlanQuickAddFormView.as_view(),
        name="spliceplan_quick_add_form",
    ),
    path("splice-plans/add/", views.SplicePlanEditView.as_view(), name="spliceplan_add"),
    path("splice-plans/import/", views.SplicePlanBulkImportView.as_view(), name="spliceplan_import"),
    path("splice-plans/edit/", views.SplicePlanBulkEditView.as_view(), name="spliceplan_bulk_edit"),
    path("splice-plans/delete/", views.SplicePlanBulkDeleteView.as_view(), name="spliceplan_bulk_delete"),
    path("splice-plans/<int:pk>/", include(get_model_urls("netbox_fms", "spliceplan"))),
    path("splice-plans/<int:pk>/", views.SplicePlanView.as_view(), name="spliceplan"),
    path("splice-plans/<int:pk>/edit/", views.SplicePlanEditView.as_view(), name="spliceplan_edit"),
    path("splice-plans/<int:pk>/delete/", views.SplicePlanDeleteView.as_view(), name="spliceplan_delete"),
    path("splice-plans/<int:pk>/editor/", views.SpliceEditorView.as_view(), name="spliceplan_editor"),
    # SplicePlanEntry
    path("splice-plan-entries/", views.SplicePlanEntryListView.as_view(), name="spliceplanentry_list"),
    path("splice-plan-entries/add/", views.SplicePlanEntryEditView.as_view(), name="spliceplanentry_add"),
    path(
        "splice-plan-entries/delete/",
        views.SplicePlanEntryBulkDeleteView.as_view(),
        name="spliceplanentry_bulk_delete",
    ),
    path("splice-plan-entries/<int:pk>/", include(get_model_urls("netbox_fms", "spliceplanentry"))),
    path("splice-plan-entries/<int:pk>/", views.SplicePlanEntryView.as_view(), name="spliceplanentry"),
    path("splice-plan-entries/<int:pk>/edit/", views.SplicePlanEntryEditView.as_view(), name="spliceplanentry_edit"),
    path(
        "splice-plan-entries/<int:pk>/delete/",
        views.SplicePlanEntryDeleteView.as_view(),
        name="spliceplanentry_delete",
    ),
    # SpliceProject
    path("splice-projects/", views.SpliceProjectListView.as_view(), name="spliceproject_list"),
    path("splice-projects/add/", views.SpliceProjectEditView.as_view(), name="spliceproject_add"),
    path(
        "splice-projects/delete/",
        views.SpliceProjectBulkDeleteView.as_view(),
        name="spliceproject_bulk_delete",
    ),
    path("splice-projects/<int:pk>/", include(get_model_urls("netbox_fms", "spliceproject"))),
    path("splice-projects/<int:pk>/", views.SpliceProjectView.as_view(), name="spliceproject"),
    path("splice-projects/<int:pk>/edit/", views.SpliceProjectEditView.as_view(), name="spliceproject_edit"),
    path("splice-projects/<int:pk>/delete/", views.SpliceProjectDeleteView.as_view(), name="spliceproject_delete"),
    # ClosureCableEntry
    path("closure-cable-entries/", views.ClosureCableEntryListView.as_view(), name="closurecableentry_list"),
    path("closure-cable-entries/add/", views.ClosureCableEntryEditView.as_view(), name="closurecableentry_add"),
    path(
        "closure-cable-entries/delete/",
        views.ClosureCableEntryBulkDeleteView.as_view(),
        name="closurecableentry_bulk_delete",
    ),
    path("closure-cable-entries/<int:pk>/", include(get_model_urls("netbox_fms", "closurecableentry"))),
    path("closure-cable-entries/<int:pk>/", views.ClosureCableEntryView.as_view(), name="closurecableentry"),
    path(
        "closure-cable-entries/<int:pk>/edit/",
        views.ClosureCableEntryEditView.as_view(),
        name="closurecableentry_edit",
    ),
    path(
        "closure-cable-entries/<int:pk>/delete/",
        views.ClosureCableEntryDeleteView.as_view(),
        name="closurecableentry_delete",
    ),
    # Import/Apply/Export for SplicePlan
    path(
        "splice-plans/<int:pk>/import/",
        views.SplicePlanImportFromDeviceView.as_view(),
        name="spliceplan_import_device",
    ),
    path("splice-plans/<int:pk>/apply/", views.SplicePlanApplyView.as_view(), name="spliceplan_apply"),
    path("splice-plans/<int:pk>/export/", views.SplicePlanExportDrawioView.as_view(), name="spliceplan_export"),
    # SlackLoop
    path("slack-loops/", views.SlackLoopListView.as_view(), name="slackloop_list"),
    path("slack-loops/add/", views.SlackLoopEditView.as_view(), name="slackloop_add"),
    path("slack-loops/import/", views.SlackLoopBulkImportView.as_view(), name="slackloop_import"),
    path("slack-loops/edit/", views.SlackLoopBulkEditView.as_view(), name="slackloop_bulk_edit"),
    path("slack-loops/delete/", views.SlackLoopBulkDeleteView.as_view(), name="slackloop_bulk_delete"),
    path("slack-loops/<int:pk>/", include(get_model_urls("netbox_fms", "slackloop"))),
    path("slack-loops/<int:pk>/", views.SlackLoopView.as_view(), name="slackloop"),
    path("slack-loops/<int:pk>/edit/", views.SlackLoopEditView.as_view(), name="slackloop_edit"),
    path("slack-loops/<int:pk>/delete/", views.SlackLoopDeleteView.as_view(), name="slackloop_delete"),
    path("slack-loops/<int:pk>/insert/", views.SlackLoopInsertView.as_view(), name="slackloop_insert"),
    # FiberCircuit
    path("fiber-circuits/", views.FiberCircuitListView.as_view(), name="fibercircuit_list"),
    path("fiber-circuits/add/", views.FiberCircuitEditView.as_view(), name="fibercircuit_add"),
    path("fiber-circuits/import/", views.FiberCircuitBulkImportView.as_view(), name="fibercircuit_import"),
    path("fiber-circuits/edit/", views.FiberCircuitBulkEditView.as_view(), name="fibercircuit_bulk_edit"),
    path("fiber-circuits/delete/", views.FiberCircuitBulkDeleteView.as_view(), name="fibercircuit_bulk_delete"),
    path("fiber-circuits/<int:pk>/", include(get_model_urls("netbox_fms", "fibercircuit"))),
    path("fiber-circuits/<int:pk>/", views.FiberCircuitView.as_view(), name="fibercircuit"),
    path("fiber-circuits/<int:pk>/edit/", views.FiberCircuitEditView.as_view(), name="fibercircuit_edit"),
    path("fiber-circuits/<int:pk>/delete/", views.FiberCircuitDeleteView.as_view(), name="fibercircuit_delete"),
    # FiberCircuitPath
    path("fiber-circuit-paths/", views.FiberCircuitPathListView.as_view(), name="fibercircuitpath_list"),
    path("fiber-circuit-paths/add/", views.FiberCircuitPathEditView.as_view(), name="fibercircuitpath_add"),
    path("fiber-circuit-paths/<int:pk>/", include(get_model_urls("netbox_fms", "fibercircuitpath"))),
    path("fiber-circuit-paths/<int:pk>/", views.FiberCircuitPathView.as_view(), name="fibercircuitpath"),
    path("fiber-circuit-paths/<int:pk>/edit/", views.FiberCircuitPathEditView.as_view(), name="fibercircuitpath_edit"),
    path(
        "fiber-circuit-paths/<int:pk>/delete/",
        views.FiberCircuitPathDeleteView.as_view(),
        name="fibercircuitpath_delete",
    ),
    # Provision Ports
    path("provision-ports/", views.ProvisionPortsView.as_view(), name="provision_ports"),
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
    # Trace detail HTMX
    path(
        "fiber-circuit-paths/<int:pk>/trace-detail/<str:node_type>/<int:object_id>/",
        views.TraceDetailView.as_view(),
        name="fibercircuitpath_trace_detail",
    ),
    # WDM Device Type Profile
    path("wdm-profiles/", views.WdmDeviceTypeProfileListView.as_view(), name="wdmdevicetypeprofile_list"),
    path("wdm-profiles/add/", views.WdmDeviceTypeProfileEditView.as_view(), name="wdmdevicetypeprofile_add"),
    path(
        "wdm-profiles/import/",
        views.WdmDeviceTypeProfileBulkImportView.as_view(),
        name="wdmdevicetypeprofile_import",
    ),
    path(
        "wdm-profiles/delete/",
        views.WdmDeviceTypeProfileBulkDeleteView.as_view(),
        name="wdmdevicetypeprofile_bulk_delete",
    ),
    path("wdm-profiles/<int:pk>/", include(get_model_urls("netbox_fms", "wdmdevicetypeprofile"))),
    path("wdm-profiles/<int:pk>/", views.WdmDeviceTypeProfileView.as_view(), name="wdmdevicetypeprofile"),
    path("wdm-profiles/<int:pk>/edit/", views.WdmDeviceTypeProfileEditView.as_view(), name="wdmdevicetypeprofile_edit"),
    path(
        "wdm-profiles/<int:pk>/delete/",
        views.WdmDeviceTypeProfileDeleteView.as_view(),
        name="wdmdevicetypeprofile_delete",
    ),
    # WDM Channel Template
    path("wdm-channel-templates/<int:pk>/", include(get_model_urls("netbox_fms", "wdmchanneltemplate"))),
    path("wdm-channel-templates/<int:pk>/", views.WdmChannelTemplateView.as_view(), name="wdmchanneltemplate"),
    path(
        "wdm-channel-templates/<int:pk>/edit/",
        views.WdmChannelTemplateEditView.as_view(),
        name="wdmchanneltemplate_edit",
    ),
    path(
        "wdm-channel-templates/<int:pk>/delete/",
        views.WdmChannelTemplateDeleteView.as_view(),
        name="wdmchanneltemplate_delete",
    ),
    # WDM Node
    path("wdm-nodes/", views.WdmNodeListView.as_view(), name="wdmnode_list"),
    path("wdm-nodes/add/", views.WdmNodeEditView.as_view(), name="wdmnode_add"),
    path("wdm-nodes/import/", views.WdmNodeBulkImportView.as_view(), name="wdmnode_import"),
    path("wdm-nodes/delete/", views.WdmNodeBulkDeleteView.as_view(), name="wdmnode_bulk_delete"),
    path("wdm-nodes/<int:pk>/", include(get_model_urls("netbox_fms", "wdmnode"))),
    path("wdm-nodes/<int:pk>/", views.WdmNodeView.as_view(), name="wdmnode"),
    path("wdm-nodes/<int:pk>/edit/", views.WdmNodeEditView.as_view(), name="wdmnode_edit"),
    path("wdm-nodes/<int:pk>/delete/", views.WdmNodeDeleteView.as_view(), name="wdmnode_delete"),
    # WDM Trunk Port
    path("wdm-trunk-ports/<int:pk>/", include(get_model_urls("netbox_fms", "wdmtrunkport"))),
    path("wdm-trunk-ports/<int:pk>/", views.WdmTrunkPortView.as_view(), name="wdmtrunkport"),
    path("wdm-trunk-ports/<int:pk>/edit/", views.WdmTrunkPortEditView.as_view(), name="wdmtrunkport_edit"),
    path("wdm-trunk-ports/<int:pk>/delete/", views.WdmTrunkPortDeleteView.as_view(), name="wdmtrunkport_delete"),
    # Wavelength Channel
    path("wavelength-channels/", views.WavelengthChannelListView.as_view(), name="wavelengthchannel_list"),
    path("wavelength-channels/add/", views.WavelengthChannelEditView.as_view(), name="wavelengthchannel_add"),
    path(
        "wavelength-channels/edit/",
        views.WavelengthChannelBulkEditView.as_view(),
        name="wavelengthchannel_bulk_edit",
    ),
    path(
        "wavelength-channels/delete/",
        views.WavelengthChannelBulkDeleteView.as_view(),
        name="wavelengthchannel_bulk_delete",
    ),
    path("wavelength-channels/<int:pk>/", include(get_model_urls("netbox_fms", "wavelengthchannel"))),
    path("wavelength-channels/<int:pk>/", views.WavelengthChannelView.as_view(), name="wavelengthchannel"),
    path(
        "wavelength-channels/<int:pk>/edit/",
        views.WavelengthChannelEditView.as_view(),
        name="wavelengthchannel_edit",
    ),
    path(
        "wavelength-channels/<int:pk>/delete/",
        views.WavelengthChannelDeleteView.as_view(),
        name="wavelengthchannel_delete",
    ),
    # Wavelength Service
    path("wavelength-services/", views.WavelengthServiceListView.as_view(), name="wavelengthservice_list"),
    path("wavelength-services/add/", views.WavelengthServiceEditView.as_view(), name="wavelengthservice_add"),
    path(
        "wavelength-services/import/",
        views.WavelengthServiceBulkImportView.as_view(),
        name="wavelengthservice_import",
    ),
    path(
        "wavelength-services/delete/",
        views.WavelengthServiceBulkDeleteView.as_view(),
        name="wavelengthservice_bulk_delete",
    ),
    path("wavelength-services/<int:pk>/", include(get_model_urls("netbox_fms", "wavelengthservice"))),
    path("wavelength-services/<int:pk>/", views.WavelengthServiceView.as_view(), name="wavelengthservice"),
    path(
        "wavelength-services/<int:pk>/edit/",
        views.WavelengthServiceEditView.as_view(),
        name="wavelengthservice_edit",
    ),
    path(
        "wavelength-services/<int:pk>/delete/",
        views.WavelengthServiceDeleteView.as_view(),
        name="wavelengthservice_delete",
    ),
]
