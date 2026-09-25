import pytest
from dcim.models import Cable, CableTermination, Manufacturer, RearPort
from django.contrib.auth import get_user_model

from netbox_fms.models import BufferTubeTemplate, FiberCable, FiberCableType, RibbonTemplate
from tests.conftest import make_central_core_type, make_closure, make_ribbon_in_tube_type


def _closure_with_cable(prefix):
    """A bare closure and an unterminated cable: the greenfield link rig. Returns (device, cable, mfr)."""
    rig = make_closure(prefix)
    return rig.closure, Cable.objects.create(), rig.mfr


def _terminated_cable(prefix):
    """A closure whose one splice RearPort terminates the cable's A end. Returns (device, cable, mfr)."""
    device, cable, mfr = _closure_with_cable(prefix)
    rear_port = RearPort.objects.create(device=device, name=f"{prefix}-RP", type="splice", positions=12)
    CableTermination.objects.create(cable=cable, cable_end="A", termination=rear_port)
    return device, cable, mfr


def _login_superuser(client, prefix):
    user = get_user_model().objects.create_superuser(f"{prefix.lower()}-admin", f"{prefix.lower()}@test.com", "pw")
    client.force_login(user)


@pytest.mark.django_db
class TestGetStrandCountFromTemplates:
    def test_ribbon_in_tube_counts_correctly(self):
        mfr = Manufacturer.objects.create(name="RIT-Mfr", slug="rit-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="RIT-24F",
            strand_count=24,
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
            construction="tight_buffer",
        )
        assert fct.get_cable_profile() == "single-1c48p"

    def test_tight_buffer_6f_uses_builtin_profile(self):
        mfr = Manufacturer.objects.create(name="TB6-Mfr", slug="tb6-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="TB-6F",
            strand_count=6,
            construction="tight_buffer",
        )
        assert fct.get_cable_profile() == "single-1c6p"  # built-in NetBox profile

    def test_tight_buffer_5f_no_profile(self):
        mfr = Manufacturer.objects.create(name="TB5-Mfr", slug="tb5-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="TB-5F",
            strand_count=5,
            construction="tight_buffer",
        )
        assert fct.get_cable_profile() is None  # no single-1c5p exists

    def test_loose_tube_12x12(self):
        mfr = Manufacturer.objects.create(name="LT12-Mfr", slug="lt12-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="LT-144F",
            strand_count=144,
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
        fct = make_ribbon_in_tube_type(mfr, "RIT-48F", tubes=4, ribbons_per_tube=1)
        assert fct.get_cable_profile() == "trunk-4c12p"

    def test_central_core_ribbon_counts_ribbons(self):
        """Rear ports are provisioned per ribbon, so the profile follows the ribbons."""
        mfr = Manufacturer.objects.create(name="CCR-Mfr", slug="ccr-mfr")
        fct = make_central_core_type(mfr, "CCR-24F", ribbons=2)
        assert fct.get_cable_profile() == "trunk-2c12p"

    def test_ribbon_in_tube_counts_ribbons_not_tubes(self):
        """12 tubes x 2 ribbons x 12F terminates on 24 ribbon rear ports."""
        mfr = Manufacturer.objects.create(name="RCT-Mfr", slug="rct-mfr")
        fct = make_ribbon_in_tube_type(mfr, "RCT-288F", tubes=12, ribbons_per_tube=2)
        assert fct.get_cable_profile() == "trunk-24c12p"

    def test_single_ribbon_uses_single_profile(self):
        mfr = Manufacturer.objects.create(name="SR-Mfr", slug="sr-mfr")
        fct = make_central_core_type(mfr, "SR-12F", ribbons=1)
        assert fct.get_cable_profile() == "single-1c12p"

    def test_mixed_ribbon_sizes_have_no_profile(self):
        mfr = Manufacturer.objects.create(name="MRS-Mfr", slug="mrs-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="MRS-36F",
            strand_count=36,
            construction="ribbon",
        )
        RibbonTemplate.objects.create(fiber_cable_type=fct, name="R1", position=1, fiber_count=12)
        RibbonTemplate.objects.create(fiber_cable_type=fct, name="R2", position=2, fiber_count=24)
        assert fct.get_cable_profile() is None

    def test_mixed_tube_sizes(self):
        mfr = Manufacturer.objects.create(name="MX-Mfr", slug="mx-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="MX-18F",
            strand_count=18,
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
        return _closure_with_cable("LT")

    def test_creates_fiber_cable_and_strands(self):
        device, cable, mfr = self._make_fixtures()
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="GF-12F",
            strand_count=12,
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

        assert RearPort.objects.filter(device=device).count() == 4

    def test_creates_single_rearport_no_tubes(self):
        device, cable, mfr = self._make_fixtures()
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="GF-6F",
            strand_count=6,
            construction="tight_buffer",
        )
        fc, warnings = link_cable_topology(cable, fct, device)

        rps = RearPort.objects.filter(device=device)
        assert rps.count() == 1
        assert rps.first().positions == 6

    def test_creates_frontports_and_links_strands(self):
        device, cable, mfr = self._make_fixtures()
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="GF-12F2",
            strand_count=12,
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


def _make_closure_with_existing_ports():
    from dcim.models import FrontPort, PortMapping

    device, cable, mfr = _closure_with_cable("AD")
    rp = RearPort.objects.create(device=device, name="Existing-RP", type="splice", positions=12)
    CableTermination.objects.create(cable=cable, cable_end="A", termination=rp)
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
        construction="tight_buffer",
    )
    return device, cable, fct, fps


def _full_mapping(fps):
    """Adopt mapping that lands strand N on the Nth existing port."""
    return {i: fp.pk for i, fp in enumerate(fps, start=1)}


def _rig_with_existing_fibercable():
    """The adopt rig plus a FiberCable already on the cable (the issue #87 state)."""
    device, cable, fct, fps = _make_closure_with_existing_ports()
    fc = FiberCable.objects.create(cable=cable, fiber_cable_type=fct)
    return device, cable, fct, fps, fc


@pytest.mark.django_db
class TestLinkCableTopologyAdopt:
    def test_raises_needs_mapping_without_port_mapping(self):
        device, cable, fct, fps = _make_closure_with_existing_ports()
        with pytest.raises(NeedsMappingConfirmation) as exc_info:
            link_cable_topology(cable, fct, device)
        assert len(exc_info.value.proposed_mapping) == 12

    def test_adopts_existing_ports_with_mapping(self):
        device, cable, fct, fps = _make_closure_with_existing_ports()
        mapping = _full_mapping(fps)
        fc, warnings = link_cable_topology(cable, fct, device, port_mapping=mapping)
        assert fc.fiber_strands.filter(front_port_a__isnull=False).count() == 12

        assert RearPort.objects.filter(device=device).count() == 1  # no new RearPorts

    def test_adopted_ports_keep_their_names(self):
        """Adoption never renames: the ports pre-exist, so their names belong to whoever made them."""
        from dcim.models import FrontPort

        device, cable, fct, fps = _make_closure_with_existing_ports()
        mapping = _full_mapping(fps)
        fc, warnings = link_cable_topology(cable, fct, device, port_mapping=mapping)

        fp_names = set(FrontPort.objects.filter(device=device).values_list("name", flat=True))
        assert fp_names == {f"EF{i}" for i in range(1, 13)}
        assert RearPort.objects.get(device=device).name == "Existing-RP"
        assert warnings == []

    def test_adopts_across_multiple_rearports(self):
        """Regression for issue #64: per-rear-port positions offset to global strand positions."""
        device, cable, fct, fps = self._make_closure_with_multiple_rearports()
        mapping = _full_mapping(fps)
        fc, warnings = link_cable_topology(cable, fct, device, port_mapping=mapping)

        linked = {s.position: s.front_port_a_id for s in fc.fiber_strands.all()}
        assert linked == {pos: fps[pos - 1].pk for pos in range(1, 49)}
        assert warnings == []

    def test_count_mismatch_has_warning(self):
        device, cable, fct, fps = _make_closure_with_existing_ports()
        fct.strand_count = 6
        fct.save()
        with pytest.raises(NeedsMappingConfirmation) as exc_info:
            link_cable_topology(cable, fct, device)
        assert len(exc_info.value.proposed_mapping) == 6
        assert len(exc_info.value.warnings) > 0

    def _make_closure_with_multiple_rearports(self):
        """Regression fixture for issue #64: one cable terminated on 4 RearPorts,
        each with 12 positions and 12 mapped FrontPorts (48 ports total)."""
        from dcim.models import FrontPort, PortMapping

        device, cable, mfr = _closure_with_cable("MR")
        fps = []
        for t in range(1, 5):
            rp = RearPort.objects.create(device=device, name=f"MR-RP{t}", type="splice", positions=12)
            CableTermination.objects.create(cable=cable, cable_end="A", termination=rp)
            for i in range(1, 13):
                fp = FrontPort.objects.create(device=device, name=f"MR-RP{t}-F{i}", type="splice")
                PortMapping.objects.create(
                    device=device, front_port=fp, rear_port=rp, front_port_position=1, rear_port_position=i
                )
                fps.append(fp)

        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="MR-48F",
            strand_count=48,
            construction="loose_tube",
        )
        for t in range(1, 5):
            BufferTubeTemplate.objects.create(
                fiber_cable_type=fct,
                name=f"T{t}",
                position=t,
                fiber_count=12,
            )
        return device, cable, fct, fps

    def test_multiple_rearports_proposes_and_links_all_strands(self):
        device, cable, fct, fps = self._make_closure_with_multiple_rearports()
        with pytest.raises(NeedsMappingConfirmation) as exc_info:
            link_cable_topology(cable, fct, device)
        expected = {pos: fps[pos - 1].pk for pos in range(1, 49)}
        assert exc_info.value.proposed_mapping == expected
        assert exc_info.value.warnings == []

        fc, warnings = link_cable_topology(cable, fct, device, port_mapping=exc_info.value.proposed_mapping)
        assert fc.fiber_strands.filter(front_port_a__isnull=False).count() == 48

        assert RearPort.objects.filter(device=device).count() == 4  # no new RearPorts


@pytest.mark.django_db
class TestLinkTopologyView:
    def test_get_returns_modal(self, client):
        device, cable, _mfr = _terminated_cable("LTV")
        _login_superuser(client, "LTV")
        url = f"/plugins/fms/fiber-overview/{device.pk}/link-topology/?cable_id={cable.pk}"
        response = client.get(url)
        assert response.status_code == 200
        assert b"Link Cable Topology" in response.content

    def test_post_flashes_provisioning_warnings(self, client):
        """Warnings the service returns must reach the operator instead of dying on the HX redirect."""
        from unittest import mock

        from django.contrib.messages import get_messages

        device, cable, mfr = _terminated_cable("LTW")
        fct = FiberCableType.objects.create(manufacturer=mfr, model="LTW-12F", strand_count=12)
        _login_superuser(client, "LTW")

        with mock.patch(
            "netbox_fms.views.link_cable_topology", return_value=(None, ["name template fell back to pk names"])
        ):
            response = client.post(
                f"/plugins/fms/fiber-overview/{device.pk}/link-topology/",
                {"cable_id": cable.pk, "fiber_cable_type": fct.pk, "port_type": "splice"},
            )

        assert response.status_code == 200
        assert [str(m) for m in get_messages(response.wsgi_request)] == ["name template fell back to pk names"]


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
        return _closure_with_cable("CT")

    def test_tube_based_sets_connector_per_tube(self):
        device, cable, mfr = self._make_fixtures()
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="CT-48F",
            strand_count=48,
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

        rps = RearPort.objects.filter(device=device).order_by("name")
        for i, rp in enumerate(rps, start=1):
            rp.refresh_from_db()
            assert rp.cable_connector == i
            assert rp.cable_positions == list(range(1, 13))


@pytest.mark.django_db
class TestLinkStrandsExistingFiberCable:
    """Issue #87: a FiberCable created without strand links must be linkable afterwards.

    Creating the FiberCable through the plain form leaves 0/N strands linked
    and, before this fix, no path existed to map them onto the device's
    pre-existing ports: the service unconditionally created a new FiberCable
    and the overview offered no action.
    """

    def test_proposes_mapping_for_existing_fibercable(self):
        device, cable, fct, fps, fc = _rig_with_existing_fibercable()
        with pytest.raises(NeedsMappingConfirmation) as exc_info:
            link_cable_topology(cable, None, device)
        assert len(exc_info.value.proposed_mapping) == 12

    def test_links_strands_into_existing_fibercable(self):
        device, cable, fct, fps, fc = _rig_with_existing_fibercable()
        mapping = _full_mapping(fps)
        linked_fc, _warnings = link_cable_topology(cable, None, device, port_mapping=mapping)
        assert linked_fc.pk == fc.pk
        assert FiberCable.objects.filter(cable=cable).count() == 1
        assert fc.fiber_strands.filter(front_port_a__isnull=False).count() == 12

    def test_fills_missing_cable_profile(self):
        """The form path never sets the cable profile; linking strands does."""
        device, cable, fct, fps, fc = _rig_with_existing_fibercable()
        assert not cable.profile
        mapping = _full_mapping(fps)
        link_cable_topology(cable, None, device, port_mapping=mapping)
        cable.refresh_from_db()
        assert cable.profile == "single-1c12p"

    def test_conflicting_type_rejected(self):
        device, cable, fct, fps, fc = _rig_with_existing_fibercable()
        other = FiberCableType.objects.create(
            manufacturer=fct.manufacturer, model="AD-Other", strand_count=12, construction="tight_buffer"
        )
        mapping = _full_mapping(fps)
        with pytest.raises(ValueError):
            link_cable_topology(cable, other, device, port_mapping=mapping)

    def test_missing_type_without_fibercable_rejected(self):
        device, cable, fct, fps = _make_closure_with_existing_ports()
        with pytest.raises(ValueError):
            link_cable_topology(cable, None, device)

    def test_greenfield_provisioning_for_existing_fibercable(self):
        """A device with no ports still gets them provisioned for an existing FiberCable."""
        from dcim.models import RearPort

        device, cable, mfr = _closure_with_cable("GX")
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="GX-2F", strand_count=2, construction="tight_buffer"
        )
        fc = FiberCable.objects.create(cable=cable, fiber_cable_type=fct)

        linked_fc, _warnings = link_cable_topology(cable, None, device)

        assert linked_fc.pk == fc.pk
        assert RearPort.objects.filter(device=device).count() == 1
        assert fc.fiber_strands.filter(front_port_a__isnull=False).count() == 2


@pytest.mark.django_db
class TestLinkTopologyViewPostFlow:
    """View-level round trips through the link-topology modal (issue #87).

    The POST side of this modal -- including the mapping_N field parsing and
    the two-step confirmation -- previously had no view-level coverage.
    """

    def _login(self, client):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_superuser("ltp-admin", "ltp@test.com", "password")
        client.force_login(user)

    def test_round_trip_adopts_into_existing_fibercable(self, client):
        device, cable, fct, fps, fc = _rig_with_existing_fibercable()
        self._login(client)
        url = f"/plugins/fms/fiber-overview/{device.pk}/link-topology/"

        # Step 1: no type field needed -- the FiberCable fixes it.
        resp = client.post(url, {"cable_id": cable.pk})
        assert resp.status_code == 200
        assert b"confirm_mapping" in resp.content

        # Step 2: confirm the proposed mapping.
        data = {"cable_id": cable.pk, "confirm_mapping": "1"}
        data.update({f"mapping_{i}": fps[i - 1].pk for i in range(1, 13)})
        resp = client.post(url, data)
        assert resp.status_code == 200
        assert resp.has_header("HX-Redirect")
        assert fc.fiber_strands.filter(front_port_a__isnull=False).count() == 12

    def test_confirm_mapping_parses_fields_for_new_fibercable(self, client):
        device, cable, fct, fps = _make_closure_with_existing_ports()
        self._login(client)
        url = f"/plugins/fms/fiber-overview/{device.pk}/link-topology/"

        data = {"cable_id": cable.pk, "confirm_mapping": "1", "fiber_cable_type_id": fct.pk}
        data.update({f"mapping_{i}": fps[i - 1].pk for i in range(1, 13)})
        resp = client.post(url, data)
        assert resp.status_code == 200
        assert resp.has_header("HX-Redirect")
        fc = FiberCable.objects.get(cable=cable)
        assert fc.fiber_strands.filter(front_port_a__isnull=False).count() == 12

    def test_get_modal_for_linked_cable_hides_type_selector(self, client):
        device, cable, fct, fps, _fc = _rig_with_existing_fibercable()
        self._login(client)
        url = f"/plugins/fms/fiber-overview/{device.pk}/link-topology/?cable_id={cable.pk}"

        resp = client.get(url)
        assert resp.status_code == 200
        assert b"id_fiber_cable_type" not in resp.content
        assert b"AD-12F" in resp.content
