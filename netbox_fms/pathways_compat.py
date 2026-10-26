"""Optional bridge to netbox-pathways.

netbox-pathways is a companion plugin: fms works without it. Everything that
touches its models lives here, with the imports inside the functions so that
importing this module never requires pathways.
"""

from django.apps import apps

__all__ = ("cable_pathway_ids", "pathways_installed", "route_segment_for")


def pathways_installed():
    return apps.is_installed("netbox_pathways")


def route_segment_for(cable_id, pathway_pk):
    """The cable's segment through the pathway, lowest sequence first; None when absent."""
    if not pathways_installed():
        return None
    from netbox_pathways.models import CableSegment

    return CableSegment.objects.filter(cable_id=cable_id, pathway_id=pathway_pk).order_by("sequence").first()


def cable_pathway_ids(cable_id):
    """Ids of the pathways on the cable's route; empty when pathways is not installed."""
    if not pathways_installed():
        return set()
    from netbox_pathways.models import CableSegment

    return set(
        CableSegment.objects.filter(cable_id=cable_id, pathway__isnull=False).values_list("pathway_id", flat=True)
    )
