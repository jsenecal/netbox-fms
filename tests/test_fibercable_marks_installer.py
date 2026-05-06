"""Tests for fms#24: cable-type sheath mark unit, FiberCable marks/installer.

- ``FiberCableType.mark_unit`` -- the printed-on-jacket marking unit, set per type.
- ``FiberCable.start_mark`` / ``end_mark`` -- absolute sheath-distance reference frame
  for the cable, read in the cable type's ``mark_unit``.
- ``FiberCable.installed_by`` -- FK to ``tenancy.Tenant``, ``on_delete=PROTECT``.

Per project memory: test our own logic (clean validators, save swap, FK behaviour);
skip framework-only round-trips and choice-string assertions.
"""

from decimal import Decimal

from dcim.choices import CableLengthUnitChoices
from dcim.models import Cable, Manufacturer
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.test import TestCase
from tenancy.models import Tenant

from netbox_fms.models import FiberCable, FiberCableType


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manufacturer = Manufacturer.objects.create(name="Acme Optics 24", slug="acme-optics-24")
        cls.fct_marked = FiberCableType.objects.create(
            manufacturer=cls.manufacturer,
            model="TYPE-MARKED",
            construction="loose_tube",
            fiber_type="smf_os2",
            strand_count=12,
            mark_unit=CableLengthUnitChoices.UNIT_METER,
        )
        cls.fct_unmarked = FiberCableType.objects.create(
            manufacturer=cls.manufacturer,
            model="TYPE-UNMARKED",
            construction="tight_buffer",
            fiber_type="smf_os2",
            strand_count=4,
            mark_unit="",
        )
        cls.contractor = Tenant.objects.create(name="Acme Splicing 24", slug="acme-splicing-24")

    def _make_cable(self):
        return Cable.objects.create()


class TestFiberCableSheathMarks(_Base):
    def test_marks_round_trip(self):
        fc = FiberCable.objects.create(
            cable=self._make_cable(),
            fiber_cable_type=self.fct_marked,
            start_mark=Decimal("100.00"),
            end_mark=Decimal("1100.00"),
        )
        fc.refresh_from_db()
        assert fc.start_mark == Decimal("100.00")
        assert fc.end_mark == Decimal("1100.00")

    def test_swap_if_inverted_on_save(self):
        fc = FiberCable.objects.create(
            cable=self._make_cable(),
            fiber_cable_type=self.fct_marked,
            start_mark=Decimal("1100.00"),
            end_mark=Decimal("100.00"),
        )
        fc.refresh_from_db()
        assert fc.start_mark == Decimal("100.00")
        assert fc.end_mark == Decimal("1100.00")

    def test_negative_start_mark_rejected(self):
        fc = FiberCable(
            cable=self._make_cable(),
            fiber_cable_type=self.fct_marked,
            start_mark=Decimal("-1.00"),
            end_mark=Decimal("100.00"),
        )
        with self.assertRaises(ValidationError):
            fc.full_clean()

    def test_negative_end_mark_rejected(self):
        fc = FiberCable(
            cable=self._make_cable(),
            fiber_cable_type=self.fct_marked,
            start_mark=Decimal("0.00"),
            end_mark=Decimal("-5.00"),
        )
        with self.assertRaises(ValidationError):
            fc.full_clean()

    def test_marks_rejected_when_type_has_no_mark_unit(self):
        fc = FiberCable(
            cable=self._make_cable(),
            fiber_cable_type=self.fct_unmarked,
            start_mark=Decimal("0.00"),
            end_mark=Decimal("100.00"),
        )
        with self.assertRaises(ValidationError):
            fc.full_clean()

    def test_no_marks_allowed_when_type_has_no_mark_unit(self):
        # Inverse: a cable with an unmarked type and no marks set is fine.
        fc = FiberCable(
            cable=self._make_cable(),
            fiber_cable_type=self.fct_unmarked,
        )
        fc.full_clean()  # no exception


class TestFiberCableInstalledBy(_Base):
    def test_installed_by_round_trip(self):
        fc = FiberCable.objects.create(
            cable=self._make_cable(),
            fiber_cable_type=self.fct_marked,
            installed_by=self.contractor,
        )
        fc.refresh_from_db()
        assert fc.installed_by_id == self.contractor.pk

    def test_installed_by_protect_on_tenant_delete(self):
        fc = FiberCable.objects.create(
            cable=self._make_cable(),
            fiber_cable_type=self.fct_marked,
            installed_by=self.contractor,
        )
        with self.assertRaises(ProtectedError):
            self.contractor.delete()
        fc.refresh_from_db()
        assert fc.installed_by_id == self.contractor.pk
