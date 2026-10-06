"""Queue plant changes for path analysis, one device at a time, in batches.

Plugin code and signal receivers call ``enqueue_devices``; the rows reach
the table when the surrounding transaction commits (nothing is written for
a rolled-back one), and the first batch of a window schedules the analysis
job ``path_analysis_window_seconds`` later. Later changes inside the window
ride along with that run.
"""

from __future__ import annotations

import logging
import weakref
from datetime import timedelta
from functools import partial

from core.choices import JobStatusChoices
from dcim.models import CableTermination
from django.db import transaction
from django.utils import timezone
from netbox.plugins import get_plugin_config

from .bulk import BATCH_SIZE
from .models import PathAnalysisQueue

logger = logging.getLogger(__name__)

# Per database connection (connections are thread-local, so this is too).
_states: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


class _State:
    """The rows of committed enqueue calls waiting for the final flush of their transaction.

    Every enqueue call registers its own on_commit callback that moves its
    rows here, so Django drops the rows of a rolled-back savepoint together
    with its callback. The newest ``flush_if_last`` callback runs after every
    row group that survived and writes them all with one bulk insert and
    one scheduling call.
    """

    def __init__(self):
        self.committed = []
        self.last_token = 0

    def commit(self, rows):
        self.committed.extend(rows)

    def flush_if_last(self, token):
        if token == self.last_token:
            self.flush()

    def flush(self):
        pending, self.committed = self.committed, []
        relevant = relevant_device_ids({device_id for device_id, _reason in pending})
        rows = [
            PathAnalysisQueue(device_id=device_id, reason=reason)
            for device_id, reason in pending
            if device_id in relevant
        ]
        if not rows:
            return
        PathAnalysisQueue.objects.bulk_create(rows, batch_size=BATCH_SIZE)
        try:
            schedule_analysis()
        except Exception:
            # The rows are written; the periodic reconcile recovers a missed schedule.
            logger.exception("Could not schedule the fiber path analysis job")


def _flush_last(connection, state):
    """Register a flush that runs after every callback registered up to now.

    It carries no savepoint ids, so a rolled-back savepoint cannot drop it.
    Each call supersedes the previous one: only the newest token flushes,
    which is the last callback of the transaction.
    """
    state.last_token += 1
    connection.run_on_commit.append(((), partial(state.flush_if_last, state.last_token), False))


def relevant_device_ids(device_ids):
    """Devices worth analyzing: a FiberCable-carrying cable terminates on them, or they lie on a stored path."""
    from .path_analysis import device_ids_on_paths

    ids = {device_id for device_id in device_ids if device_id is not None}
    if not ids:
        return set()
    with_fiber = set(
        CableTermination.objects.filter(_device_id__in=ids, cable__fiber_attributes__isnull=False).values_list(
            "_device_id", flat=True
        )
    )
    return with_fiber | device_ids_on_paths(ids - with_fiber)


def enqueue_devices(device_ids, reason):
    """Record a plant change on these devices for the next analysis run."""
    rows = [(device_id, reason) for device_id in sorted({d for d in device_ids if d is not None})]
    if not rows:
        return
    connection = transaction.get_connection()
    state = _states.setdefault(connection, _State())
    transaction.on_commit(partial(state.commit, rows), using=connection.alias)
    if connection.in_atomic_block:
        _flush_last(connection, state)
    else:
        state.flush()


def schedule_analysis():
    """Schedule the analysis one window out unless a run is already waiting.

    A pending or scheduled job will pick the new rows up. A running job has
    taken its snapshot, so a new one is scheduled behind it. enqueue_once is
    avoided on purpose: it re-creates a pending job whose schedule differs,
    which would push the run back on every change.
    """
    from .jobs import PathAnalysisJob

    waiting = (JobStatusChoices.STATUS_PENDING, JobStatusChoices.STATUS_SCHEDULED)
    if PathAnalysisJob.get_jobs().filter(status__in=waiting).exists():
        return None
    window = timedelta(seconds=get_plugin_config("netbox_fms", "path_analysis_window_seconds"))
    return PathAnalysisJob.enqueue(schedule_at=timezone.now() + window)
