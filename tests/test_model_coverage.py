"""Tests targeting uncovered model branches to push coverage from 87% toward 93%+."""

from decimal import Decimal

import pytest
from dcim.models import Cable, Device, DeviceRole, DeviceType, Manufacturer, RearPort, Site
from django.core.exceptions import ValidationError

from netbox_fms.choices import (
    CableElementTypeChoices,
    ConstructionChoices,
    FiberCircuitStatusChoices,
    FiberTypeChoices,
)
from netbox_fms.models import (
    BufferTubeTemplate,
    CableElementTemplate,
    FiberCable,
    FiberCableType,
    FiberCircuit,
    FiberCircuitNode,
    FiberCircuitPath,
    RibbonTemplate,
    SlackLoop,
    SplicePlan,
    SplicePlanEntry,
)
from tests.conftest import make_front_port


@pytest.fixture
def base_fixtures(db):
    site = Site.objects.create(name="Cov-Site", slug="cov-site")
    mfr = Manufacturer.objects.create(name="Cov-Mfr", slug="cov-mfr")
    role = DeviceRole.objects.create(name="Cov-Role", slug="cov-role")
    dt = DeviceType.objects.create(manufacturer=mfr, model="Cov-DT", slug="cov-dt")
    device = Device.objects.create(name="Cov-Dev", site=site, device_type=dt, role=role)
    return {"site": site, "mfr": mfr, "role": role, "dt": dt, "device": device}


# ---------------------------------------------------------------------------
# FiberCableType
# ---------------------------------------------------------------------------


class TestFiberCableTypeEdgeCases:
    def test_get_absolute_url(self, base_fixtures):
        fct = FiberCableType.objects.create(
            manufacturer=base_fixtures["mfr"],
            model="URL-Test",
            construction=ConstructionChoices.TIGHT_BUFFER,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=12,
        )
        url = fct.get_absolute_url()
        assert "/cable-types/" in url
        assert str(fct.pk) in url

    def test_str(self, base_fixtures):
        fct = FiberCableType.objects.create(
            manufacturer=base_fixtures["mfr"],
            model="Str-Test",
            construction=ConstructionChoices.TIGHT_BUFFER,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=12,
        )
        assert str(fct) == f"{base_fixtures['mfr']} Str-Test"

    def test_get_strand_count_from_templates_no_tubes(self, base_fixtures):
        fct = FiberCableType.objects.create(
            manufacturer=base_fixtures["mfr"],
            model="NoTube",
            construction=ConstructionChoices.TIGHT_BUFFER,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=12,
        )
        assert fct.get_strand_count_from_templates() == 0

    def test_get_strand_count_from_templates_with_tubes(self, base_fixtures):
        fct = FiberCableType.objects.create(
            manufacturer=base_fixtures["mfr"],
            model="WithTube",
            construction=ConstructionChoices.LOOSE_TUBE,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=24,
        )
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=12)
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T2", position=2, fiber_count=12)
        assert fct.get_strand_count_from_templates() == 24

    def test_get_cable_profile_no_tubes(self, base_fixtures):
        fct = FiberCableType.objects.create(
            manufacturer=base_fixtures["mfr"],
            model="ProfileNoTube",
            construction=ConstructionChoices.TIGHT_BUFFER,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=12,
        )
        # Returns None or a valid key; just ensure no crash
        result = fct.get_cable_profile()
        assert result is None or isinstance(result, str)

    def test_get_cable_profile_mixed_fiber_counts(self, base_fixtures):
        fct = FiberCableType.objects.create(
            manufacturer=base_fixtures["mfr"],
            model="MixedTubes",
            construction=ConstructionChoices.LOOSE_TUBE,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=18,
        )
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=12)
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T2", position=2, fiber_count=6)
        # Mixed counts -> None
        assert fct.get_cable_profile() is None

    def test_clean_armor_without_type_raises(self, base_fixtures):
        fct = FiberCableType(
            manufacturer=base_fixtures["mfr"],
            model="ArmorNoType",
            construction=ConstructionChoices.TIGHT_BUFFER,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=12,
            is_armored=True,
            armor_type="",
        )
        with pytest.raises(ValidationError, match="armor_type"):
            fct.clean()

    def test_clean_armor_type_without_armored_raises(self, base_fixtures):
        fct = FiberCableType(
            manufacturer=base_fixtures["mfr"],
            model="TypeNoArmor",
            construction=ConstructionChoices.TIGHT_BUFFER,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=12,
            is_armored=False,
            armor_type="steel_tape",
        )
        with pytest.raises(ValidationError, match="armor_type"):
            fct.clean()

    def test_clean_strand_count_mismatch(self, base_fixtures):
        fct = FiberCableType.objects.create(
            manufacturer=base_fixtures["mfr"],
            model="MismatchCount",
            construction=ConstructionChoices.LOOSE_TUBE,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=12,
        )
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=6)
        with pytest.raises(ValidationError, match="strand_count"):
            fct.clean()


# ---------------------------------------------------------------------------
# FiberCable instantiation
# ---------------------------------------------------------------------------


class TestFiberCableInstantiation:
    def _make_cable(self, base_fixtures):
        cable = Cable.objects.create()
        cable.a_terminations = []
        cable.b_terminations = []
        cable.save()
        return cable

    def test_tight_buffer_instantiation(self, base_fixtures):
        """Tight buffer: no tubes, fibers directly on cable."""
        fct = FiberCableType.objects.create(
            manufacturer=base_fixtures["mfr"],
            model="TB-12",
            construction=ConstructionChoices.TIGHT_BUFFER,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=12,
        )
        cable = self._make_cable(base_fixtures)
        fc = FiberCable(cable=cable, fiber_cable_type=fct)
        fc.save()

        assert fc.fiber_strands.count() == 12
        assert fc.buffer_tubes.count() == 0
        assert fc.ribbons.count() == 0
        # Verify naming convention
        first = fc.fiber_strands.order_by("position").first()
        assert first.name == "F1"

    def test_loose_tube_instantiation(self, base_fixtures):
        """Loose tube: tubes with fiber_count -> fibers in tubes."""
        fct = FiberCableType.objects.create(
            manufacturer=base_fixtures["mfr"],
            model="LT-24",
            construction=ConstructionChoices.LOOSE_TUBE,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=24,
        )
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=12)
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T2", position=2, fiber_count=12)

        cable = self._make_cable(base_fixtures)
        fc = FiberCable(cable=cable, fiber_cable_type=fct)
        fc.save()

        assert fc.buffer_tubes.count() == 2
        assert fc.fiber_strands.count() == 24
        # All strands belong to a tube
        assert fc.fiber_strands.filter(buffer_tube__isnull=True).count() == 0

    def test_ribbon_in_tube_instantiation(self, base_fixtures):
        """Ribbon-in-tube: tubes with ribbon templates -> ribbons -> fibers."""
        fct = FiberCableType.objects.create(
            manufacturer=base_fixtures["mfr"],
            model="RIT-24",
            construction=ConstructionChoices.RIBBON_IN_TUBE,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=24,
        )
        tt = BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1)
        RibbonTemplate.objects.create(
            fiber_cable_type=fct, buffer_tube_template=tt, name="R1", position=1, fiber_count=12
        )
        RibbonTemplate.objects.create(
            fiber_cable_type=fct, buffer_tube_template=tt, name="R2", position=2, fiber_count=12
        )

        cable = self._make_cable(base_fixtures)
        fc = FiberCable(cable=cable, fiber_cable_type=fct)
        fc.save()

        assert fc.buffer_tubes.count() == 1
        assert fc.ribbons.count() == 2
        assert fc.fiber_strands.count() == 24
        # All strands belong to a ribbon
        assert fc.fiber_strands.filter(ribbon__isnull=True).count() == 0

    def test_central_core_ribbon_instantiation(self, base_fixtures):
        """Central-core ribbon: ribbon templates on type (no tube) -> ribbons -> fibers."""
        fct = FiberCableType.objects.create(
            manufacturer=base_fixtures["mfr"],
            model="CCR-24",
            construction=ConstructionChoices.RIBBON,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=24,
        )
        RibbonTemplate.objects.create(fiber_cable_type=fct, name="R1", position=1, fiber_count=12)
        RibbonTemplate.objects.create(fiber_cable_type=fct, name="R2", position=2, fiber_count=12)

        cable = self._make_cable(base_fixtures)
        fc = FiberCable(cable=cable, fiber_cable_type=fct)
        fc.save()

        assert fc.buffer_tubes.count() == 0
        assert fc.ribbons.count() == 2
        assert fc.fiber_strands.count() == 24
        # All strands belong to a ribbon, none to a tube
        assert fc.fiber_strands.filter(ribbon__isnull=True).count() == 0
        assert fc.fiber_strands.filter(buffer_tube__isnull=False).count() == 0

    def test_cable_element_instantiation(self, base_fixtures):
        """Cable elements are instantiated from templates."""
        fct = FiberCableType.objects.create(
            manufacturer=base_fixtures["mfr"],
            model="CE-12",
            construction=ConstructionChoices.TIGHT_BUFFER,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=12,
        )
        CableElementTemplate.objects.create(
            fiber_cable_type=fct, name="SM1", element_type=CableElementTypeChoices.STRENGTH_MEMBER
        )

        cable = self._make_cable(base_fixtures)
        fc = FiberCable(cable=cable, fiber_cable_type=fct)
        fc.save()

        assert fc.cable_elements.count() == 1
        assert fc.cable_elements.first().name == "SM1"

    def test_get_absolute_url(self, base_fixtures):
        fct = FiberCableType.objects.create(
            manufacturer=base_fixtures["mfr"],
            model="URL-FC",
            construction=ConstructionChoices.TIGHT_BUFFER,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=4,
        )
        cable = self._make_cable(base_fixtures)
        fc = FiberCable(cable=cable, fiber_cable_type=fct)
        fc.save()
        assert str(fc.pk) in fc.get_absolute_url()

    def test_str(self, base_fixtures):
        fct = FiberCableType.objects.create(
            manufacturer=base_fixtures["mfr"],
            model="Str-FC",
            construction=ConstructionChoices.TIGHT_BUFFER,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=4,
        )
        cable = self._make_cable(base_fixtures)
        fc = FiberCable(cable=cable, fiber_cable_type=fct)
        fc.save()
        assert "Str-FC" in str(fc)


# ---------------------------------------------------------------------------
# BufferTubeTemplate / RibbonTemplate / CableElementTemplate __str__ and URLs
# ---------------------------------------------------------------------------


class TestTemplateStrAndUrl:
    def test_buffer_tube_template_str(self, base_fixtures):
        fct = FiberCableType.objects.create(
            manufacturer=base_fixtures["mfr"],
            model="BTT-Test",
            construction=ConstructionChoices.LOOSE_TUBE,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=12,
        )
        btt = BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=12)
        assert "T1" in str(btt)
        assert str(btt.pk) in btt.get_absolute_url()

    def test_ribbon_template_str_with_tube(self, base_fixtures):
        fct = FiberCableType.objects.create(
            manufacturer=base_fixtures["mfr"],
            model="RT-Test",
            construction=ConstructionChoices.RIBBON_IN_TUBE,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=12,
        )
        btt = BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1)
        rt = RibbonTemplate.objects.create(
            fiber_cable_type=fct, buffer_tube_template=btt, name="R1", position=1, fiber_count=12
        )
        # Parent is tube
        assert "T1" in str(rt)
        assert str(rt.pk) in rt.get_absolute_url()

    def test_ribbon_template_str_without_tube(self, base_fixtures):
        fct = FiberCableType.objects.create(
            manufacturer=base_fixtures["mfr"],
            model="RT-NoTube",
            construction=ConstructionChoices.RIBBON,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=12,
        )
        rt = RibbonTemplate.objects.create(fiber_cable_type=fct, name="R1", position=1, fiber_count=12)
        # Parent is cable type
        assert "RT-NoTube" in str(rt)

    def test_cable_element_template_str(self, base_fixtures):
        fct = FiberCableType.objects.create(
            manufacturer=base_fixtures["mfr"],
            model="CET-Test",
            construction=ConstructionChoices.TIGHT_BUFFER,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=12,
        )
        cet = CableElementTemplate.objects.create(
            fiber_cable_type=fct, name="SM1", element_type=CableElementTypeChoices.STRENGTH_MEMBER
        )
        assert "SM1" in str(cet)
        assert str(cet.pk) in cet.get_absolute_url()


# ---------------------------------------------------------------------------
# Instance-level __str__ and get_absolute_url
# ---------------------------------------------------------------------------


class TestInstanceStrAndUrl:
    @pytest.fixture
    def fiber_cable_with_components(self, base_fixtures):
        fct = FiberCableType.objects.create(
            manufacturer=base_fixtures["mfr"],
            model="Inst-Test",
            construction=ConstructionChoices.LOOSE_TUBE,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=12,
        )
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=12)
        CableElementTemplate.objects.create(
            fiber_cable_type=fct, name="SM1", element_type=CableElementTypeChoices.STRENGTH_MEMBER
        )
        cable = Cable.objects.create()
        cable.a_terminations = []
        cable.b_terminations = []
        cable.save()
        fc = FiberCable(cable=cable, fiber_cable_type=fct)
        fc.save()
        return fc

    def test_buffer_tube_str(self, fiber_cable_with_components):
        bt = fiber_cable_with_components.buffer_tubes.first()
        assert "T1" in str(bt)

    def test_fiber_strand_str(self, fiber_cable_with_components):
        fs = fiber_cable_with_components.fiber_strands.first()
        assert "F" in str(fs)

    def test_cable_element_str(self, fiber_cable_with_components):
        ce = fiber_cable_with_components.cable_elements.first()
        assert "SM1" in str(ce)

    def test_ribbon_str(self, base_fixtures):
        fct = FiberCableType.objects.create(
            manufacturer=base_fixtures["mfr"],
            model="Rib-Inst",
            construction=ConstructionChoices.RIBBON,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=12,
        )
        RibbonTemplate.objects.create(fiber_cable_type=fct, name="R1", position=1, fiber_count=12)
        cable = Cable.objects.create()
        cable.a_terminations = []
        cable.b_terminations = []
        cable.save()
        fc = FiberCable(cable=cable, fiber_cable_type=fct)
        fc.save()
        ribbon = fc.ribbons.first()
        assert "R1" in str(ribbon)


# ---------------------------------------------------------------------------
# BufferTubeTemplate.clean() — mutual exclusion of fiber_count + ribbon templates
# ---------------------------------------------------------------------------


class TestBufferTubeTemplateClean:
    def test_clean_fiber_count_with_ribbon_raises(self, base_fixtures):
        fct = FiberCableType.objects.create(
            manufacturer=base_fixtures["mfr"],
            model="BTT-Clean",
            construction=ConstructionChoices.RIBBON_IN_TUBE,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=12,
        )
        btt = BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=12)
        RibbonTemplate.objects.create(
            fiber_cable_type=fct, buffer_tube_template=btt, name="R1", position=1, fiber_count=12
        )
        with pytest.raises(ValidationError, match="fiber_count"):
            btt.clean()


# ---------------------------------------------------------------------------
# SlackLoop
# ---------------------------------------------------------------------------


class TestSlackLoopEdgeCases:
    @pytest.fixture
    def slack_fixtures(self, base_fixtures):
        fct = FiberCableType.objects.create(
            manufacturer=base_fixtures["mfr"],
            model="SL-Type",
            construction=ConstructionChoices.TIGHT_BUFFER,
            fiber_type=FiberTypeChoices.SMF_OS2,
            strand_count=4,
        )
        cable = Cable.objects.create()
        cable.a_terminations = []
        cable.b_terminations = []
        cable.save()
        fc = FiberCable(cable=cable, fiber_cable_type=fct)
        fc.save()
        return {**base_fixtures, "fc": fc}

    def test_clean_negative_start_mark(self, slack_fixtures):
        sl = SlackLoop(
            fiber_cable=slack_fixtures["fc"],
            site=slack_fixtures["site"],
            start_mark=Decimal("-10"),
            end_mark=Decimal("20"),
            length_unit="m",
        )
        with pytest.raises(ValidationError, match="start_mark"):
            sl.clean()

    def test_clean_negative_end_mark(self, slack_fixtures):
        sl = SlackLoop(
            fiber_cable=slack_fixtures["fc"],
            site=slack_fixtures["site"],
            start_mark=Decimal("10"),
            end_mark=Decimal("-5"),
            length_unit="m",
        )
        with pytest.raises(ValidationError, match="end_mark"):
            sl.clean()

    def test_save_swaps_marks(self, slack_fixtures):
        sl = SlackLoop(
            fiber_cable=slack_fixtures["fc"],
            site=slack_fixtures["site"],
            start_mark=Decimal("50"),
            end_mark=Decimal("10"),
            length_unit="m",
        )
        sl.save()
        assert sl.start_mark == Decimal("10")
        assert sl.end_mark == Decimal("50")

    def test_loop_length_property(self, slack_fixtures):
        sl = SlackLoop.objects.create(
            fiber_cable=slack_fixtures["fc"],
            site=slack_fixtures["site"],
            start_mark=Decimal("10"),
            end_mark=Decimal("30"),
            length_unit="m",
        )
        assert sl.loop_length == Decimal("20")

    def test_str_and_url(self, slack_fixtures):
        sl = SlackLoop.objects.create(
            fiber_cable=slack_fixtures["fc"],
            site=slack_fixtures["site"],
            start_mark=Decimal("10"),
            end_mark=Decimal("30"),
            length_unit="m",
        )
        assert "10" in str(sl)
        assert str(sl.pk) in sl.get_absolute_url()


# ---------------------------------------------------------------------------
# FiberCircuitPath.clean()
# ---------------------------------------------------------------------------


class TestFiberCircuitPathClean:
    @pytest.fixture
    def circuit_fixtures(self, base_fixtures):
        fp = make_front_port(base_fixtures["device"], "FP-Origin")
        circuit = FiberCircuit.objects.create(
            name="Clean-Circuit", strand_count=2, status=FiberCircuitStatusChoices.ACTIVE
        )
        return {**base_fixtures, "fp": fp, "circuit": circuit}

    def test_loss_without_wavelength_raises(self, circuit_fixtures):
        path = FiberCircuitPath(
            circuit=circuit_fixtures["circuit"],
            position=1,
            origin=circuit_fixtures["fp"],
            calculated_loss_db=Decimal("1.5"),
            wavelength_nm=None,
        )
        with pytest.raises(ValidationError, match="wavelength"):
            path.clean()

    def test_actual_loss_without_wavelength_raises(self, circuit_fixtures):
        path = FiberCircuitPath(
            circuit=circuit_fixtures["circuit"],
            position=1,
            origin=circuit_fixtures["fp"],
            actual_loss_db=Decimal("2.0"),
            wavelength_nm=None,
        )
        with pytest.raises(ValidationError, match="wavelength"):
            path.clean()

    def test_loss_with_wavelength_passes(self, circuit_fixtures):
        path = FiberCircuitPath(
            circuit=circuit_fixtures["circuit"],
            position=1,
            origin=circuit_fixtures["fp"],
            calculated_loss_db=Decimal("1.5"),
            actual_loss_db=Decimal("2.0"),
            wavelength_nm=1550,
        )
        path.clean()  # should not raise

    def test_path_count_exceeds_strand_count_raises(self, circuit_fixtures):
        circuit = circuit_fixtures["circuit"]
        fp = circuit_fixtures["fp"]
        fp2 = make_front_port(circuit_fixtures["device"], "FP-P2")
        fp3 = make_front_port(circuit_fixtures["device"], "FP-P3")

        # Create paths up to strand_count (2)
        FiberCircuitPath.objects.create(circuit=circuit, position=1, origin=fp)
        FiberCircuitPath.objects.create(circuit=circuit, position=2, origin=fp2)

        # Third path should fail
        path = FiberCircuitPath(circuit=circuit, position=3, origin=fp3)
        with pytest.raises(ValidationError, match="strand count"):
            path.clean()

    def test_str(self, circuit_fixtures):
        path = FiberCircuitPath(
            circuit=circuit_fixtures["circuit"],
            position=1,
            origin=circuit_fixtures["fp"],
        )
        assert "path 1" in str(path)
        assert "incomplete" in str(path)

    def test_str_with_destination(self, circuit_fixtures):
        fp2 = make_front_port(circuit_fixtures["device"], "FP-Dest")
        path = FiberCircuitPath(
            circuit=circuit_fixtures["circuit"],
            position=1,
            origin=circuit_fixtures["fp"],
            destination=fp2,
        )
        assert "incomplete" not in str(path)


# ---------------------------------------------------------------------------
# FiberCircuit.save() — status transitions
# ---------------------------------------------------------------------------


class TestFiberCircuitStatusTransitions:
    @pytest.fixture
    def circuit_with_path(self, base_fixtures):
        device = base_fixtures["device"]
        fp = make_front_port(device, "FC-Origin")
        circuit = FiberCircuit.objects.create(
            name="Trans-Circuit", strand_count=1, status=FiberCircuitStatusChoices.ACTIVE
        )
        path = FiberCircuitPath.objects.create(
            circuit=circuit,
            position=1,
            origin=fp,
            path=[{"type": "front_port", "id": fp.pk}],
            is_complete=False,
        )
        path.rebuild_nodes()
        return {"circuit": circuit, "path": path, "fp": fp}

    def test_decommission_deletes_nodes(self, circuit_with_path):
        circuit = circuit_with_path["circuit"]
        path = circuit_with_path["path"]
        assert path.nodes.count() > 0

        circuit.status = FiberCircuitStatusChoices.DECOMMISSIONED
        circuit.save()
        assert FiberCircuitNode.objects.filter(path=path).count() == 0

    def test_reactivation_rebuilds_nodes(self, circuit_with_path):
        circuit = circuit_with_path["circuit"]
        path = circuit_with_path["path"]

        # Decommission first
        circuit.status = FiberCircuitStatusChoices.DECOMMISSIONED
        circuit.save()
        assert path.nodes.count() == 0

        # Reactivate
        circuit.status = FiberCircuitStatusChoices.ACTIVE
        circuit.save()
        path.refresh_from_db()
        assert path.nodes.count() > 0


# ---------------------------------------------------------------------------
# FiberCircuitPath.rebuild_nodes()
# ---------------------------------------------------------------------------


class TestFiberCircuitPathRebuildNodes:
    def test_rebuild_with_various_node_types(self, base_fixtures):
        device = base_fixtures["device"]
        fp = make_front_port(device, "RN-FP")
        rp = RearPort.objects.create(device=device, name="RN-RP", type="lc")
        cable = Cable.objects.create()
        cable.a_terminations = []
        cable.b_terminations = []
        cable.save()

        circuit = FiberCircuit.objects.create(
            name="Rebuild-Circuit", strand_count=1, status=FiberCircuitStatusChoices.ACTIVE
        )
        path = FiberCircuitPath.objects.create(
            circuit=circuit,
            position=1,
            origin=fp,
            path=[
                {"type": "front_port", "id": fp.pk},
                {"type": "cable", "id": cable.pk},
                {"type": "rear_port", "id": rp.pk},
            ],
            is_complete=False,
        )
        path.rebuild_nodes()

        nodes = list(path.nodes.order_by("position"))
        assert len(nodes) >= 3
        assert nodes[0].front_port_id == fp.pk
        assert nodes[1].cable_id == cable.pk
        assert nodes[2].rear_port_id == rp.pk


# ---------------------------------------------------------------------------
# FiberCircuitNode.__str__
# ---------------------------------------------------------------------------


class TestFiberCircuitNodeStr:
    def test_str_with_cable(self, base_fixtures):
        device = base_fixtures["device"]
        fp = make_front_port(device, "NS-FP")
        cable = Cable.objects.create()
        cable.a_terminations = []
        cable.b_terminations = []
        cable.save()

        circuit = FiberCircuit.objects.create(
            name="NodeStr-Circuit", strand_count=1, status=FiberCircuitStatusChoices.ACTIVE
        )
        path = FiberCircuitPath.objects.create(
            circuit=circuit, position=1, origin=fp, path=[{"type": "cable", "id": cable.pk}], is_complete=False
        )
        path.rebuild_nodes()
        node = path.nodes.first()
        assert "cable" in str(node)


# ---------------------------------------------------------------------------
# SplicePlanEntry.is_inter_platter
# ---------------------------------------------------------------------------


class TestSplicePlanEntryIsInterPlatter:
    def test_is_inter_platter_true(self, base_fixtures):
        from dcim.models import Module, ModuleBay, ModuleType

        device = base_fixtures["device"]
        mt = ModuleType.objects.create(manufacturer=base_fixtures["mfr"], model="Tray-IP")
        mb1 = ModuleBay.objects.create(device=device, name="Bay1")
        mb2 = ModuleBay.objects.create(device=device, name="Bay2")
        mod1 = Module.objects.create(device=device, module_bay=mb1, module_type=mt)
        mod2 = Module.objects.create(device=device, module_bay=mb2, module_type=mt)
        fp_a = make_front_port(device, "IP-FP-A", module=mod1)
        fp_b = make_front_port(device, "IP-FP-B", module=mod2)

        plan = SplicePlan.objects.create(closure=device, name="IP-Plan")
        entry = SplicePlanEntry.objects.create(plan=plan, tray=mod1, fiber_a=fp_a, fiber_b=fp_b)
        assert entry.is_inter_platter is True

    def test_is_inter_platter_false(self, base_fixtures):
        from dcim.models import Module, ModuleBay, ModuleType

        device = base_fixtures["device"]
        mt = ModuleType.objects.create(manufacturer=base_fixtures["mfr"], model="Tray-Same")
        mb = ModuleBay.objects.create(device=device, name="Bay-Same")
        mod = Module.objects.create(device=device, module_bay=mb, module_type=mt)
        fp_a = make_front_port(device, "Same-FP-A", module=mod)
        fp_b = make_front_port(device, "Same-FP-B", module=mod)

        plan = SplicePlan.objects.create(closure=device, name="Same-Plan")
        entry = SplicePlanEntry.objects.create(plan=plan, tray=mod, fiber_a=fp_a, fiber_b=fp_b)
        assert entry.is_inter_platter is False


# ---------------------------------------------------------------------------
# SplicePlanEntry.clean()
# ---------------------------------------------------------------------------


class TestSplicePlanEntryClean:
    def test_fiber_a_wrong_device_raises(self, base_fixtures):
        from dcim.models import Module, ModuleBay, ModuleType

        device = base_fixtures["device"]
        device2 = Device.objects.create(
            name="Other-Dev", site=base_fixtures["site"], device_type=base_fixtures["dt"], role=base_fixtures["role"]
        )
        mt = ModuleType.objects.create(manufacturer=base_fixtures["mfr"], model="Tray-CE")
        mb = ModuleBay.objects.create(device=device, name="Bay-CE")
        mod = Module.objects.create(device=device, module_bay=mb, module_type=mt)

        fp_a = make_front_port(device2, "CE-FP-Wrong")  # wrong device
        fp_b = make_front_port(device, "CE-FP-B", module=mod)

        plan = SplicePlan.objects.create(closure=device, name="CE-Plan")
        entry = SplicePlanEntry(plan=plan, tray=mod, fiber_a=fp_a, fiber_b=fp_b)
        with pytest.raises(ValidationError, match="fiber_a"):
            entry.clean()
