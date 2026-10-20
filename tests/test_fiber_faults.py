"""Tests for FiberFault validation and lifecycle (#198)."""

from datetime import timedelta
from decimal import Decimal

from dcim.models import Cable, Manufacturer
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from netbox_fms.choices import ConstructionChoices, FiberFaultStatusChoices
from netbox_fms.models import FiberCable, FiberCableType, FiberFault, validate_fault_strands


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

    def test_resolving_stamps_resolved_at_and_reopening_clears_it(self):
        fault = self._fault()
        fault.save()
        self.assertTrue(fault.is_whole_cable)
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
