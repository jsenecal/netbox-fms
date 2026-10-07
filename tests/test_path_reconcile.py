"""The nightly reconcile (change-queue spec section 10) repairs drift and purges stale bookkeeping."""

import threading
import uuid
from datetime import timedelta
from unittest.mock import patch

from core.models import Job
from django.core.management import CommandError
from django.db import connections
from django.test import TestCase
from django.utils import timezone

from netbox_fms import NetBoxFMSConfig
from netbox_fms.choices import PathAnalysisReasonChoices
from netbox_fms.jobs import PathReconcileJob
from netbox_fms.models import (
    FiberCableType,
    FiberCircuit,
    FiberStrand,
    FiberStrandPath,
    PathAnalysisQueue,
    RouteChangeAuthorization,
)
from netbox_fms.path_analysis import ANALYSIS_LOCK_KEY, run_reconcile, try_analysis_lock
from netbox_fms.services import create_closure_cable
from tests.conftest import call_command_capture, make_closure_pair


class TestRunReconcile(TestCase):
    @classmethod
    def setUpTestData(cls):
        pair = make_closure_pair("RC")
        cls.dev_a, cls.dev_b = pair.dev_a, pair.dev_b
        fct = FiberCableType.objects.create(
            manufacturer=pair.mfr, model="RC-2", strand_count=2, construction="tight_buffer"
        )
        cls.fc, _ = create_closure_cable(device_a=cls.dev_a, device_b=cls.dev_b, fiber_cable_type=fct)
        cls.s1, cls.s2 = list(cls.fc.fiber_strands.order_by("position"))

    def test_reconcile_stores_every_strand_once(self):
        stats = run_reconcile()
        assert stats.paths_created == 2
        assert stats.devices == 2
        assert sorted(p.hop_refs() for p in FiberStrandPath.objects.prefetch_related("hops")) == sorted(
            [[("strand", self.s1.pk)], [("strand", self.s2.pk)]]
        )

    def test_drift_from_a_signal_bypassing_update_is_repaired(self):
        run_reconcile()
        FiberStrand.objects.filter(pk=self.s1.pk).update(front_port_a=None, front_port_b=None)
        stats = run_reconcile()
        assert stats.paths_updated == 1
        assert stats.paths_created == 1
        path = FiberStrandPath.objects.get(hops__strand=self.s1)
        assert path.end_a_port_id is None
        assert path.end_b_port_id is None
        assert path.completeness == "open_open"
        assert FiberStrandPath.objects.filter(hops__cable=self.fc.cable).count() == 1

    def test_queue_rows_from_before_the_start_are_cleared_and_newer_ones_kept(self):
        old = PathAnalysisQueue.objects.create(device=self.dev_a, reason=PathAnalysisReasonChoices.CABLE_CHANGED)
        fresh = PathAnalysisQueue.objects.create(device=self.dev_a, reason=PathAnalysisReasonChoices.CABLE_CHANGED)
        PathAnalysisQueue.objects.filter(pk=fresh.pk).update(created=timezone.now() + timedelta(minutes=5))
        run_reconcile()
        assert list(PathAnalysisQueue.objects.values_list("pk", flat=True)) == [fresh.pk]
        assert not PathAnalysisQueue.objects.filter(pk=old.pk).exists()

    def test_authorizations_older_than_one_cycle_are_purged(self):
        circuit = FiberCircuit.objects.create(name="RC-C", strand_count=1)
        stale = RouteChangeAuthorization.objects.create(circuit=circuit, source=circuit)
        RouteChangeAuthorization.objects.filter(pk=stale.pk).update(created=timezone.now() - timedelta(days=2))
        fresh = RouteChangeAuthorization.objects.create(circuit=circuit, source=circuit)
        run_reconcile()
        assert list(RouteChangeAuthorization.objects.values_list("pk", flat=True)) == [fresh.pk]

    def test_devices_only_on_stored_paths_are_still_reconciled(self):
        run_reconcile()
        self.fc.delete()  # the cable keeps terminating on both closures, now without a FiberCable
        stats = run_reconcile()
        assert stats.devices == 2
        assert stats.paths_deleted == 2

    def test_command_reports_the_summary(self):
        out, _err = call_command_capture("reconcile_fiber_paths")
        assert out.startswith("Reconciled fiber paths: devices=2 paths_created=2")

    def test_default_settings(self):
        assert NetBoxFMSConfig.default_settings == {
            "path_analysis_window_seconds": 30,
            "path_reconcile_interval_minutes": 1440,
            "reroute_window_ratio": 0.2,
            "analysis_username": "netbox-fms",
        }


class TestReconcileJob(TestCase):
    def _job(self):
        return Job.objects.create(name=PathReconcileJob.name, status="running", job_id=uuid.uuid4())

    def test_job_runs_the_reconcile_under_the_lock(self):
        with patch("netbox_fms.jobs.run_reconcile") as run:
            run.return_value.summary.return_value = "ok"
            PathReconcileJob(self._job()).run()
        run.assert_called_once_with()

    def test_job_skips_when_the_lock_is_held(self):
        with (
            patch("netbox_fms.jobs.try_analysis_lock", return_value=False),
            patch("netbox_fms.jobs.run_reconcile") as run,
        ):
            PathReconcileJob(self._job()).run()
        run.assert_not_called()

    def test_command_refuses_when_the_lock_is_held(self):
        with patch("netbox_fms.management.commands.reconcile_fiber_paths.try_analysis_lock", return_value=False):
            with self.assertRaises(CommandError):
                call_command_capture("reconcile_fiber_paths")


class TestAdvisoryLock(TestCase):
    def test_lock_held_by_another_session_is_not_taken(self):
        held, release = threading.Event(), threading.Event()

        def hold():
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT pg_advisory_lock(%s)", [ANALYSIS_LOCK_KEY])
                held.set()
                release.wait(timeout=10)
                cursor.execute("SELECT pg_advisory_unlock(%s)", [ANALYSIS_LOCK_KEY])
            connections["default"].close()

        holder = threading.Thread(target=hold)
        holder.start()
        held.wait(timeout=10)
        try:
            assert try_analysis_lock() is False
        finally:
            release.set()
            holder.join(timeout=10)
        assert try_analysis_lock() is True
