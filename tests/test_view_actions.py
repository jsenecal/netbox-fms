"""Tests for the action buttons the plugin's list and child views declare."""

from django.urls import URLResolver
from netbox.views.generic import ObjectChildrenView, ObjectListView

from netbox_fms.urls import urlpatterns

# NetBox renders these buttons even when the action's URL does not resolve, so
# a missing route becomes a ".../None" link. Export ignores its URL and rename
# hides itself without one.
_LINKED_ACTIONS = {"add", "bulk_import", "bulk_edit", "bulk_delete"}


def _iter_view_classes(patterns):
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from _iter_view_classes(pattern.url_patterns)
        elif view_class := getattr(pattern.callback, "view_class", None):
            yield view_class


def test_table_view_actions_resolve_to_a_route():
    """Every add/import/bulk button a routed table view shows must point at a real URL.

    Regression test for issue #191: the Fiber Circuit Paths list offered Add,
    Import and bulk buttons for routes #196 removed, and every Import button
    linked to <model>_import while NetBox resolves <model>_bulk_import.
    """
    broken = set()
    for view in set(_iter_view_classes(urlpatterns)):
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
