from unittest.mock import patch

from dcim.models import Cable, Device
from django.test import TestCase
from netbox_pathways.models import CableSegment

from netbox_fms.pathways_compat import cable_pathway_ids, route_segment_for
from tests.conftest import make_front_port, make_infra, make_route


class TestPathwaysCompat(TestCase):
    @classmethod
    def setUpTestData(cls):
        site, _mfr, dt, role = make_infra("PwCompat")
        device = Device.objects.create(name="PwCompat-1", site=site, device_type=dt, role=role)
        cls.cable = Cable.objects.create(
            a_terminations=[make_front_port(device, "A")], b_terminations=[make_front_port(device, "B")]
        )

    def test_route_segment_for_picks_lowest_sequence(self):
        """A route passing one pathway twice resolves to the first pass (#198)."""
        segments = make_route(self.cable, [100.0, 200.0])
        CableSegment.objects.create(cable=self.cable, pathway=segments[0].pathway, sequence=3)

        found = route_segment_for(self.cable.pk, segments[0].pathway_id)

        self.assertEqual(found.sequence, 1)
        self.assertEqual(cable_pathway_ids(self.cable.pk), {s.pathway_id for s in segments})

    def test_route_segment_for_survives_rebuilt_segments(self):
        segments = make_route(self.cable, [100.0, 200.0])
        old_pks = {s.pk for s in segments}
        CableSegment.objects.filter(cable=self.cable).delete()
        for seq, seg in enumerate(segments, start=1):
            CableSegment.objects.create(cable=self.cable, pathway=seg.pathway, sequence=seq)

        found = route_segment_for(self.cable.pk, segments[1].pathway_id)

        self.assertNotIn(found.pk, old_pks)
        self.assertEqual(found.sequence, 2)

    def test_absent_pathways_returns_none(self):
        segments = make_route(self.cable, [100.0])
        with patch("netbox_fms.pathways_compat.pathways_installed", return_value=False):
            self.assertIsNone(route_segment_for(self.cable.pk, segments[0].pathway_id))
            self.assertEqual(cable_pathway_ids(self.cable.pk), set())
