"""Shared machinery for the ``rerender_*`` management commands.

The module name is underscore-prefixed on purpose: Django's command
autodiscovery skips such modules, so this base class never shows up as a
runnable ``manage.py`` command of its own.

Subclasses supply only what actually differs between them -- which objects a
cable's re-render touches -- and inherit the walk (cable-type resolution,
``--limit`` accounting), the ``None``-protocol reporting, the collision guard
and the dry-run gate.
"""

from collections import Counter

from django.core.management.base import BaseCommand

from netbox_fms import naming
from netbox_fms.models import FiberCableType


class RerenderCommand(BaseCommand):
    """Walk FiberCableTypes and their FiberCables, re-rendering one family of names."""

    def add_arguments(self, parser):
        parser.add_argument("--cable-type", help="Limit to one FiberCableType by pk or model name.")
        parser.add_argument("--dry-run", action="store_true", help="Report changes without writing.")
        parser.add_argument("--limit", type=int, help="Process at most N fiber cables.")

    # -- subclass hooks --------------------------------------------------

    def prepare(self, options):
        """Validate subclass-specific options. Return False to abort the run."""
        return True

    def check_cable_type(self, fct):
        """Pre-flight for one cable type, run once before its first cable."""

    def process_cable(self, fc, fct, dry_run):
        """Re-render this subclass's objects for one FiberCable."""
        raise NotImplementedError

    # -- the walk --------------------------------------------------------

    def handle(self, *args, **options):
        if not self.prepare(options):
            return

        types = FiberCableType.objects.all()
        key = options["cable_type"]
        if key:
            types = types.filter(pk=key) if key.isdigit() else types.filter(model=key)

        limit = options["limit"]
        processed = 0
        for fct in types.iterator():
            checked = False
            for fc in fct.instances.select_related("cable").iterator():
                if limit and processed >= limit:
                    return
                # Deferred to the first cable so a cable type with no
                # instances never emits a pre-flight warning about work that
                # is not going to happen.
                if not checked:
                    self.check_cable_type(fct)
                    checked = True
                self.process_cable(fc, fct, options["dry_run"])
                processed += 1

    # -- shared helpers --------------------------------------------------

    def stage_rendered(self, obj, kind, *, name=None, label=None):
        """Apply rendered values to ``obj``, report the diff, return changed fields.

        A ``None`` value means "no template configured for that target" (see
        ``naming.render``): ``naming.apply_rendered`` skips it, so the stored
        value is left alone and the field never reaches ``bulk_update``. That
        is what stops a run on an install with no label template from blanking
        operator-set labels.
        """
        old_name = obj.name
        old_label = getattr(obj, "label", None)
        changed = naming.apply_rendered(obj, name=name, label=label)
        if "name" in changed:
            self.stdout.write(f"{kind} {obj.pk}: {old_name} -> {obj.name}")
        if "label" in changed:
            self.stdout.write(f"{kind} {obj.pk}: label {old_label} -> {obj.label}")
        return changed

    def check_collisions(self, proposed):
        """Report and refuse any device whose proposed names collide. True if clean.

        ``proposed`` maps a port instance to its ``(name, label)`` render; a
        ``None`` name means the stored one is kept, so that is what gets
        compared.

        Two kinds of collision are checked:

        1. Within this cable's own proposal -- two of these ports asking for
           one name.
        2. Against names already stored on the same device, excluding the
           ports this run is renaming. ``proposed`` only ever holds one
           FiberCable's ports, so without this a rename onto a name owned by a
           DIFFERENT cable's port passes the guard and dies on the database
           unique constraint partway through the walk, with earlier cables
           already committed.

        Names are grouped per (device, model), never merged across models:
        FrontPort and RearPort are separate tables, each carrying its own
        ``(device, name)`` unique constraint from
        ``ComponentModel.Meta`` (``%(app_label)s_%(class)s_unique_device_name``).
        A FrontPort and a RearPort on one device may therefore legitimately
        share a name, and merging the two groups would refuse writes that the
        database accepts.
        """
        by_key = {}
        for port, (name, _label) in proposed.items():
            key = (port.device_id, type(port).__name__)
            group = by_key.setdefault(key, {"model": type(port), "pks": [], "names": []})
            group["pks"].append(port.pk)
            group["names"].append(port.name if name is None else name)

        clean = True
        for (device_id, model_name), group in sorted(by_key.items()):
            dupes = sorted(n for n, count in Counter(group["names"]).items() if count > 1)
            if dupes:
                self.stderr.write(f"Refusing device {device_id}: {model_name} name collision on {', '.join(dupes)}")
                clean = False

            taken = sorted(
                group["model"]
                .objects.filter(device_id=device_id, name__in=set(group["names"]))
                .exclude(pk__in=group["pks"])
                .values_list("name", flat=True)
            )
            if taken:
                self.stderr.write(
                    f"Refusing device {device_id}: {model_name} name collision on {', '.join(taken)} "
                    f"-- already used by a port outside this run"
                )
                clean = False
        return clean

    def write_updates(self, model, objects, fields, dry_run):
        """Persist ``objects``, writing only the columns a render actually changed."""
        if dry_run or not objects or not fields:
            return
        model.objects.bulk_update(objects, sorted(fields), batch_size=500)
