"""Rebuild the stored fiber paths from the plant, synchronously."""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from netbox_fms.jobs import analysis_request
from netbox_fms.path_analysis import run_reconcile, try_analysis_lock


class Command(BaseCommand):
    help = "Analyze the whole fiber plant and rebuild the stored fiber paths (the upgrade step after installing 0039)."

    def handle(self, *args, **options):
        with analysis_request(), transaction.atomic():
            if not try_analysis_lock():
                raise CommandError("Another fiber path analysis is running; try again later.")
            stats = run_reconcile()
        self.stdout.write(f"Reconciled fiber paths: {stats.summary()}")
