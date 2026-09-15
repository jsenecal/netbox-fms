"""Re-render FMS-provisioned FrontPort and RearPort labels from the current templates.

Brownfield companion to the always-on cable post_save re-render: ports
provisioned before the label engine existed (or before a template change)
only pick up fresh labels when their cable happens to be saved. This command
walks every FiberCable and applies the same rendering path in one pass.

Labels carry no uniqueness constraint, so unlike port names there is no
collision to guard against before writing.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from netbox_fms import naming
from netbox_fms.models import FiberCable
from netbox_fms.signals import _render_cable_port_labels, _stage_label_changes, _write_label_changes


class Command(BaseCommand):
    help = "Re-render FMS-provisioned FrontPort and RearPort labels from the current label templates."

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
        try:
            staged = _stage_label_changes(_render_cable_port_labels(fc))
        except naming.NamingError as exc:
            self.stderr.write(f"{fc}: label template failed: {exc}")
            return
        for port, old_label in staged:
            self.stdout.write(f"{type(port).__name__} {port.pk}: label {old_label!r} -> {port.label!r}")
        if staged and not dry_run:
            with transaction.atomic():
                _write_label_changes(staged)
