from netbox.search import SearchIndex, register_search

from .models import FiberCable, FiberCableType, FiberCircuit, SlackLoop, SplicePlan, SpliceProject


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
class SpliceProjectIndex(SearchIndex):
    model = SpliceProject
    fields = (
        ("name", 100),
        ("description", 500),
    )
    display_attrs = ("description",)


@register_search
class FiberCircuitIndex(SearchIndex):
    model = FiberCircuit
    fields = (
        ("name", 100),
        ("cid", 80),
        ("description", 500),
    )
    display_attrs = ("status", "strand_count", "cid")


@register_search
class SlackLoopIndex(SearchIndex):
    model = SlackLoop
    fields = (("notes", 5000),)
    display_attrs = ("fiber_cable", "site", "start_mark", "end_mark", "length_unit")
