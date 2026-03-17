import pytest
from dcim.models import Manufacturer

from netbox_fms.models import BufferTubeTemplate, FiberCableType, RibbonTemplate


@pytest.mark.django_db
class TestGetStrandCountFromTemplates:
    def test_ribbon_in_tube_counts_correctly(self):
        mfr = Manufacturer.objects.create(name="RIT-Mfr", slug="rit-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="RIT-24F",
            strand_count=24,
            fiber_type="smf_os2",
            construction="ribbon_in_tube",
        )
        btt = BufferTubeTemplate.objects.create(
            fiber_cable_type=fct,
            name="T1",
            position=1,
            fiber_count=None,
        )
        RibbonTemplate.objects.create(
            fiber_cable_type=fct,
            buffer_tube_template=btt,
            name="R1",
            position=1,
            fiber_count=12,
        )
        RibbonTemplate.objects.create(
            fiber_cable_type=fct,
            buffer_tube_template=btt,
            name="R2",
            position=2,
            fiber_count=12,
        )
        assert fct.get_strand_count_from_templates() == 24

    def test_loose_tube_counts_correctly(self):
        mfr = Manufacturer.objects.create(name="LT-Mfr", slug="lt-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="LT-48F",
            strand_count=48,
            fiber_type="smf_os2",
            construction="loose_tube",
        )
        for i in range(1, 5):
            BufferTubeTemplate.objects.create(
                fiber_cable_type=fct,
                name=f"T{i}",
                position=i,
                fiber_count=12,
            )
        assert fct.get_strand_count_from_templates() == 48


from netbox_fms.cable_profiles import FIBER_CABLE_PROFILES


class TestCableProfileRegistry:
    def test_single_connector_profiles_exist(self):
        for count in [24, 48, 72, 96, 144, 216, 288, 432]:
            key = f"single-1c{count}p"
            assert key in FIBER_CABLE_PROFILES, f"Missing: {key}"
            _label, cls = FIBER_CABLE_PROFILES[key]
            assert cls.a_connectors == {1: count}
            assert cls.b_connectors == cls.a_connectors

    def test_trunk_12p_profiles_exist(self):
        for connectors in [2, 4, 6, 8, 12, 18, 24]:
            key = f"trunk-{connectors}c12p"
            assert key in FIBER_CABLE_PROFILES, f"Missing: {key}"
            _label, cls = FIBER_CABLE_PROFILES[key]
            assert len(cls.a_connectors) == connectors
            assert all(v == 12 for v in cls.a_connectors.values())
            assert cls.b_connectors == cls.a_connectors

    def test_trunk_24p_profiles_exist(self):
        for connectors in [2, 4, 6, 12]:
            key = f"trunk-{connectors}c24p"
            assert key in FIBER_CABLE_PROFILES, f"Missing: {key}"
            _label, cls = FIBER_CABLE_PROFILES[key]
            assert len(cls.a_connectors) == connectors
            assert all(v == 24 for v in cls.a_connectors.values())
