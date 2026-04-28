import pytest
from dcim.models import Cable, Device, DeviceRole, DeviceType, Manufacturer, Site

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
            manufacturer=mfr,
            model="TB-48F",
            strand_count=48,
            fiber_type="smf_os2",
            construction="tight_buffer",
        )
        assert fct.get_cable_profile() == "single-1c48p"

    def test_tight_buffer_6f_uses_builtin_profile(self):
        mfr = Manufacturer.objects.create(name="TB6-Mfr", slug="tb6-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="TB-6F",
            strand_count=6,
            fiber_type="smf_os2",
            construction="tight_buffer",
        )
        assert fct.get_cable_profile() == "single-1c6p"  # built-in NetBox profile

    def test_tight_buffer_5f_no_profile(self):
        mfr = Manufacturer.objects.create(name="TB5-Mfr", slug="tb5-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="TB-5F",
            strand_count=5,
            fiber_type="smf_os2",
            construction="tight_buffer",
        )
        assert fct.get_cable_profile() is None  # no single-1c5p exists

    def test_loose_tube_12x12(self):
        mfr = Manufacturer.objects.create(name="LT12-Mfr", slug="lt12-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="LT-144F",
            strand_count=144,
            fiber_type="smf_os2",
            construction="loose_tube",
        )
        for i in range(1, 13):
            BufferTubeTemplate.objects.create(
                fiber_cable_type=fct,
                name=f"T{i}",
                position=i,
                fiber_count=12,
            )
        assert fct.get_cable_profile() == "trunk-12c12p"

    def test_ribbon_in_tube_4x12(self):
        mfr = Manufacturer.objects.create(name="RIT2-Mfr", slug="rit2-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="RIT-48F",
            strand_count=48,
            fiber_type="smf_os2",
            construction="ribbon_in_tube",
        )
        for i in range(1, 5):
            btt = BufferTubeTemplate.objects.create(
                fiber_cable_type=fct,
                name=f"T{i}",
                position=i,
                fiber_count=None,
            )
            RibbonTemplate.objects.create(
                fiber_cable_type=fct,
                buffer_tube_template=btt,
                name=f"R{i}",
                position=1,
                fiber_count=12,
            )
        assert fct.get_cable_profile() == "trunk-4c12p"

    def test_mixed_tube_sizes(self):
        mfr = Manufacturer.objects.create(name="MX-Mfr", slug="mx-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="MX-18F",
            strand_count=18,
            fiber_type="smf_os2",
            construction="loose_tube",
        )
        BufferTubeTemplate.objects.create(
            fiber_cable_type=fct,
            name="T1",
            position=1,
            fiber_count=12,
        )
        BufferTubeTemplate.objects.create(
            fiber_cable_type=fct,
            name="T2",
            position=2,
            fiber_count=6,
        )
        assert fct.get_cable_profile() is None

    def test_topology_not_in_registry(self):
        mfr = Manufacturer.objects.create(name="NR-Mfr", slug="nr-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="NR-36F",
            strand_count=36,
            fiber_type="smf_os2",
            construction="loose_tube",
        )
        for i in range(1, 4):
            BufferTubeTemplate.objects.create(
                fiber_cable_type=fct,
                name=f"T{i}",
                position=i,
                fiber_count=12,
            )
        assert fct.get_cable_profile() is None  # trunk-3c12p not in registry


from netbox_fms.services import NeedsMappingConfirmation, link_cable_topology, propose_port_mapping


class TestNeedsMappingConfirmation:
    def test_has_proposed_mapping(self):
        exc = NeedsMappingConfirmation({1: 100, 2: 200}, warnings=["mismatch"])
        assert exc.proposed_mapping == {1: 100, 2: 200}
        assert exc.warnings == ["mismatch"]

    def test_propose_port_mapping(self):
        from unittest.mock import MagicMock

        fp1 = MagicMock(pk=10)
        fp2 = MagicMock(pk=20)
        result = propose_port_mapping(3, {1: fp1, 2: fp2})
        assert result == {1: 10, 2: 20}  # position 3 has no match


@pytest.mark.django_db
class TestLinkCableTopologyGreenfield:
    def _make_fixtures(self):
        site = Site.objects.create(name="LT-Site", slug="lt-site")
        mfr = Manufacturer.objects.create(name="LT-Mfr2", slug="lt-mfr2")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Closure", slug="closure")
        role = DeviceRole.objects.create(name="LT-Role", slug="lt-role")
        device = Device.objects.create(name="LT-Closure", site=site, device_type=dt, role=role)
        cable = Cable.objects.create()
        return device, cable, mfr

    def test_creates_fiber_cable_and_strands(self):
        device, cable, mfr = self._make_fixtures()
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="GF-12F",
            strand_count=12,
            fiber_type="smf_os2",
            construction="tight_buffer",
        )
        fc, warnings = link_cable_topology(cable, fct, device)
        assert fc.cable == cable
        assert fc.fiber_strands.count() == 12

    def test_creates_rearports_per_tube(self):
        device, cable, mfr = self._make_fixtures()
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="GF-48F",
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
        fc, warnings = link_cable_topology(cable, fct, device)
        from dcim.models import RearPort

        assert RearPort.objects.filter(device=device).count() == 4

    def test_creates_single_rearport_no_tubes(self):
        device, cable, mfr = self._make_fixtures()
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="GF-6F",
            strand_count=6,
            fiber_type="smf_os2",
            construction="tight_buffer",
        )
        fc, warnings = link_cable_topology(cable, fct, device)
        from dcim.models import RearPort

        rps = RearPort.objects.filter(device=device)
        assert rps.count() == 1
        assert rps.first().positions == 6

    def test_creates_frontports_and_links_strands(self):
        device, cable, mfr = self._make_fixtures()
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="GF-12F2",
            strand_count=12,
            fiber_type="smf_os2",
            construction="tight_buffer",
        )
        fc, warnings = link_cable_topology(cable, fct, device)
        from dcim.models import FrontPort

        assert FrontPort.objects.filter(device=device).count() == 12
        assert fc.fiber_strands.filter(front_port_a__isnull=False).count() == 12

    def test_sets_cable_profile(self):
        device, cable, mfr = self._make_fixtures()
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="GF-48F2",
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
        fc, warnings = link_cable_topology(cable, fct, device)
        cable.refresh_from_db()
        assert cable.profile == "trunk-4c12p"

    def test_missing_profile_adds_warning(self):
        device, cable, mfr = self._make_fixtures()
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="GF-36F",
            strand_count=36,
            fiber_type="smf_os2",
            construction="loose_tube",
        )
        for i in range(1, 4):
            BufferTubeTemplate.objects.create(
                fiber_cable_type=fct,
                name=f"T{i}",
                position=i,
                fiber_count=12,
            )
        fc, warnings = link_cable_topology(cable, fct, device)
        assert len(warnings) > 0
        assert "profile" in warnings[0].lower()


@pytest.mark.django_db
class TestLinkCableTopologyAdopt:
    def _make_closure_with_existing_ports(self):
        site = Site.objects.create(name="AD-Site", slug="ad-site")
        mfr = Manufacturer.objects.create(name="AD-Mfr", slug="ad-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="AD-Closure", slug="ad-closure")
        role = DeviceRole.objects.create(name="AD-Role", slug="ad-role")
        device = Device.objects.create(name="AD-Closure", site=site, device_type=dt, role=role)
        cable = Cable.objects.create()

        from dcim.models import CableTermination, FrontPort, PortMapping, RearPort
        from django.contrib.contenttypes.models import ContentType

        rp = RearPort.objects.create(device=device, name="Existing-RP", type="splice", positions=12)
        rp_ct = ContentType.objects.get_for_model(RearPort)
        CableTermination.objects.create(cable=cable, cable_end="A", termination_type=rp_ct, termination_id=rp.pk)
        fps = []
        for i in range(1, 13):
            fp = FrontPort.objects.create(device=device, name=f"EF{i}", type="splice")
            PortMapping.objects.create(
                device=device, front_port=fp, rear_port=rp, front_port_position=1, rear_port_position=i
            )
            fps.append(fp)

        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="AD-12F",
            strand_count=12,
            fiber_type="smf_os2",
            construction="tight_buffer",
        )
        return device, cable, fct, fps

    def test_raises_needs_mapping_without_port_mapping(self):
        device, cable, fct, fps = self._make_closure_with_existing_ports()
        with pytest.raises(NeedsMappingConfirmation) as exc_info:
            link_cable_topology(cable, fct, device)
        assert len(exc_info.value.proposed_mapping) == 12

    def test_adopts_existing_ports_with_mapping(self):
        device, cable, fct, fps = self._make_closure_with_existing_ports()
        mapping = {i: fps[i - 1].pk for i in range(1, 13)}
        fc, warnings = link_cable_topology(cable, fct, device, port_mapping=mapping)
        assert fc.fiber_strands.filter(front_port_a__isnull=False).count() == 12
        from dcim.models import RearPort

        assert RearPort.objects.filter(device=device).count() == 1  # no new RearPorts

    def test_count_mismatch_has_warning(self):
        device, cable, fct, fps = self._make_closure_with_existing_ports()
        fct.strand_count = 6
        fct.save()
        with pytest.raises(NeedsMappingConfirmation) as exc_info:
            link_cable_topology(cable, fct, device)
        assert len(exc_info.value.proposed_mapping) == 6
        assert len(exc_info.value.warnings) > 0


@pytest.mark.django_db
class TestLinkTopologyView:
    def test_get_returns_modal(self, client):
        from django.contrib.auth import get_user_model

        site = Site.objects.create(name="LTV-Site", slug="ltv-site")
        mfr = Manufacturer.objects.create(name="LTV-Mfr", slug="ltv-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="LTV-Closure", slug="ltv-closure")
        role = DeviceRole.objects.create(name="LTV-Role", slug="ltv-role")
        device = Device.objects.create(name="LTV-Device", site=site, device_type=dt, role=role)
        cable = Cable.objects.create()
        User = get_user_model()
        user = User.objects.create_superuser("ltv-admin", "ltv@test.com", "password")
        client.force_login(user)
        url = f"/plugins/fms/fiber-overview/{device.pk}/link-topology/?cable_id={cable.pk}"
        response = client.get(url)
        assert response.status_code == 200
        assert b"Link Cable Topology" in response.content


class TestMonkeyPatchCableProfiles:
    """Test that the monkey patch correctly extends NetBox's cable profile system."""

    def test_custom_profiles_in_cable_profile_choices(self):
        from dcim.choices import CableProfileChoices

        # Flatten all choice values
        values = set()
        for group in CableProfileChoices.CHOICES:
            for choice in group[1]:
                if isinstance(choice, (list, tuple)):
                    values.add(choice[0])
        # Custom single profiles
        assert "single-1c24p" in values
        assert "single-1c48p" in values
        assert "single-1c288p" in values
        # Custom trunk profiles
        assert "trunk-4c12p" in values
        assert "trunk-24c12p" in values
        # Built-in profiles still present
        assert "single-1c1p" in values
        assert "trunk-2c2p" in values

    def test_cable_profile_class_returns_custom_profile(self):
        from dcim.models import Cable

        cable = Cable()
        cable.profile = "trunk-24c12p"
        cls = cable.profile_class
        assert cls is not None
        assert cls.a_connectors == dict.fromkeys(range(1, 25), 12)
        assert cls.b_connectors == cls.a_connectors

    def test_cable_profile_class_returns_builtin_profile(self):
        from dcim.models import Cable

        cable = Cable()
        cable.profile = "single-1c1p"
        cls = cable.profile_class
        assert cls is not None
        assert cls.a_connectors == {1: 1}

    def test_cable_profile_field_accepts_custom_values(self):
        from dcim.models import Cable

        field = Cable._meta.get_field("profile")
        choice_values = set()
        for group in field.choices:
            if isinstance(group[1], list):
                for choice in group[1]:
                    choice_values.add(choice[0])
            elif isinstance(group[1], tuple):
                for choice in group[1]:
                    if isinstance(choice, (list, tuple)):
                        choice_values.add(choice[0])
        assert "trunk-24c12p" in choice_values
        assert "single-1c288p" in choice_values


@pytest.mark.django_db
class TestCableTerminationConnectorPositions:
    """Test that link_cable_topology sets connector/positions on CableTerminations."""

    def _make_fixtures(self):
        site = Site.objects.create(name="CT-Site", slug="ct-site")
        mfr = Manufacturer.objects.create(name="CT-Mfr", slug="ct-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="CT-Closure", slug="ct-closure")
        role = DeviceRole.objects.create(name="CT-Role", slug="ct-role")
        device = Device.objects.create(name="CT-Closure", site=site, device_type=dt, role=role)
        cable = Cable.objects.create()
        return device, cable, mfr

    def test_tube_based_sets_connector_per_tube(self):
        device, cable, mfr = self._make_fixtures()
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="CT-48F",
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
        fc, warnings = link_cable_topology(cable, fct, device)

        from dcim.models import CableTermination, RearPort
        from django.contrib.contenttypes.models import ContentType

        rp_ct = ContentType.objects.get_for_model(RearPort)
        terms = CableTermination.objects.filter(
            cable=cable,
            termination_type=rp_ct,
        ).order_by("connector")
        assert terms.count() == 4
        for i, term in enumerate(terms, start=1):
            assert term.connector == i
            assert term.positions == list(range(1, 13))

    def test_tight_buffer_sets_single_connector(self):
        device, cable, mfr = self._make_fixtures()
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="CT-12F",
            strand_count=12,
            fiber_type="smf_os2",
            construction="tight_buffer",
        )
        fc, warnings = link_cable_topology(cable, fct, device)

        from dcim.models import CableTermination, RearPort
        from django.contrib.contenttypes.models import ContentType

        rp_ct = ContentType.objects.get_for_model(RearPort)
        terms = CableTermination.objects.filter(
            cable=cable,
            termination_type=rp_ct,
        )
        assert terms.count() == 1
        term = terms.first()
        assert term.connector == 1
        assert term.positions == list(range(1, 13))

    def test_rearport_syncs_cable_connector(self):
        device, cable, mfr = self._make_fixtures()
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="CT-24F",
            strand_count=24,
            fiber_type="smf_os2",
            construction="loose_tube",
        )
        for i in range(1, 3):
            BufferTubeTemplate.objects.create(
                fiber_cable_type=fct,
                name=f"T{i}",
                position=i,
                fiber_count=12,
            )
        fc, warnings = link_cable_topology(cable, fct, device)

        from dcim.models import RearPort

        rps = RearPort.objects.filter(device=device).order_by("name")
        for i, rp in enumerate(rps, start=1):
            rp.refresh_from_db()
            assert rp.cable_connector == i
            assert rp.cable_positions == list(range(1, 13))
