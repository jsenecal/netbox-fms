from netbox.plugins import PluginTemplateExtension

from .models import FiberCable


class CableFiberCablePanel(PluginTemplateExtension):
    models = ["dcim.cable"]

    def left_page(self):
        cable = self.context["object"]
        fiber_cable = FiberCable.objects.filter(cable=cable).select_related("fiber_cable_type").first()
        if not fiber_cable:
            return ""
        tube_count = fiber_cable.buffer_tubes.count()
        return self.render(
            "netbox_fms/inc/cable_fibercable_panel.html",
            extra_context={
                "fiber_cable": fiber_cable,
                "tube_count": tube_count,
            },
        )


template_extensions = [CableFiberCablePanel]
