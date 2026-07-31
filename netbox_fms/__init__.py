import logging

from netbox.plugins import PluginConfig

__version__ = "0.2.0"

logger = logging.getLogger(__name__)


class NetBoxFMSConfig(PluginConfig):
    name = "netbox_fms"
    verbose_name = "Fiber Management System"
    description = "Fiber cable management, splice planning, and loss budgeting for NetBox"
    version = __version__
    author = "Jonathan Senecal"
    author_email = "contact@jonathansenecal.com"
    base_url = "fms"
    min_version = "4.5.0"
    default_settings = {}

    def ready(self):
        super().ready()
        from netbox_fms.monkey_patches import patch_cable_profiles

        patch_cable_profiles()
        from .signals import connect_signals

        connect_signals()
        from utilities.counters import connect_counters

        from .models import FiberCableType

        connect_counters(FiberCableType)

        self._check_naming_templates()
        self._register_map_layers()
        logger.info("%s plugin loaded", self.name)

    @staticmethod
    def _check_naming_templates():
        """Report malformed naming templates set in PLUGINS_CONFIG, at startup.

        Cable-type template fields go through ``FiberCableType.clean()``;
        plugin-wide ones never see a form or serializer, so without this they
        would first surface as a render failure on some unrelated cable save.

        Logs and returns -- it must never raise. A bad plugin setting has to be
        reported, not turned into a failure to boot NetBox; the per-render
        ``NamingError`` guards leave the affected names unchanged meanwhile.
        """
        from . import naming

        for setting_key, message in naming.validate_plugin_config():
            logger.error(
                "Invalid netbox_fms naming template in PLUGINS_CONFIG setting '%s': %s "
                "Generated names for this target will be left unchanged until it is fixed.",
                setting_key,
                message,
            )

    @staticmethod
    def _register_map_layers():
        """Register FMS map layers with netbox-pathways if installed."""
        try:
            from netbox_pathways.registry import LayerDetail, LayerStyle, register_map_layer
        except ImportError:
            return

        from dcim.models import Device

        from .models import SlackLoop

        register_map_layer(
            name="fms_splice_closures",
            label="Splice Closures",
            geometry_type="Point",
            source="reference",
            queryset=lambda r: (
                Device.objects.filter(
                    splice_plans__isnull=False,
                )
                .distinct()
                .restrict(r.user, "view")
            ),
            geometry_field="site",
            feature_fields=["name", "site", "role", "status"],
            popover_fields=["name", "role"],
            style=LayerStyle(color="#4caf50", icon="mdi-lan-connect"),
            detail=LayerDetail(
                url_template="/dcim/devices/{id}/",
                fields=["name", "site", "role", "status"],
                label_field="name",
            ),
            group="Fiber Management",
            sort_order=10,
        )

        register_map_layer(
            name="fms_slack_loops",
            label="Slack Loops",
            geometry_type="Point",
            source="reference",
            queryset=lambda r: SlackLoop.objects.restrict(r.user, "view"),
            geometry_field="site",
            feature_fields=["name", "site", "fiber_cable", "loop_length"],
            popover_fields=["name", "fiber_cable"],
            style=LayerStyle(color="#ff9800", icon="mdi-rotate-right"),
            detail=LayerDetail(
                url_template="/plugins/fms/slack-loops/{id}/",
                fields=["name", "site", "fiber_cable", "loop_length", "storage_method"],
                label_field="name",
            ),
            group="Fiber Management",
            sort_order=30,
        )


config = NetBoxFMSConfig
