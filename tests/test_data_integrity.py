import pytest
from unittest.mock import patch, MagicMock
from django.db import IntegrityError

from netbox_fms.models import (
    BufferTube,
    BufferTubeTemplate,
    CableElement,
    FiberCable,
    FiberCableType,
    FiberStrand,
)


def _make_cable_type(suffix=""):
    from dcim.models import Manufacturer

    mfr, _ = Manufacturer.objects.get_or_create(name=f"TestMfr{suffix}", slug=f"testmfr{suffix}")
    fct = FiberCableType.objects.create(
        manufacturer=mfr,
        model=f"Test-12F{suffix}",
        strand_count=12,
        fiber_type="sm",
        construction="loose",
        deployment="underground",
    )
    BufferTubeTemplate.objects.create(
        fiber_cable_type=fct,
        name="T1",
        position=1,
        color="0000ff",
        fiber_count=12,
    )
    return fct


@pytest.mark.django_db
class TestInstantiateComponentsTransaction:
    """Verify _instantiate_components is atomic — partial creation rolls back."""

    def test_partial_failure_rolls_back_all_components(self):
        """If bulk_create of strands fails, no tubes should be left behind."""
        from dcim.models import Cable

        fct = _make_cable_type("-txn")
        cable = Cable.objects.create()

        with patch.object(FiberStrand.objects, "bulk_create", side_effect=IntegrityError("simulated")):
            with pytest.raises(IntegrityError):
                FiberCable.objects.create(
                    fiber_cable_type=fct,
                    cable=cable,
                )

        assert not FiberCable.objects.filter(cable=cable).exists()
        assert BufferTube.objects.count() == 0


@pytest.mark.django_db
class TestFiberCableTypeValidation:
    """Verify FiberCableType.clean() catches strand_count mismatches."""

    def test_strand_count_mismatch_with_templates(self):
        from dcim.models import Manufacturer
        from django.core.exceptions import ValidationError

        mfr = Manufacturer.objects.create(name="TestMfr-val", slug="testmfr-val")
        fct = FiberCableType(
            manufacturer=mfr,
            model="Mismatch-12F",
            strand_count=24,
            fiber_type="sm",
            construction="loose",
            deployment="underground",
        )
        fct.save()

        BufferTubeTemplate.objects.create(
            fiber_cable_type=fct,
            name="T1",
            position=1,
            color="0000ff",
            fiber_count=12,
        )

        with pytest.raises(ValidationError, match="strand_count"):
            fct.clean()

    def test_strand_count_matches_templates_passes(self):
        from dcim.models import Manufacturer

        mfr = Manufacturer.objects.create(name="TestMfr-val2", slug="testmfr-val2")
        fct = FiberCableType(
            manufacturer=mfr,
            model="Match-12F",
            strand_count=12,
            fiber_type="sm",
            construction="loose",
            deployment="underground",
        )
        fct.save()

        BufferTubeTemplate.objects.create(
            fiber_cable_type=fct,
            name="T1",
            position=1,
            color="0000ff",
            fiber_count=12,
        )

        fct.clean()

    def test_no_templates_allows_any_strand_count(self):
        from dcim.models import Manufacturer

        mfr = Manufacturer.objects.create(name="TestMfr-val3", slug="testmfr-val3")
        fct = FiberCableType(
            manufacturer=mfr,
            model="Tight-6F",
            strand_count=6,
            fiber_type="sm",
            construction="tight",
            deployment="underground",
        )
        fct.save()

        fct.clean()
