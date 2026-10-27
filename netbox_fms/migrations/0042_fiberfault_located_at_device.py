import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dcim', '0226_modulebay_rebuild_tree'),
        ('netbox_fms', '0041_fiberfault_location'),
    ]

    operations = [
        migrations.AddField(
            model_name='fiberfault',
            name='located_at_device',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='dcim.device'),
        ),
        # Closure links carry over to the device foreign key, as long as the device still exists. A fault
        # located at a pathway has no stored distance to fall back on, so its location is reset; its jacket
        # mark or OTDR evidence stays and can be re-estimated. Django's foreign keys are DEFERRABLE INITIALLY
        # DEFERRED, so these updates would queue trigger events that make the ALTER TABLEs below fail on any
        # database holding rows; checking them immediately leaves nothing pending.
        migrations.RunSQL(
            [
                "SET CONSTRAINTS ALL IMMEDIATE",
                "UPDATE netbox_fms_fiberfault AS fault SET located_at_device_id = fault.located_at_id"
                " FROM django_content_type AS ct, dcim_device AS device"
                " WHERE ct.id = fault.located_at_type_id AND ct.app_label = 'dcim' AND ct.model = 'device'"
                " AND device.id = fault.located_at_id",
                "UPDATE netbox_fms_fiberfault SET located_at_status = 'none'"
                " WHERE located_at_device_id IS NULL AND located_at_status <> 'none'",
                "SET CONSTRAINTS ALL DEFERRED",
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RemoveField(
            model_name='fiberfault',
            name='located_at_type',
        ),
        migrations.RemoveField(
            model_name='fiberfault',
            name='located_at_id',
        ),
        migrations.RenameField(
            model_name='fiberfault',
            old_name='located_at_device',
            new_name='located_at',
        ),
        migrations.AlterField(
            model_name='fiberfault',
            name='located_at',
            field=models.ForeignKey(blank=True, help_text='Closure the fault sits at, such as a broken splice.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='located_faults', to='dcim.device'),
        ),
        migrations.AddField(
            model_name='fiberfault',
            name='distance_from_a',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Where the fault lies along the cable, in meters from its A end.', max_digits=10, null=True, validators=[django.core.validators.MinValueValidator(0)]),
        ),
    ]
