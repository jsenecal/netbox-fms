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


@pytest.mark.django_db
class TestBufferTubeTemplateValidation:
    """BufferTubeTemplate must have fiber_count XOR ribbon children."""

    def _make_type(self):
        from dcim.models import Manufacturer

        mfr = Manufacturer.objects.create(name="TestMfr-btt", slug="testmfr-btt")
        return FiberCableType.objects.create(
            manufacturer=mfr,
            model="BTT-Test",
            strand_count=12,
            fiber_type="sm",
            construction="loose",
            deployment="underground",
        )

    def test_fiber_count_and_ribbons_raises(self):
        from django.core.exceptions import ValidationError
        from netbox_fms.models import RibbonTemplate

        fct = self._make_type()
        btt = BufferTubeTemplate.objects.create(
            fiber_cable_type=fct,
            name="T1",
            position=1,
            color="0000ff",
            fiber_count=12,
        )
        RibbonTemplate.objects.create(
            fiber_cable_type=fct,
            buffer_tube_template=btt,
            name="R1",
            position=1,
            fiber_count=12,
        )

        with pytest.raises(ValidationError, match="fiber_count"):
            btt.clean()

    def test_fiber_count_only_passes(self):
        fct = self._make_type()
        btt = BufferTubeTemplate.objects.create(
            fiber_cable_type=fct,
            name="T1",
            position=1,
            color="0000ff",
            fiber_count=12,
        )
        btt.clean()


@pytest.mark.django_db
class TestFiberPathLossUniqueness:
    """FiberPathLoss should enforce unique (cable, wavelength_nm)."""

    def test_duplicate_cable_wavelength_rejected(self):
        from dcim.models import Cable
        from netbox_fms.models import FiberPathLoss

        cable = Cable.objects.create()

        FiberPathLoss.objects.create(
            cable=cable,
            wavelength_nm=1310,
            measured_loss_db=0.5,
        )

        with pytest.raises(IntegrityError):
            FiberPathLoss.objects.create(
                cable=cable,
                wavelength_nm=1310,
                measured_loss_db=0.8,
            )


@pytest.mark.django_db
class TestImportLiveStateValidation:
    """import_live_state should validate entries before bulk_create."""

    def test_import_empty_returns_zero(self):
        from unittest.mock import patch
        from netbox_fms.services import import_live_state
        from netbox_fms.models import SplicePlan

        plan = MagicMock(spec=SplicePlan)
        plan.pk = 999
        plan.closure_id = 1

        with patch("netbox_fms.services.get_live_state", return_value={}):
            count = import_live_state(plan)
            assert count == 0


@pytest.mark.django_db
class TestRibbonTemplateUniqueness:
    """RibbonTemplate should enforce name uniqueness even with NULL tube."""

    def test_duplicate_central_ribbon_name_rejected(self):
        from dcim.models import Manufacturer
        from netbox_fms.models import RibbonTemplate

        mfr = Manufacturer.objects.create(name="TestMfr-rt", slug="testmfr-rt")
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="RT-Test",
            strand_count=24,
            fiber_type="sm",
            construction="ribbon",
            deployment="underground",
        )
        RibbonTemplate.objects.create(
            fiber_cable_type=fct,
            buffer_tube_template=None,
            name="R1",
            position=1,
            fiber_count=12,
        )

        with pytest.raises(IntegrityError):
            RibbonTemplate.objects.create(
                fiber_cable_type=fct,
                buffer_tube_template=None,
                name="R1",
                position=2,
                fiber_count=12,
            )
