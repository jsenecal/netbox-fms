from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_fms", "0036_remove_fibercircuitnode_fibercircuitnode_exactly_one_ref_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="trayprofile",
            old_name="max_fibers",
            new_name="splice_capacity",
        ),
        migrations.AlterField(
            model_name="trayprofile",
            name="splice_capacity",
            field=models.PositiveIntegerField(
                default=24,
                help_text="Number of splice positions in this tray. Each position joins one A-side and one B-side strand.",
                verbose_name="splice capacity",
            ),
        ),
        migrations.AddField(
            model_name="trayprofile",
            name="tube_capacity",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Number of buffer tubes this tray can hold. Leave blank for no limit.",
                null=True,
                verbose_name="tube capacity",
            ),
        ),
    ]
