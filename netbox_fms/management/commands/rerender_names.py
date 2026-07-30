"""Re-render generated names and labels after a naming template change."""

from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from netbox_fms import naming
from netbox_fms.models import FiberCableType
from netbox_fms.services import render_port_strings
from netbox_fms.signals import _tray_name_for, _tray_position_for

TARGET_CHOICES = ("strands", "port-names", "port-labels")


class Command(BaseCommand):
    help = "Re-render FMS generated names and labels from the current templates."

    def add_arguments(self, parser):
        parser.add_argument("--cable-type", help="Limit to one FiberCableType by pk or model name.")
        parser.add_argument(
            "--targets",
            default=",".join(TARGET_CHOICES),
            help=f"Comma-separated subset of: {', '.join(TARGET_CHOICES)}",
        )
        parser.add_argument("--dry-run", action="store_true", help="Report changes without writing.")
        parser.add_argument("--limit", type=int, help="Process at most N fiber cables.")

    def handle(self, *args, **options):
        targets = {t.strip() for t in options["targets"].split(",") if t.strip()}
        unknown = targets - set(TARGET_CHOICES)
        if unknown:
            self.stderr.write(f"Unknown target(s): {', '.join(sorted(unknown))}")
            return

        types = FiberCableType.objects.all()
        if options["cable_type"]:
            key = options["cable_type"]
            types = types.filter(pk=key) if key.isdigit() else types.filter(model=key)

        processed = 0
        for fct in types.iterator():
            for fc in fct.instances.select_related("cable").iterator():
                if options["limit"] and processed >= options["limit"]:
                    return
                self._process_cable(fc, fct, targets, options["dry_run"])
                processed += 1

    def _process_cable(self, fc, fct, targets, dry_run):
        # Strands first: a port template may reference {{ strand_name }}.
        if "strands" in targets:
            self._rerender_strands(fc, fct, dry_run)
        if targets & {"port-names", "port-labels"}:
            self._rerender_ports(fc, fct, targets, dry_run)

    def _rerender_strands(self, fc, fct, dry_run):
        from netbox_fms.models import FiberStrand

        pending = []
        local_counter = Counter()
        for strand in fc.fiber_strands.select_related("buffer_tube", "ribbon").order_by("position"):
            parent = strand.ribbon_id or strand.buffer_tube_id or 0
            local_counter[parent] += 1
            try:
                new_name = fct.resolve_strand_name(
                    **naming.strand_context(
                        cable=fc.cable,
                        cable_type=fct,
                        tube=strand.buffer_tube,
                        ribbon=strand.ribbon,
                        position=strand.position,
                        local=local_counter[parent],
                        strand_color_hex=strand.color,
                        color_scheme=fct.color_scheme,
                    )
                )
            except naming.NamingError as exc:
                self.stderr.write(f"{fc}: strand template failed: {exc}")
                return
            old_name = strand.name
            if naming.apply_rendered(strand, name=new_name):
                self.stdout.write(f"strand {strand.pk}: {old_name} -> {strand.name}")
                pending.append(strand)
        if pending and not dry_run:
            FiberStrand.objects.bulk_update(pending, ["name"], batch_size=500)

    def _rerender_ports(self, fc, fct, targets, dry_run):
        from dcim.models import FrontPort

        proposed = {}
        for strand in fc.fiber_strands.select_related("buffer_tube", "ribbon").all():
            for port in (strand.front_port_a, strand.front_port_b):
                if port is None:
                    continue
                try:
                    name, label = render_port_strings(
                        port,
                        strand,
                        strand.buffer_tube,
                        _tray_name_for(port),
                        _tray_position_for(port),
                    )
                except naming.NamingError as exc:
                    self.stderr.write(f"{fc}: port template failed: {exc}")
                    return
                # None means "leave this target alone": either it is not in
                # --targets, or the cable type configures no template for it.
                proposed[port] = (
                    name if "port-names" in targets else None,
                    label if "port-labels" in targets else None,
                )

        by_device = {}
        for port, (name, _label) in proposed.items():
            by_device.setdefault(port.device_id, []).append(port.name if name is None else name)
        for device_id, names in by_device.items():
            dupes = [n for n, count in Counter(names).items() if count > 1]
            if dupes:
                self.stderr.write(f"Refusing device {device_id}: name collision on {', '.join(sorted(dupes))}")
                return

        pending = []
        fields = set()
        for port, (name, label) in proposed.items():
            old_name, old_label = port.name, port.label
            changed = naming.apply_rendered(port, name=name, label=label)
            if not changed:
                continue
            if "name" in changed:
                self.stdout.write(f"port {port.pk}: {old_name} -> {port.name}")
            if "label" in changed:
                self.stdout.write(f"port {port.pk}: label {old_label} -> {port.label}")
            fields |= changed
            pending.append(port)
        if pending and not dry_run:
            # Only the columns a render actually changed: a run with no label
            # template configured must not write the label column at all.
            with transaction.atomic():
                FrontPort.objects.bulk_update(pending, sorted(fields), batch_size=500)
