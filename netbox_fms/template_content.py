from netbox.plugins import PluginTemplateExtension

from .models import FiberCable, WdmNode


class CableFiberCablePanel(PluginTemplateExtension):
    """Template extension that adds a FiberCable panel to the Cable detail view."""

    models = ["dcim.cable"]

    def left_page(self):
        cable = self.context["object"]
        fiber_cable = FiberCable.objects.filter(cable=cable).select_related("fiber_cable_type").first()
        if fiber_cable:
            tube_count = fiber_cable.buffer_tubes.count()
            return self.render(
                "netbox_fms/inc/cable_fibercable_panel.html",
                extra_context={
                    "fiber_cable": fiber_cable,
                    "tube_count": tube_count,
                },
            )
        # Show "Link Fiber Cable" action button
        return self.render(
            "netbox_fms/inc/cable_link_action.html",
            extra_context={"cable": cable},
        )


class DeviceWdmNodePanel(PluginTemplateExtension):
    """Template extension that adds a WDM node panel to the Device detail view."""

    models = ["dcim.device"]

    def right_page(self):
        device = self.context["object"]
        wdm_node = WdmNode.objects.filter(device=device).first()
        if wdm_node:
            return self.render(
                "netbox_fms/inc/device_wdm_panel.html",
                extra_context={"wdm_node": wdm_node},
            )
        return ""


template_extensions = [CableFiberCablePanel, DeviceWdmNodePanel]
