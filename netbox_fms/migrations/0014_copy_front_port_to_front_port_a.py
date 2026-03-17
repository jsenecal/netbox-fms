from django.db import migrations, models


def copy_front_port(apps, schema_editor):
    FiberStrand = apps.get_model("netbox_fms", "FiberStrand")
    FiberStrand.objects.filter(front_port__isnull=False).update(front_port_a=models.F("front_port"))


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_fms", "0013_fiberstrand_front_port_a"),
    ]

    operations = [
        migrations.RunPython(copy_front_port, noop),
    ]
