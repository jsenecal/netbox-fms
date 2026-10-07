"""Internal path models of the #196 analysis: hop references and the one-reference rule."""

import pytest
from dcim.models import Cable, Device
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.test import TestCase

from netbox_fms.choices import (
    PathAnalysisReasonChoices,
    PathAnomalyKindChoices,
)
from netbox_fms.models import (
    FiberCable,
    FiberCableType,
    FiberCircuit,
    FiberStrandPathHop,
    PathAnalysisQueue,
    PathAnomaly,
    RouteChangeAuthorization,
    hops_to_json,
    refs_from_json,
)
from tests.conftest import make_front_port, make_infra, make_strand_path


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

    def test_hop_str_names_the_reference(self):
        hop = FiberStrandPathHop(path=self.path, position=1, strand=self.s1)
        assert str(hop) == f"strand {self.s1.pk}"

    def test_hop_without_reference_has_no_ref(self):
        with pytest.raises(ValueError):
            _ = FiberStrandPathHop(path=self.path, position=1).ref

    def test_str_names_the_path_by_pk(self):
        assert str(self.path) == f"Fiber path #{self.path.pk}"


class TestPathLabels(TestCase):
    @classmethod
    def setUpTestData(cls):
        site, _mfr, dt, role = make_infra("PLB")
        cls.device = Device.objects.create(name="plb-dev", site=site, device_type=dt, role=role)
        cls.fp = make_front_port(cls.device, "PLB1")
        cls.circuit = FiberCircuit.objects.create(name="PLB-Circuit", strand_count=1)

    def test_anomaly_str_names_the_front_port(self):
        anomaly = PathAnomaly.objects.create(kind=PathAnomalyKindChoices.TOO_MANY_CONNECTIONS, front_port=self.fp)
        assert str(anomaly) == f"{anomaly.get_kind_display()} ({self.fp})"

    def test_route_change_authorization_str_names_the_circuit(self):
        auth = RouteChangeAuthorization.objects.create(
            circuit=self.circuit, source_type=ContentType.objects.get_for_model(Device), source_id=self.device.pk
        )
        assert auth.source == self.device
        assert str(auth) == f"route change authorization for {self.circuit}"

    def test_queue_entry_str_names_device_and_reason(self):
        entry = PathAnalysisQueue.objects.create(device=self.device, reason=PathAnalysisReasonChoices.CABLE_CHANGED)
        assert str(entry) == f"{self.device}: {entry.get_reason_display()}"
