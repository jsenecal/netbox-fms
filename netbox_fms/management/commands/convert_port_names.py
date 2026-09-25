"""Convert generated port names to the configured write-once scheme.

Generated names are write-once, so ports never self-convert: ports
provisioned under the old label-derived scheme keep those names, and ports
provisioned before a name template was configured keep their pk-grammar
names. This command walks every FiberCable's provisioned ports (the same
FiberCable -> strand -> FrontPort -> PortMapping walk the label re-render
uses) and applies the current scheme -- the configured name templates,
else the pk grammar ({cable.id}:F{n}, {cable.id}:T{n}/{cable.id}:R{n},
bare {cable.id}) -- in one pass to the ports FMS created
(``services.fms_owned_front_port_ids`` decides which those are).

Names are unique per device, so each cable's rename plan is checked for
collisions first and a conflicted cable is skipped whole, with a message,
rather than half-renamed. A cable whose template names fail the pre-check
gets pk-grammar names instead, and the reason is reported.
"""

from django.db import transaction

from netbox_fms.services import apply_port_names, plan_port_names

from ._fibercable_walk import FiberCableWalkCommand


class Command(FiberCableWalkCommand):
    help = (
        "Rewrite FMS-provisioned FrontPort and RearPort names from any earlier scheme to the "
        "current one: the configured name templates, else the write-once pk-based grammar "
        "({cable.id}:F{n} fronts, {cable.id}:T{n}/{cable.id}:R{n} rears). A cable whose template "
        "names would not fit or would not be unique falls back to the pk grammar, with a message. "
        "Renames stay within the EXISTING rear-port structure: rear-port grouping is not migrated, "
        "so a ribbon cable provisioned before the per-ribbon grouping keeps its tube-grouped rear "
        "ports and gets {cable.id}:T{n} names -- the per-ribbon structure applies to newly "
        "provisioned cables only. Adopted ports keep their names. A cable whose new names would "
        "collide with existing port names is reported and skipped whole."
    )

    def _process_cable(self, fc, dry_run):
        renames, problems, warnings = plan_port_names(fc)
        for warning in warnings:
            self.stderr.write(f"{fc}: {warning}")
        if problems:
            self.stderr.write(f"{fc}: skipped, generated names would collide: " + "; ".join(problems))
            return
        for port, new_name in renames:
            self.stdout.write(f"{type(port).__name__} {port.pk}: name {port.name!r} -> {new_name!r}")
        if renames and not dry_run:
            with transaction.atomic():
                apply_port_names(renames)
