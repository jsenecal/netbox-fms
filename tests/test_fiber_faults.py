"""Tests for FiberFault validation and lifecycle (#198)."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from core.models import ObjectChange
from dcim.models import Cable, Device, Manufacturer, Site
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from netbox_fms.choices import ConstructionChoices, FiberFaultLocatedAtStatusChoices, FiberFaultStatusChoices
from netbox_fms.filters import FiberCableFilterSet, FiberStrandFilterSet
from netbox_fms.forms import FiberFaultForm
from netbox_fms.models import FiberCable, FiberCableType, FiberFault, FiberStrand, validate_fault_strands
from tests.conftest import (
    AuthedAPIClientMixin,
    create_fault_with_location,
    make_front_port,
    make_infra,
    make_route,
    superuser_client,
    ui_client_with,
)


def _make_cable(fct, **fields):
    cable = Cable.objects.create()
    cable.a_terminations = []
    cable.b_terminations = []
    cable.save()
    return FiberCable.objects.create(cable=cable, fiber_cable_type=fct, **fields)


class TestFiberFault(TestCase):
    @classmethod
    def setUpTestData(cls):
        mfr = Manufacturer.objects.create(name="Fault-Mfr", slug="fault-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="Fault-TB-4",
            construction=ConstructionChoices.TIGHT_BUFFER,
            strand_count=4,
            mark_unit="m",
        )
        cls.fc = _make_cable(fct, start_mark=Decimal("100"), end_mark=Decimal("0"))
        cls.other = _make_cable(fct)

    def _fault(self, **fields):
        return FiberFault(fiber_cable=self.fc, **fields)

    def test_location_mark_outside_the_sheath_marks_is_refused(self):
        with self.assertRaises(ValidationError) as ctx:
            self._fault(location_mark=Decimal("150")).full_clean()
        self.assertIn("location_mark", ctx.exception.message_dict)

    def test_location_mark_between_descending_marks_is_accepted(self):
        self._fault(location_mark=Decimal("40")).full_clean()

    def test_location_mark_equal_to_a_sheath_mark_is_accepted(self):
        self._fault(location_mark=Decimal("100")).full_clean()

    def test_unset_cable_and_date_give_field_errors_not_a_crash(self):
        """#198: clean() runs even when the required fields failed validation."""
        fault = FiberFault(location_mark=Decimal("5"), resolved_at=timezone.now(), reported_at=None)
        with self.assertRaises(ValidationError) as ctx:
            fault.full_clean()
        self.assertIn("fiber_cable", ctx.exception.message_dict)

    def test_resolving_stamps_resolved_at_and_reopening_clears_it(self):
        fault = self._fault()
        fault.save()
        fault.status = FiberFaultStatusChoices.RESOLVED
        fault.save()
        self.assertIsNotNone(fault.resolved_at)
        fault.status = FiberFaultStatusChoices.OPEN
        fault.save()
        self.assertIsNone(fault.resolved_at)

    def test_resolved_before_reported_is_refused(self):
        now = timezone.now()
        fault = self._fault(
            status=FiberFaultStatusChoices.RESOLVED,
            reported_at=now,
            resolved_at=now - timedelta(days=1),
        )
        with self.assertRaises(ValidationError) as ctx:
            fault.full_clean()
        self.assertIn("resolved_at", ctx.exception.message_dict)

    def test_strands_of_another_cable_are_refused(self):
        own = list(self.fc.fiber_strands.all()[:2])
        validate_fault_strands(self.fc, own)
        with self.assertRaises(ValidationError) as ctx:
            validate_fault_strands(self.fc, [*own, self.other.fiber_strands.first()])
        self.assertIn("strands", ctx.exception.message_dict)

    def test_str_names_cable_and_report_date(self):
        fault = self._fault(reported_at=timezone.now())
        self.assertIn(f"{fault.reported_at:%Y-%m-%d}", str(fault))


class FaultWorld:
    """Three cables of four strands each, shared by the surface tests below."""

    @classmethod
    def build(cls):
        mfr = Manufacturer.objects.create(name="FaultUI-Mfr", slug="faultui-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="FaultUI-TB-4",
            construction=ConstructionChoices.TIGHT_BUFFER,
            strand_count=4,
            mark_unit="m",
        )
        cls.cable_1, cls.cable_2, cls.cable_3 = (_make_cable(fct) for _ in range(3))


class TestFaultValidationSurfaces(FaultWorld, AuthedAPIClientMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.build()
        cls.user = get_user_model().objects.create_superuser("fault-api", password="x")

    def test_form_refuses_strands_of_another_cable(self):
        """#198: the form cannot name strands that sit on a different cable."""
        foreign = self.cable_2.fiber_strands.first()
        form = FiberFaultForm(
            data={
                "fiber_cable": self.cable_1.pk,
                "strands": [foreign.pk],
                "status": FiberFaultStatusChoices.OPEN,
                "reported_at": "2026-10-01 12:00:00",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("strands", form.errors)

    def test_form_without_a_cable_reports_the_missing_cable(self):
        form = FiberFaultForm(data={"status": FiberFaultStatusChoices.OPEN, "reported_at": "2026-10-01 12:00:00"})
        self.assertFalse(form.is_valid())
        self.assertIn("fiber_cable", form.errors)

    def test_serializer_refuses_strands_of_another_cable(self):
        """#198: the API applies the same cable check as the form."""
        foreign = self.cable_2.fiber_strands.first()
        resp = self.client.post(
            "/api/plugins/fms/fiber-faults/",
            {"fiber_cable": self.cable_1.pk, "strands": [foreign.pk]},
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("strands", resp.json())

    def test_patch_checks_strands_against_the_stored_cable(self):
        fault = FiberFault.objects.create(fiber_cable=self.cable_1)
        foreign = self.cable_2.fiber_strands.first()
        resp = self.client.patch(f"/api/plugins/fms/fiber-faults/{fault.pk}/", {"strands": [foreign.pk]}, format="json")
        self.assertEqual(resp.status_code, 400, resp.content)
        own = self.cable_1.fiber_strands.first()
        resp = self.client.patch(f"/api/plugins/fms/fiber-faults/{fault.pk}/", {"strands": [own.pk]}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_patch_moving_the_fault_rechecks_its_existing_strands(self):
        fault = FiberFault.objects.create(fiber_cable=self.cable_1)
        fault.strands.add(self.cable_1.fiber_strands.first())
        resp = self.client.patch(
            f"/api/plugins/fms/fiber-faults/{fault.pk}/", {"fiber_cable": self.cable_2.pk}, format="json"
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("strands", resp.json())

    def test_whole_cable_fault_can_be_created_without_strands(self):
        resp = self.client.post("/api/plugins/fms/fiber-faults/", {"fiber_cable": self.cable_1.pk}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_patch_without_strands_skips_the_cable_check(self):
        fault = FiberFault.objects.create(fiber_cable=self.cable_1)
        resp = self.client.patch(
            f"/api/plugins/fms/fiber-faults/{fault.pk}/", {"description": "cut by backhoe"}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)


class TestIsFaultedFilters(FaultWorld, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.build()
        cls.whole = FiberFault.objects.create(fiber_cable=cls.cable_1)
        cls.strand_fault = FiberFault.objects.create(fiber_cable=cls.cable_2)
        cls.faulted_strand = cls.cable_2.fiber_strands.get(position=2)
        cls.strand_fault.strands.add(cls.faulted_strand)
        FiberFault.objects.create(fiber_cable=cls.cable_3, status=FiberFaultStatusChoices.RESOLVED)

    def _strands(self, value):
        return set(FiberStrandFilterSet({"is_faulted": value}, FiberStrand.objects.all()).qs)

    def test_strand_filter_covers_whole_cable_and_named_strand_faults(self):
        expected = set(self.cable_1.fiber_strands.all()) | {self.faulted_strand}
        self.assertEqual(self._strands(True), expected)

    def test_strand_filter_false_is_the_complement(self):
        faulted = self._strands(True)
        self.assertEqual(self._strands(False), set(FiberStrand.objects.all()) - faulted)

    def test_cable_filter_counts_any_open_fault(self):
        qs = FiberCableFilterSet({"is_faulted": True}, FiberCable.objects.all()).qs
        self.assertEqual(set(qs), {self.cable_1, self.cable_2})
        qs = FiberCableFilterSet({"is_faulted": False}, FiberCable.objects.all()).qs
        self.assertEqual(set(qs), {self.cable_3})


class TestFaultQuerySets(FaultWorld, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.build()
        cls.open_fault = FiberFault.objects.create(fiber_cable=cls.cable_1)
        cls.resolved = FiberFault.objects.create(fiber_cable=cls.cable_2, status=FiberFaultStatusChoices.RESOLVED)
        cls.strand_fault = FiberFault.objects.create(fiber_cable=cls.cable_2)
        cls.s1, cls.s2 = cls.cable_2.fiber_strands.order_by("position")[:2]
        cls.strand_fault.strands.add(cls.s1)
        cls.resolved.strands.add(cls.s2)

    def test_open_excludes_resolved(self):
        self.assertEqual(set(FiberFault.objects.open()), {self.open_fault, self.strand_fault})

    def test_whole_cable_excludes_strand_faults(self):
        self.assertEqual(set(FiberFault.objects.open().whole_cable()), {self.open_fault})

    def test_faulted_strands(self):
        expected = {self.s1} | set(self.cable_1.fiber_strands.all())
        self.assertEqual(set(FiberStrand.objects.faulted()), expected)


class TestFaultPages(FaultWorld, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.build()
        cls.whole = FiberFault.objects.create(fiber_cable=cls.cable_1, location_mark=Decimal("12"))
        cls.partial = FiberFault.objects.create(fiber_cable=cls.cable_1)
        cls.partial.strands.add(*cls.cable_1.fiber_strands.all()[:2])
        FiberFault.objects.create(
            fiber_cable=cls.cable_1, status=FiberFaultStatusChoices.RESOLVED, description="old-resolved-fault"
        )

    def setUp(self):
        self.client = superuser_client("fault-pages")

    def test_list_renders_zero_strands_as_whole_cable(self):
        content = self.client.get(reverse("plugins:netbox_fms:fiberfault_list")).content.decode()
        self.assertIn("Whole cable", content)
        self.assertRegex(content, r"<td[^>]*>\s*2\s*</td>")

    def test_cable_panel_lists_only_open_faults_with_report_button(self):
        content = self.client.get(self.cable_1.get_absolute_url()).content.decode()
        self.assertIn(self.whole.get_absolute_url(), content)
        self.assertIn(self.partial.get_absolute_url(), content)
        self.assertNotIn("old-resolved-fault", content)
        self.assertIn(f"{reverse('plugins:netbox_fms:fiberfault_add')}?fiber_cable={self.cable_1.pk}", content)

    def test_report_button_requires_add_permission(self):
        client = ui_client_with("fault-viewer", [(FiberCable, ["view"], None), (FiberFault, ["view"], None)])
        content = client.get(self.cable_1.get_absolute_url()).content.decode()
        self.assertIn(self.whole.get_absolute_url(), content)
        self.assertNotIn(reverse("plugins:netbox_fms:fiberfault_add"), content)

    def test_cable_panel_hides_faults_the_user_may_not_view(self):
        client = ui_client_with("fault-blind", [(FiberCable, ["view"], None)])
        content = client.get(self.cable_1.get_absolute_url()).content.decode()
        self.assertNotIn(self.whole.get_absolute_url(), content)
        self.assertNotIn(self.partial.get_absolute_url(), content)

    def test_cable_panel_hides_strands_the_user_may_not_view(self):
        hidden, shown = self.partial.strands.order_by("position")
        client = ui_client_with(
            "fault-strand-blind",
            [
                (FiberCable, ["view"], None),
                (FiberFault, ["view"], None),
                (FiberStrand, ["view"], {"pk": shown.pk}),
            ],
        )
        content = client.get(self.cable_1.get_absolute_url()).content.decode()
        self.assertIn(self.partial.get_absolute_url(), content)
        self.assertIn(f"<td>{shown.name}</td>", content)
        self.assertNotIn(f"<td>{hidden.name}", content)


class RoutedFaultWorld:
    """A cable between two devices, routed through two pathways."""

    @classmethod
    def build(cls):
        site, mfr, dt, role = make_infra("FaultLoc")
        cls.end_device = Device.objects.create(name="FaultLoc-A", site=site, device_type=dt, role=role)
        cls.other_device = Device.objects.create(name="FaultLoc-B", site=site, device_type=dt, role=role)
        cls.far_device = Device.objects.create(name="FaultLoc-C", site=site, device_type=dt, role=role)
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="FaultLoc-TB-4", construction=ConstructionChoices.TIGHT_BUFFER, strand_count=4
        )
        cable = Cable.objects.create(
            a_terminations=[make_front_port(cls.end_device, "A")],
            b_terminations=[make_front_port(cls.far_device, "B")],
        )
        cls.fc = FiberCable.objects.create(cable=cable, fiber_cable_type=fct)
        cls.segments = make_route(cable, [100.0, 200.0])
        cls.pathway_ct = ContentType.objects.get_by_natural_key("netbox_pathways", "pathway")
        cls.device_ct = ContentType.objects.get_for_model(Device)


class TestFaultLocationValidation(RoutedFaultWorld, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.build()

    def _fault(self, **fields):
        return FiberFault(fiber_cable=self.fc, **fields)

    def _errors(self, fault):
        with self.assertRaises(ValidationError) as ctx:
            fault.full_clean()
        return ctx.exception.message_dict

    def test_located_at_type_must_be_device_or_pathway(self):
        site_ct = ContentType.objects.get_for_model(Site)
        errors = self._errors(self._fault(located_at_type=site_ct, located_at_id=1))
        self.assertIn("located_at_type", errors)

    def test_device_must_terminate_the_cable(self):
        errors = self._errors(self._fault(located_at_type=self.device_ct, located_at_id=self.other_device.pk))
        self.assertIn("located_at_id", errors)
        self._fault(located_at_type=self.device_ct, located_at_id=self.end_device.pk).full_clean()

    def test_pathway_must_be_on_the_route(self):
        other = Cable.objects.create(
            a_terminations=[make_front_port(self.end_device, "A2")],
            b_terminations=[make_front_port(self.far_device, "B2")],
        )
        stray = make_route(other, [50.0])[0].pathway_id
        errors = self._errors(self._fault(located_at_type=self.pathway_ct, located_at_id=stray))
        self.assertIn("located_at_id", errors)
        on_route = self.segments[0].pathway_id
        self._fault(located_at_type=self.pathway_ct, located_at_id=on_route).full_clean()

    def test_stale_link_does_not_block_other_edits(self):
        """#198: a fault whose pathway left the route can still be resolved; a new off-route link is refused."""
        fault = create_fault_with_location(
            fiber_cable=self.fc,
            located_at_status=FiberFaultLocatedAtStatusChoices.CONFIRMED,
            located_at_type=self.pathway_ct,
            located_at_id=self.segments[1].pathway_id,
        )
        self.segments[1].delete()

        fault.status = FiberFaultStatusChoices.RESOLVED
        fault.full_clean()
        fault.save()

        other = Cable.objects.create(
            a_terminations=[make_front_port(self.end_device, "A3")],
            b_terminations=[make_front_port(self.far_device, "B3")],
        )
        fault.located_at_id = make_route(other, [50.0])[0].pathway_id
        self.assertEqual(self._errors(fault)["located_at_id"], ["The pathway is not on this cable's route."])

    def test_pathway_without_pathways_installed(self):
        fault = self._fault(located_at_type=self.pathway_ct, located_at_id=self.segments[0].pathway_id)
        with patch("netbox_fms.pathways_compat.pathways_installed", return_value=False):
            errors = self._errors(fault)
        self.assertEqual(errors["located_at_type"], ["netbox-pathways is not installed."])

    def test_otdr_origin_and_distance_go_together(self):
        self.assertIn("otdr_distance", self._errors(self._fault(otdr_origin=self.end_device)))
        self.assertIn("otdr_origin", self._errors(self._fault(otdr_distance=Decimal("10"))))

    def test_located_at_is_stale_after_pathway_leaves_route(self):
        """#198: a link to a pathway the cable no longer crosses reads as stale; a rebuild heals it."""
        seg = self.segments[1]
        fault = self._fault(located_at_type=self.pathway_ct, located_at_id=seg.pathway_id)
        self.assertFalse(fault.located_at_is_stale)
        self.assertEqual(fault.route_segment().pk, seg.pk)
        seg.delete()
        self.assertTrue(fault.located_at_is_stale)
        self.assertIsNone(fault.route_segment())
        rebuilt = type(seg).objects.create(cable=self.fc.cable, pathway=seg.pathway, sequence=2)
        self.assertEqual(fault.route_segment().pk, rebuilt.pk)
        self.assertFalse(fault.located_at_is_stale)

    def test_located_at_is_stale_when_device_is_gone(self):
        fault = self._fault(located_at_type=self.device_ct, located_at_id=999999999)
        self.assertTrue(fault.located_at_is_stale)
        self.assertIsNone(self._fault().route_segment())
        self.assertFalse(self._fault().located_at_is_stale)

    def test_helpers_set_confirm_and_clear(self):
        fault = self._fault(estimate_note="guess")
        fault.set_located_at_pathway(self.segments[0].pathway_id)
        self.assertEqual(fault.located_at_pathway_pk, self.segments[0].pathway_id)
        self.assertIsNone(fault.located_at_device)
        fault.confirm_located_at()
        self.assertEqual((fault.located_at_status, fault.estimate_note), ("confirmed", ""))
        fault.clear_located_at()
        self.assertEqual((fault.located_at_status, fault.located_at_type, fault.located_at_id), ("none", None, None))
        fault.located_at_type, fault.located_at_id = self.device_ct, self.end_device.pk
        self.assertEqual(fault.located_at_device, self.end_device)
        self.assertIsNone(fault.located_at_pathway_pk)


class TestFaultLocationSurfaces(RoutedFaultWorld, AuthedAPIClientMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.build()
        cls.user = get_user_model().objects.create_superuser("fault-loc-api", password="x")

    def _form(self, fault=None, **data):
        base = {"fiber_cable": self.fc.pk, "status": FiberFaultStatusChoices.OPEN, "reported_at": "2026-10-01 12:00"}
        return FiberFaultForm(instance=fault, data=base | data)

    def _estimated(self, **fields):
        return create_fault_with_location(
            fiber_cable=self.fc,
            located_at_status=FiberFaultLocatedAtStatusChoices.ESTIMATED,
            located_at_type=self.pathway_ct,
            located_at_id=self.segments[1].pathway_id,
            estimate_note="old guess",
            **fields,
        )

    def test_form_pick_segment_confirms(self):
        """#198: picking a route segment in the form confirms the location and drops the estimate note."""
        fault = self._estimated()
        pathway_pk = self.segments[0].pathway_id
        form = self._form(fault, located_at_type=self.pathway_ct.pk, located_at=pathway_pk)
        self.assertTrue(form.is_valid(), form.errors)
        fault = form.save()
        self.assertEqual((fault.located_at_status, fault.estimate_note), ("confirmed", ""))
        self.assertEqual(fault.located_at_pathway_pk, pathway_pk)

    def test_form_clearing_confirmed_located_at_resets(self):
        fault = FiberFault.objects.create(
            fiber_cable=self.fc,
            located_at_status=FiberFaultLocatedAtStatusChoices.CONFIRMED,
            located_at_type=self.device_ct,
            located_at_id=self.end_device.pk,
        )
        form = self._form(fault, located_at_type="", located_at="")
        self.assertTrue(form.is_valid(), form.errors)
        fault = form.save()
        self.assertEqual((fault.located_at_status, fault.located_at_type, fault.located_at_id), ("none", None, None))

    def test_form_clearing_estimated_located_at_resets(self):
        """#198: removing an estimated link leaves no stale "estimated" status behind."""
        form = self._form(self._estimated(), located_at_type="", located_at="")
        self.assertTrue(form.is_valid(), form.errors)
        fault = form.save()
        self.assertEqual((fault.located_at_status, fault.estimate_note), ("none", ""))

    def test_form_device_off_the_cable_errors_on_the_picker(self):
        form = self._form(located_at_type=self.device_ct.pk, located_at=self.other_device.pk)
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["located_at"], ["The device does not terminate this cable."])

    def test_form_without_pathways_offers_device_only(self):
        with patch("netbox_fms.pathways_compat.pathways_installed", return_value=False):
            form = FiberFaultForm()
        self.assertEqual(list(form.fields["located_at_type"].queryset), [self.device_ct])

    def test_serializer_device_confirms_and_status_is_read_only(self):
        """#198: an API-picked closure is confirmed; the status itself cannot be written."""
        fault = self._estimated()
        url = f"/api/plugins/fms/fiber-faults/{fault.pk}/"
        resp = self.client.patch(
            url, {"located_at_type": "dcim.device", "located_at_id": self.end_device.pk}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual((body["located_at_status"], body["estimate_note"]), ("confirmed", ""))
        self.assertEqual(body["located_at"]["id"], self.end_device.pk)
        resp = self.client.patch(url, {"located_at_status": "none"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        fault.refresh_from_db()
        self.assertEqual(fault.located_at_status, "confirmed")

    def test_serializer_clearing_estimated_located_at_resets(self):
        fault = self._estimated()
        resp = self.client.patch(
            f"/api/plugins/fms/fiber-faults/{fault.pk}/",
            {"located_at_type": None, "located_at_id": None},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual((resp.json()["located_at_status"], resp.json()["located_at"]), ("none", None))

    def test_serializer_tolerates_pathway_link_without_pathways(self):
        """#198: a pathway link left behind after netbox-pathways is removed serializes as null, not a 500."""
        fault = self._estimated()
        with patch.object(ContentType, "model_class", return_value=None):
            resp = self.client.get(f"/api/plugins/fms/fiber-faults/{fault.pk}/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIsNone(resp.json()["located_at"])

    def test_serializer_resending_an_estimated_link_keeps_it_estimated(self):
        fault = self._estimated()
        resp = self.client.patch(
            f"/api/plugins/fms/fiber-faults/{fault.pk}/",
            {"located_at_type": "netbox_pathways.pathway", "located_at_id": fault.located_at_id},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        fault.refresh_from_db()
        self.assertEqual((fault.located_at_status, fault.estimate_note), ("estimated", "old guess"))


class TestFaultLocationPage(RoutedFaultWorld, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.build()

    def setUp(self):
        self.client = superuser_client("fault-loc-page")

    def _page(self, **fields):
        fault = create_fault_with_location(fiber_cable=self.fc, **fields)
        resp = self.client.get(fault.get_absolute_url())
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode()

    def test_detail_links_segment_on_cable_map(self):
        segment = self.segments[1]
        content = self._page(
            located_at_status=FiberFaultLocatedAtStatusChoices.ESTIMATED,
            located_at_type=self.pathway_ct,
            located_at_id=segment.pathway_id,
            estimate_note="from the jacket mark",
        )
        self.assertIn(f"route-map/?segment={segment.pk}", content)
        self.assertIn("Estimated", content)
        self.assertIn("from the jacket mark", content)
        self.assertNotIn("no longer on the cable's route", content)

    def test_detail_marks_stale_location(self):
        other = Cable.objects.create(
            a_terminations=[make_front_port(self.end_device, "S-A")],
            b_terminations=[make_front_port(self.far_device, "S-B")],
        )
        stray = make_route(other, [30.0])[0].pathway_id
        content = self._page(located_at_type=self.pathway_ct, located_at_id=stray)
        self.assertIn("no longer on the cable's route", content)

    def test_detail_without_pathways_renders(self):
        fields = {"located_at_type": self.device_ct, "located_at_id": self.end_device.pk}
        self.assertIn(f"/plugins/pathways/map/#site={self.end_device.site_id}", self._page(**fields))
        with patch("netbox_fms.pathways_compat.pathways_installed", return_value=False):
            content = self._page(**fields)
        self.assertIn(self.end_device.get_absolute_url(), content)
        self.assertNotIn("/plugins/pathways/map/#site=", content)


class TestFaultLocationActions(RoutedFaultWorld, AuthedAPIClientMixin, TestCase):
    """Confirm and re-estimate (#198)."""

    @classmethod
    def setUpTestData(cls):
        cls.build()
        cls.user = get_user_model().objects.create_superuser("fault-loc-actions", password="x")
        cls.marked_type = FiberCableType.objects.create(
            manufacturer=cls.fc.fiber_cable_type.manufacturer,
            model="FaultLoc-Marked",
            construction=ConstructionChoices.TIGHT_BUFFER,
            strand_count=2,
            mark_unit="m",
        )
        cls.fault_ct = ContentType.objects.get_for_model(FiberFault)

    def _routed_fault(self):
        cable = Cable.objects.create(
            a_terminations=[make_front_port(self.end_device, "M-A")],
            b_terminations=[make_front_port(self.far_device, "M-B")],
            length=300,
            length_unit="m",
        )
        fc = FiberCable.objects.create(cable=cable, fiber_cable_type=self.marked_type, start_mark=0, end_mark=300)
        segments = make_route(cable, [100.0, 200.0])
        return FiberFault.objects.create(fiber_cable=fc, location_mark=Decimal("200")), cable, segments

    @staticmethod
    def _reshape_route(segments):
        """Lengthen the first pathway and shorten the second, so the same mark now falls on the first."""
        for segment, length in zip(segments, (250.0, 50.0), strict=True):
            segment.pathway.length = length
            segment.pathway.save()
        return segments

    def _url(self, fault, action):
        return reverse(f"plugins-api:netbox_fms-api:fiberfault-{action}", kwargs={"pk": fault.pk})

    def test_confirm_estimated_location(self):
        fault, _cable, segments = self._routed_fault()
        self.assertEqual(fault.located_at_status, FiberFaultLocatedAtStatusChoices.ESTIMATED)
        resp = superuser_client("fault-confirm-ui").post(
            reverse("plugins:netbox_fms:fiberfault_confirm_location", args=[fault.pk])
        )
        self.assertEqual(resp.status_code, 302)
        fault.refresh_from_db()
        self.assertEqual(fault.located_at_status, FiberFaultLocatedAtStatusChoices.CONFIRMED)
        self.assertEqual(fault.located_at_pathway_pk, segments[1].pathway_id)
        self.assertEqual(fault.estimate_note, "")

    def test_confirm_refused_without_estimate(self):
        fault = create_fault_with_location(fiber_cable=self.fc)
        resp = self.client.post(self._url(fault, "confirm-location"))
        self.assertEqual(resp.status_code, 409)
        fault.refresh_from_db()
        self.assertEqual(fault.located_at_status, FiberFaultLocatedAtStatusChoices.NONE)

    def test_actions_record_the_location_before_the_change(self):
        """#198: the changelog entries of confirm and re-estimate carry the pre-change location."""
        fault, _cable, segments = self._routed_fault()
        self.client.post(self._url(fault, "confirm-location"))
        FiberFault.objects.filter(pk=fault.pk).update(located_at_status=FiberFaultLocatedAtStatusChoices.ESTIMATED)
        self._reshape_route(segments)
        self.client.post(self._url(fault, "re-estimate"))

        confirm, reestimate = ObjectChange.objects.filter(
            changed_object_id=fault.pk, changed_object_type=self.fault_ct
        ).order_by("pk")
        self.assertEqual((confirm.prechange_data or {}).get("located_at_status"), "estimated")
        self.assertEqual((reestimate.prechange_data or {}).get("located_at_status"), "estimated")
        self.assertEqual(
            (reestimate.prechange_data["located_at_id"], reestimate.postchange_data["located_at_id"]),
            (segments[1].pathway_id, segments[0].pathway_id),
        )

    def test_confirm_refused_for_a_stale_estimate(self):
        fault, _cable, segments = self._routed_fault()
        segments[1].delete()
        resp = self.client.post(self._url(fault, "confirm-location"))
        self.assertEqual(resp.status_code, 409)
        fault.refresh_from_db()
        self.assertEqual(fault.located_at_status, FiberFaultLocatedAtStatusChoices.ESTIMATED)

    def test_confirm_via_api_returns_the_fault(self):
        fault, _cable, _segments = self._routed_fault()
        resp = self.client.post(self._url(fault, "confirm-location"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["id"], fault.pk)
        fault.refresh_from_db()
        self.assertEqual(fault.located_at_status, FiberFaultLocatedAtStatusChoices.CONFIRMED)

    def test_reestimate_picks_up_new_route(self):
        fault, _cable, segments = self._routed_fault()
        new_segments = self._reshape_route(segments)
        resp = self.client.post(self._url(fault, "re-estimate"))
        self.assertEqual(resp.status_code, 200)
        fault.refresh_from_db()
        self.assertEqual(fault.located_at_pathway_pk, new_segments[0].pathway_id)
        self.assertEqual(fault.located_at_status, FiberFaultLocatedAtStatusChoices.ESTIMATED)

    def test_reestimate_from_the_page(self):
        fault, _cable, segments = self._routed_fault()
        new_segments = self._reshape_route(segments)
        resp = superuser_client("fault-reest-ui").post(
            reverse("plugins:netbox_fms:fiberfault_reestimate", args=[fault.pk])
        )
        self.assertEqual(resp.status_code, 302)
        fault.refresh_from_db()
        self.assertEqual(fault.located_at_pathway_pk, new_segments[0].pathway_id)

    def test_reestimate_refused_when_confirmed(self):
        fault, _cable, segments = self._routed_fault()
        fault.confirm_located_at()
        fault.save()
        resp = self.client.post(self._url(fault, "re-estimate"))
        self.assertEqual(resp.status_code, 409)
        resp = superuser_client("fault-reest-refused").post(
            reverse("plugins:netbox_fms:fiberfault_reestimate", args=[fault.pk])
        )
        self.assertEqual(resp.status_code, 302)
        fault.refresh_from_db()
        self.assertEqual(fault.located_at_status, FiberFaultLocatedAtStatusChoices.CONFIRMED)
        self.assertEqual(fault.located_at_pathway_pk, segments[1].pathway_id)

    def test_confirm_from_the_page_refused_without_estimate(self):
        fault = create_fault_with_location(fiber_cable=self.fc)
        resp = superuser_client("fault-confirm-none").post(
            reverse("plugins:netbox_fms:fiberfault_confirm_location", args=[fault.pk])
        )
        self.assertEqual(resp.status_code, 302)
        fault.refresh_from_db()
        self.assertEqual(fault.located_at_status, FiberFaultLocatedAtStatusChoices.NONE)

    def test_actions_need_change_permission(self):
        fault, _cable, _segments = self._routed_fault()
        view_only = [(FiberFault, ["view"], None)]
        client = ui_client_with("fault-view-only", view_only)
        for name in ("fiberfault_confirm_location", "fiberfault_reestimate"):
            resp = client.post(reverse(f"plugins:netbox_fms:{name}", args=[fault.pk]))
            self.assertEqual(resp.status_code, 403)
        from tests.conftest import make_authed_client, user_with

        api = make_authed_client("fault-view-api")
        api.force_authenticate(user_with("fault-view-only-api", view_only))
        for action in ("confirm-location", "re-estimate"):
            self.assertEqual(api.post(self._url(fault, action)).status_code, 403)

    def test_buttons_follow_the_location_status(self):
        fault, _cable, _segments = self._routed_fault()
        client = superuser_client("fault-buttons")
        page = client.get(fault.get_absolute_url()).content.decode()
        self.assertIn("confirm-location/", page)
        self.assertIn("re-estimate/", page)
        fault.confirm_located_at()
        fault.save()
        page = client.get(fault.get_absolute_url()).content.decode()
        self.assertNotIn("confirm-location/", page)
        self.assertNotIn("re-estimate/", page)
