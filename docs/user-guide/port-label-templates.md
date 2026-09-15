# Port Label Templates

NetBox FMS generates the `label` of every FrontPort and RearPort it
provisions from Jinja2 templates. The label is the human-readable display
layer for FMS-managed ports: generated port names are machine-facing
identifiers, so the label carries the identity a technician needs -- the
cable, the tube or ribbon, the strand color, and the absolute cable-wide
fiber number.

Two templates control this:

| Template | Controls |
|----------|----------|
| `front_port_label_template` | FrontPort `label` (one per strand) |
| `rear_port_label_template` | RearPort `label` (one per container: buffer tube, or the whole cable) |

## Resolution order

For each of the two targets, NetBox FMS resolves the template source in
this order:

1. **`PLUGINS_CONFIG['netbox_fms'][<template name>]`**, if the setting is
   present.
2. **The built-in default** shipped with the plugin.

Example plugin-wide override in `configuration.py`:

```python
PLUGINS_CONFIG = {
    "netbox_fms": {
        "front_port_label_template": "{{ cable }} F{{ strand }}",
    },
}
```

Setting a template to the **empty string** opts that target out of label
management entirely: FMS then never writes that label field, newly
provisioned ports start blank, and operator-set labels are left alone.

## Built-in defaults

Quoted from `netbox_fms/naming.py`:

```
front_port_label_template =
    {{ cable }}
    {% if tube_name %} / {{ tube_name }}{% if tube_color %} ({{ tube_color }}){% endif %}{% endif %}
    {% if ribbon_name %} / {{ ribbon_name }}{% endif %}
    {% if strand_color %} / {{ strand_color }}{% endif %}
     / F{{ strand }}

rear_port_label_template =
    {{ cable }}
    {% if tube_name %} / {{ tube_name }}{% if tube_color %} ({{ tube_color }}){% endif %}{% endif %}
```

(The line breaks above are for readability; the shipped defaults are single
strings.) Rendered examples:

| Construction | FrontPort label | RearPort label |
|--------------|-----------------|----------------|
| Loose tube | `CL-01 / T1 (Blue) / Slate / F25` | `CL-01 / T1 (Blue)` |
| Central-core ribbon | `CL-01 / R1 / Blue / F1` | `CL-01` |
| Tight buffer | `CL-01 / Orange / F2` | `CL-01` |

## Token reference

Each target only sees a subset of tokens -- a RearPort covers a whole
container and has no single strand, so ribbon and strand tokens are not
available to rear-port templates. Referencing a token that is not available
to a target fails validation and rendering.

| Token | Front | Rear | Meaning |
|-------|:-----:|:----:|---------|
| `cable` | yes | yes | The linked `dcim.Cable`'s display string. |
| `cable_id` | yes | yes | The `dcim.Cable` primary key. |
| `cable_type` | yes | yes | `"{manufacturer} {model}"` of the FiberCableType. |
| `tube` | yes | yes | The BufferTube's `position`, or `None` for tubeless constructions. |
| `tube_name` | yes | yes | The BufferTube's `name`, or `None`. |
| `tube_color` | yes | yes | The tube color resolved to a palette name under the cable type's color scheme (raw hex if off-palette), or `None`. |
| `tube_color_hex` | yes | yes | The tube's raw hex color, or `None`. |
| `ribbon` | yes | -- | The Ribbon's `position`, or `None` outside ribbon constructions. |
| `ribbon_name` | yes | -- | The Ribbon's `name`, or `None`. |
| `ribbon_color` / `ribbon_color_hex` | yes | -- | Same pattern as the tube colors, for the Ribbon. |
| `strand` | yes | -- | The FiberStrand's **absolute, cable-wide** `position` -- the industry fiber number. |
| `strand_color` / `strand_color_hex` | yes | -- | Resolved color name / raw hex of the strand. |
| `device` | yes | yes | The port's device name. |
| `end` | yes | yes | `"A"` or `"B"`, or `"AB"` for a cable that loops back onto one device. |

**Optional tokens render as the literal text `None` if referenced
unguarded.** Any token that can be absent (`tube`, `ribbon`, and the color
and name tokens) should be wrapped in an `{% if %}` block, exactly as the
built-in defaults do.

## Rendering rules

- Templates run in a **sandboxed** Jinja2 environment with strict
  undefined-variable handling; attribute escapes and unknown tokens fail
  instead of rendering garbage.
- Rendered labels are **truncated to 64 characters**, the length of the
  dcim port label columns.
- A malformed template set in `PLUGINS_CONFIG` is reported in the NetBox
  log at startup and every affected write degrades to leaving labels
  unchanged -- it never breaks a cable save or provisioning.

## When labels are (re)rendered

- **At provisioning**: every FrontPort and RearPort created by the closure
  cable and link-topology services is stamped with a rendered label.
- **On cable save**: saving the linked `dcim.Cable` (for example after a
  relabel) re-renders the labels of all of that cable's FMS-provisioned
  ports, so labels track the cable's display name.
- **On demand**: the `rerender_port_labels` management command backfills
  labels on data provisioned before the engine existed, or after a
  template change:

```
python manage.py rerender_port_labels [--cable-type <pk-or-model>] [--dry-run] [--limit N]
```

`--dry-run` reports every label change without writing anything.

## Known limitations

- There are no per-FiberCableType template fields; templates are
  plugin-wide only.
- Splice tray placement is not yet part of the label context: there is no
  `{{ tray }}` token, and assigning a buffer tube to a tray does not
  trigger a label re-render. This is a planned follow-up.
