"""Port name grammar and Jinja2 rendering of generated port labels.

Pure by design: nothing here imports ``netbox_fms.models``, and model
instances are read by attribute only. That keeps the module unit-testable
without database fixtures and free of circular imports.

Generated port NAMES are machine-facing, write-once identifiers built from
the dcim.Cable primary key and the strand's absolute cable-wide fiber
number (ArcFM FiberNumber / OSP convention: identity is cable + absolute
number). The pk is immutable, so a name never has to change after
provisioning. The grammar lives only here -- :func:`front_port_name` and
:func:`rear_port_name` -- and every producer of generated names must call
these helpers.

Port LABELS are the display layer: names carry no readable identity, so the
label does (cable display label, tube, ribbon, strand color, absolute fiber
number). The built-in defaults are therefore deliberately non-blank.
Operators customize them plugin-wide through ``PLUGINS_CONFIG['netbox_fms']``;
setting a template to the empty string opts that target out of label
management entirely.
"""

from collections import namedtuple

from jinja2 import StrictUndefined, TemplateError, TemplateSyntaxError
from jinja2.sandbox import SandboxedEnvironment
from netbox.plugins.utils import get_plugin_config

from .constants import COLOR_SCHEME_PALETTES

__all__ = (
    "DEFAULT_FRONT_PORT_LABEL",
    "DEFAULT_REAR_PORT_LABEL",
    "FRONT_PORT_LABEL",
    "REAR_PORT_LABEL",
    "TARGETS",
    "NamingError",
    "labels_use_tray",
    "color_name",
    "compile_labels",
    "dummy_contexts",
    "front_port_name",
    "port_context",
    "rear_port_name",
    "render",
    "resolve_source",
    "validate",
    "validate_plugin_config",
)


class NamingError(ValueError):
    """A label template failed to compile or render."""


def front_port_name(cable_id, position):
    """Write-once FrontPort name: cable pk plus absolute fiber number.

    ``position`` is ``FiberStrand.position``, the absolute cable-wide
    number -- never a per-container renumbering. The ``F`` prefix keeps
    the scheme uniform with the ``T``/``R`` rear-port containers and
    disambiguates the fiber number from the pk.
    """
    return f"{cable_id}:F{position}"


def rear_port_name(cable_id, tube=None, ribbon=None):
    """Write-once RearPort name for a cable's container.

    ``tube`` and ``ribbon`` are cable-wide container numbers (ints), not
    model instances. A ribbon wins over its enclosing tube because the
    ribbon is the mass-fusion splice unit the rear port represents; a
    containerless (tight-buffer) cable gets the bare pk.
    """
    if ribbon is not None:
        return f"{cable_id}:R{ribbon}"
    if tube is not None:
        return f"{cable_id}:T{tube}"
    return str(cable_id)


FRONT_PORT_LABEL = "front_port_label"
REAR_PORT_LABEL = "rear_port_label"

_CABLE = ("cable", "cable_id", "cable_type")
_TUBE = ("tube", "tube_name", "tube_color", "tube_color_hex")
_RIBBON = ("ribbon", "ribbon_name", "ribbon_color", "ribbon_color_hex")
_STRAND = ("strand", "strand_color", "strand_color_hex")
_PORT = ("device", "end")
# Front-only: tube assignments move FRONT ports onto trays; rear ports stay
# at device level, so a rear template has no tray to reference.
_TRAY = ("tray", "tray_position")
_TRAY_TOKENS = frozenset(_TRAY)

_FRONT_TOKENS = frozenset(_CABLE + _TUBE + _RIBBON + _STRAND + _PORT + _TRAY)
_REAR_TOKENS = frozenset(_CABLE + _TUBE + _RIBBON + _PORT)

# Non-blank on purpose: with pk-based port names on the roadmap, the label is
# the only human-readable identity a port carries. Every optional token is
# guarded so absent containers vanish instead of rendering the literal "None".
# ``strand`` is FiberStrand.position, the absolute cable-wide fiber number.
DEFAULT_FRONT_PORT_LABEL = (
    "{{ cable }}"
    "{% if tube_name %} / {{ tube_name }}{% if tube_color %} ({{ tube_color }}){% endif %}{% endif %}"
    "{% if ribbon_name %} / {{ ribbon_name }}{% endif %}"
    "{% if strand_color %} / {{ strand_color }}{% endif %}"
    " / F{{ strand }}"
)
DEFAULT_REAR_PORT_LABEL = (
    "{{ cable }}"
    "{% if tube_name %} / {{ tube_name }}{% if tube_color %} ({{ tube_color }}){% endif %}{% endif %}"
    "{% if ribbon_name %} / {{ ribbon_name }}{% endif %}"
)

TargetSpec = namedtuple("TargetSpec", "setting max_length tokens default")

# max_length matches dcim's FrontPort.label / RearPort.label columns (64).
TARGETS = {
    FRONT_PORT_LABEL: TargetSpec("front_port_label_template", 64, _FRONT_TOKENS, DEFAULT_FRONT_PORT_LABEL),
    REAR_PORT_LABEL: TargetSpec("rear_port_label_template", 64, _REAR_TOKENS, DEFAULT_REAR_PORT_LABEL),
}

# autoescape stays off deliberately: these render device component labels,
# not HTML. Escaping would corrupt legitimate characters such as "&".
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
    "strand_color": None,
    "strand_color_hex": None,
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


def labels_use_tray():
    """True when any effective label template references a tray token.

    Gates the tube-assignment-driven re-render: with tray-free templates
    (the defaults included) an assignment change cannot alter any label,
    so the re-render is skipped entirely.
    """
    from jinja2 import meta

    for target in TARGETS:
        source = resolve_source(target)
        if not source.strip():
            continue
        try:
            ast = _ENV.parse(source)
        except TemplateSyntaxError:
            continue
        if meta.find_undeclared_variables(ast) & _TRAY_TOKENS:
            return True
    return False


def resolve_source(target):
    """Template source: the ``PLUGINS_CONFIG['netbox_fms']`` key, else built-in."""
    spec = TARGETS[target]
    configured = get_plugin_config("netbox_fms", spec.setting, None)
    if configured is not None:
        return configured
    return spec.default


def _syntax_guard(target, func, source):
    """Run a Jinja parse/compile, re-raising a syntax error as :class:`NamingError`.

    A template supplied through ``PLUGINS_CONFIG`` never passes through a form
    or serializer, so a malformed one reaches the renderer intact. A raw
    ``TemplateSyntaxError`` is not a ``NamingError``, so the callers' guards
    would miss it and every FMS cable save and provisioning call would raise.
    Normalising it here is what lets those guards degrade to "leave the
    labels alone" instead.
    """
    try:
        return func(source)
    except TemplateSyntaxError as exc:
        raise NamingError(f"{target}: template syntax error: {exc.message}") from exc


def compile_labels():
    """Compile every label target's template once. A blank source compiles to None.

    Raises :class:`NamingError` -- never a raw ``TemplateSyntaxError`` -- so a
    malformed ``PLUGINS_CONFIG`` template is caught by the callers' existing
    ``except NamingError`` guards. See :func:`_syntax_guard`.
    """
    compiled = {}
    for target in TARGETS:
        source = resolve_source(target)
        compiled[target] = _syntax_guard(target, _ENV.from_string, source) if source.strip() else None
    return compiled


def validate_plugin_config():
    """Validate every label template set in ``PLUGINS_CONFIG``.

    Returns a list of ``(setting_key, message)`` pairs, empty when the config
    is clean. Never raises: a bad plugin setting must be reported, not turned
    into a failure to boot NetBox.
    """
    problems = []
    for target, spec in TARGETS.items():
        source = get_plugin_config("netbox_fms", spec.setting, None)
        if source is None:
            continue
        try:
            validate(target, source)
        except NamingError as exc:
            problems.append((spec.setting, str(exc)))
    return problems


def render(target, compiled, context):
    """Render one target, scoped to its tokens and truncated to its max length.

    Returns ``None`` -- not ``""`` -- when the target has no configured
    template (an operator opted out with an empty setting). "No template
    configured" and "the configured template rendered empty" are different
    states: the first must leave whatever value the field already holds
    alone, the second is a deliberate blanking. Callers writing to an
    existing object must skip the assignment on ``None``; callers creating a
    new object must coerce it to ``""``.
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


def dummy_contexts(target):
    """Representative validation contexts: fully populated, then bare."""
    tokens = TARGETS[target].tokens
    return [{k: v for k, v in ctx.items() if k in tokens} for ctx in (_DUMMY_TUBED, _DUMMY_BARE)]


def validate(target, source):
    """Compile and dummy-render a template source. Raise NamingError on failure."""
    source = (source or "").strip()
    if not source:
        return None
    template = _syntax_guard(target, _ENV.from_string, source)
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


def port_context(
    *, cable, cable_type, device, end, color_scheme, tube=None, strand=None, ribbon=None, tray_assignment=None
):
    """Build the render context for the label targets.

    ``strand`` is a FiberStrand or None (a RearPort covers a whole container
    and has no single strand); its position and colour are read from it.
    ``tube`` and ``ribbon`` are the strand's containers, passed separately
    because the rear-port callers have a container but no strand; a front
    port's ribbon falls back to the strand's own. ``tray_assignment`` is the
    TubeAssignment placing the strand's tube on this closure, when one
    exists -- it feeds the front-only tray tokens.
    """
    if ribbon is None:
        ribbon = getattr(strand, "ribbon", None)
    ctx = {
        "tray": str(tray_assignment.tray) if tray_assignment else None,
        "tray_position": tray_assignment.position if tray_assignment else None,
        "cable": str(cable) if cable else "",
        "cable_id": getattr(cable, "pk", None),
        "cable_type": str(cable_type),
        "device": getattr(device, "name", None) or str(device),
        "end": end,
        "strand": strand.position if strand else None,
        "strand_color": color_name(strand.color, color_scheme) if strand else None,
        "strand_color_hex": strand.color if strand else None,
    }
    ctx.update(_tube_tokens(tube, color_scheme))
    ctx.update(_ribbon_tokens(ribbon, color_scheme))
    return ctx
