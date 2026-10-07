"""Background jobs of the fiber path analysis."""

import time

from django.db import transaction
from netbox.jobs import JobRunner

from .models import PathAnalysisQueue
from .path_analysis import analyze_devices, run_reconcile, try_analysis_lock
from .path_queue import schedule_analysis


class PathReconcileJob(JobRunner):
    """Rebuild every stored fiber path from the plant; the safety net under the change queue."""

    class Meta:
        name = "Fiber path reconcile"

    def run(self, *args, **kwargs):
        with transaction.atomic():
            if not try_analysis_lock():
                self.logger.warning("Another fiber path analysis holds the lock; skipping this reconcile")
                return
            stats = run_reconcile()
        self.logger.info("Reconciled fiber paths: %s", stats.summary())


class PathAnalysisJob(JobRunner):
    """Re-analyze the fiber paths through the devices queued since the last run.

    One transaction under the analysis lock: snapshot the queue, analyze the
    distinct devices, delete exactly the snapshot rows. Rows inserted while
    it runs survive for their own scheduled run; an exception rolls
    everything back so the next run retries.
    """

    class Meta:
        name = "Fiber path analysis"

    def run(self, *args, **kwargs):
        started = time.monotonic()
        with transaction.atomic():
            if not try_analysis_lock():
                self.logger.info("Another fiber path analysis holds the lock; rescheduling one window later")
                schedule_analysis()
                return
            rows = list(PathAnalysisQueue.objects.values_list("pk", "device_id"))
            if not rows:
                self.logger.info("Queue empty; nothing to analyze")
                return
            stats = analyze_devices({device_id for _pk, device_id in rows})
            PathAnalysisQueue.objects.filter(pk__in=[pk for pk, _device_id in rows]).delete()
        self.logger.info("Analyzed %d queue rows in %.1fs: %s", len(rows), time.monotonic() - started, stats.summary())
