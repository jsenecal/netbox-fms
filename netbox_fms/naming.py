"""Jinja2 rendering of generated names and labels.

Pure and DB-free by design: nothing here imports ``netbox_fms.models``, and
model instances are read by attribute only. That keeps the module unit-testable
without database fixtures and avoids a circular import, since
``FiberCableType.clean()`` calls :func:`validate`.
"""

from collections import namedtuple

from jinja2 import StrictUndefined, TemplateError, TemplateSyntaxError, meta
from jinja2.sandbox import SandboxedEnvironment
from netbox.plugins.utils import get_plugin_config

from .constants import COLOR_SCHEME_PALETTES

__all__ = (
    "DEFAULT_FRONT_PORT_NAME",
    "DEFAULT_REAR_PORT_NAME",
    "DEFAULT_STRAND_NAME",
    "FRONT_PORT_LABEL",
    "FRONT_PORT_NAME",
    "REAR_PORT_LABEL",
    "REAR_PORT_NAME",
    "STRAND_NAME",
    "TARGETS",
    "TRAY_TOKENS",
    "NamingError",
    "apply_rendered",
    "color_name",
    "compile_for",
    "dummy_contexts",
    "port_context",
    "render",
    "resolve_source",
    "strand_context",
    "uses_tokens",
    "uses_tray",
    "validate",
)


class NamingError(ValueError):
    """A naming template failed to compile or render."""


FRONT_PORT_NAME = "front_port_name"
REAR_PORT_NAME = "rear_port_name"
FRONT_PORT_LABEL = "front_port_label"
REAR_PORT_LABEL = "rear_port_label"
STRAND_NAME = "strand_name"

_CABLE = ("cable", "cable_id", "cable_type")
_TUBE = ("tube", "tube_name", "tube_color", "tube_color_hex")
_RIBBON = ("ribbon", "ribbon_name", "ribbon_color", "ribbon_color_hex")
_STRAND = ("strand", "strand_local", "strand_color", "strand_color_hex")
_PORT = ("device", "end", "tray", "tray_position")

_FRONT_TOKENS = frozenset(_CABLE + _TUBE + _RIBBON + _STRAND + _PORT + ("strand_name",))
_REAR_TOKENS = frozenset(_CABLE + _TUBE + _PORT)
_STRAND_TOKENS = frozenset(_CABLE + _TUBE + _RIBBON + _STRAND)

DEFAULT_FRONT_PORT_NAME = "{{ cable }}{% if tube %}:T{{ tube }}{% endif %}:F{{ strand }}"
DEFAULT_REAR_PORT_NAME = "{{ cable }}{% if tube %}:T{{ tube }}{% endif %}"
DEFAULT_STRAND_NAME = (
    "{% if ribbon_name %}{{ ribbon_name }}-{% elif tube_name %}{{ tube_name }}-{% endif %}F{{ strand_local }}"
)

TargetSpec = namedtuple("TargetSpec", "field max_length tokens default")

TARGETS = {
    FRONT_PORT_NAME: TargetSpec("front_port_name_template", 64, _FRONT_TOKENS, DEFAULT_FRONT_PORT_NAME),
    REAR_PORT_NAME: TargetSpec("rear_port_name_template", 64, _REAR_TOKENS, DEFAULT_REAR_PORT_NAME),
    FRONT_PORT_LABEL: TargetSpec("front_port_label_template", 64, _FRONT_TOKENS, ""),
    REAR_PORT_LABEL: TargetSpec("rear_port_label_template", 64, _REAR_TOKENS, ""),
    STRAND_NAME: TargetSpec("strand_name_template", 64, _STRAND_TOKENS, DEFAULT_STRAND_NAME),
}

# autoescape stays off deliberately: these render device component names, not
# HTML. Escaping would corrupt legitimate characters such as "&" in a label.
_ENV = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False)  # noqa: S701

_DUMMY_TUBED = {
    "cable": "CABLE",
    "cable_id": 1,
    "cable_type": "TYPE",
    "tube": 1,
    "tube_name": "T1",
    "tube_color": "Blue",
    "tube_color_hex": "0000ff",
    "ribbon": 1,
    "ribbon_name": "R1",
    "ribbon_color": "Blue",
    "ribbon_color_hex": "0000ff",
    "strand": 1,
    "strand_local": 1,
    "strand_name": "T1-F1",
    "strand_color": "Blue",
    "strand_color_hex": "0000ff",
    "device": "DEVICE",
    "end": "A",
    "tray": "Tray 1",
    "tray_position": 1,
}

_DUMMY_BARE = {
    **_DUMMY_TUBED,
    "tube": None,
    "tube_name": None,
    "tube_color": None,
    "tube_color_hex": None,
    "ribbon": None,
    "ribbon_name": None,
    "ribbon_color": None,
    "ribbon_color_hex": None,
    "tray": None,
    "tray_position": None,
}


def color_name(hex_value, scheme):
    """Return the palette name for a hex colour, or the hex itself if unknown."""
    if not hex_value:
        return None
    for palette_hex, name in COLOR_SCHEME_PALETTES.get(scheme, ()):
        if palette_hex == hex_value:
            return str(name)
    return hex_value


def resolve_source(target, fiber_cable_type):
    """Template source: cable-type override, else plugin config, else built-in."""
    spec = TARGETS[target]
    override = (getattr(fiber_cable_type, spec.field, "") or "").strip()
    if override:
        return override
    configured = get_plugin_config("netbox_fms", spec.field, None)
    if configured is not None:
        return configured
    return spec.default


TRAY_TOKENS = frozenset({"tray", "tray_position"})


def uses_tokens(fiber_cable_type, targets, tokens):
    """True if any of ``targets``' resolved templates references any of ``tokens``.

    Parsed statically via ``jinja2.meta`` so ``{% if tray %}`` counts, and so
    a literal "tray" appearing in surrounding text does not. Blank sources are
    skipped: a target with no configured template references nothing.
    """
    wanted = frozenset(tokens)
    for target in targets:
        source = resolve_source(target, fiber_cable_type)
        if not source.strip():
            continue
        if wanted & meta.find_undeclared_variables(_ENV.parse(source)):
            return True
    return False


def uses_tray(fiber_cable_type):
    """True if either front-port template references a tray token.

    Only the two FRONT port targets are checked: ``_tube_assignment_target_ports``
    (the tube-assignment sync path this guards) returns FrontPorts only, so
    rear-port templates are irrelevant here.
    """
    return uses_tokens(fiber_cable_type, (FRONT_PORT_NAME, FRONT_PORT_LABEL), TRAY_TOKENS)


def compile_for(fiber_cable_type):
    """Compile every target's template once. A blank source compiles to None."""
    compiled = {}
    for target in TARGETS:
        source = resolve_source(target, fiber_cable_type)
        compiled[target] = _ENV.from_string(source) if source.strip() else None
    return compiled


def render(target, compiled, context):
    """Render one target, scoped to its tokens and truncated to its max length.

    Returns ``None`` -- not ``""`` -- when the target has no configured
    template. "No template configured" and "the configured template rendered
    empty" are different states: the first must leave whatever value the field
    already holds alone, the second is a deliberate blanking. Callers writing
    to an existing object must skip the assignment on ``None``; callers
    creating a new object must coerce it to ``""``.
    """
    template = compiled.get(target)
    if template is None:
        return None
    spec = TARGETS[target]
    scoped = {key: value for key, value in context.items() if key in spec.tokens}
    try:
        return template.render(**scoped)[: spec.max_length]
    except TemplateError as exc:
        raise NamingError(f"{target}: {exc}") from exc


def apply_rendered(obj, name=None, label=None):
    """Assign rendered ``name``/``label`` onto an existing object.

    A ``None`` value means "no template configured for that target" (see
    :func:`render`) and is skipped, leaving the stored value alone. Returns
    the set of field names actually modified, which is what a caller should
    feed to ``bulk_update`` -- passing a field no render touched would write
    back stale in-memory values.
    """
    changed = set()
    if name is not None and obj.name != name:
        obj.name = name
        changed.add("name")
    if label is not None and obj.label != label:
        obj.label = label
        changed.add("label")
    return changed


def dummy_contexts(target):
    """Representative validation contexts: fully populated, then bare."""
    tokens = TARGETS[target].tokens
    return [{k: v for k, v in ctx.items() if k in tokens} for ctx in (_DUMMY_TUBED, _DUMMY_BARE)]


def validate(target, source):
    """Compile and dummy-render a template source. Raise NamingError on failure."""
    source = (source or "").strip()
    if not source:
        return None
    try:
        template = _ENV.from_string(source)
    except TemplateSyntaxError as exc:
        raise NamingError(f"Template syntax error: {exc.message}") from exc
    spec = TARGETS[target]
    for ctx in dummy_contexts(target):
        try:
            rendered = template.render(**ctx)
        except TemplateError as exc:
            raise NamingError(f"Template failed to render: {exc}") from exc
        if len(rendered) > spec.max_length:
            raise NamingError(f"Rendered value is {len(rendered)} characters; the maximum is {spec.max_length}.")
    return None


def _tube_tokens(tube, color_scheme):
    return {
        "tube": tube.position if tube else None,
        "tube_name": tube.name if tube else None,
        "tube_color": color_name(tube.color, color_scheme) if tube else None,
        "tube_color_hex": tube.color if tube else None,
    }


def _ribbon_tokens(ribbon, color_scheme):
    return {
        "ribbon": ribbon.position if ribbon else None,
        "ribbon_name": ribbon.name if ribbon else None,
        "ribbon_color": color_name(ribbon.color, color_scheme) if ribbon else None,
        "ribbon_color_hex": ribbon.color if ribbon else None,
    }


def strand_context(*, cable, cable_type, tube, ribbon, position, local, strand_color_hex, color_scheme):
    """Build the render context for STRAND_NAME."""
    ctx = {
        "cable": str(cable) if cable else "",
        "cable_id": getattr(cable, "pk", None),
        "cable_type": str(cable_type),
        "strand": position,
        "strand_local": local,
        "strand_color": color_name(strand_color_hex, color_scheme),
        "strand_color_hex": strand_color_hex,
    }
    ctx.update(_tube_tokens(tube, color_scheme))
    ctx.update(_ribbon_tokens(ribbon, color_scheme))
    return ctx


def port_context(
    *,
    cable,
    cable_type,
    device,
    end,
    color_scheme,
    tube=None,
    strand=None,
    strand_local=None,
    tray=None,
    tray_position=None,
):
    """Build the render context for the port targets.

    ``strand`` is a FiberStrand or None; its ribbon, position, name and colour
    are read from it. ``tray`` is the tray module bay name or None.
    """
    ribbon = getattr(strand, "ribbon", None)
    ctx = {
        "cable": str(cable) if cable else "",
        "cable_id": getattr(cable, "pk", None),
        "cable_type": str(cable_type),
        "device": getattr(device, "name", None) or str(device),
        "end": end,
        "tray": tray,
        "tray_position": tray_position,
        "strand": strand.position if strand else None,
        "strand_local": strand_local,
        "strand_name": strand.name if strand else None,
        "strand_color": color_name(strand.color, color_scheme) if strand else None,
        "strand_color_hex": strand.color if strand else None,
    }
    ctx.update(_tube_tokens(tube, color_scheme))
    ctx.update(_ribbon_tokens(ribbon, color_scheme))
    return ctx
