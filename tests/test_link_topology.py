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
            assert cls.b_connectors == cls.a_connectors


@pytest.mark.django_db
class TestGetCableProfile:
    def test_tight_buffer_48f(self):
        mfr = Manufacturer.objects.create(name="TB48-Mfr", slug="tb48-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="TB-48F", strand_count=48,
            fiber_type="smf_os2", construction="tight_buffer",
        )
        assert fct.get_cable_profile() == "single-1c48p"

    def test_tight_buffer_6f_not_in_registry(self):
        mfr = Manufacturer.objects.create(name="TB6-Mfr", slug="tb6-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="TB-6F", strand_count=6,
            fiber_type="smf_os2", construction="tight_buffer",
        )
        assert fct.get_cable_profile() is None  # 6p not in plugin registry

    def test_loose_tube_12x12(self):
        mfr = Manufacturer.objects.create(name="LT12-Mfr", slug="lt12-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="LT-144F", strand_count=144,
            fiber_type="smf_os2", construction="loose_tube",
        )
        for i in range(1, 13):
            BufferTubeTemplate.objects.create(
                fiber_cable_type=fct, name=f"T{i}", position=i, fiber_count=12,
            )
        assert fct.get_cable_profile() == "trunk-12c12p"

    def test_ribbon_in_tube_4x12(self):
        mfr = Manufacturer.objects.create(name="RIT2-Mfr", slug="rit2-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="RIT-48F", strand_count=48,
            fiber_type="smf_os2", construction="ribbon_in_tube",
        )
        for i in range(1, 5):
            btt = BufferTubeTemplate.objects.create(
                fiber_cable_type=fct, name=f"T{i}", position=i, fiber_count=None,
            )
            RibbonTemplate.objects.create(
                fiber_cable_type=fct, buffer_tube_template=btt,
                name=f"R{i}", position=1, fiber_count=12,
            )
        assert fct.get_cable_profile() == "trunk-4c12p"

    def test_mixed_tube_sizes(self):
        mfr = Manufacturer.objects.create(name="MX-Mfr", slug="mx-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="MX-18F", strand_count=18,
            fiber_type="smf_os2", construction="loose_tube",
        )
        BufferTubeTemplate.objects.create(
            fiber_cable_type=fct, name="T1", position=1, fiber_count=12,
        )
        BufferTubeTemplate.objects.create(
            fiber_cable_type=fct, name="T2", position=2, fiber_count=6,
        )
        assert fct.get_cable_profile() is None

    def test_topology_not_in_registry(self):
        mfr = Manufacturer.objects.create(name="NR-Mfr", slug="nr-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="NR-36F", strand_count=36,
            fiber_type="smf_os2", construction="loose_tube",
        )
        for i in range(1, 4):
            BufferTubeTemplate.objects.create(
                fiber_cable_type=fct, name=f"T{i}", position=i, fiber_count=12,
            )
        assert fct.get_cable_profile() is None  # trunk-3c12p not in registry
