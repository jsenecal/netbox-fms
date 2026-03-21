from netbox.search import SearchIndex, register_search

from .models import FiberCable, FiberCableType, FiberCircuit, SlackLoop, SplicePlan, SpliceProject


@register_search
class FiberCableTypeIndex(SearchIndex):
    """Search index for FiberCableType."""

    model = FiberCableType
    fields = (
        ("model", 100),
        ("part_number", 300),
        ("notes", 5000),
    )
    display_attrs = ("manufacturer", "construction", "fiber_type", "strand_count")


@register_search
class FiberCableIndex(SearchIndex):
    """Search index for FiberCable."""

    model = FiberCable
    fields = (
        ("serial_number", 300),
        ("notes", 5000),
    )
    display_attrs = ("cable", "fiber_cable_type")


@register_search
class SplicePlanIndex(SearchIndex):
    """Search index for SplicePlan."""

    model = SplicePlan
    fields = (
        ("name", 100),
        ("description", 500),
    )
    display_attrs = ("closure", "status")


@register_search
class SpliceProjectIndex(SearchIndex):
    """Search index for SpliceProject."""

    model = SpliceProject
    fields = (
        ("name", 100),
        ("description", 500),
    )
    display_attrs = ("description",)


@register_search
class FiberCircuitIndex(SearchIndex):
    """Search index for FiberCircuit."""

    model = FiberCircuit
    fields = (
        ("name", 100),
        ("cid", 80),
        ("description", 500),
    )
    display_attrs = ("status", "strand_count", "cid")


@register_search
class SlackLoopIndex(SearchIndex):
    """Search index for SlackLoop."""

    model = SlackLoop
    fields = (("notes", 5000),)
    display_attrs = ("fiber_cable", "site", "start_mark", "end_mark", "length_unit")
