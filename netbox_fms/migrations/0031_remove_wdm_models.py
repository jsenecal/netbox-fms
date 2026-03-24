from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_fms", "0030_rename_splice_plan_statuses"),
    ]

    operations = [
        migrations.DeleteModel(name="WavelengthServiceNode"),
        migrations.DeleteModel(name="WavelengthServiceChannelAssignment"),
        migrations.DeleteModel(name="WavelengthServiceCircuit"),
        migrations.DeleteModel(name="WavelengthService"),
        migrations.DeleteModel(name="WavelengthChannel"),
        migrations.DeleteModel(name="WdmTrunkPort"),
        migrations.DeleteModel(name="WdmNode"),
        migrations.DeleteModel(name="WdmChannelTemplate"),
        migrations.DeleteModel(name="WdmDeviceTypeProfile"),
    ]
