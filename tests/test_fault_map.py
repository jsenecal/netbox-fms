"""Tests for the fault layers on the netbox-pathways map (#198)."""

from types import SimpleNamespace
from unittest.mock import patch

from dcim.models import Cable, Device
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from netbox_pathways.geo import to_leaflet
from netbox_pathways.models import Pathway
from netbox_pathways.registry import registry

from netbox_fms.choices import ConstructionChoices, FiberFaultLocatedAtStatusChoices, FiberFaultStatusChoices
from netbox_fms.fault_map import fault_segment_features, parse_bbox
from netbox_fms.models import FiberCable, FiberCableType, FiberFault
from tests.conftest import make_front_port, make_infra, make_route, superuser_client, user_with

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
            cable = Cable.objects.create(
                a_terminations=[make_front_port(cls.closure, f"A{index}")],
                b_terminations=[make_front_port(cls.quiet, f"B{index}")],
            )
            cls.cables.append(FiberCable.objects.create(cable=cable, fiber_cable_type=fct))
            cls.pathways.append(make_route(cable, [100.0])[0].pathway)
        pathway_ct = ContentType.objects.get_by_natural_key("netbox_pathways", "pathway")
        device_ct = ContentType.objects.get_for_model(Device)

        def fault(cable, located_at_status=FiberFaultLocatedAtStatusChoices.NONE, located_at=None, **fields):
            ct = None if located_at is None else (device_ct if isinstance(located_at, Device) else pathway_ct)
            return FiberFault.objects.create(
                fiber_cable=cable,
                located_at_status=located_at_status,
                located_at_type=ct,
                located_at_id=getattr(located_at, "pk", None),
                **fields,
            )

        cls.confirmed = fault(cls.cables[0], CONFIRMED, cls.pathways[0])
        cls.resolved = fault(cls.cables[0], CONFIRMED, cls.pathways[0], status=FiberFaultStatusChoices.RESOLVED)
        cls.unlocated = fault(cls.cables[0])
        cls.estimated = fault(cls.cables[1], ESTIMATED, cls.pathways[1])
        cls.other_confirmed = fault(cls.cables[1], CONFIRMED, cls.pathways[1])
        # Linked to a pathway the cable does not cross: the location went stale.
        cls.stale = fault(cls.cables[0], CONFIRMED, cls.pathways[1])
        cls.at_closure = fault(cls.cables[0], CONFIRMED, cls.closure)
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

    def test_stale_fault_is_skipped(self):
        self.assertNotIn(self.stale.pk, self._ids())

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

    def test_view_returns_feature_collection(self):
        client = superuser_client("faultmap-view")
        url = reverse("plugins:netbox_fms:fiberfault_map_segments")
        bbox = ",".join(str(v) for v in to_leaflet(self.pathways[1].path).extent)
        body = client.get(url, {"located_at_status": ESTIMATED, "bbox": bbox}).json()
        self.assertEqual(body["type"], "FeatureCollection")
        self.assertEqual([f["id"] for f in body["features"]], [self.estimated.pk])
