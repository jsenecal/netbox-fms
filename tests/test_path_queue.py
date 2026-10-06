"""The change queue (change-queue spec sections 2-4): device filter, batching, window scheduling."""

import uuid
from datetime import timedelta
from unittest.mock import patch

from core.choices import JobStatusChoices
from core.models import Job
from dcim.models import Device
from django.db import transaction
from django.test import TestCase
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
            self.captureOnCommitCallbacks(execute=True) as callbacks,
        ):
            changes()
        assert len(callbacks) == 1
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
