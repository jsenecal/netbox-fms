"""Internal path models of the #196 analysis: hop references and the one-reference rule."""

from dcim.models import Cable
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from netbox_fms.choices import PathCompletenessChoices, PathEndKindChoices
from netbox_fms.models import (
    FiberCable,
    FiberCableType,
    FiberStrandPath,
    FiberStrandPathHop,
    hops_to_json,
    refs_from_json,
)
from tests.conftest import make_infra


def make_strand_path(**overrides):
    fields = {
        "end_a_kind": PathEndKindChoices.OPEN,
        "end_b_kind": PathEndKindChoices.OPEN,
        "completeness": PathCompletenessChoices.OPEN_OPEN,
        "route_key": "",
        "computed_at": timezone.now(),
    }
    fields.update(overrides)
    return FiberStrandPath.objects.create(**fields)


def test_hops_json_round_trip_is_pure():
    refs = [("strand", 5), ("cable", 9), ("provider_circuit", 3)]
    assert hops_to_json(refs) == [
        {"type": "strand", "id": 5},
        {"type": "cable", "id": 9},
        {"type": "provider_circuit", "id": 3},
    ]
    assert refs_from_json(hops_to_json(refs)) == refs


class TestFiberStrandPathHop(TestCase):
    @classmethod
    def setUpTestData(cls):
        _site, mfr, _dt, _role = make_infra("SPM")
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="SPM-2", strand_count=2, construction="tight_buffer"
        )
        cls.cable = Cable.objects.create()
        cls.fc = FiberCable.objects.create(cable=cls.cable, fiber_cable_type=fct)
        cls.s1, cls.s2 = list(cls.fc.fiber_strands.order_by("position"))
        cls.path = make_strand_path()

    def test_hop_refs_follow_position_not_insertion_order(self):
        FiberStrandPathHop.objects.create(path=self.path, position=2, strand=self.s2)
        FiberStrandPathHop.objects.create(path=self.path, position=1, strand=self.s1)
        assert self.path.hop_refs() == [("strand", self.s1.pk), ("strand", self.s2.pk)]

    def test_hop_ref_names_the_populated_reference(self):
        hop = FiberStrandPathHop(path=self.path, position=1, cable=self.cable)
        assert hop.ref == ("cable", self.cable.pk)

    def test_a_hop_with_two_references_is_rejected(self):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            FiberStrandPathHop.objects.create(path=self.path, position=1, strand=self.s1, cable=self.cable)

    def test_a_hop_with_no_reference_is_rejected(self):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            FiberStrandPathHop.objects.create(path=self.path, position=1)

    def test_str_names_the_path_by_pk(self):
        assert str(self.path) == f"Fiber path #{self.path.pk}"
