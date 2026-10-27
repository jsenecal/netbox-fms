"""GeoJSON of located faults for the netbox-pathways map.

The map fetches the segment layers by bounding box. A fault is drawn along the route segment that holds its
distance from the cable's A end, worked out from the cable's current route each time; a fault whose distance
cannot be placed on the route is left off the map rather than drawn somewhere wrong.
"""

import math

from django.db.models import Exists, OuterRef

from . import pathways_compat
from .fault_location import place_on_route
from .models import FiberFault

__all__ = ("fault_segment_features", "parse_bbox")


def parse_bbox(value):
    """Parse a ``W,S,E,N`` query value into four finite floats; None when missing or malformed."""
    try:
        bbox = tuple(float(part) for part in value.split(","))
    except (AttributeError, ValueError):
        return None
    return bbox if len(bbox) == 4 and all(map(math.isfinite, bbox)) else None


def fault_segment_features(user, *, located_at_status, bbox):
    """FeatureCollection (EPSG:4326) of the open faults the user may view that sit on a visible pathway.

    ``bbox`` is ``(W, S, E, N)`` in EPSG:4326, or None for no spatial filter.
    """
    features = []
    if pathways_compat.pathways_installed():
        features = _segment_features(user, located_at_status, bbox)
    return {"type": "FeatureCollection", "features": features}


def _segment_features(user, located_at_status, bbox):
    """Place each candidate fault on its route; keep those whose pathway the user may view and the bbox shows."""
    from django.contrib.gis.geos import Polygon
    from netbox_pathways.geo import LEAFLET_SRID, get_srid, linestring_to_coords
    from netbox_pathways.models import CableSegment, Pathway

    pathways = Pathway.objects.restrict(user, "view").filter(path__isnull=False)
    if bbox is not None:
        area = Polygon.from_bbox(bbox)
        area.srid = LEAFLET_SRID
        area.transform(get_srid())
        pathways = pathways.filter(path__bboverlaps=area)
    faults = (
        FiberFault.objects.open()
        .restrict(user, "view")
        .filter(located_at_status=located_at_status, distance_from_a__isnull=False)
        .filter(Exists(CableSegment.objects.filter(cable_id=OuterRef("fiber_cable__cable_id"), pathway__in=pathways)))
        .select_related("fiber_cable__cable", "fiber_cable__fiber_cable_type")
    )
    placed = [(fault, place_on_route(fault).pathway_pk) for fault in faults]
    paths = dict(pathways.filter(pk__in={pk for _fault, pk in placed if pk}).values_list("pk", "path"))
    return [_feature(fault, linestring_to_coords(paths[pk])) for fault, pk in placed if pk in paths]


def _feature(fault, coordinates):
    return {
        "type": "Feature",
        "id": fault.pk,
        "geometry": {"type": "LineString", "coordinates": coordinates},
        "properties": {
            "name": str(fault),
            "fiber_cable": str(fault.fiber_cable),
            "located_at_status": fault.located_at_status,
            "url": fault.get_absolute_url(),
        },
    }
