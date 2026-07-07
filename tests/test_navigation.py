"""Tests for the FMS plugin menu declaration."""

from django.urls import NoReverseMatch, reverse

from netbox_fms.navigation import menu


def _iter_menu_items():
    for group in menu.groups:
        yield from group.items


def test_list_menu_items_declare_add_button_when_add_url_exists():
    """Every list menu item whose model has an <model>_add URL must expose it as a button.

    Regression test for issue #63: Fiber Circuit Paths and Splice Plan Entries
    were missing the add (+) button even though their add views exist.
    """
    missing = []
    for item in _iter_menu_items():
        link = str(item.link)
        if not link.endswith("_list"):
            continue
        add_link = link.removesuffix("_list") + "_add"
        try:
            reverse(add_link)
        except NoReverseMatch:
            continue
        button_links = {str(button.link) for button in item.buttons}
        if add_link not in button_links:
            missing.append(link)
    assert not missing, f"Menu items missing an add button: {missing}"
