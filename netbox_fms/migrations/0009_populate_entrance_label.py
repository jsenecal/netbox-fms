from django.db import migrations


def copy_entrance_port_name(apps, schema_editor):
    ClosureCableEntry = apps.get_model("netbox_fms", "ClosureCableEntry")
    for entry in ClosureCableEntry.objects.select_related("entrance_port").filter(entrance_port__isnull=False):
        entry.entrance_label = entry.entrance_port.name
        entry.save(update_fields=["entrance_label"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_fms", "0008_closurecableentry_entrance_label"),
    ]

    operations = [
        migrations.RunPython(copy_entrance_port_name, noop),
    ]
