"""The incremental analysis job (change-queue spec section 8) and the reconcile registration (section 10)."""

import uuid
from unittest.mock import patch

from core.models import Job, ObjectChange
from dcim.models import Cable, PortMapping
from django.contrib.auth import get_user_model
from django.test import TestCase
from netbox.plugins import get_plugin_config
from netbox.registry import registry

from netbox_fms.choices import FiberCircuitStatusChoices, PathAnalysisReasonChoices
from netbox_fms.jobs import PathAnalysisJob, PathReconcileJob
from netbox_fms.models import FiberCableType, FiberCircuit, FiberStrand, FiberStrandPath, PathAnalysisQueue, PathAnomaly
from netbox_fms.path_analysis import analyze_devices, run_reconcile
from netbox_fms.services import create_closure_cable
from netbox_fms.signals import fms_portmapping_bypass
from tests.conftest import assign_strand_path, connect_front_ports, make_closure_pair, make_front_port


def snapshot_paths():
    return sorted(
        (tuple(path.hop_refs()), path.end_a_kind, path.end_b_kind, path.end_a_port_id, path.end_b_port_id)
        for path in FiberStrandPath.objects.prefetch_related("hops")
    )


class JobCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        pair = make_closure_pair("JOB")
        cls.dev_a, cls.dev_b = pair.dev_a, pair.dev_b
        cls.dev_c = make_closure_pair("JOB2").dev_b
        fct = FiberCableType.objects.create(
            manufacturer=pair.mfr, model="JOB-2", strand_count=2, construction="tight_buffer"
        )
        cls.fc_ab, _ = create_closure_cable(device_a=cls.dev_a, device_b=cls.dev_b, fiber_cable_type=fct)
        cls.fc_bc, _ = create_closure_cable(device_a=cls.dev_b, device_b=cls.dev_c, fiber_cable_type=fct)
        cls.s1 = cls.fc_ab.fiber_strands.order_by("position").first()
        cls.t1 = cls.fc_bc.fiber_strands.order_by("position").first()
        run_reconcile()
        cls.circuit = FiberCircuit.objects.create(name="JOB-C", strand_count=1, status=FiberCircuitStatusChoices.ACTIVE)
        cls.assignment = assign_strand_path(cls.circuit, FiberStrandPath.objects.get(hops__strand=cls.s1))

    @staticmethod
    def job():
        return Job.objects.create(name=PathAnalysisJob.name, status="running", job_id=uuid.uuid4())

    def queue(self, *devices):
        for device in devices:
            PathAnalysisQueue.objects.create(device=device, reason=PathAnalysisReasonChoices.SPLICE_CHANGED)


class TestAnalyzeDevices(JobCase):
    def test_a_splice_at_a_queued_device_rewrites_and_breaks_the_assignment(self):
        connect_front_ports(self.s1.front_port_b, self.t1.front_port_a)
        stats = analyze_devices({self.dev_b.pk})
        self.assignment.refresh_from_db()
        assert stats.devices == 1
        # s1's path absorbs t1's (deleted); the two other strands' paths now end 'unspliced' at the spliced device
        assert stats.paths_updated == 3 and stats.paths_deleted == 1
        assert self.assignment.is_broken is True
        assert self.assignment.strand_path.hop_refs() == [("strand", self.s1.pk), ("strand", self.t1.pk)]

    def test_an_unchanged_device_rewrites_nothing(self):
        stats = analyze_devices({self.dev_c.pk})
        assert (stats.paths_created, stats.paths_updated, stats.paths_deleted) == (0, 0, 0)

    def test_incremental_result_equals_a_full_reconcile(self):
        connect_front_ports(self.s1.front_port_b, self.t1.front_port_a)
        analyze_devices({self.dev_b.pk})
        incremental = snapshot_paths()
        run_reconcile()
        assert snapshot_paths() == incremental

    def test_a_path_outside_the_dirty_devices_that_holds_a_walked_strand_is_rewritten_too(self):
        dev_d = make_closure_pair("JOB3").dev_b
        fc_cd, _ = create_closure_cable(
            device_a=self.dev_c, device_b=dev_d, fiber_cable_type=self.fc_bc.fiber_cable_type
        )
        u1 = fc_cd.fiber_strands.order_by("position").first()
        connect_front_ports(self.s1.front_port_b, self.t1.front_port_a)
        run_reconcile()
        connect_front_ports(self.t1.front_port_b, u1.front_port_a)  # joins the stored s1+t1 path to u1 at dev_c
        stats = analyze_devices({dev_d.pk})
        assert stats.paths_deleted == 1  # u1's own path merged into the stored s1+t1 path, which does not touch dev_d
        merged = FiberStrandPath.objects.get(hops__strand=self.s1)
        assert merged.hop_refs() == [("strand", self.s1.pk), ("strand", self.t1.pk), ("strand", u1.pk)]

    def anomaly_rows(self):
        return sorted(PathAnomaly.objects.values_list("kind", "strand_id", "front_port_id"))

    def test_an_anomaly_beyond_the_analyzed_device_is_not_inserted_again(self):
        t2 = self.fc_bc.fiber_strands.order_by("position").last()
        extra = make_front_port(self.dev_c, "JOB-extra")
        connect_front_ports(self.s1.front_port_b, self.t1.front_port_a)
        Cable.objects.create(a_terminations=[self.t1.front_port_b], b_terminations=[t2.front_port_b, extra])
        run_reconcile()
        (row,) = self.anomaly_rows()
        assert row == ("too_many_connections", None, self.t1.front_port_b_id)
        analyze_devices({self.dev_a.pk})
        analyze_devices({self.dev_a.pk})
        assert self.anomaly_rows() == [row]

    def test_a_strand_anomaly_is_replaced_on_its_cable_devices_and_left_alone_elsewhere(self):
        t2 = self.fc_bc.fiber_strands.order_by("position").last()
        connect_front_ports(self.t1.front_port_a, t2.front_port_a)
        connect_front_ports(self.t1.front_port_b, t2.front_port_b)  # a loop on the B-C cable
        run_reconcile()
        before = self.anomaly_rows()
        assert before and {kind for kind, _s, _f in before} == {"loop"}
        analyze_devices({self.dev_b.pk})
        analyze_devices({self.dev_a.pk})
        assert self.anomaly_rows() == before

    def test_a_strand_landed_on_a_port_outside_the_graph_survives_both_analyses(self):
        s2 = self.fc_ab.fiber_strands.order_by("position").last()
        FiberStrand.objects.filter(pk=s2.pk).update(front_port_b=None)
        with fms_portmapping_bypass():
            PortMapping.objects.filter(front_port=s2.front_port_a).delete()
        analyze_devices({self.dev_a.pk})
        incremental = snapshot_paths()
        assert any(hops == (("strand", s2.pk),) for hops, *_rest in incremental)
        run_reconcile()
        assert snapshot_paths() == incremental


class TestJobRun(JobCase):
    def test_run_analyzes_the_queued_devices_and_clears_exactly_those_rows(self):
        self.queue(self.dev_a, self.dev_b)
        before = set(PathAnalysisQueue.objects.values_list("pk", flat=True))

        def analyze_and_insert(device_ids):
            PathAnalysisQueue.objects.create(device=self.dev_c, reason=PathAnalysisReasonChoices.CABLE_CHANGED)
            return analyze_devices(device_ids)

        with patch("netbox_fms.jobs.analyze_devices", side_effect=analyze_and_insert) as analyze:
            PathAnalysisJob(self.job()).run()
        analyze.assert_called_once_with({self.dev_a.pk, self.dev_b.pk})
        remaining = set(PathAnalysisQueue.objects.values_list("pk", flat=True))
        assert remaining.isdisjoint(before) and len(remaining) == 1

    def test_a_failed_run_deletes_no_rows(self):
        self.queue(self.dev_a)
        with patch("netbox_fms.jobs.analyze_devices", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                PathAnalysisJob(self.job()).run()
        assert PathAnalysisQueue.objects.count() == 1

    def test_a_held_lock_reschedules_instead_of_running(self):
        self.queue(self.dev_a)
        with (
            patch("netbox_fms.jobs.try_analysis_lock", return_value=False),
            patch("netbox_fms.jobs.schedule_analysis") as schedule,
            patch("netbox_fms.jobs.analyze_devices") as analyze,
        ):
            PathAnalysisJob(self.job()).run()
        schedule.assert_called_once_with()
        analyze.assert_not_called()
        assert PathAnalysisQueue.objects.count() == 1

    def test_an_empty_queue_is_a_no_op(self):
        with patch("netbox_fms.jobs.analyze_devices") as analyze:
            PathAnalysisJob(self.job()).run()
        analyze.assert_not_called()

    def circuit_flip_changes(self):
        return ObjectChange.objects.filter(changed_object_type__model="fibercircuit", changed_object_id=self.circuit.pk)

    def test_run_logs_the_circuit_flip_under_the_service_user_without_a_request(self):
        """rqworker runs the job with no request; the is_broken flip must still reach the change log (#196)."""
        connect_front_ports(self.s1.front_port_b, self.t1.front_port_a)
        self.queue(self.dev_b)
        PathAnalysisJob(self.job()).run()
        change = self.circuit_flip_changes().get()
        assert change.postchange_data["is_broken"] is True
        assert change.request_id is not None
        service = get_user_model().objects.get(username=get_plugin_config("netbox_fms", "analysis_username"))
        assert change.user == service
        assert (service.is_active, service.has_usable_password()) == (False, False)

    def test_run_attributes_changes_to_the_job_user_when_there_is_one(self):
        connect_front_ports(self.s1.front_port_b, self.t1.front_port_a)
        self.queue(self.dev_b)
        job = self.job()
        job.user = get_user_model().objects.create(username="JOB-operator")
        PathAnalysisJob(job).run()
        assert self.circuit_flip_changes().get().user == job.user
        assert (
            not get_user_model().objects.filter(username=get_plugin_config("netbox_fms", "analysis_username")).exists()
        )


def test_reconcile_is_registered_as_a_system_job_with_the_configured_interval():
    assert registry["system_jobs"][PathReconcileJob] == {
        "interval": get_plugin_config("netbox_fms", "path_reconcile_interval_minutes")
    }
