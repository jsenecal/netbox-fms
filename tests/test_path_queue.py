"""The change queue (change-queue spec sections 2-4): device filter, batching, window scheduling."""

import uuid
from datetime import timedelta
from unittest.mock import patch

from core.choices import JobStatusChoices
from core.models import Job
from dcim.models import Device
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from netbox_fms.choices import PathAnalysisReasonChoices
from netbox_fms.jobs import PathAnalysisJob
from netbox_fms.models import FiberCableType, PathAnalysisQueue
from netbox_fms.path_queue import enqueue_devices, relevant_device_ids, schedule_analysis
from netbox_fms.services import create_closure_cable
from tests.conftest import make_closure_pair, make_front_port, make_strand_path

CABLE = PathAnalysisReasonChoices.CABLE_CHANGED


class QueueCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        pair = make_closure_pair("PQ")
        cls.dev_a, cls.dev_b = pair.dev_a, pair.dev_b
        fct = FiberCableType.objects.create(
            manufacturer=pair.mfr, model="PQ-1", strand_count=1, construction="tight_buffer"
        )
        create_closure_cable(device_a=cls.dev_a, device_b=cls.dev_b, fiber_cable_type=fct)
        cls.bare = Device.objects.create(name="PQ-bare", site=pair.site, device_type=pair.device_type, role=pair.role)
        cls.on_path = Device.objects.create(
            name="PQ-path", site=pair.site, device_type=pair.device_type, role=pair.role
        )
        make_strand_path(end_a=make_front_port(cls.on_path, "PQ-path-F1"))

    def flushed(self, fn):
        """Run fn, firing on_commit callbacks, with the job enqueue mocked; returns the mock."""
        with patch.object(PathAnalysisJob, "enqueue") as enqueue, self.captureOnCommitCallbacks(execute=True):
            fn()
        return enqueue


class TestDeviceFilter(QueueCase):
    def test_only_devices_with_fiber_or_on_a_path_are_relevant(self):
        ids = relevant_device_ids([self.dev_a.pk, self.bare.pk, self.on_path.pk, None])
        assert ids == {self.dev_a.pk, self.on_path.pk}
        assert relevant_device_ids([]) == set()

    def test_irrelevant_devices_write_no_rows(self):
        enqueue = self.flushed(lambda: enqueue_devices([self.bare.pk], CABLE))
        assert not PathAnalysisQueue.objects.exists()
        enqueue.assert_not_called()

    def test_nothing_to_enqueue_registers_nothing(self):
        with self.captureOnCommitCallbacks() as callbacks:
            enqueue_devices([None], CABLE)
        assert callbacks == []


class TestBatching(QueueCase):
    def test_many_changes_in_one_transaction_insert_once_and_schedule_once(self):
        def changes():
            enqueue_devices([self.dev_a.pk], CABLE)
            enqueue_devices([self.dev_b.pk, self.dev_a.pk], PathAnalysisReasonChoices.SPLICE_CHANGED)
            enqueue_devices([self.on_path.pk], PathAnalysisReasonChoices.PORT_MAPPING_CHANGED)

        with (
            patch.object(PathAnalysisJob, "enqueue") as enqueue,
            CaptureQueriesContext(connection) as queries,
            self.captureOnCommitCallbacks(execute=True),
        ):
            changes()
        inserts = [q for q in queries if q["sql"].startswith('INSERT INTO "netbox_fms_pathanalysisqueue"')]
        assert len(inserts) == 1
        enqueue.assert_called_once()
        rows = sorted(PathAnalysisQueue.objects.values_list("device_id", "reason"))
        assert rows == sorted(
            [
                (self.dev_a.pk, "cable_changed"),
                (self.dev_a.pk, "splice_changed"),
                (self.dev_b.pk, "splice_changed"),
                (self.on_path.pk, "port_mapping_changed"),
            ]
        )

    def test_rolled_back_transaction_enqueues_nothing_and_leaves_no_stale_buffer(self):
        def rolled_back():
            with transaction.atomic():
                enqueue_devices([self.dev_a.pk], CABLE)
                transaction.set_rollback(True)

        self.flushed(rolled_back)
        assert not PathAnalysisQueue.objects.exists()
        self.flushed(lambda: enqueue_devices([self.dev_b.pk], CABLE))
        assert list(PathAnalysisQueue.objects.values_list("device_id", flat=True)) == [self.dev_b.pk]

    def test_a_rolled_back_savepoint_drops_only_its_own_rows(self):
        def nested():
            enqueue_devices([self.dev_a.pk], CABLE)
            with transaction.atomic():
                enqueue_devices([self.dev_b.pk], CABLE)
                transaction.set_rollback(True)

        enqueue = self.flushed(nested)
        assert list(PathAnalysisQueue.objects.values_list("device_id", flat=True)) == [self.dev_a.pk]
        enqueue.assert_called_once()

    def test_a_fully_rolled_back_savepoint_schedules_nothing(self):
        def nested():
            with transaction.atomic():
                enqueue_devices([self.dev_a.pk], CABLE)
                transaction.set_rollback(True)

        enqueue = self.flushed(nested)
        assert not PathAnalysisQueue.objects.exists()
        enqueue.assert_not_called()

    def test_a_failing_schedule_does_not_escape_the_commit(self):
        with patch.object(PathAnalysisJob, "enqueue", side_effect=ConnectionError("redis down")):
            with self.captureOnCommitCallbacks(execute=True):
                enqueue_devices([self.dev_a.pk], CABLE)
        assert PathAnalysisQueue.objects.filter(device=self.dev_a).exists()


class TestFilterShortcut(QueueCase):
    def test_path_lookup_skips_devices_that_already_have_fiber(self):
        with patch("netbox_fms.path_analysis.device_ids_on_paths", return_value=set()) as lookup:
            relevant_device_ids([self.dev_a.pk, self.on_path.pk])
        lookup.assert_called_once_with({self.on_path.pk})


class TestAutocommit(TransactionTestCase):
    def setUp(self):
        self.enterContext(patch.object(PathAnalysisJob, "enqueue"))
        self.pair = pair = make_closure_pair("PQT")
        fct = FiberCableType.objects.create(
            manufacturer=pair.mfr, model="PQT-1", strand_count=1, construction="tight_buffer"
        )
        create_closure_cable(device_a=pair.dev_a, device_b=pair.dev_b, fiber_cable_type=fct)
        PathAnalysisQueue.objects.all().delete()

    def test_a_real_commit_keeps_surviving_rows_and_drops_a_rolled_back_savepoint(self):
        pair = self.pair
        with transaction.atomic():
            enqueue_devices([pair.dev_a.pk], CABLE)
            with transaction.atomic():
                enqueue_devices([pair.dev_b.pk], CABLE)
                transaction.set_rollback(True)
        assert list(PathAnalysisQueue.objects.values_list("device_id", flat=True)) == [pair.dev_a.pk]

    def test_a_hook_that_enqueues_in_its_own_atomic_strands_no_row(self):
        """NetBox runs atomic() blocks from on_commit hooks; a nested commit must not strand later groups."""
        pair = self.pair

        def hook():
            with transaction.atomic():
                enqueue_devices([pair.dev_b.pk], CABLE)

        with transaction.atomic():
            enqueue_devices([pair.dev_a.pk], CABLE)
            transaction.on_commit(hook)
            enqueue_devices([pair.dev_a.pk], PathAnalysisReasonChoices.SPLICE_CHANGED)
        assert sorted(PathAnalysisQueue.objects.values_list("device_id", "reason")) == sorted(
            [(pair.dev_a.pk, "cable_changed"), (pair.dev_b.pk, "cable_changed"), (pair.dev_a.pk, "splice_changed")]
        )
        enqueue_devices([pair.dev_b.pk], PathAnalysisReasonChoices.SPLICE_CHANGED)
        assert PathAnalysisQueue.objects.count() == 4

    def test_outside_an_atomic_block_rows_are_written_at_once(self):
        pair = self.pair
        enqueue_devices([pair.dev_a.pk], CABLE)
        assert list(PathAnalysisQueue.objects.values_list("device_id", flat=True)) == [pair.dev_a.pk]


class TestScheduling(QueueCase):
    def test_first_change_schedules_one_window_out(self):
        before = timezone.now()
        with patch.object(PathAnalysisJob, "enqueue") as enqueue:
            schedule_analysis()
        (_args, kwargs) = enqueue.call_args
        assert timedelta(seconds=29) <= kwargs["schedule_at"] - before <= timedelta(seconds=31)

    def test_a_pending_or_scheduled_job_is_not_rescheduled(self):
        for status in (JobStatusChoices.STATUS_PENDING, JobStatusChoices.STATUS_SCHEDULED):
            Job.objects.create(name=PathAnalysisJob.name, status=status, job_id=uuid.uuid4())
            with patch.object(PathAnalysisJob, "enqueue") as enqueue:
                assert schedule_analysis() is None
            enqueue.assert_not_called()
            Job.objects.all().delete()

    def test_a_running_job_does_not_suppress_the_next_one(self):
        Job.objects.create(name=PathAnalysisJob.name, status=JobStatusChoices.STATUS_RUNNING, job_id=uuid.uuid4())
        with patch.object(PathAnalysisJob, "enqueue") as enqueue:
            schedule_analysis()
        enqueue.assert_called_once()
