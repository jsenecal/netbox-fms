"""GeoJSON of located faults for the netbox-pathways map.

The map fetches the segment layers by bounding box. A fault is drawn along the
pathway it is located at, as long as its cable still runs through that pathway;
a stale location is left off the map rather than drawn somewhere wrong.
"""

from django.db.models import Exists, OuterRef, Subquery

from . import pathways_compat
from .models import FiberFault

__all__ = ("fault_segment_features", "parse_bbox")


def parse_bbox(value):
    """Parse a ``W,S,E,N`` query value into four floats; None when missing or malformed."""
    try:
        west, south, east, north = (float(part) for part in value.split(","))
    except (AttributeError, ValueError):
        return None
    return west, south, east, north


def fault_segment_features(user, *, located_at_status, bbox):
    """FeatureCollection (EPSG:4326) of the open faults the user may view that sit on a visible pathway.

    ``bbox`` is ``(W, S, E, N)`` in EPSG:4326, or None for no spatial filter.
    """
    features = []
    if pathways_compat.pathways_installed():
        features = [_feature(fault) for fault in _located_on_pathways(user, located_at_status, bbox)]
    return {"type": "FeatureCollection", "features": features}


def _located_on_pathways(user, located_at_status, bbox):
    """Faults annotated with ``located_path``; the pathway must be viewable and still on the cable's route."""
    from django.contrib.gis.geos import Polygon
    from netbox_pathways.geo import LEAFLET_SRID, get_srid
    from netbox_pathways.models import CableSegment, Pathway

    pathways = Pathway.objects.restrict(user, "view").filter(path__isnull=False)
    if bbox is not None:
        area = Polygon.from_bbox(bbox)
        area.srid = LEAFLET_SRID
        area.transform(get_srid())
        pathways = pathways.filter(path__bboverlaps=area)
    return (
        FiberFault.objects.open()
        .restrict(user, "view")
        .filter(
            located_at_status=located_at_status,
            located_at_type__app_label="netbox_pathways",
            located_at_type__model="pathway",
        )
        .annotate(located_path=Subquery(pathways.filter(pk=OuterRef("located_at_id")).values("path")))
        .filter(
            Exists(
                CableSegment.objects.filter(
                    cable_id=OuterRef("fiber_cable__cable_id"), pathway_id=OuterRef("located_at_id")
                )
            ),
            located_path__isnull=False,
        )
        .select_related("fiber_cable__cable")
    )


def _feature(fault):
    from netbox_pathways.geo import linestring_to_coords

    return {
        "type": "Feature",
        "id": fault.pk,
        "geometry": {"type": "LineString", "coordinates": linestring_to_coords(fault.located_path)},
        "properties": {
            "name": str(fault),
            "fiber_cable": str(fault.fiber_cable),
            "located_at_status": fault.located_at_status,
            "url": fault.get_absolute_url(),
        },
    }
