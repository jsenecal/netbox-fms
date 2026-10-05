"""Number the connectors of fiber cables linked onto pre-existing rear ports.

Linking a cable to rear ports that already existed set the cable profile
without numbering its terminations, so a cable end landing on two or more
rear ports kept every connector NULL. The fiber trace pairs connector N
with connector N across a cable and refuses to guess between several
connector-less rear ports, so paths over such cables never completed.

Each affected end is numbered in strand order -- the rear port holding the
lowest strand position gets connector 1 -- matching what linking now does.
Ends that already carry any connector are left alone. The logic is
repeated here rather than imported so the migration stays frozen.
"""

from collections import defaultdict

from django.db import migrations


def backfill_connectors(apps, schema_editor):
    alias = schema_editor.connection.alias
    CableTermination = apps.get_model("dcim", "CableTermination")
    PortMapping = apps.get_model("dcim", "PortMapping")
    RearPort = apps.get_model("dcim", "RearPort")
    FiberCable = apps.get_model("netbox_fms", "FiberCable")
    FiberStrand = apps.get_model("netbox_fms", "FiberStrand")

    # Matched by name through the join: on a fresh database the rear port
    # ContentType row may not exist yet, and then no terminations match.
    fiber_cable_by_cable = dict(FiberCable.objects.using(alias).values_list("cable_id", "pk"))
    ends = defaultdict(list)
    for term in CableTermination.objects.using(alias).filter(
        cable_id__in=fiber_cable_by_cable,
        termination_type__app_label="dcim",
        termination_type__model="rearport",
    ):
        ends[(term.cable_id, term.cable_end)].append(term)

    for (cable_id, _end), terms in ends.items():
        if len(terms) < 2 or any(t.connector is not None for t in terms):
            continue

        rear_port_ids = [t.termination_id for t in terms]
        fp_to_rp = dict(
            PortMapping.objects.using(alias)
            .filter(rear_port_id__in=rear_port_ids)
            .values_list("front_port_id", "rear_port_id")
        )
        first_strand = {}
        strands = FiberStrand.objects.using(alias).filter(fiber_cable_id=fiber_cable_by_cable[cable_id])
        for position, fp_a, fp_b in strands.values_list("position", "front_port_a_id", "front_port_b_id"):
            rp_id = fp_to_rp.get(fp_a) or fp_to_rp.get(fp_b)
            if rp_id is not None:
                first_strand[rp_id] = min(position, first_strand.get(rp_id, position))

        positions_by_rp = dict(RearPort.objects.using(alias).filter(pk__in=rear_port_ids).values_list("pk", "positions"))
        terms.sort(key=lambda t: (t.termination_id not in first_strand, first_strand.get(t.termination_id, 0)))
        for connector, term in enumerate(terms, start=1):
            positions = list(range(1, positions_by_rp[term.termination_id] + 1))
            CableTermination.objects.using(alias).filter(pk=term.pk).update(connector=connector, positions=positions)
            RearPort.objects.using(alias).filter(pk=term.termination_id).update(
                cable_connector=connector, cable_positions=positions
            )


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_fms", "0037_trayprofile_capacity"),
        ("dcim", "0226_add_mptt_tree_indexes"),
    ]

    operations = [
        migrations.RunPython(backfill_connectors, migrations.RunPython.noop),
    ]
