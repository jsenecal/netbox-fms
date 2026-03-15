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
