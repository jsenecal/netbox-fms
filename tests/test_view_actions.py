"""Tests for the plugin's URL table and the action buttons its list and child views declare."""

from collections import Counter

from django.urls import URLResolver
from netbox.views.generic import ObjectChildrenView, ObjectListView

from netbox_fms.urls import urlpatterns

# NetBox renders these buttons even when the action's URL does not resolve, so
# a missing route becomes a ".../None" link. Export ignores its URL and rename
# hides itself without one.
_LINKED_ACTIONS = {"add", "bulk_import", "bulk_edit", "bulk_delete"}


def _iter_patterns(patterns, prefix=""):
    """Every leaf URL pattern with its full route, in match order."""
    for pattern in patterns:
        route = prefix + str(pattern.pattern)
        if isinstance(pattern, URLResolver):
            yield from _iter_patterns(pattern.url_patterns, route)
        else:
            yield route, pattern


def test_no_route_is_declared_twice():
    """A second pattern on the same route is dead: the first one always matches.

    Regression test for issue #213: detail views registered with
    register_model_view were also hand-declared on the same path.
    """
    counts = Counter(route for route, _ in _iter_patterns(urlpatterns))
    assert sorted(route for route, count in counts.items() if count > 1) == []


def test_table_view_actions_resolve_to_a_route():
    """Every add/import/bulk button a routed table view shows must point at a real URL.

    Regression test for issue #191: the Fiber Circuit Paths list offered Add,
    Import and bulk buttons for routes #196 removed, and every Import button
    linked to <model>_import while NetBox resolves <model>_bulk_import.
    """
    broken = set()
    views = {getattr(pattern.callback, "view_class", None) for _, pattern in _iter_patterns(urlpatterns)}
    for view in views - {None}:
        # A child tab's single-object actions are the parent's own buttons;
        # only its multi-select actions act on the child table.
        if issubclass(view, ObjectChildrenView):
            model, actions = view.child_model, [action for action in view.actions if action.multi]
        elif issubclass(view, ObjectListView):
            model, actions = view.queryset.model, view.actions
        else:
            continue
        for action in actions:
            if action.name in _LINKED_ACTIONS and action.get_url(model) is None:
                broken.add(f"{view.__name__}: {action.name}")
    assert not broken, f"Buttons linking to missing routes: {sorted(broken)}"
