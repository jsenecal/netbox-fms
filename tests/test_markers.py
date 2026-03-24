"""Tests for the fiber marker system (marker_count, marker_color, marker_type)."""

import pytest
from dcim.models import Cable, Manufacturer

from netbox_fms.choices import ConstructionChoices
from netbox_fms.models import (
    BufferTubeTemplate,
    FiberCable,
    FiberCableType,
    RibbonTemplate,
)


@pytest.fixture
def mfr(db):
    return Manufacturer.objects.create(name="Marker-Mfr", slug="marker-mfr")


def _make_cable():
    cable = Cable.objects.create()
    cable.a_terminations = []
    cable.b_terminations = []
    cable.save()
    return cable


class TestTubeMarkers:
    def test_tube_markers_copied_from_template(self, mfr):
        """Tube template marker fields are copied to tube instances."""
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="MK-Tube-Copy",
            construction=ConstructionChoices.LOOSE_TUBE,
            fiber_type="smf_os2",
            strand_count=24,
        )
        # Unmarked tube
        BufferTubeTemplate.objects.create(
            fiber_cable_type=fct,
            name="T1",
            position=1,
            fiber_count=12,
        )
        # Marked tube
        BufferTubeTemplate.objects.create(
            fiber_cable_type=fct,
            name="T2",
            position=2,
            fiber_count=12,
            marker_count=1,
            marker_color="000000",
            marker_type="stripe",
        )

        cable = _make_cable()
        fc = FiberCable(cable=cable, fiber_cable_type=fct)
        fc.save()

        tubes = list(fc.buffer_tubes.order_by("position"))
        assert len(tubes) == 2

        # Unmarked tube: defaults
        assert tubes[0].marker_count == 0
        assert tubes[0].marker_color == ""
        assert tubes[0].marker_type == ""

        # Marked tube: copied from template
        assert tubes[1].marker_count == 1
        assert tubes[1].marker_color == "000000"
        assert tubes[1].marker_type == "stripe"


class TestStrandMarkers:
    def test_loose_tube_48f_strand_markers(self, mfr):
        """Strand markers are computed from tube template's strand_marker_interval."""
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="MK-LT-48",
            construction=ConstructionChoices.LOOSE_TUBE,
            fiber_type="smf_os2",
            strand_count=48,
        )
        BufferTubeTemplate.objects.create(
            fiber_cable_type=fct,
            name="T1",
            position=1,
            fiber_count=48,
            strand_marker_interval=12,
            strand_marker_type="dash",
        )

        cable = _make_cable()
        fc = FiberCable(cable=cable, fiber_cable_type=fct)
        fc.save()

        strands = list(fc.fiber_strands.order_by("position"))
        assert len(strands) == 48

        # Strands 1-12: group 0 → no marker
        for s in strands[:12]:
            assert s.marker_count == 0, f"Strand {s.position} should have marker_count=0"

        # Strands 13-24: group 1
        for s in strands[12:24]:
            assert s.marker_count == 1, f"Strand {s.position} should have marker_count=1"
            assert s.marker_type == "dash"

        # Strands 25-36: group 2
        for s in strands[24:36]:
            assert s.marker_count == 2, f"Strand {s.position} should have marker_count=2"

        # Strands 37-48: group 3
        for s in strands[36:48]:
            assert s.marker_count == 3, f"Strand {s.position} should have marker_count=3"

    def test_no_interval_means_no_strand_markers(self, mfr):
        """strand_marker_interval=0 means no strand markers."""
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="MK-NoInt",
            construction=ConstructionChoices.LOOSE_TUBE,
            fiber_type="smf_os2",
            strand_count=24,
        )
        BufferTubeTemplate.objects.create(
            fiber_cable_type=fct,
            name="T1",
            position=1,
            fiber_count=24,
            strand_marker_interval=0,
        )

        cable = _make_cable()
        fc = FiberCable(cable=cable, fiber_cable_type=fct)
        fc.save()

        for s in fc.fiber_strands.all():
            assert s.marker_count == 0

    def test_tight_buffer_strand_markers_from_cable_type(self, mfr):
        """Tight buffer cables use FiberCableType's strand_marker_* fields."""
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="MK-TB-48",
            construction=ConstructionChoices.TIGHT_BUFFER,
            fiber_type="smf_os2",
            strand_count=48,
            strand_marker_interval=12,
            strand_marker_type="dash",
        )

        cable = _make_cable()
        fc = FiberCable(cable=cable, fiber_cable_type=fct)
        fc.save()

        strands = list(fc.fiber_strands.order_by("position"))
        assert len(strands) == 48

        # Group 0 (1-12): no markers
        for s in strands[:12]:
            assert s.marker_count == 0

        # Group 1 (13-24)
        for s in strands[12:24]:
            assert s.marker_count == 1
            assert s.marker_type == "dash"

        # Group 2 (25-36)
        for s in strands[24:36]:
            assert s.marker_count == 2

        # Group 3 (37-48)
        for s in strands[36:48]:
            assert s.marker_count == 3

    def test_ribbon_in_tube_uses_ribbon_marker_config(self, mfr):
        """Ribbon-in-tube: strands get markers from RibbonTemplate, not BufferTubeTemplate."""
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="MK-RIT",
            construction=ConstructionChoices.RIBBON_IN_TUBE,
            fiber_type="smf_os2",
            strand_count=24,
        )
        tt = BufferTubeTemplate.objects.create(
            fiber_cable_type=fct,
            name="T1",
            position=1,
            # Tube has strand markers that should NOT be used for ribbon fibers
            strand_marker_interval=99,
            strand_marker_type="band",
        )
        RibbonTemplate.objects.create(
            fiber_cable_type=fct,
            buffer_tube_template=tt,
            name="R1",
            position=1,
            fiber_count=24,
            strand_marker_interval=12,
            strand_marker_type="ring",
        )

        cable = _make_cable()
        fc = FiberCable(cable=cable, fiber_cable_type=fct)
        fc.save()

        strands = list(fc.fiber_strands.order_by("position"))
        assert len(strands) == 24

        # Strands 13-24 should get "ring" from ribbon, not "band" from tube
        for s in strands[12:24]:
            assert s.marker_type == "ring", f"Strand {s.position} should have marker_type='ring'"
            assert s.marker_count == 1

        # Strands 1-12 should have no markers
        for s in strands[:12]:
            assert s.marker_count == 0

    def test_strand_marker_color_copied(self, mfr):
        """strand_marker_color on tube template is copied to marked strands."""
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="MK-Color",
            construction=ConstructionChoices.LOOSE_TUBE,
            fiber_type="smf_os2",
            strand_count=24,
        )
        BufferTubeTemplate.objects.create(
            fiber_cable_type=fct,
            name="T1",
            position=1,
            fiber_count=24,
            strand_marker_interval=12,
            strand_marker_color="ff0000",
            strand_marker_type="dash",
        )

        cable = _make_cable()
        fc = FiberCable(cable=cable, fiber_cable_type=fct)
        fc.save()

        strands = list(fc.fiber_strands.order_by("position"))

        # Unmarked strands (1-12): no color
        for s in strands[:12]:
            assert s.marker_color == ""

        # Marked strands (13-24): red
        for s in strands[12:24]:
            assert s.marker_color == "ff0000"
