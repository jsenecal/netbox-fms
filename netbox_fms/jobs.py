"""Background jobs of the fiber path analysis."""

import time
import uuid
from contextlib import contextmanager

from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import QueryDict
from django.utils.datastructures import MultiValueDict
from netbox.jobs import JobRunner
from netbox.plugins import get_plugin_config
from utilities.request import NetBoxFakeRequest, apply_request_processors

from .models import PathAnalysisQueue
from .path_analysis import analyze_devices, run_reconcile, try_analysis_lock
from .path_queue import schedule_analysis


def analysis_user():
    """The inactive service user the analysis writes change-log entries as when no job user exists."""
    User = get_user_model()  # noqa: N806
    username = get_plugin_config("netbox_fms", "analysis_username")
    user, created = User.objects.get_or_create(username=username, defaults={"is_active": False})
    if created:
        user.set_unusable_password()
        user.save()
    return user


@contextmanager
def analysis_request(user=None):
    """Run the analysis as a NetBox request so its writes are change-logged and fire event rules.

    NetBox's change logging bails out when no current request is set, and a
    worker has none; the breaking of an assignment and the circuit's
    ``is_broken`` flip are exactly the changes event rules are meant to see.
    Writes are attributed to ``user`` (the job's) or to the service user.
    """
    request = NetBoxFakeRequest(
        {
            "id": uuid.uuid4(),
            "user": user or analysis_user(),
            "method": "",
            "path": "",
            "path_info": "",
            "META": {},
            "COOKIES": {},
            "GET": QueryDict(),
            "POST": QueryDict(),
            "FILES": MultiValueDict(),
        }
    )
    with apply_request_processors(request):
        yield request


class PathReconcileJob(JobRunner):
    """Rebuild every stored fiber path from the plant; the safety net under the change queue."""

    class Meta:
        name = "Fiber path reconcile"

    def run(self, *args, **kwargs):
        with analysis_request(self.job.user), transaction.atomic():
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
        with analysis_request(self.job.user), transaction.atomic():
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
