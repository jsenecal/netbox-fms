"""Shared driver for management commands that walk FiberCables.

Both brownfield port commands (name conversion and label re-render) iterate
the same queryset with the same --cable-type / --dry-run / --limit plumbing;
this base class holds that shell once. The leading underscore keeps Django's
command discovery from treating the module as a command.
"""

from django.core.management.base import BaseCommand

from netbox_fms.models import FiberCable


class FiberCableWalkCommand(BaseCommand):
    """Iterate FiberCables and hand each to ``_process_cable(fc, dry_run)``."""

    def add_arguments(self, parser):
        parser.add_argument("--cable-type", help="Limit to one FiberCableType by pk or model name.")
        parser.add_argument("--dry-run", action="store_true", help="Report changes without writing.")
        parser.add_argument("--limit", type=int, help="Process at most N fiber cables.")

    def handle(self, *args, **options):
        cables = FiberCable.objects.select_related("cable", "fiber_cable_type").order_by("pk")
        key = options["cable_type"]
        if key:
            filters = {"fiber_cable_type_id": key} if key.isdigit() else {"fiber_cable_type__model": key}
            cables = cables.filter(**filters)

        limit = options["limit"]
        processed = 0
        for fc in cables.iterator():
            if limit and processed >= limit:
                return
            self._process_cable(fc, options["dry_run"])
            processed += 1

    def _process_cable(self, fc, dry_run):
        raise NotImplementedError
