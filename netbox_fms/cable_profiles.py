"""Custom cable profiles for fiber plant cables.

NetBox's built-in profiles cap at Single1C16P (16 positions). Fiber cables
commonly have 24, 48, 96, 144, 288, or 432 strands. These profiles extend
the cable profile system so that the trace algorithm can route at the
individual strand level through unprofiled fiber trunk cables.

Registered via monkey-patch in PluginConfig.ready().
"""

from dcim.cable_profiles import BaseCableProfile


class Single1C24PCableProfile(BaseCableProfile):
    """24-strand fiber cable (e.g., 2 tubes × 12F, or 2 × 12F ribbon)."""

    a_connectors = {1: 24}
    b_connectors = a_connectors


class Single1C48PCableProfile(BaseCableProfile):
    """48-strand fiber cable (e.g., 4 tubes × 12F)."""

    a_connectors = {1: 48}
    b_connectors = a_connectors


class Single1C72PCableProfile(BaseCableProfile):
    """72-strand fiber cable (e.g., 6 tubes × 12F)."""

    a_connectors = {1: 72}
    b_connectors = a_connectors


class Single1C96PCableProfile(BaseCableProfile):
    """96-strand fiber cable (e.g., 8 tubes × 12F)."""

    a_connectors = {1: 96}
    b_connectors = a_connectors


class Single1C144PCableProfile(BaseCableProfile):
    """144-strand fiber cable (e.g., 12 tubes × 12F, or 12 × 12F ribbon)."""

    a_connectors = {1: 144}
    b_connectors = a_connectors


class Single1C216PCableProfile(BaseCableProfile):
    """216-strand fiber cable (e.g., 18 tubes × 12F)."""

    a_connectors = {1: 216}
    b_connectors = a_connectors


class Single1C288PCableProfile(BaseCableProfile):
    """288-strand fiber cable (e.g., 24 tubes × 12F, or 12 tubes × 2 × 12F ribbon)."""

    a_connectors = {1: 288}
    b_connectors = a_connectors


class Single1C432PCableProfile(BaseCableProfile):
    """432-strand fiber cable (e.g., 18 tubes × 24F)."""

    a_connectors = {1: 432}
    b_connectors = a_connectors


# Registry of custom fiber cable profiles: choice value → (label, profile class)
FIBER_CABLE_PROFILES = {
    "single-1c24p": ("1C24P", Single1C24PCableProfile),
    "single-1c48p": ("1C48P", Single1C48PCableProfile),
    "single-1c72p": ("1C72P", Single1C72PCableProfile),
    "single-1c96p": ("1C96P", Single1C96PCableProfile),
    "single-1c144p": ("1C144P", Single1C144PCableProfile),
    "single-1c216p": ("1C216P", Single1C216PCableProfile),
    "single-1c288p": ("1C288P", Single1C288PCableProfile),
    "single-1c432p": ("1C432P", Single1C432PCableProfile),
}


def _make_trunk_profile(connectors, positions):
    """Create a trunk cable profile class dynamically."""
    conns = dict.fromkeys(range(1, connectors + 1), positions)
    return type(
        f"Trunk{connectors}C{positions}PCableProfile",
        (BaseCableProfile,),
        {"a_connectors": conns, "b_connectors": conns},
    )


_TRUNK_CONFIGS = [
    (2, 12),
    (4, 12),
    (6, 12),
    (8, 12),
    (12, 12),
    (18, 12),
    (24, 12),
    (2, 24),
    (4, 24),
    (6, 24),
    (12, 24),
]

for _c, _p in _TRUNK_CONFIGS:
    _key = f"trunk-{_c}c{_p}p"
    _label = f"{_c}C{_p}P"
    FIBER_CABLE_PROFILES[_key] = (_label, _make_trunk_profile(_c, _p))
