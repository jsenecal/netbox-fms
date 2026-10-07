"""Retrace NetBox cable paths that earlier splice-plan applies left dead-ended at a closure."""

from django.core.management.base import BaseCommand
from django.db import transaction

from netbox_fms.bulk import rebuild_paths_through, stale_cable_paths


class Command(BaseCommand):
    help = (
        "Rebuild NetBox cable paths that stop at a front port which has since been cabled -- "
        "what splice-plan apply left behind before it rebuilt paths itself."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report the stale paths without rebuilding them.")

    def handle(self, *args, dry_run=False, **options):
        paths, ports = stale_cable_paths()
        if not paths:
            self.stdout.write("No stale cable paths.")
            return
        summary = f"{len(paths)} stale cable path(s) through {len(ports)} port(s)"
        if dry_run:
            self.stdout.write(f"Would rebuild {summary}.")
            return
        with transaction.atomic():
            rebuild_paths_through(ports)
        self.stdout.write(self.style.SUCCESS(f"Rebuilt {summary}."))
