"""Tests for FiberFault validation and lifecycle (#198)."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from core.models import ObjectChange
from dcim.models import Cable, Device, Manufacturer
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
    make_cable_between,
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
    """A 300 m cable between two devices, routed through two pathways of 100 m and 200 m."""

    @classmethod
    def build(cls):
        site, mfr, dt, role = make_infra("FaultLoc")
        cls.end_device = Device.objects.create(name="FaultLoc-A", site=site, device_type=dt, role=role)
        cls.other_device = Device.objects.create(name="FaultLoc-B", site=site, device_type=dt, role=role)
        cls.far_device = Device.objects.create(name="FaultLoc-C", site=site, device_type=dt, role=role)
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="FaultLoc-TB-4", construction=ConstructionChoices.TIGHT_BUFFER, strand_count=4
        )
        cls.cable = make_cable_between("FL", cls.end_device, cls.far_device, 300)
        cls.fc = FiberCable.objects.create(cable=cls.cable, fiber_cable_type=fct)
        cls.segments = make_route(cls.cable, [100.0, 200.0])


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

    def test_device_must_terminate_the_cable(self):
        errors = self._errors(self._fault(located_at=self.other_device))
        self.assertEqual(errors["located_at"], ["The device does not terminate this cable."])
        self._fault(located_at=self.end_device).full_clean()

    def test_closure_or_distance_not_both(self):
        errors = self._errors(self._fault(located_at=self.end_device, distance_from_a=Decimal("10")))
        self.assertIn("distance_from_a", errors)

    def test_distance_must_lie_on_the_cable(self):
        errors = self._errors(self._fault(distance_from_a=Decimal("300.01")))
        self.assertEqual(errors["distance_from_a"], ["The distance runs past the end of the cable."])
        self._fault(distance_from_a=Decimal("300")).full_clean()

    def test_unchanged_location_does_not_block_other_edits(self):
        """#228: a cable shortened or re-terminated later must not stop the fault from being resolved."""
        at_closure = create_fault_with_location(fiber_cable=self.fc, located_at=self.end_device)
        on_span = create_fault_with_location(fiber_cable=self.fc, distance_from_a=Decimal("250"))
        Cable.objects.filter(pk=self.cable.pk).update(length=200)
        self.fc.cable.refresh_from_db()
        self.fc.cable.terminations.filter(cable_end="A").delete()

        for fault in (at_closure, on_span):
            fault.refresh_from_db()
            fault.status = FiberFaultStatusChoices.RESOLVED
            fault.full_clean()
            fault.save()

        on_span.distance_from_a = Decimal("260")
        self.assertIn("distance_from_a", self._errors(on_span))

    def test_otdr_origin_and_distance_go_together(self):
        self.assertIn("otdr_distance", self._errors(self._fault(otdr_origin=self.end_device)))
        self.assertIn("otdr_origin", self._errors(self._fault(otdr_distance=Decimal("10"))))

    def test_helpers_confirm_and_clear(self):
        fault = self._fault(estimate_note="guess", distance_from_a=Decimal("10"))
        fault.confirm_located_at()
        self.assertEqual((fault.located_at_status, fault.estimate_note), ("confirmed", ""))
        fault.located_at = self.end_device
        fault.clear_located_at()
        self.assertEqual((fault.located_at_status, fault.located_at, fault.distance_from_a), ("none", None, None))


class TestFaultLocationSurfaces(RoutedFaultWorld, AuthedAPIClientMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.build()
        cls.user = get_user_model().objects.create_superuser("fault-loc-api", password="x")

    def _form(self, fault=None, **data):
        base = {"fiber_cable": self.fc.pk, "status": FiberFaultStatusChoices.OPEN, "reported_at": "2026-10-01 12:00"}
        return FiberFaultForm(instance=fault, data=base | data)

    def _estimated(self, **fields):
        fields = {"distance_from_a": Decimal("150.00"), "estimate_note": "old guess"} | fields
        return create_fault_with_location(
            fiber_cable=self.fc, located_at_status=FiberFaultLocatedAtStatusChoices.ESTIMATED, **fields
        )

    def test_form_pick_pathway_sets_its_midpoint_confirmed(self):
        """#228: a picked route pathway places the fault in the middle of the cable's stretch through it."""
        form = self._form(self._estimated(), route_pathway=self.segments[0].pathway_id)
        self.assertTrue(form.is_valid(), form.errors)
        fault = form.save()
        self.assertEqual((fault.located_at_status, fault.estimate_note), ("confirmed", ""))
        self.assertEqual(fault.distance_from_a, Decimal("50.00"))

    def test_form_pathway_off_the_route_errors_on_the_picker(self):
        other = make_cable_between("FL2", self.end_device, self.far_device)
        form = self._form(route_pathway=make_route(other, [50.0])[0].pathway_id)
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["route_pathway"], ["The pathway is not on this cable's route."])

    def test_form_pathway_on_a_cable_without_length_errors(self):
        unmeasured = make_cable_between("FL4", self.end_device, self.far_device)
        fc = FiberCable.objects.create(cable=unmeasured, fiber_cable_type=self.fc.fiber_cable_type)
        pathway = make_route(unmeasured, [50.0])[0].pathway_id
        form = self._form(fiber_cable=fc.pk, route_pathway=pathway)
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["route_pathway"], [f"Cable {unmeasured} has no length."])

    def test_form_typed_distance_confirms(self):
        form = self._form(self._estimated(), distance_from_a="120")
        self.assertTrue(form.is_valid(), form.errors)
        fault = form.save()
        self.assertEqual((fault.located_at_status, fault.distance_from_a), ("confirmed", Decimal("120")))

    def test_form_clearing_confirmed_closure_resets(self):
        fault = FiberFault.objects.create(
            fiber_cable=self.fc,
            located_at_status=FiberFaultLocatedAtStatusChoices.CONFIRMED,
            located_at=self.end_device,
        )
        form = self._form(fault, located_at="")
        self.assertTrue(form.is_valid(), form.errors)
        fault = form.save()
        self.assertEqual((fault.located_at_status, fault.located_at), ("none", None))

    def test_form_clearing_estimated_distance_resets(self):
        """#198: removing an estimated distance leaves no stale "estimated" status behind."""
        form = self._form(self._estimated(), distance_from_a="")
        self.assertTrue(form.is_valid(), form.errors)
        fault = form.save()
        self.assertEqual((fault.located_at_status, fault.estimate_note), ("none", ""))

    def test_form_device_off_the_cable_errors_on_the_picker(self):
        form = self._form(located_at=self.other_device.pk)
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["located_at"], ["The device does not terminate this cable."])

    def test_form_without_pathways_has_no_pathway_picker(self):
        with patch("netbox_fms.pathways_compat.pathways_installed", return_value=False):
            form = FiberFaultForm()
        self.assertNotIn("route_pathway", form.fields)

    def test_serializer_device_confirms_and_status_is_read_only(self):
        """#198: an API-picked closure is confirmed; the status itself cannot be written."""
        fault = self._estimated(distance_from_a=None)
        url = f"/api/plugins/fms/fiber-faults/{fault.pk}/"
        resp = self.client.patch(url, {"located_at": self.end_device.pk}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual((body["located_at_status"], body["estimate_note"]), ("confirmed", ""))
        self.assertEqual(body["located_at"]["id"], self.end_device.pk)
        resp = self.client.patch(url, {"located_at_status": "none"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        fault.refresh_from_db()
        self.assertEqual(fault.located_at_status, "confirmed")

    def test_serializer_clearing_estimated_distance_resets(self):
        fault = self._estimated()
        resp = self.client.patch(f"/api/plugins/fms/fiber-faults/{fault.pk}/", {"distance_from_a": None}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual((resp.json()["located_at_status"], resp.json()["distance_from_a"]), ("none", None))

    def test_serializer_resending_an_estimated_distance_keeps_it_estimated(self):
        fault = self._estimated()
        resp = self.client.patch(
            f"/api/plugins/fms/fiber-faults/{fault.pk}/", {"distance_from_a": "150.00"}, format="json"
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
        content = self._page(
            located_at_status=FiberFaultLocatedAtStatusChoices.ESTIMATED,
            distance_from_a=Decimal("150"),
            estimate_note="from the jacket mark",
        )
        self.assertIn(f"route-map/?segment={self.segments[1].pk}", content)
        self.assertIn("Estimated", content)
        self.assertIn("from the jacket mark", content)

    def test_detail_says_why_a_distance_is_not_on_the_route(self):
        content = self._page(distance_from_a=Decimal("400"))
        self.assertIn("The distance runs past the end of the cable.", content)
        self.assertNotIn("route-map/?segment=", content)

    def test_detail_without_pathways_renders(self):
        fields = {"located_at": self.end_device}
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

    def _marked_fault(self):
        """A fault at jacket mark 200 on a cable marked 0..300: estimated 200 m from the A end."""
        cable = make_cable_between("FLM", self.end_device, self.far_device, 300)
        fc = FiberCable.objects.create(cable=cable, fiber_cable_type=self.marked_type, start_mark=0, end_mark=300)
        return FiberFault.objects.create(fiber_cable=fc, location_mark=Decimal("200"))

    @staticmethod
    def _remark(fault):
        """Correct the cable's start mark, so the same jacket mark now sits 150 m from the A end."""
        FiberCable.objects.filter(pk=fault.fiber_cable_id).update(start_mark=50)
        fault.fiber_cable.refresh_from_db()

    def _url(self, fault, action):
        return reverse(f"plugins-api:netbox_fms-api:fiberfault-{action}", kwargs={"pk": fault.pk})

    def test_confirm_estimated_location(self):
        fault = self._marked_fault()
        self.assertEqual(fault.located_at_status, FiberFaultLocatedAtStatusChoices.ESTIMATED)
        resp = superuser_client("fault-confirm-ui").post(
            reverse("plugins:netbox_fms:fiberfault_confirm_location", args=[fault.pk])
        )
        self.assertEqual(resp.status_code, 302)
        fault.refresh_from_db()
        self.assertEqual(fault.located_at_status, FiberFaultLocatedAtStatusChoices.CONFIRMED)
        self.assertEqual(fault.distance_from_a, Decimal("200.00"))
        self.assertEqual(fault.estimate_note, "")

    def test_confirm_refused_without_estimate(self):
        fault = create_fault_with_location(fiber_cable=self.fc)
        resp = self.client.post(self._url(fault, "confirm-location"))
        self.assertEqual(resp.status_code, 409)
        fault.refresh_from_db()
        self.assertEqual(fault.located_at_status, FiberFaultLocatedAtStatusChoices.NONE)

    def test_actions_record_the_location_before_the_change(self):
        """#198: the changelog entries of confirm and re-estimate carry the pre-change location."""
        fault = self._marked_fault()
        self.client.post(self._url(fault, "confirm-location"))
        FiberFault.objects.filter(pk=fault.pk).update(located_at_status=FiberFaultLocatedAtStatusChoices.ESTIMATED)
        self._remark(fault)
        self.client.post(self._url(fault, "re-estimate"))

        confirm, reestimate = ObjectChange.objects.filter(
            changed_object_id=fault.pk, changed_object_type=self.fault_ct
        ).order_by("pk")
        self.assertEqual((confirm.prechange_data or {}).get("located_at_status"), "estimated")
        self.assertEqual((reestimate.prechange_data or {}).get("located_at_status"), "estimated")
        self.assertEqual(
            (float(reestimate.prechange_data["distance_from_a"]), float(reestimate.postchange_data["distance_from_a"])),
            (200.0, 150.0),
        )

    def test_confirm_via_api_returns_the_fault(self):
        fault = self._marked_fault()
        resp = self.client.post(self._url(fault, "confirm-location"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["id"], fault.pk)
        fault.refresh_from_db()
        self.assertEqual(fault.located_at_status, FiberFaultLocatedAtStatusChoices.CONFIRMED)

    def test_reestimate_picks_up_new_cable_marks(self):
        fault = self._marked_fault()
        self._remark(fault)
        resp = self.client.post(self._url(fault, "re-estimate"))
        self.assertEqual(resp.status_code, 200)
        fault.refresh_from_db()
        self.assertEqual(fault.distance_from_a, Decimal("150.00"))
        self.assertEqual(fault.located_at_status, FiberFaultLocatedAtStatusChoices.ESTIMATED)

    def test_reestimate_from_the_page(self):
        fault = self._marked_fault()
        self._remark(fault)
        resp = superuser_client("fault-reest-ui").post(
            reverse("plugins:netbox_fms:fiberfault_reestimate", args=[fault.pk])
        )
        self.assertEqual(resp.status_code, 302)
        fault.refresh_from_db()
        self.assertEqual(fault.distance_from_a, Decimal("150.00"))

    def test_reestimate_refused_when_confirmed(self):
        fault = self._marked_fault()
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
        self.assertEqual(fault.distance_from_a, Decimal("200.00"))

    def test_confirm_from_the_page_refused_without_estimate(self):
        fault = create_fault_with_location(fiber_cable=self.fc)
        resp = superuser_client("fault-confirm-none").post(
            reverse("plugins:netbox_fms:fiberfault_confirm_location", args=[fault.pk])
        )
        self.assertEqual(resp.status_code, 302)
        fault.refresh_from_db()
        self.assertEqual(fault.located_at_status, FiberFaultLocatedAtStatusChoices.NONE)

    def test_actions_need_change_permission(self):
        fault = self._marked_fault()
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
        fault = self._marked_fault()
        client = superuser_client("fault-buttons")
        page = client.get(fault.get_absolute_url()).content.decode()
        self.assertIn("confirm-location/", page)
        self.assertIn("re-estimate/", page)
        fault.confirm_located_at()
        fault.save()
        page = client.get(fault.get_absolute_url()).content.decode()
        self.assertNotIn("confirm-location/", page)
        self.assertNotIn("re-estimate/", page)
