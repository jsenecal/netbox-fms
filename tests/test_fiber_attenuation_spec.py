"""Tests for issue #23: per-wavelength attenuation specs on FiberCableType.

Covers:
- FiberCableType.get_attenuation(wavelength_nm) helper.
- FiberAttenuationSpec model + (fiber_cable_type, wavelength_nm) uniqueness.
- FiberCircuitPath.calculated_loss_db is a @property returning
  [(wavelength_nm, loss_db), ...] tuples computed from spec rows and
  cable glass length, with wavelengths intersected across all cables in
  the path.
"""

from decimal import Decimal

from dcim.models import (
    Cable,
    Device,
    DeviceRole,
    DeviceType,
    FrontPort,
    Manufacturer,
    Site,
)
from django.db import IntegrityError
from django.test import TestCase

from netbox_fms.choices import FiberCircuitStatusChoices
from netbox_fms.models import (
    FiberAttenuationSpec,
    FiberCable,
    FiberCableType,
    FiberCircuit,
    FiberCircuitNode,
    FiberCircuitPath,
)


class TestFiberAttenuationSpecModel(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mfr = Manufacturer.objects.create(name="SpecMfr", slug="spec-mfr")
        cls.type = FiberCableType.objects.create(
            manufacturer=cls.mfr,
            model="SpecType",
            construction="loose_tube",
            strand_count=12,
        )

    def test_create_spec(self):
        spec = FiberAttenuationSpec.objects.create(
            fiber_cable_type=self.type,
            wavelength_nm=1310,
            max_loss_db_per_km=Decimal("0.3500"),
        )
        assert spec.pk is not None
        assert spec.fiber_cable_type == self.type
        assert spec.wavelength_nm == 1310
        assert spec.max_loss_db_per_km == Decimal("0.3500")

    def test_str_includes_wavelength_and_value(self):
        spec = FiberAttenuationSpec.objects.create(
            fiber_cable_type=self.type,
            wavelength_nm=1550,
            max_loss_db_per_km=Decimal("0.2200"),
        )
        rendered = str(spec)
        assert "1550" in rendered
        assert "0.22" in rendered

    def test_unique_together_blocks_duplicates(self):
        FiberAttenuationSpec.objects.create(
            fiber_cable_type=self.type,
            wavelength_nm=1310,
            max_loss_db_per_km=Decimal("0.3500"),
        )
        with self.assertRaises(IntegrityError):
            FiberAttenuationSpec.objects.create(
                fiber_cable_type=self.type,
                wavelength_nm=1310,
                max_loss_db_per_km=Decimal("0.4000"),
            )


class TestFiberCableTypeGetAttenuation(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mfr = Manufacturer.objects.create(name="GetMfr", slug="get-mfr")
        cls.type = FiberCableType.objects.create(
            manufacturer=cls.mfr,
            model="GetType",
            construction="loose_tube",
            strand_count=12,
        )
        FiberAttenuationSpec.objects.create(
            fiber_cable_type=cls.type,
            wavelength_nm=1310,
            max_loss_db_per_km=Decimal("0.3500"),
        )
        FiberAttenuationSpec.objects.create(
            fiber_cable_type=cls.type,
            wavelength_nm=1550,
            max_loss_db_per_km=Decimal("0.2200"),
        )

    def test_returns_value_for_known_wavelength(self):
        assert self.type.get_attenuation(1310) == Decimal("0.3500")
        assert self.type.get_attenuation(1550) == Decimal("0.2200")

    def test_returns_none_for_unknown_wavelength(self):
        assert self.type.get_attenuation(1625) is None


class TestFiberCableCalculatedLossProperty(TestCase):
    """FiberCable.calculated_loss_db returns per-wavelength loss for one cable."""

    @classmethod
    def setUpTestData(cls):
        cls.mfr = Manufacturer.objects.create(name="FCMfr", slug="fc-mfr")
        cls.fct = FiberCableType.objects.create(
            manufacturer=cls.mfr,
            model="FCType",
            construction="loose_tube",
            strand_count=12,
            twist_factor_ratio=0.0,
        )
        FiberAttenuationSpec.objects.create(
            fiber_cable_type=cls.fct,
            wavelength_nm=1310,
            max_loss_db_per_km=Decimal("0.3500"),
        )
        FiberAttenuationSpec.objects.create(
            fiber_cable_type=cls.fct,
            wavelength_nm=1550,
            max_loss_db_per_km=Decimal("0.2200"),
        )

    def _make_fc(self, length, unit="m"):
        cable = Cable.objects.create(length=length, length_unit=unit)
        return FiberCable.objects.create(cable=cable, fiber_cable_type=self.fct)

    def test_returns_sorted_tuples_for_one_km(self):
        fc = self._make_fc(Decimal("1000"), "m")
        result = fc.calculated_loss_db
        assert result == [(1310, Decimal("0.350")), (1550, Decimal("0.220"))]

    def test_kilometer_unit(self):
        fc = self._make_fc(Decimal("2"), "km")
        result = dict(fc.calculated_loss_db)
        assert result[1310] == Decimal("0.700")
        assert result[1550] == Decimal("0.440")

    def test_empty_when_no_glass_length(self):
        fc = self._make_fc(None, "")
        assert fc.calculated_loss_db == []

    def test_empty_when_cable_type_has_no_specs(self):
        empty_fct = FiberCableType.objects.create(
            manufacturer=self.mfr,
            model="EmptyType",
            construction="loose_tube",
            strand_count=12,
            twist_factor_ratio=0.0,
        )
        cable = Cable.objects.create(length=Decimal("1000"), length_unit="m")
        fc = FiberCable.objects.create(cable=cable, fiber_cable_type=empty_fct)
        assert fc.calculated_loss_db == []


class TestFiberCircuitPathCalculatedLossProperty(TestCase):
    """FiberCircuitPath.calculated_loss_db is a property returning tuples."""

    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="LossSite", slug="loss-site")
        mfr = Manufacturer.objects.create(name="LossMfr", slug="loss-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="LossDev", slug="lossdev")
        role = DeviceRole.objects.create(name="LossRole", slug="loss-role")
        device = Device.objects.create(name="LossD1", site=site, device_type=dt, role=role)
        cls.fp_a = FrontPort.objects.create(device=device, name="LFP-A", type="lc")
        cls.fp_b = FrontPort.objects.create(device=device, name="LFP-B", type="lc")

        cls.fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="LossType",
            construction="loose_tube",
            strand_count=12,
            twist_factor_ratio=0.0,  # so glass_length == sheath length
        )
        FiberAttenuationSpec.objects.create(
            fiber_cable_type=cls.fct,
            wavelength_nm=1310,
            max_loss_db_per_km=Decimal("0.3500"),
        )
        FiberAttenuationSpec.objects.create(
            fiber_cable_type=cls.fct,
            wavelength_nm=1550,
            max_loss_db_per_km=Decimal("0.2200"),
        )

        cls.circuit = FiberCircuit.objects.create(
            name="LossCircuit",
            status=FiberCircuitStatusChoices.ACTIVE,
            strand_count=2,
        )

    def _make_path_with_cables(self, *length_unit_pairs, position=1):
        path = FiberCircuitPath.objects.create(
            circuit=self.circuit,
            position=position,
            origin=self.fp_a,
            destination=self.fp_b,
            path=[],
            is_complete=True,
        )
        for idx, (length, unit) in enumerate(length_unit_pairs, start=1):
            cable = Cable.objects.create(
                length=length if length is not None else None,
                length_unit=unit,
            )
            FiberCable.objects.create(cable=cable, fiber_cable_type=self.fct)
            FiberCircuitNode.objects.create(path=path, position=idx, cable=cable)
        return path

    def test_property_returns_list_of_tuples_sorted_by_wavelength(self):
        path = self._make_path_with_cables((Decimal("1000"), "m"))
        result = path.calculated_loss_db
        assert isinstance(result, list)
        wavelengths = [w for w, _v in result]
        assert wavelengths == sorted(wavelengths)
        assert all(isinstance(w, int) for w, _v in result)
        assert all(isinstance(v, Decimal) for _w, v in result)

    def test_loss_at_each_wavelength_for_one_km(self):
        # 1000m = 1km, glass_length matches sheath (twist=0)
        path = self._make_path_with_cables((Decimal("1000"), "m"))
        result = dict(path.calculated_loss_db)
        # 1km × 0.35 dB/km = 0.350 dB
        assert result[1310] == Decimal("0.350")
        # 1km × 0.22 dB/km = 0.220 dB
        assert result[1550] == Decimal("0.220")

    def test_loss_in_kilometer_units(self):
        path = self._make_path_with_cables((Decimal("2"), "km"))
        result = dict(path.calculated_loss_db)
        assert result[1310] == Decimal("0.700")
        assert result[1550] == Decimal("0.440")

    def test_loss_sums_across_multiple_cables(self):
        # 500m + 1500m = 2000m total = 2km
        path = self._make_path_with_cables(
            (Decimal("500"), "m"),
            (Decimal("1500"), "m"),
        )
        result = dict(path.calculated_loss_db)
        assert result[1310] == Decimal("0.700")  # 2km × 0.35
        assert result[1550] == Decimal("0.440")  # 2km × 0.22

    def test_empty_when_no_cables_in_path(self):
        path = FiberCircuitPath.objects.create(
            circuit=self.circuit,
            position=2,
            origin=self.fp_a,
            path=[],
            is_complete=False,
        )
        assert path.calculated_loss_db == []

    def test_empty_when_cable_has_no_length(self):
        path = self._make_path_with_cables((None, ""))
        assert path.calculated_loss_db == []

    def test_wavelength_excluded_when_any_cable_lacks_spec(self):
        """If one cable's type has no spec at 1625, 1625 is excluded
        from the result even if another cable's type covers it.
        """
        other_type = FiberCableType.objects.create(
            manufacturer=self.fct.manufacturer,
            model="LossType-Partial",
            construction="loose_tube",
            strand_count=12,
            twist_factor_ratio=0.0,
        )
        # other_type only has 1310, not 1550
        FiberAttenuationSpec.objects.create(
            fiber_cable_type=other_type,
            wavelength_nm=1310,
            max_loss_db_per_km=Decimal("0.3500"),
        )

        path = FiberCircuitPath.objects.create(
            circuit=self.circuit,
            position=3,
            origin=self.fp_a,
            destination=self.fp_b,
            path=[],
            is_complete=True,
        )
        c1 = Cable.objects.create(length=Decimal("1000"), length_unit="m")
        FiberCable.objects.create(cable=c1, fiber_cable_type=self.fct)
        FiberCircuitNode.objects.create(path=path, position=1, cable=c1)
        c2 = Cable.objects.create(length=Decimal("1000"), length_unit="m")
        FiberCable.objects.create(cable=c2, fiber_cable_type=other_type)
        FiberCircuitNode.objects.create(path=path, position=2, cable=c2)

        result = dict(path.calculated_loss_db)
        assert 1310 in result  # both cables have 1310 spec
        assert 1550 not in result  # other_type has no 1550 spec


class TestFiberCableCableTypeValidation(TestCase):
    """FiberCable.clean() rejects non-fibre dcim.Cable.type values."""

    @classmethod
    def setUpTestData(cls):
        cls.mfr = Manufacturer.objects.create(name="ValMfr", slug="val-mfr")
        cls.fct = FiberCableType.objects.create(
            manufacturer=cls.mfr,
            model="ValType",
            construction="loose_tube",
            strand_count=12,
        )

    def test_rejects_copper_cable_type(self):
        from django.core.exceptions import ValidationError

        cable = Cable.objects.create(type="cat6")
        fc = FiberCable(cable=cable, fiber_cable_type=self.fct)
        with self.assertRaises(ValidationError):
            fc.clean()

    def test_accepts_smf_cable_type(self):
        cable = Cable.objects.create(type="smf-os2")
        fc = FiberCable(cable=cable, fiber_cable_type=self.fct)
        fc.clean()  # should not raise

    def test_accepts_mmf_cable_type(self):
        cable = Cable.objects.create(type="mmf-om4")
        fc = FiberCable(cable=cable, fiber_cable_type=self.fct)
        fc.clean()  # should not raise

    def test_accepts_blank_cable_type(self):
        """A Cable with no type set is allowed (validation kicks in only when type is set)."""
        cable = Cable.objects.create()
        fc = FiberCable(cable=cable, fiber_cable_type=self.fct)
        fc.clean()  # should not raise
