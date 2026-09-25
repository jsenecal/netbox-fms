"""Convert legacy generated port names to the write-once pk-based scheme.

Generated names became write-once with the absolute-number grammar
({cable.id}:F{n}, {cable.id}:T{n}/{cable.id}:R{n}, bare {cable.id}), so
ports provisioned under the old label-derived scheme never self-convert.
This command walks every FiberCable's provisioned ports (the same
FiberCable -> strand -> FrontPort -> PortMapping walk the label re-render
uses) and applies the new grammar in one pass to the ports FMS created
(``services.fms_owned_front_port_ids`` decides which those are).

Names are unique per device, so each cable's rename plan is checked for
collisions first and a conflicted cable is skipped whole, with a message,
rather than half-renamed.
"""

from django.db import transaction

from netbox_fms.services import apply_port_names, plan_port_names

from ._fibercable_walk import FiberCableWalkCommand


class Command(FiberCableWalkCommand):
    help = (
        "Rewrite FMS-provisioned FrontPort and RearPort names from any legacy scheme to the "
        "write-once pk-based grammar ({cable.id}:F{n} fronts, {cable.id}:T{n}/{cable.id}:R{n} "
        "rears). Renames stay within the EXISTING rear-port structure: rear-port grouping is "
        "not migrated, so a ribbon cable provisioned before the per-ribbon grouping keeps its "
        "tube-grouped rear ports and gets {cable.id}:T{n} names -- the per-ribbon structure "
        "applies to newly provisioned cables only. Adopted ports keep their names. A cable whose "
        "new names would collide with existing port names is reported and skipped whole."
    )

    def _process_cable(self, fc, dry_run):
        renames, problems = plan_port_names(fc)
        if problems:
            self.stderr.write(f"{fc}: skipped, generated names would collide: " + "; ".join(problems))
            return
        for port, new_name in renames:
            self.stdout.write(f"{type(port).__name__} {port.pk}: name {port.name!r} -> {new_name!r}")
        if renames and not dry_run:
            with transaction.atomic():
                apply_port_names(renames)
