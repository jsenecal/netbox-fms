"""Monkey-patches to extend NetBox's cable profile system for fiber cables.

Applied in PluginConfig.ready(). Extends:
1. CableProfileChoices - adds fiber strand counts (24-432) to the choices list
2. Cable.profile_class - adds our profile classes to the lookup dict
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
