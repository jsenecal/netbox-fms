from netbox.plugins import PluginTemplateExtension

from .services import fiber_cable_for, is_intra_closure_jumper


class CableFiberCablePanel(PluginTemplateExtension):
    """Template extension that adds a FiberCable panel to the Cable detail view."""

    models = ["dcim.cable"]

    def left_page(self):
        cable = self.context["object"]
        fiber_cable = fiber_cable_for(cable)
        if fiber_cable:
            tube_count = fiber_cable.buffer_tubes.count()
            return self.render(
                "netbox_fms/inc/cable_fibercable_panel.html",
                extra_context={
                    "fiber_cable": fiber_cable,
                    "tube_count": tube_count,
                },
            )
        # A splice jumper is not fiber topology; linking would be refused by
        # FiberCable.clean(), so do not offer the action at all.
        if is_intra_closure_jumper(cable):
            return ""
        # Show "Link Fiber Cable" action button
        return self.render(
            "netbox_fms/inc/cable_link_action.html",
            extra_context={"cable": cable},
        )


class ModuleTypeTrayProfilePanel(PluginTemplateExtension):
    """Template extension that surfaces the FMS tray profile on the ModuleType detail view."""

    models = ["dcim.moduletype"]

    def left_page(self):
        module_type = self.context["object"]
        tray_profile = getattr(module_type, "tray_profile", None)
        if tray_profile:
            return self.render(
                "netbox_fms/inc/moduletype_trayprofile_panel.html",
                extra_context={"tray_profile": tray_profile},
            )
        return self.render(
            "netbox_fms/inc/moduletype_trayprofile_action.html",
            extra_context={"module_type": module_type},
        )


template_extensions = [CableFiberCablePanel, ModuleTypeTrayProfilePanel]
