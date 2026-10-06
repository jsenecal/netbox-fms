"""Queue plant changes for path analysis, one device at a time, in batches.

Plugin code and signal receivers call ``enqueue_devices``; the rows reach
the table when the surrounding transaction commits (nothing is written for
a rolled-back one), and the first batch of a window schedules the analysis
job ``path_analysis_window_seconds`` later. Later changes inside the window
ride along with that run. Nothing is kept between transactions; if an
unrelated non-robust on_commit callback raises mid-chain, the rest of the
chain, our flush included, is skipped and the reconcile recovers those rows.
"""

from __future__ import annotations

import logging
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


class _Batch:
    """The rows of one transaction's committed enqueue calls, flushed once at its end.

    Every enqueue call registers its own on_commit callback that moves its
    rows here, so Django drops the rows of a rolled-back savepoint together
    with its callback. The newest ``_Flush`` of the batch runs after every
    row group that survived and writes them all with one bulk insert and
    one scheduling call.
    """

    def __init__(self):
        self.committed = []
        self.last_token = 0

    def commit(self, rows):
        self.committed.extend(rows)

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


class _Flush:
    """An on_commit entry that flushes its batch when it is the batch's newest one."""

    def __init__(self, batch):
        batch.last_token += 1
        self.batch = batch
        self.token = batch.last_token

    def __call__(self):
        if self.token == self.batch.last_token:
            self.batch.flush()


def _live_batch(connection):
    """The batch of the transaction in progress, or a new one.

    Found through its flush entry in the connection's live callback list, so
    no state outlives a transaction: a rolled-back one drops its batch with
    its callbacks, and a transaction opened by an on_commit hook (Django has
    emptied the list by then) gets a batch of its own.
    """
    for _sids, callback, _robust in connection.run_on_commit:
        if isinstance(callback, _Flush):
            return callback.batch
    return _Batch()


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
    batch = _live_batch(connection)
    transaction.on_commit(partial(batch.commit, rows), using=connection.alias)
    if connection.in_atomic_block:
        # No savepoint ids: a rolled-back savepoint must not drop the flush of
        # the groups that survive it. A newer entry supersedes the older ones.
        connection.run_on_commit.append(((), _Flush(batch), False))
    else:
        batch.flush()


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
