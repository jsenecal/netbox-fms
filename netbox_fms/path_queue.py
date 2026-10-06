"""Queue plant changes for path analysis, one device at a time, in batches.

Plugin code and signal receivers call ``enqueue_devices``; the rows reach
the table when the surrounding transaction commits (nothing is written for
a rolled-back one), and the first batch of a window schedules the analysis
job ``path_analysis_window_seconds`` later. Later changes inside the window
ride along with that run.
"""

from __future__ import annotations

from datetime import timedelta

from core.choices import JobStatusChoices
from dcim.models import CableTermination
from django.db import transaction
from django.utils import timezone
from netbox.plugins import get_plugin_config

from .bulk import BATCH_SIZE
from .models import PathAnalysisQueue

# One buffer per database connection, keyed by alias; emptied by its on_commit flush.
_buffers: dict[str, _Buffer] = {}


class _Buffer:
    """The (device_id, reason) rows of one transaction, flushed once on commit."""

    def __init__(self, alias):
        self.alias = alias
        self.rows = []

    def flush(self):
        _buffers.pop(self.alias, None)
        relevant = relevant_device_ids({device_id for device_id, _reason in self.rows})
        rows = [
            PathAnalysisQueue(device_id=device_id, reason=reason)
            for device_id, reason in self.rows
            if device_id in relevant
        ]
        if not rows:
            return
        PathAnalysisQueue.objects.bulk_create(rows, batch_size=BATCH_SIZE)
        schedule_analysis()


def _is_registered(connection, callback):
    """Whether the buffer's flush still awaits this connection's commit.

    Django drops on_commit callbacks of a rolled-back transaction, which
    leaves the buffer object behind; a buffer whose flush is no longer
    registered is stale and must not collect the next transaction's rows.
    """
    return any(entry[1] == callback for entry in connection.run_on_commit)


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
    return with_fiber | device_ids_on_paths(ids)


def enqueue_devices(device_ids, reason):
    """Record a plant change on these devices for the next analysis run."""
    rows = sorted({device_id for device_id in device_ids if device_id is not None})
    if not rows:
        return
    connection = transaction.get_connection()
    buffer = _buffers.get(connection.alias)
    if buffer is not None and not _is_registered(connection, buffer.flush):
        buffer = None
    fresh = buffer is None
    if fresh:
        buffer = _buffers[connection.alias] = _Buffer(connection.alias)
    buffer.rows.extend((device_id, reason) for device_id in rows)
    if fresh:
        transaction.on_commit(buffer.flush, using=connection.alias)


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
