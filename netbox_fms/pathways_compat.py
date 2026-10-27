"""Optional bridge to netbox-pathways.

netbox-pathways is a companion plugin: fms works without it. Code that uses it
checks ``pathways_installed()`` first and imports ``netbox_pathways`` inside the
function, never at module level, so importing any fms module never requires
pathways. Small lookups shared by views live here; the fault route walk and map
layers keep their pathways queries next to the logic that uses them.
"""

from django.apps import apps

__all__ = ("cable_segment", "pathways_installed", "site_map_url")


def pathways_installed():
    return apps.is_installed("netbox_pathways")


def cable_segment(segment_pk):
    """The route segment with its pathway; None when pathways is not installed or the segment is gone."""
    if not pathways_installed():
        return None
    from netbox_pathways.models import CableSegment

    return CableSegment.objects.select_related("pathway").filter(pk=segment_pk).first()


def site_map_url(device):
    """The pathways map zoomed to the device's site; None without pathways or a site."""
    if not pathways_installed() or not device.site_id:
        return None
    return f"/plugins/pathways/map/#site={device.site_id}"
