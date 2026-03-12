# Manually written migration — rework SplicePlanEntry:
# - Remove fiber_a/fiber_b (FiberStrand FKs), mode_override, cable
# - Add tray (dcim.Module FK), fiber_a/fiber_b (dcim.FrontPort FKs), notes
# - Add unique_together constraints

import django.db.models.deletion
from django.db import migrations, models


def clear_splice_entries(apps, schema_editor):
    """Clear existing SplicePlanEntry rows — FK targets and schema change incompatibly."""
    SplicePlanEntry = apps.get_model("netbox_fms", "SplicePlanEntry")
    SplicePlanEntry.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("dcim", "0226_modulebay_rebuild_tree"),
        ("netbox_fms", "0005_remove_spliceplan_mode_remove_spliceplan_tray_and_more"),
    ]

    operations = [
        # Clear rows before altering non-nullable FKs
        migrations.RunPython(clear_splice_entries, migrations.RunPython.noop),
        # Remove old fields
        migrations.RemoveField(
            model_name="spliceplanentry",
            name="mode_override",
        ),
        migrations.RemoveField(
            model_name="spliceplanentry",
            name="cable",
        ),
        migrations.RemoveField(
            model_name="spliceplanentry",
            name="fiber_a",
        ),
        migrations.RemoveField(
            model_name="spliceplanentry",
            name="fiber_b",
        ),
        # Add new fields
        migrations.AddField(
            model_name="spliceplanentry",
            name="tray",
            field=models.ForeignKey(
                help_text="Tray owning fiber_a (canonical tray for this entry).",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="splice_plan_entries",
                to="dcim.module",
                verbose_name="tray",
            ),
        ),
        migrations.AddField(
            model_name="spliceplanentry",
            name="fiber_a",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="splice_entries_a",
                to="dcim.frontport",
                verbose_name="fiber A",
            ),
        ),
        migrations.AddField(
            model_name="spliceplanentry",
            name="fiber_b",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="splice_entries_b",
                to="dcim.frontport",
                verbose_name="fiber B",
            ),
        ),
        migrations.AddField(
            model_name="spliceplanentry",
            name="notes",
            field=models.TextField(blank=True, verbose_name="notes"),
        ),
        # Add unique_together constraints
        migrations.AlterUniqueTogether(
            name="spliceplanentry",
            unique_together={
                ("plan", "fiber_a"),
                ("plan", "fiber_b"),
            },
        ),
    ]
