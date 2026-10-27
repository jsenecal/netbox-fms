from unittest.mock import patch

from dcim.models import Device
from django.test import TestCase

from netbox_fms.pathways_compat import cable_segment
from tests.conftest import make_cable_between, make_infra, make_route


class TestPathwaysCompat(TestCase):
    @classmethod
    def setUpTestData(cls):
        site, _mfr, dt, role = make_infra("PwCompat")
        device = Device.objects.create(name="PwCompat-1", site=site, device_type=dt, role=role)
        cls.cable = make_cable_between("PwC", device, device)

    def test_cable_segment_with_pathway(self):
        segment = make_route(self.cable, [100.0])[0]

        self.assertEqual(cable_segment(segment.pk).pathway.pk, segment.pathway_id)

    def test_absent_pathways_returns_none(self):
        segment = make_route(self.cable, [100.0])[0]
        with patch("netbox_fms.pathways_compat.pathways_installed", return_value=False):
            self.assertIsNone(cable_segment(segment.pk))
