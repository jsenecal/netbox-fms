"""Re-render FMS-provisioned FrontPort and RearPort labels from the current templates.

Brownfield companion to the always-on cable post_save re-render: ports
provisioned before the label engine existed (or before a template change)
only pick up fresh labels when their cable happens to be saved. This command
walks every FiberCable and applies the same rendering path in one pass.

Labels carry no uniqueness constraint, so unlike port names there is no
collision to guard against before writing.
"""

from django.db import transaction

from netbox_fms import naming
from netbox_fms.signals import _render_cable_port_labels, _stage_label_changes, _write_label_changes

from ._fibercable_walk import FiberCableWalkCommand


class Command(FiberCableWalkCommand):
    help = "Re-render FMS-provisioned FrontPort and RearPort labels from the current label templates."

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
