"""Tests for fms#22: physical-construction additions to FiberCableType
plus the derived `glass_length` property on FiberCable.

- ``FiberCableType.outer_diameter`` -- nullable FloatField, mm-implicit.
- ``FiberCableType.twist_factor_ratio`` -- nullable FloatField, dimensionless.
- ``FiberCable.glass_length`` -- read-only property, returns
  ``cable.length * (Decimal(1) + twist_factor_ratio)``; ``None`` when
  either operand is missing.
"""

from decimal import Decimal

from dcim.models import Cable, Manufacturer
from django.test import TestCase

from netbox_fms.models import FiberCable, FiberCableType


class TestFiberCableTypePhysicalFields(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manufacturer = Manufacturer.objects.create(name="Acme Optics", slug="acme-optics")

    def _make_type(self, **overrides):
        defaults = {
            "manufacturer": self.manufacturer,
            "model": "TYPE-1",
            "construction": "loose_tube",
            "strand_count": 12,
        }
        defaults.update(overrides)
        return FiberCableType.objects.create(**defaults)

    def test_outer_diameter_stored(self):
        fct = self._make_type(model="TYPE-OD", outer_diameter=12.7)
        fct.refresh_from_db()
        assert fct.outer_diameter == 12.7

    def test_outer_diameter_optional(self):
        fct = self._make_type(model="TYPE-OD-NULL")
        assert fct.outer_diameter is None

    def test_twist_factor_ratio_stored(self):
        fct = self._make_type(model="TYPE-TWIST", twist_factor_ratio=0.005)
        fct.refresh_from_db()
        assert fct.twist_factor_ratio == 0.005

    def test_twist_factor_ratio_optional(self):
        fct = self._make_type(model="TYPE-TWIST-NULL")
        assert fct.twist_factor_ratio is None


class TestFiberCableGlassLength(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manufacturer = Manufacturer.objects.create(name="Acme Optics 2", slug="acme-optics-2")

    def _make_fc(self, length=None, twist_factor_ratio=None):
        fct = FiberCableType.objects.create(
            manufacturer=self.manufacturer,
            model=f"TYPE-GL-{twist_factor_ratio}-{length}",
            construction="loose_tube",
            strand_count=12,
            twist_factor_ratio=twist_factor_ratio,
        )
        cable = Cable.objects.create(length=length, length_unit="m" if length is not None else "")
        return FiberCable.objects.create(cable=cable, fiber_cable_type=fct)

    def test_glass_length_with_twist(self):
        fc = self._make_fc(length=Decimal("1000.00"), twist_factor_ratio=0.005)
        # 1000m sheath * 1.005 = 1005m glass
        assert fc.glass_length == Decimal("1005.000")

    def test_glass_length_zero_twist(self):
        fc = self._make_fc(length=Decimal("1000.00"), twist_factor_ratio=0.0)
        assert fc.glass_length == Decimal("1000.00")

    def test_glass_length_none_when_length_missing(self):
        fc = self._make_fc(length=None, twist_factor_ratio=0.005)
        assert fc.glass_length is None

    def test_glass_length_none_when_twist_missing(self):
        fc = self._make_fc(length=Decimal("1000.00"), twist_factor_ratio=None)
        assert fc.glass_length is None
