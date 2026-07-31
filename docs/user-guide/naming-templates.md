# Naming Templates

NetBox FMS generates the `name` and `label` of every FrontPort and RearPort it
creates, plus the `name` of every FiberStrand, from Jinja2 templates. Five
template fields on **FiberCableType** control this:

| Field | Controls |
|-------|----------|
| `front_port_name_template` | FrontPort `name` |
| `rear_port_name_template` | RearPort `name` |
| `front_port_label_template` | FrontPort `label` |
| `rear_port_label_template` | RearPort `label` |
| `strand_name_template` | FiberStrand `name` |

All five are plain `TextField`s and all five are optional -- a blank field
means "inherit", as explained below. They appear on the FiberCableType
add/edit form, in CSV import, in bulk edit, and over the REST API and
GraphQL like any other FiberCableType field.

---

## Resolution order

For each of the five targets, NetBox FMS resolves the template source in
this order:

1. **The FiberCableType field**, if it is non-blank.
2. **`PLUGINS_CONFIG['netbox_fms'][<field name>]`**, a plugin-wide default,
   if the setting is present.
3. **The built-in default** shipped with the plugin.

A blank cable-type field means "inherit from the plugin config, or from the
built-in default" -- it does not mean "render nothing". To render nothing
(for the two label fields), leave the field blank at every level; the
built-in label defaults are already the empty string, so labels stay unset
until you explicitly configure one.

Example plugin-wide override in `configuration.py`:

```python
PLUGINS_CONFIG = {
    "netbox_fms": {
        "front_port_name_template": "{{ cable }}:B{{ tube }}F{{ strand }}",
    },
}
```

This changes the default for every FiberCableType that does not set its own
`front_port_name_template`. Cable types that do set their own field are
unaffected.

---

## Token reference

Each of the five targets only sees a subset of tokens -- for example, a
RearPort covers a whole tube and has no single strand, so `strand` and
`ribbon` tokens are not available to rear-port templates. Referencing a
token that is not available to a target raises a template error at save
time (see [Validation and the 64-character limit](#validation-and-the-64-character-limit)).

| Token | Front Port Name | Front Port Label | Rear Port Name | Rear Port Label | Strand Name |
|-------|:---:|:---:|:---:|:---:|:---:|
| `cable` | yes | yes | yes | yes | yes |
| `cable_id` | yes | yes | yes | yes | yes |
| `cable_type` | yes | yes | yes | yes | yes |
| `tube` | yes | yes | yes | yes | yes |
| `tube_name` | yes | yes | yes | yes | yes |
| `tube_color` | yes | yes | yes | yes | yes |
| `tube_color_hex` | yes | yes | yes | yes | yes |
| `ribbon` | yes | yes | -- | -- | yes |
| `ribbon_name` | yes | yes | -- | -- | yes |
| `ribbon_color` | yes | yes | -- | -- | yes |
| `ribbon_color_hex` | yes | yes | -- | -- | yes |
| `strand` | yes | yes | -- | -- | yes |
| `strand_local` | yes | yes | -- | -- | yes |
| `strand_color` | yes | yes | -- | -- | yes |
| `strand_color_hex` | yes | yes | -- | -- | yes |
| `strand_name` | yes | yes | -- | -- | -- |
| `device` | yes | yes | yes | yes | -- |
| `end` | yes | yes | yes | yes | -- |
| `tray` | yes | yes | yes | yes | -- |
| `tray_position` | yes | yes | yes | yes | -- |

This table is the authoritative token/target matrix -- it is taken directly
from the `TARGETS` registry in `netbox_fms/naming.py`, not reconstructed
from the design spec.

### Token meanings

| Token | Meaning |
|-------|---------|
| `cable` | The linked `dcim.Cable`'s display string, or `""` if the FiberCable has no cable linked yet. |
| `cable_id` | The `dcim.Cable` primary key, or `None`. |
| `cable_type` | `"{manufacturer} {model}"` of the FiberCableType. |
| `tube` | The BufferTube's `position` (integer), or `None` for tubeless constructions (tight buffer, central-core ribbon). |
| `tube_name` | The BufferTube's `name`, or `None`. |
| `tube_color` | The tube color resolved to a palette name under the cable type's color scheme (falls back to the raw hex if the color is not a standard palette entry), or `None` if the tube has no color or there is no tube. |
| `tube_color_hex` | The tube's raw hex color, or `None`. |
| `ribbon` | The Ribbon's `position`, or `None` outside ribbon constructions. |
| `ribbon_name` | The Ribbon's `name`, or `None`. |
| `ribbon_color` / `ribbon_color_hex` | Same pattern as `tube_color` / `tube_color_hex`, for the Ribbon. |
| `strand` | The FiberStrand's cable-wide `position` -- see [`strand` vs `strand_local`](#strand-vs-strand_local). |
| `strand_local` | The strand's 1-based index within its immediate parent -- see [`strand` vs `strand_local`](#strand-vs-strand_local). |
| `strand_color` / `strand_color_hex` | Resolved color name / raw hex for the strand. |
| `strand_name` | The FiberStrand's already-rendered `name`, available to front-port templates only, so a port name can embed the strand's own name. |
| `device` | The port's device name. |
| `end` | `"A"` or `"B"`, or `"AB"` for a cable that loops back onto the same device. |
| `tray` | The splice tray's ModuleBay name, if the port is currently placed on a tray module; otherwise `None`. Populated only on the code paths described in [The `tray` token is opt-in](#the-tray-token-is-opt-in). |
| `tray_position` | The `TubeAssignment.position` of that tray placement, or `None`. |

**Optional tokens render as the literal text `None` if referenced
unguarded.** Jinja renders a Python `None` value as the string `"None"`, not
as empty text. Any token that can be absent (`tube`, `ribbon`, `tray`,
`tray_position`, and the tube/ribbon/strand color and name tokens) should be
wrapped in an `{% if %}` block, exactly as the built-in defaults do:

```
{{ cable }}{% if tube %}:T{{ tube }}{% endif %}:F{{ strand_local }}
```

not

```
{{ cable }}:T{{ tube }}:F{{ strand_local }}
```

which renders `NST:TNone:F7` for a tubeless cable.

---

## Built-in defaults

Quoted verbatim from `netbox_fms/naming.py`:

```
front_port_name_template  = {{ cable }}{% if tube %}:T{{ tube }}{% endif %}:F{{ strand_local }}
rear_port_name_template   = {{ cable }}{% if tube %}:T{{ tube }}{% endif %}
front_port_label_template = (empty string)
rear_port_label_template  = (empty string)
strand_name_template      = {% if ribbon_name %}{{ ribbon_name }}-{% elif tube_name %}{{ tube_name }}-{% endif %}F{{ strand_local }}
```

The two label defaults are the empty string, so **port labels stay unset
unless you configure a label template** -- see
[the label warning](#the-label-warning-setting-a-label-changes-strport-everywhere)
before you do.

---

## Upgrade behavior

The defaults are chosen to leave the names already stored in your database
alone, so that physical splice labels keep matching NetBox after the
upgrade. Concretely:

- **Front port names** were, before naming templates, last written by the
  cable `post_save` handler, which numbered a front port by its **tube-local**
  index (`PortMapping.rear_port_position`) -- `NST:T2:F1`, not `NST:T2:F4`.
  `DEFAULT_FRONT_PORT_NAME` therefore uses `strand_local`, not `strand`. On a
  tubeless cable the two indices are identical, so tubeless names are
  unaffected either way.
- **Rear port names** were `str(cable)`, plus `:T<tube position>` on a tubed
  cable. That is exactly what `DEFAULT_REAR_PORT_NAME` renders.
- **Labels** were never written by FMS at all, and the two label defaults are
  the empty string, so FMS still never writes a port's `label` until you
  configure a label template.

If you *want* cable-wide numbering (`NST:T2:F4`), set
`front_port_name_template` to `{{ cable }}{% if tube %}:T{{ tube }}{% endif %}:F{{ strand }}`
and run `rerender_port_names` -- but expect every front port on tube 2 and
beyond to be renamed, and plan for the field labels.

---

## Worked example: the issue #69 form

The naming scheme requested in issue #69 was:

```
{{ cable }}:B{{ tube }}F{{ strand }}
```

Set this as `front_port_name_template` (per cable type, or plugin-wide via
`PLUGINS_CONFIG`). For a cable whose `str(cable)` is `NST`, tube position
12, and strand (cable-wide position) 2, it renders:

```
NST:B12F2
```

---

## `strand` vs `strand_local`

`strand` is the FiberStrand's **cable-wide position** -- assigned once, in
order, across the entire cable at instantiation time, and never reused.
`strand_local` is the strand's **1-based index within its immediate
parent**: within the ribbon if it is in one, else within the tube if it is
in one, else within the cable. Conflating the two renumbers every strand in
a multi-tube (or multi-ribbon) cable relative to what an installer expects
when reading labels tube-by-tube.

### Two-tube example

A loose-tube cable with two 3-fiber tubes, "Tube 1" (position 1) and
"Tube 2" (position 2):

| Fiber | `tube` | `tube_name` | `strand` (global) | `strand_local` (per-tube) |
|-------|--------|-------------|--------------------|---------------------------|
| Tube 1, fiber 1 | 1 | Tube 1 | 1 | 1 |
| Tube 1, fiber 2 | 1 | Tube 1 | 2 | 2 |
| Tube 1, fiber 3 | 1 | Tube 1 | 3 | 3 |
| Tube 2, fiber 1 | 2 | Tube 2 | 4 | 1 |
| Tube 2, fiber 2 | 2 | Tube 2 | 5 | 2 |
| Tube 2, fiber 3 | 2 | Tube 2 | 6 | 3 |

Take the first fiber of Tube 2. With the built-in defaults:

- **Strand name** (`strand_name_template`, uses `strand_local`): `Tube 2-F1`
- **Front port name** (`front_port_name_template`, uses `strand_local`): `NST:T2:F1`

Both built-in defaults use `strand_local` on purpose. If either were
rewritten to use `strand`, Tube 2's fibers would render `F4`, `F5`, `F6` --
every strand in Tube 2 (and every tube after it) renumbered away from the
F1, F2, F3 an installer expects to see repeated tube by tube, and away from
what NetBox already holds for cables provisioned before naming templates
existed (see [Upgrade behavior](#upgrade-behavior)).

---

## Validation and the 64-character limit

Every rendered value is capped at **64 characters**, matching the database
column each target writes into (`FrontPort`/`RearPort` `name` and `label`,
`FiberStrand` `name`).

The limit is enforced at two different points, in two different ways:

- **At save time**, `FiberCableType.clean()` compiles the template and
  renders it against two representative dummy contexts (a fully-populated
  tubed/ribboned context and a bare tubeless context). If either dummy
  render exceeds 64 characters, or the template fails to compile or
  render, `clean()` raises a `ValidationError` and the cable type cannot be
  saved with that template.
- **At real render time** (cable/strand provisioning, the automatic
  re-render on every `dcim.Cable` save, tray assignment, and the
  `rerender_*` commands), the same 64-character limit is applied by
  slicing the rendered string: `template.render(**scoped)[:64]`. Real-world
  values -- a long device name, a long cable label -- can be longer than the
  short dummy strings used at validation time, so a template that validated
  cleanly can still **silently truncate** in production. Overflow is never
  rejected at render time, only at validation time.

---

## The label warning: setting a label changes `str(port)` everywhere

Configuring `front_port_label_template` or `rear_port_label_template` to
render a non-empty value has a consequence well beyond FMS's own pages.
NetBox's `ComponentModel.__str__` (`dcim/models/device_components.py:111-114`)
returns:

```python
def __str__(self):
    if self.label:
        return f"{self.name} ({self.label})"
    return self.name
```

Every FrontPort or RearPort that gets a non-blank label therefore displays
as `"{name} ({label})"` -- not just `name` -- **everywhere** NetBox renders
that port as a string: cable-connection dropdowns, cable trace views,
device component tables, the REST API's `display` field, and the GraphQL
schema. This is the single most surprising consequence of configuring
naming templates. Leave the label templates blank (the built-in default)
unless you specifically want this everywhere-in-NetBox display change.

### A blank label template never writes the label column

"No label template configured" and "a label template that rendered empty"
are distinct states, and only the second one writes. With the label
templates left blank -- the default -- FMS never touches a port's `label`
on any path: not on a `dcim.Cable` save, not on tube assignment, not in
`rerender_port_names`. Labels that arrived from a DeviceType template, an
import, or an operator's edit are preserved exactly.

Configure a label template and it becomes authoritative for that target,
including when it renders to an empty string -- for example
`{% if tray %}{{ tray }}{% endif %}` deliberately blanks the label of a
port that is not on a tray. The same rule applies to the name templates.

---

## Re-render existing objects after changing a template

Changing a naming template on a FiberCableType (or in `PLUGINS_CONFIG`)
only affects **future** renders. `_rename_ports_for_cable` recomputes a
cable's RearPort/FrontPort names and labels automatically, but only on
every `dcim.Cable` `post_save` -- so a template change by itself does
nothing to cables that are not re-saved. Skipping the re-render after a
template edit leaves the install split: cables saved (or re-saved) after
the change carry the new names, and every other cable keeps its old ones,
silently, with no error anywhere.

Two management commands cover the five targets, each named for the objects
it writes:

| Command | Re-renders |
|---------|------------|
| `rerender_strand_names` | `FiberStrand.name` |
| `rerender_port_names` | FrontPort **and RearPort** `name` and `label` |

```bash
python manage.py rerender_strand_names
python manage.py rerender_port_names
```

Both accept the same flags:

| Flag | Effect |
|------|--------|
| `--cable-type <pk-or-model>` | Limit the run to one FiberCableType, by primary key or `model` name. |
| `--dry-run` | Report what would change without writing anything. |
| `--limit <N>` | Process at most N FiberCable instances. |

`rerender_port_names` adds one more:

| Flag | Effect |
|------|--------|
| `--targets <list>` | Comma-separated subset of `names`, `labels` (default: both). |

Example -- preview strand-name changes for one cable type only:

```bash
python manage.py rerender_strand_names --cable-type "Corning ALTOS 288F" --dry-run
```

Example -- re-render only the port labels, leaving every port name alone:

```bash
python manage.py rerender_port_names --targets labels
```

### Run `rerender_strand_names` first when port templates use `strand_name`

`{{ strand_name }}` renders from the `FiberStrand.name` column **as
currently stored**, not from the strand template. If you changed
`strand_name_template` and a port template references `{{ strand_name }}`,
run the strand command first, or the port names will embed the old strand
names:

```bash
python manage.py rerender_strand_names
python manage.py rerender_port_names
```

`rerender_port_names` detects this case for you: before processing a cable
type whose selected port templates reference `strand_name` (parsed
statically with `jinja2.meta`, the same way the tray-token guard below
works), it prints a warning naming that cable type and telling you to run
`rerender_strand_names` first. It is a warning, not a refusal -- the run
continues, because a re-render against current strand names is stale at
worst, never wrong.

### Collisions

`rerender_port_names` refuses to write a device's port names if the render
would produce a duplicate `name` on that device, printing the collision
instead of saving it -- resolve the underlying template or data conflict
and re-run.

Names are compared per device **and per model**. `FrontPort` and `RearPort`
are separate tables, each carrying its own `(device, name)` uniqueness
constraint, so a FrontPort and a RearPort on one device may legitimately
share a name and that is not reported as a collision.

---

## The `tray` token is opt-in

`tray` and `tray_position` are only populated by the code paths that
explicitly thread splice-tray placement through: the automatic re-render on
every `dcim.Cable` save, `rerender_port_names`, and the tube-assignment
sync/clear paths described below. They are `None` at initial port
provisioning, before any tube has been assigned to a tray.

Both tokens are available to **rear**-port templates as well as front-port
ones. FMS never places a RearPort on a tray itself, but a RearPort inherits
`module` from NetBox's `ModularComponentModel`, so an operator can; both the
cable-save re-render and `rerender_port_names` read the port's real
placement, so the two agree on the rendered name either way.

The **tube-assignment path** in particular (assigning a buffer tube to a
splice tray, moving it to a different tray, or clearing the assignment) is
guarded: it re-renders that tube's closure-side FrontPort names and labels
**only if `front_port_name_template` or `front_port_label_template`
actually references `tray` or `tray_position`** (`FiberCableType.naming_uses_tray`,
detected by statically parsing the template with `jinja2.meta` -- a
literal word "tray" in surrounding text does not count, only an actual
`{{ tray }}` / `{{ tray_position }}` / `{% if tray %}` reference does).

If a cable type's front-port templates do not reference either token, tube
assignment never touches port names or labels at all. This is deliberate:
it protects hand-built port names and names adopted from an existing
DeviceType template from being silently rewritten by an unrelated
operation (assigning a tube to a tray) on a cable type that was never
configured to care about tray placement.

---

## `strand_local` on re-render paths

`{{ strand_local }}` is safe in front-port templates: every path that
names or renames a FrontPort agrees on its value.

- **Initial provisioning** (`_provision_device_ports`) numbers the strands
  within each tube and passes that index directly.
- **The automatic re-render on every `dcim.Cable` save** recovers it from
  the stored `PortMapping.rear_port_position`.
- **The tube-assignment sync and clear paths, and the
  `rerender_port_names` command**, all go through the shared
  `render_port_strings()` helper,
  which looks the same value up from the port's `PortMapping` (one extra
  query per port).

`PortMapping.rear_port_position` is authoritative here because
`_provision_device_ports` writes the very index it rendered with into that
column, so the lookup reproduces the original number rather than guessing
at one.

`strand_local` renders as `None` only for a FrontPort with no PortMapping
at all -- a port adopted from outside FMS, which was never provisioned
with a local index in the first place. Guard such templates with
`{% if strand_local %}` if the cable type is used on the adopt path, or
use `strand` (the cable-wide position, always available) instead.

---

## Unrelated: FiberCircuit's `{n}` name template

`provisioning.py` has its own, unrelated `{n}` auto-increment mechanism for
naming a `FiberCircuit` when one is created from a proposal
(`create_circuit_from_proposal(..., name_template="Circuit-{n}")`). It
supports exactly one placeholder, literal `{n}`, resolved by scanning
existing `FiberCircuit` names for the highest number sharing the same
prefix/suffix and incrementing it -- it is not Jinja2, does not accept any
of the tokens on this page, and is not affected by anything documented
here. Do not confuse the two: cable-type naming templates render with
Jinja2 and the token tables above; `FiberCircuit` naming uses `{n}` only.

---

## Related topics

- [Fiber Cable Types](fiber-cable-types.md) -- where the five template
  fields live on the FiberCableType form.
- [Fiber Cables](fiber-cables.md) -- when ports and strands are created
  (and therefore first named) during auto-instantiation.
- [Configuration](../getting-started/configuration.md) -- `PLUGINS_CONFIG`
  settings in general.
