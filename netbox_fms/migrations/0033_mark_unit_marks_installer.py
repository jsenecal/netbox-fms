"""Migration: cable-type sheath mark unit, FiberCable marks/installer, SlackLoop length_unit cleanup.

Adds:
- ``FiberCableType.mark_unit`` -- the unit of the markings printed on the cable jacket.
- ``FiberCable.start_mark`` / ``end_mark`` -- absolute sheath-distance reference frame for the cable.
- ``FiberCable.installed_by`` -- FK to ``tenancy.Tenant``.

Removes:
- ``SlackLoop.length_unit`` -- redundant; the marking unit is a per-cable-type property.

Backfills ``FiberCableType.mark_unit`` from any pre-existing ``SlackLoop.length_unit`` values
(mode per cable type) before the column is dropped.
"""

import django.db.models.deletion
from django.db import migrations, models


def _backfill_mark_unit(apps, schema_editor):
    """Set FiberCableType.mark_unit from the modal length_unit of its slack loops."""
    from collections import Counter

    FiberCableType = apps.get_model("netbox_fms", "FiberCableType")
    SlackLoop = apps.get_model("netbox_fms", "SlackLoop")

    for fct in FiberCableType.objects.all():
        units = list(
            SlackLoop.objects.filter(
                fiber_cable__fiber_cable_type=fct,
            )
            .exclude(length_unit="")
            .values_list("length_unit", flat=True)
        )
        if not units:
            continue
        most_common, _ = Counter(units).most_common(1)[0]
        fct.mark_unit = most_common
        fct.save(update_fields=["mark_unit"])


def _noop_reverse(apps, schema_editor):
    """No reverse data step: the dropped column is reintroduced by the reverse schema migration."""


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_fms", "0032_cabletype_outer_diameter_twist"),
        ("tenancy", "0023_add_mptt_tree_indexes"),
    ]

    operations = [
        # 1. Add the new fields.
        migrations.AddField(
            model_name="fibercabletype",
            name="mark_unit",
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(
            model_name="fibercable",
            name="start_mark",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="fibercable",
            name="end_mark",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="fibercable",
            name="installed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="installed_fiber_cables",
                to="tenancy.tenant",
            ),
        ),
        # 2. Backfill mark_unit from existing SlackLoop.length_unit values.
        migrations.RunPython(_backfill_mark_unit, _noop_reverse),
        # 3. Drop the now-redundant SlackLoop.length_unit column.
        migrations.RemoveField(
            model_name="slackloop",
            name="length_unit",
        ),
    ]
