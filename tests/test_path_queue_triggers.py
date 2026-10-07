"""Every plant-changing receiver queues the right devices with the right reason (change-queue spec section 5)."""

from unittest.mock import patch

from dcim.models import Cable, CableTermination, PortMapping, RearPort
from django.test import TestCase

from netbox_fms.choices import PathAnalysisReasonChoices as Reason
from netbox_fms.jobs import PathAnalysisJob
from netbox_fms.models import ClosureCableEntry, FiberCableType, PathAnalysisQueue
from netbox_fms.path_analysis import run_reconcile
from netbox_fms.services import create_closure_cable
from netbox_fms.signals import fms_portmapping_bypass
from tests.conftest import connect_front_ports, connect_rp_to_ct, make_closure_pair, make_provider_circuit


class TriggerCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        pair = make_closure_pair("TRG")
        cls.dev_a, cls.dev_b = pair.dev_a, pair.dev_b
        cls.dev_c = make_closure_pair("TRG2").dev_b
        cls.fct = FiberCableType.objects.create(
            manufacturer=pair.mfr, model="TRG-2", strand_count=2, construction="tight_buffer"
        )
        cls.fc_ab, _ = create_closure_cable(device_a=cls.dev_a, device_b=cls.dev_b, fiber_cable_type=cls.fct)
        cls.fc_bc, _ = create_closure_cable(device_a=cls.dev_b, device_b=cls.dev_c, fiber_cable_type=cls.fct)
        cls.s1, cls.s2 = list(cls.fc_ab.fiber_strands.order_by("position"))
        cls.t1 = cls.fc_bc.fiber_strands.order_by("position").first()
        run_reconcile()  # stored paths make a device relevant even after its last cable is deleted

    def queued(self, fn):
        """(device_id, reason) rows written by fn, with the scheduler mocked."""
        PathAnalysisQueue.objects.all().delete()
        with patch.object(PathAnalysisJob, "enqueue"), self.captureOnCommitCallbacks(execute=True):
            fn()
        return set(PathAnalysisQueue.objects.values_list("device_id", "reason"))


class TestTriggers(TriggerCase):
    def test_trunk_cable_save_queues_both_ends(self):
        rows = self.queued(lambda: self.fc_ab.cable.save())
        assert {(self.dev_a.pk, Reason.CABLE_CHANGED), (self.dev_b.pk, Reason.CABLE_CHANGED)} <= rows

    def test_splice_jumper_queues_its_closure_as_a_splice_change(self):
        rows = self.queued(lambda: connect_front_ports(self.s1.front_port_b, self.t1.front_port_a).save())
        assert (self.dev_b.pk, Reason.SPLICE_CHANGED) in rows
        assert not {d for d, _ in rows} - {self.dev_b.pk}

    def test_deleting_a_device_s_last_cable_still_queues_it(self):
        rows = self.queued(lambda: self.fc_bc.cable.delete())
        assert (self.dev_c.pk, Reason.CABLE_DELETED) in rows
        assert (self.dev_b.pk, Reason.CABLE_DELETED) in rows

    def test_circuit_termination_rows_have_no_device_and_queue_nothing(self):
        """Review focus: CableTermination._device_id is None for circuit terminations."""
        span = make_provider_circuit("TRG")
        free = RearPort.objects.create(device=self.dev_c, name="TRG-FREE", type="lc", positions=1)
        rows = self.queued(lambda: connect_rp_to_ct(free, span.term_a))
        assert (self.dev_c.pk, Reason.CABLE_CHANGED) in rows
        assert all(device_id is not None for device_id, _ in rows)

    def test_port_mapping_changes_queue_the_device(self):
        mapping = PortMapping.objects.get(front_port=self.s2.front_port_a)
        with fms_portmapping_bypass():
            rows = self.queued(mapping.save)
            assert rows == {(self.dev_a.pk, Reason.PORT_MAPPING_CHANGED)}
            rows = self.queued(mapping.delete)
        assert rows == {(self.dev_a.pk, Reason.PORT_MAPPING_CHANGED)}

    def test_fiber_cable_save_and_delete_queue_the_cable_ends(self):
        rows = self.queued(self.fc_bc.save)
        assert {(self.dev_b.pk, Reason.CABLE_CHANGED), (self.dev_c.pk, Reason.CABLE_CHANGED)} <= rows
        rows = self.queued(self.fc_bc.delete)
        assert {(self.dev_b.pk, Reason.CABLE_CHANGED), (self.dev_c.pk, Reason.CABLE_CHANGED)} <= rows

    def test_strand_save_queues_its_landing_devices(self):
        rows = self.queued(self.s1.save)
        assert rows == {(self.dev_a.pk, Reason.STRAND_CHANGED), (self.dev_b.pk, Reason.STRAND_CHANGED)}

    def test_closure_cable_entry_save_and_delete_queue_the_closure(self):
        entry = ClosureCableEntry.objects.get(closure=self.dev_b, fiber_cable=self.fc_ab)
        rows = self.queued(entry.save)
        assert rows == {(self.dev_b.pk, Reason.CLOSURE_ENTRY_CHANGED)}
        rows = self.queued(entry.delete)
        assert rows == {(self.dev_b.pk, Reason.CLOSURE_ENTRY_CHANGED)}

    def test_devices_without_fiber_are_filtered_out_of_receiver_rows(self):
        lonely = make_closure_pair("TRG3").dev_a
        plain = Cable.objects.create()
        rp = RearPort.objects.create(device=lonely, name="TRG-RP", type="lc", positions=1)
        rows = self.queued(lambda: CableTermination.objects.create(cable=plain, cable_end="A", termination=rp))
        assert rows == set()
