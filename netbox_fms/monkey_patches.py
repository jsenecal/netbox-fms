"""Monkey-patches applied in PluginConfig.ready().

1. CableProfileChoices - adds fiber strand counts (24-432) to the choices list
2. Cable.profile_class - adds our profile classes to the lookup dict
3. DeleteMixin.delete - forwards origin to the deletion collector on NetBox 4.5
"""

from dcim.choices import CableProfileChoices
from dcim.models import Cable

from netbox_fms.cable_profiles import FIBER_CABLE_PROFILES


def patch_cable_profiles():
    """Register custom fiber cable profiles with NetBox's cable system."""

    single_choices = tuple(
        (value, label) for value, (label, _cls) in FIBER_CABLE_PROFILES.items() if value.startswith("single-")
    )
    trunk_choices = tuple(
        (value, label) for value, (label, _cls) in FIBER_CABLE_PROFILES.items() if value.startswith("trunk-")
    )

    # 1. Extend CableProfileChoices (runtime class)
    CableProfileChoices.CHOICES = (
        *CableProfileChoices.CHOICES,
        ("Fiber (Single)", single_choices),
        ("Fiber (Trunk)", trunk_choices),
    )
    CableProfileChoices._choices = list(CableProfileChoices.CHOICES)

    # 2. Extend the model field's choices (used by forms and validation)
    profile_field = Cable._meta.get_field("profile")
    profile_field.choices = list(profile_field.choices) + [
        ("Fiber (Single)", list(single_choices)),
        ("Fiber (Trunk)", list(trunk_choices)),
    ]

    # 3. Patch Cable.profile_class to include our profile classes
    _original_profile_class = Cable.profile_class.fget

    def _patched_profile_class(self):
        entry = FIBER_CABLE_PROFILES.get(self.profile)
        if entry:
            return entry[1]
        return _original_profile_class(self)

    Cable.profile_class = property(_patched_profile_class)


def patch_delete_origin():
    """Make DeleteMixin.delete() pass origin=self to its collector on NetBox 4.5.

    Django's Model.delete() has passed origin to the deletion Collector since
    Django 4.1, so pre_delete/post_delete receivers can tell which object a
    cascade started from. NetBox's DeleteMixin overrides delete() with its
    CustomCollector but only forwards origin since NetBox 4.6; on 4.5 every
    cascaded signal fires with origin=None. The FMS PortMapping guard relies
    on that origin to let closure deletions cascade through protected
    mappings, so recreate the upstream 4.6 behavior when the running NetBox
    lacks it.
    """
    import inspect

    from django.db import router
    from netbox.models import deletion

    if "origin" in inspect.getsource(deletion.DeleteMixin.delete):
        return

    def delete(self, using=None, keep_parents=False):
        using = using or router.db_for_write(self.__class__, instance=self)
        if self._get_pk_val() is None:
            raise ValueError(
                f"{self._meta.object_name} object can't be deleted because its "
                f"{self._meta.pk.attname} attribute is set to None."
            )
        collector = deletion.CustomCollector(using=using, origin=self)
        collector.collect([self], keep_parents=keep_parents)
        return collector.delete()

    delete.alters_data = True
    deletion.DeleteMixin.delete = delete
