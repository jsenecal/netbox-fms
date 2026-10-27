"""Tests for the fault layers on the netbox-pathways map (#198, #228)."""

from types import SimpleNamespace
from unittest.mock import patch

from dcim.models import Device
from django.test import TestCase
from django.urls import reverse
from netbox_pathways.geo import to_leaflet
from netbox_pathways.models import Pathway
from netbox_pathways.registry import registry

from netbox_fms.choices import ConstructionChoices, FiberFaultLocatedAtStatusChoices, FiberFaultStatusChoices
from netbox_fms.fault_map import fault_segment_features, parse_bbox
from netbox_fms.models import FiberCable, FiberCableType, FiberFault
from tests.conftest import (
    create_fault_with_location,
    make_cable_between,
    make_infra,
    make_route,
    superuser_client,
    user_with,
)

CONFIRMED = FiberFaultLocatedAtStatusChoices.CONFIRMED
ESTIMATED = FiberFaultLocatedAtStatusChoices.ESTIMATED


class TestFaultMap(TestCase):
    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = make_infra("FaultMap")
        cls.closure = Device.objects.create(name="FaultMap-A", site=site, device_type=dt, role=role)
        cls.quiet = Device.objects.create(name="FaultMap-B", site=site, device_type=dt, role=role)
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="FaultMap-TB-4", construction=ConstructionChoices.TIGHT_BUFFER, strand_count=4
        )
        cls.cables, cls.pathways = [], []
        for index in range(2):
            cable = make_cable_between(f"FM{index}", cls.closure, cls.quiet, 100)
            cls.cables.append(FiberCable.objects.create(cable=cable, fiber_cable_type=fct))
            cls.pathways.append(make_route(cable, [100.0])[0].pathway)

        def fault(cable, located_at_status=FiberFaultLocatedAtStatusChoices.NONE, **fields):
            return create_fault_with_location(fiber_cable=cable, located_at_status=located_at_status, **fields)

        cls.confirmed = fault(cls.cables[0], CONFIRMED, distance_from_a=50)
        cls.resolved = fault(cls.cables[0], CONFIRMED, distance_from_a=50, status=FiberFaultStatusChoices.RESOLVED)
        cls.unlocated = fault(cls.cables[0])
        cls.estimated = fault(cls.cables[1], ESTIMATED, distance_from_a=50)
        cls.other_confirmed = fault(cls.cables[1], CONFIRMED, distance_from_a=20)
        # Past the end of its 100 m cable: it cannot be placed on the route.
        cls.unplaceable = fault(cls.cables[0], CONFIRMED, distance_from_a=150)
        cls.at_closure = fault(cls.cables[0], CONFIRMED, located_at=cls.closure)
        cls.admin = user_with(
            "faultmap-admin", [(FiberFault, ["view"], None), (Pathway, ["view"], None), (Device, ["view"], None)]
        )

    def _ids(self, user=None, status=CONFIRMED, bbox=None):
        collection = fault_segment_features(user or self.admin, located_at_status=status, bbox=bbox)
        return {feature["id"] for feature in collection["features"]}

    def test_features_only_open_located_faults(self):
        collection = fault_segment_features(self.admin, located_at_status=CONFIRMED, bbox=None)
        self.assertEqual(collection["type"], "FeatureCollection")
        self.assertEqual({f["id"] for f in collection["features"]}, {self.confirmed.pk, self.other_confirmed.pk})
        feature = next(f for f in collection["features"] if f["id"] == self.confirmed.pk)
        self.assertEqual(feature["geometry"]["type"], "LineString")
        self.assertEqual(len(feature["geometry"]["coordinates"]), 2)
        self.assertEqual(
            feature["properties"],
            {
                "name": str(self.confirmed),
                "fiber_cable": str(self.cables[0]),
                "located_at_status": CONFIRMED,
                "url": self.confirmed.get_absolute_url(),
            },
        )

    def test_status_split(self):
        self.assertEqual(self._ids(status=ESTIMATED), {self.estimated.pk})
        self.assertNotIn(self.estimated.pk, self._ids())

    def test_constrained_user_sees_only_viewable_faults(self):
        """#198: fault and pathway permissions both gate a feature."""
        fault_scoped = user_with(
            "faultmap-faults",
            [(FiberFault, ["view"], {"fiber_cable": self.cables[0].pk}), (Pathway, ["view"], None)],
        )
        self.assertEqual(self._ids(fault_scoped), {self.confirmed.pk})
        pathway_scoped = user_with(
            "faultmap-pathways",
            [(FiberFault, ["view"], None), (Pathway, ["view"], {"pk": self.pathways[1].pk})],
        )
        self.assertEqual(self._ids(pathway_scoped), {self.other_confirmed.pk})

    def test_bbox_excludes_far_segment(self):
        west, south, east, north = to_leaflet(self.pathways[0].path).extent
        self.assertEqual(self._ids(bbox=(west, south, east, north)), {self.confirmed.pk, self.other_confirmed.pk})
        self.assertEqual(self._ids(bbox=(west + 10, south, east + 10, north)), set())

    def test_unplaceable_fault_is_skipped(self):
        self.assertNotIn(self.unplaceable.pk, self._ids())

    def test_no_features_without_pathways(self):
        with patch("netbox_fms.pathways_compat.pathways_installed", return_value=False):
            self.assertEqual(self._ids(), set())

    def test_parse_bbox(self):
        self.assertEqual(parse_bbox("-1,2.5,3,4"), (-1.0, 2.5, 3.0, 4.0))
        for junk in (None, "", "1,2,3", "a,b,c,d", "nan,0,1,1", "0,0,inf,1"):
            self.assertIsNone(parse_bbox(junk))

    def test_layers_registered(self):
        expected = {
            "fms_fault_segments_confirmed": "LineString",
            "fms_fault_segments_estimated": "LineString",
            "fms_fault_closures": "Point",
        }
        for name, geometry_type in expected.items():
            layer = registry.get(name)
            self.assertEqual(
                (layer.geometry_type, layer.group, layer.default_visible), (geometry_type, "Fiber Faults", False)
            )
        self.assertTrue(registry.get("fms_fault_segments_confirmed").url.endswith("?located_at_status=confirmed"))
        estimated = registry.get("fms_fault_segments_estimated")
        self.assertTrue(estimated.url.endswith("?located_at_status=estimated"))
        self.assertEqual(estimated.style.dash, "6 6")
        for status in ("confirmed", "estimated"):
            self.assertIn("located_at_status", registry.get(f"fms_fault_segments_{status}").popover_fields)

    def test_closure_layer_lists_devices_of_open_faults(self):
        closures = registry.get("fms_fault_closures").queryset(SimpleNamespace(user=self.admin))
        self.assertEqual(list(closures), [self.closure])

    def test_deleting_the_closure_deletes_its_faults(self):
        """#228: a fault at a closure goes with the closure."""
        pk = self.at_closure.pk
        self.closure.delete()
        self.assertFalse(FiberFault.objects.filter(pk=pk).exists())

    def test_view_returns_feature_collection(self):
        client = superuser_client("faultmap-view")
        url = reverse("plugins:netbox_fms:fiberfault_map_segments")
        bbox = ",".join(str(v) for v in to_leaflet(self.pathways[1].path).extent)
        body = client.get(url, {"located_at_status": ESTIMATED, "bbox": bbox}).json()
        self.assertEqual(body["type"], "FeatureCollection")
        self.assertEqual([f["id"] for f in body["features"]], [self.estimated.pk])
