"""Fault distance estimates from a jacket mark or an OTDR shot, applied on save, and placed on the route (#198, #228)."""

from decimal import Decimal
from unittest.mock import patch

from dcim.models import Cable, Device, Location
from django.test import TestCase
from netbox_pathways.models import CableSegment, DirectBuried, Structure

from netbox_fms.choices import ConstructionChoices, FiberFaultLocatedAtStatusChoices
from netbox_fms.fault_location import place_on_route, route_legs
from netbox_fms.models import FiberCable, FiberCableType, FiberFault, SlackLoop
from tests.conftest import (
    land_strands,
    make_cable_between,
    make_front_port,
    make_infra,
    make_provider_circuit,
    make_route,
    make_strand_path,
)


def _strand_ports(device, label, count=2):
    return [make_front_port(device, f"{label}-{n}") for n in range(1, count + 1)]


class TestFaultLocationEstimate(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site, mfr, dt, role = make_infra("FlEst")
        d0, d1, d2, e0, e1 = (
            Device.objects.create(name=f"FlEst-{n}", site=cls.site, device_type=dt, role=role)
            for n in ("D0", "D1", "D2", "E0", "E1")
        )
        cls.d0, cls.d1, cls.d2, cls.e0 = d0, d1, d2, e0
        marked = FiberCableType.objects.create(
            manufacturer=mfr,
            model="FlEst-Marked",
            construction=ConstructionChoices.TIGHT_BUFFER,
            strand_count=2,
            mark_unit="m",
        )
        plain = FiberCableType.objects.create(
            manufacturer=mfr, model="FlEst-Plain", construction=ConstructionChoices.TIGHT_BUFFER, strand_count=2
        )

        # Jacket-mark rig: cable M, marks 1000..1330 m, 330 m long, route 100/100/100.
        cls.m = FiberCable.objects.create(
            cable=make_cable_between("M", d0, d2, 330), fiber_cable_type=marked, start_mark=1000, end_mark=1330
        )
        cls.m_segments = make_route(cls.m.cable, [100.0, 100.0, 100.0])

        # OTDR rig: X (D0 -> D1, 120 m) spliced at D1 to Y (D1 -> D2, 330 m, route 100/100/100).
        cls.x = FiberCable.objects.create(cable=make_cable_between("X", d0, d1, 120), fiber_cable_type=plain)
        cls.y = FiberCable.objects.create(cable=make_cable_between("Y", d1, d2, 330), fiber_cable_type=plain)
        cls.y_segments = make_route(cls.y.cable, [100.0, 100.0, 100.0])
        cls.xs = land_strands(cls.x, _strand_ports(d0, "XA"))
        land_strands(cls.x, _strand_ports(d1, "XB"), fk="front_port_b")
        cls.ys = land_strands(cls.y, _strand_ports(d1, "YA"))
        land_strands(cls.y, _strand_ports(d2, "YB"), fk="front_port_b")
        odf_a, odf_b = make_front_port(d0, "ODF-1"), make_front_port(d2, "ODF-1")
        make_strand_path(cls.xs[0], cls.ys[0], end_a=odf_a, end_b=odf_b)

        # Plain cable C (40 m), then a provider circuit, then Y's second strand.
        plain_cable = make_cable_between("C", e0, e1, 40)
        make_strand_path(plain_cable, make_provider_circuit("FlEst").circuit, cls.ys[1])

    def _mark_fault(self, mark, **fields):
        return FiberFault.objects.create(fiber_cable=self.m, location_mark=Decimal(mark), **fields)

    def _shot(self, fiber_cable, origin, distance, strand=None):
        return FiberFault.objects.create(
            fiber_cable=fiber_cable, otdr_origin=origin, otdr_distance=Decimal(distance), otdr_strand=strand
        )

    def _assert_lands_on(self, fault, segment, distance=None):
        self.assertEqual(fault.estimate_note, "")
        self.assertEqual(fault.located_at_status, FiberFaultLocatedAtStatusChoices.ESTIMATED)
        if distance is not None:
            self.assertEqual(fault.distance_from_a, Decimal(distance))
        self.assertEqual(place_on_route(fault).segment_pk, segment.pk)

    def _assert_note(self, fault, note):
        self.assertEqual((fault.distance_from_a, fault.estimate_note), (None, note))
        self.assertEqual(fault.located_at_status, FiberFaultLocatedAtStatusChoices.NONE)

    def test_mark_estimate_lands_on_segment(self):
        self._assert_lands_on(self._mark_fault("1150"), self.m_segments[1], "150.00")

    def test_mark_without_start_mark_notes(self):
        FiberCable.objects.filter(pk=self.m.pk).update(start_mark=None)
        self.m.refresh_from_db()
        self._assert_note(self._mark_fault("1150"), "The cable has no start mark.")

    def test_mark_length_falls_back_to_sheath_marks(self):
        Cable.objects.filter(pk=self.m.cable_id).update(length=None, length_unit="")
        self.m.cable.refresh_from_db()
        self._assert_lands_on(self._mark_fault("1150"), self.m_segments[1])

        FiberCable.objects.filter(pk=self.m.pk).update(end_mark=None)
        self.m.refresh_from_db()
        fault = self._mark_fault("1150")
        self.assertEqual(fault.distance_from_a, Decimal("150.00"))
        self.assertEqual(place_on_route(fault).note, "Cable M has no length.")

    def test_otdr_on_cable_without_length_notes(self):
        Cable.objects.filter(pk=self.m.cable_id).update(length=None, length_unit="")
        FiberCable.objects.filter(pk=self.m.pk).update(end_mark=None)
        self.m.refresh_from_db()
        self._assert_note(self._shot(self.m, self.d0, "50"), "Cable M has no length.")

    def test_placed_slack_absorbs_the_distance_it_covers(self):
        """A coil at a route structure holds its length there; a site-only coil is spread instead."""
        location = Location.objects.create(site=self.site, name="FlEst Vault", slug="flest-vault")
        Structure.objects.filter(pk=self.m_segments[0].pathway.end_structure_id).update(location=location)
        SlackLoop.objects.create(fiber_cable=self.m, site=self.site, location=location, start_mark=500, end_mark=530)
        SlackLoop.objects.create(fiber_cable=self.m, site=self.site, start_mark=600, end_mark=630)

        # 115 m sits inside the coil after segment 1 (100..130 m), not on segment 2 as the plain spread says.
        self._assert_lands_on(self._mark_fault("1115"), self.m_segments[0])

    def test_slack_is_placed_on_pathways_drawn_against_the_route(self):
        """#198: a coil at the joint after reverse-drawn pathways lands as it does on a forward-drawn route."""
        fiber_cable = FiberCable.objects.create(
            cable=make_cable_between("V", self.d0, self.d2, 330),
            fiber_cable_type=self.m.fiber_cable_type,
            start_mark=1000,
            end_mark=1330,
        )
        segments = make_route(fiber_cable.cable, [100.0, 100.0, 100.0], reverse={0, 1})
        location = Location.objects.create(site=self.site, name="FlEst Joint", slug="flest-joint")
        Structure.objects.filter(pk=segments[2].pathway.start_structure_id).update(location=location)
        SlackLoop.objects.create(
            fiber_cable=fiber_cable, site=self.site, location=location, start_mark=500, end_mark=530
        )

        # 225 m sits inside the coil after segment 2 (200..230 m); spread over the route it falls on segment 3.
        fault = FiberFault.objects.create(fiber_cable=fiber_cable, location_mark=Decimal("1225"))

        self._assert_lands_on(fault, segments[1])

    def test_route_legs_orient_a_lone_pathway_from_the_a_end(self):
        segment = make_route(make_cable_between("L", self.d0, self.d2, 100), [100.0], reverse={0})[0]
        Structure.objects.filter(pk=segment.pathway.end_structure_id).update(site=self.site)

        (leg,) = route_legs(segment.cable_id)

        self.assertEqual(leg.start_nodes, {("structure", segment.pathway.end_structure_id)})

    def test_route_legs_measure_path_geometry_and_flag_gaps(self):
        cable = make_cable_between("G", self.d0, self.d2, 300)
        segments = make_route(cable, [100.0, 100.0, 100.0], set_length=False)
        far = [Structure.objects.create(name=f"G-far-{n}", geometry=segments[0].pathway.path.centroid) for n in (1, 2)]
        stray = DirectBuried.objects.create(
            start_structure=far[0], end_structure=far[1], path=segments[1].pathway.path, length=50.0
        )
        CableSegment.objects.filter(pk=segments[1].pk).update(pathway=stray)
        CableSegment.objects.filter(pk=segments[2].pk).update(pathway=None)

        legs = route_legs(cable.pk)

        self.assertEqual(
            [(leg.pathway_pk, leg.length_m) for leg in legs],
            [(segments[0].pathway_id, 100.0), (stray.pk, None), (None, None)],
        )
        self.assertEqual(legs[0].start_nodes, {("structure", segments[0].pathway.start_structure_id)})
        self.assertEqual(legs[2].end_nodes, frozenset())

    def test_otdr_from_cable_end_without_strand(self):
        self._assert_lands_on(self._shot(self.y, self.d2, "50"), self.y_segments[2], "280.00")

    def test_otdr_past_the_far_end_notes(self):
        self._assert_note(self._shot(self.y, self.d2, "400"), "The distance runs past the end of the cable.")

    def test_otdr_across_a_splice(self):
        self._assert_lands_on(self._shot(self.y, self.d0, "170", self.xs[0]), self.y_segments[0], "50.00")

    def test_otdr_short_shot_lands_on_other_cable(self):
        self._assert_note(
            self._shot(self.y, self.d0, "80", self.xs[0]), "The shot lands on cable X, not this fault's cable."
        )

    def test_otdr_past_the_fault_cable_names_the_next_cable(self):
        self._assert_note(
            self._shot(self.y, self.d2, "400", self.xs[0]), "The shot lands on cable X, not this fault's cable."
        )

    def test_provider_circuit_hop_notes(self):
        self._assert_note(
            self._shot(self.y, self.e0, "500", self.ys[1]), "Hop 2 of the shot's path has no known length."
        )

    def test_otdr_origin_off_path_notes(self):
        note = "The shot's origin is not on the shot strand's path."
        self._assert_note(self._shot(self.y, self.e0, "50"), note)
        self._assert_note(self._shot(self.y, self.e0, "50", self.xs[0]), note)

    def test_otdr_strand_without_path_notes(self):
        self._assert_note(self._shot(self.y, self.d0, "50", self.xs[1]), "The shot strand has no analyzed path.")

    def test_otdr_path_missing_the_fault_cable_notes(self):
        self._assert_note(
            self._shot(self.x, self.e0, "50", self.ys[1]), "The shot strand's path does not cross this fault's cable."
        )

    def test_mark_beats_otdr(self):
        fault = self._mark_fault("1150", otdr_origin=self.d2, otdr_distance=Decimal("50"))
        self._assert_lands_on(fault, self.m_segments[1])

    def test_confirmed_location_is_not_overwritten(self):
        fault = self._mark_fault("1150")
        fault.confirm_located_at()
        fault.save()
        fault.location_mark = Decimal("1290")
        fault.save()

        self.assertEqual(fault.located_at_status, FiberFaultLocatedAtStatusChoices.CONFIRMED)
        self.assertEqual(fault.distance_from_a, Decimal("150.00"))

    def test_unrelated_edit_does_not_recompute(self):
        fault = self._shot(self.y, self.d2, "50")
        Cable.objects.filter(pk=self.y.cable_id).update(length=300)

        fault.description = "Backhoe"
        fault.save()

        self.assertEqual(fault.distance_from_a, Decimal("280.00"))

    def test_estimate_needs_no_pathways_but_placement_does(self):
        with patch("netbox_fms.pathways_compat.pathways_installed", return_value=False):
            fault = self._mark_fault("1150")
            place = place_on_route(fault)
        self.assertEqual(fault.distance_from_a, Decimal("150.00"))
        self.assertEqual(place.note, "netbox-pathways is not installed.")

    def test_no_distance_has_no_place(self):
        self.assertIsNone(place_on_route(FiberFault(fiber_cable=self.m)))

    def test_removing_evidence_clears_estimate(self):
        fault = self._mark_fault("1150")
        fault.location_mark = None
        fault.save()

        self._assert_note(fault, "")
