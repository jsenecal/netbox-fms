"""Signal handlers for splice plan diff cache invalidation."""

from django.db.models.signals import post_save, pre_delete


def _invalidate_plans_for_cable(cable):
    """If this cable terminates on FrontPorts of a closure with a SplicePlan, mark diff stale."""
    from dcim.models import CableTermination, FrontPort
    from django.contrib.contenttypes.models import ContentType

    from .models import SplicePlan

    fp_ct = ContentType.objects.get_for_model(FrontPort)

    device_ids = set(
        FrontPort.objects.filter(
            pk__in=CableTermination.objects.filter(
                cable=cable,
                termination_type=fp_ct,
            ).values("termination_id"),
            module__isnull=False,
        ).values_list("device_id", flat=True)
    )

    if device_ids:
        SplicePlan.objects.filter(
            closure_id__in=device_ids,
            diff_stale=False,
        ).update(diff_stale=True)


def _cable_post_save(sender, instance, **kwargs):
    """Invalidate splice plan diff cache when a cable is saved."""
    _invalidate_plans_for_cable(instance)


def _cable_pre_delete(sender, instance, **kwargs):
    """Invalidate splice plan diff cache before a cable is deleted."""
    _invalidate_plans_for_cable(instance)


def _device_post_save(sender, instance, created, **kwargs):
    """Auto-create WdmNode when a Device is created from a DeviceType with a WDM profile."""
    if not created:
        return

    from .models import WdmDeviceTypeProfile, WdmNode

    try:
        profile = WdmDeviceTypeProfile.objects.get(device_type=instance.device_type)
    except WdmDeviceTypeProfile.DoesNotExist:
        return

    WdmNode.objects.create(
        device=instance,
        node_type=profile.node_type,
        grid=profile.grid,
    )


def connect_signals():
    """Connect cable and device signals. Called from AppConfig.ready()."""
    from dcim.models import Cable, Device

    post_save.connect(_cable_post_save, sender=Cable, dispatch_uid="fms_cable_post_save")
    pre_delete.connect(_cable_pre_delete, sender=Cable, dispatch_uid="fms_cable_pre_delete")
    post_save.connect(_device_post_save, sender=Device, dispatch_uid="fms_device_post_save")
