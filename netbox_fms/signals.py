"""Signal handlers for splice plan diff cache invalidation."""

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver


def _invalidate_plans_for_cable(cable):
    """If this cable terminates on FrontPorts of a closure with a SplicePlan, mark diff stale."""
    from dcim.models import CableTermination, FrontPort
    from django.contrib.contenttypes.models import ContentType

    from .models import SplicePlan

    fp_ct = ContentType.objects.get_for_model(FrontPort)

    fp_ids = list(
        CableTermination.objects.filter(
            cable=cable,
            termination_type=fp_ct,
        ).values_list("termination_id", flat=True)
    )

    if not fp_ids:
        return

    device_ids = set(
        FrontPort.objects.filter(
            pk__in=fp_ids,
            module__isnull=False,
        ).values_list("device_id", flat=True)
    )

    if not device_ids:
        return

    SplicePlan.objects.filter(
        closure_id__in=device_ids,
        diff_stale=False,
    ).update(diff_stale=True)


def connect_signals():
    """Connect cable signals. Called from AppConfig.ready()."""
    from dcim.models import Cable

    @receiver(post_save, sender=Cable)
    def cable_post_save(sender, instance, **kwargs):
        _invalidate_plans_for_cable(instance)

    # Use pre_delete (not post_delete) so cable terminations still exist
    # for the device lookup. After delete, terminations are cascade-deleted.
    @receiver(pre_delete, sender=Cable)
    def cable_pre_delete(sender, instance, **kwargs):
        _invalidate_plans_for_cable(instance)
