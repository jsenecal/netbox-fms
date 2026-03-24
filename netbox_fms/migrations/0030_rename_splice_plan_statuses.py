from django.db import migrations


def rename_statuses(apps, schema_editor):
    SplicePlan = apps.get_model("netbox_fms", "SplicePlan")
    SplicePlan.objects.filter(status="pending_review").update(status="pending_approval")
    SplicePlan.objects.filter(status="ready_to_apply").update(status="approved")
    SplicePlan.objects.filter(status="applied").update(status="archived")


def reverse_rename(apps, schema_editor):
    SplicePlan = apps.get_model("netbox_fms", "SplicePlan")
    SplicePlan.objects.filter(status="pending_approval").update(status="pending_review")
    SplicePlan.objects.filter(status="approved").update(status="ready_to_apply")
    SplicePlan.objects.filter(status="archived").update(status="applied")


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_fms", "0029_alter_spliceplan_options_spliceplan_submitted_by_and_more"),
    ]
    operations = [
        migrations.RunPython(rename_statuses, reverse_rename),
    ]
