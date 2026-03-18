from netbox.plugins import PluginConfig

__version__ = "0.1.0"


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
        # from netbox_fms.monkey_patches import patch_cable_profiles
        # patch_cable_profiles()
        from .signals import connect_signals

        connect_signals()
        from utilities.counters import connect_counters
        from .models import FiberCableType
        connect_counters(FiberCableType)


config = NetBoxFMSConfig
