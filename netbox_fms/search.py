from netbox.search import SearchIndex, register_search

from .models import FiberCable, FiberCableType, FiberPathLoss, SplicePlan, SpliceProject


@register_search
class FiberCableTypeIndex(SearchIndex):
    model = FiberCableType
    fields = (
        ("model", 100),
        ("part_number", 300),
        ("notes", 5000),
    )
    display_attrs = ("manufacturer", "construction", "fiber_type", "strand_count")


@register_search
class FiberCableIndex(SearchIndex):
    model = FiberCable
    fields = (
        ("serial_number", 300),
        ("notes", 5000),
    )
    display_attrs = ("cable", "fiber_cable_type")


@register_search
class SplicePlanIndex(SearchIndex):
    model = SplicePlan
    fields = (
        ("name", 100),
        ("description", 500),
    )
    display_attrs = ("closure", "status")


@register_search
class FiberPathLossIndex(SearchIndex):
    model = FiberPathLoss
    fields = (("notes", 5000),)
    display_attrs = ("cable", "wavelength_nm", "measured_loss_db")


@register_search
class SpliceProjectIndex(SearchIndex):
    model = SpliceProject
    fields = (
        ("name", 100),
        ("description", 500),
    )
    display_attrs = ("description",)
