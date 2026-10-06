"""Background jobs of the fiber path analysis."""

from django.db import transaction
from netbox.jobs import JobRunner

from .path_analysis import run_reconcile, try_analysis_lock


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
    """Re-analyze the fiber paths through the devices queued since the last run."""

    class Meta:
        name = "Fiber path analysis"

    def run(self, *args, **kwargs):
        raise NotImplementedError
