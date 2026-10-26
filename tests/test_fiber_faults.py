"""Tests for FiberFault validation and lifecycle (#198)."""

from datetime import timedelta
from decimal import Decimal

from dcim.models import Cable, Manufacturer
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from netbox_fms.choices import ConstructionChoices, FiberFaultStatusChoices
from netbox_fms.filters import FiberCableFilterSet, FiberStrandFilterSet
from netbox_fms.forms import FiberFaultForm
from netbox_fms.models import FiberCable, FiberCableType, FiberFault, FiberStrand, validate_fault_strands
from tests.conftest import AuthedAPIClientMixin, superuser_client, ui_client_with


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
        self.assertNotIn(hidden.name, content)
        self.assertIn(f"<td>{shown.name}</td>", content)
