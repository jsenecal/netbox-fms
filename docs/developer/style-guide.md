# FMS Visual Component Library — Style Guide

## 1. Overview

The FMS component library (`fms-components.css`) provides shared UI primitives for all FMS visualization views: splice editors, wavelength planners, cable maps. It is **not** a full design system — it covers the specific patterns that appear across FMS canvases and panels.

**Files:**
- CSS: `netbox_fms/static/netbox_fms/css/fms-components.css`
- Built output: `netbox_fms/static/netbox_fms/dist/` (via `npm run build`)

SVG-specific styles (strand nodes, splice links, cable labels) live in `splice_editor.css` and are **not** part of this library.

---

## 2. Getting Started

Add the `fms-component` class to any wrapper element. This activates all CSS custom properties.

```html
<div class="fms-component">
  <!-- toolbar, canvas, panel, stats bar go here -->
</div>
```

Load the stylesheet in your template:

```html
{% load static %}
<link rel="stylesheet" href="{% static 'netbox_fms/dist/fms-components.css' %}">
```

The component root reads `data-bs-theme` from a parent element to switch between dark and light palettes automatically — no extra JS needed.

---

## 3. Color Palette

All colors are defined as CSS custom properties on `.fms-component`. Never use hex values directly — always reference these variables.

| Variable | Purpose |
|---|---|
| `--fms-bg` | Canvas / panel background |
| `--fms-bg-card` | Card / input surface (slightly lighter than bg) |
| `--fms-border` | Borders, dividers, separator lines |
| `--fms-text` | Primary body text |
| `--fms-text-muted` | Secondary / hint text |
| `--fms-text-label` | Row label text (left side of detail rows) |
| `--fms-link` | Interactive links and active pill highlight |
| `--fms-live` | Live / active status (green) |
| `--fms-planned` | Planned status (amber) |
| `--fms-pending` | Pending / in-progress status (orange) |
| `--fms-danger` | Error / protected / destructive (red) |
| `--fms-muted` | Disabled / draft state (grey) |

Light mode overrides are applied via `[data-bs-theme="light"] .fms-component`.

---

## 4. Badge (`.fms-badge`)

Use badges to show status inline with text. They are small (9px, uppercase) and meant for tight spaces.

**Available variants:**

| Class | Color | When to use |
|---|---|---|
| `.fms-badge--live` | Green | Service is carrying traffic |
| `.fms-badge--active` | Green | Same as live (alias) |
| `.fms-badge--planned` | Amber | Designed but not provisioned |
| `.fms-badge--pending` | Orange | Change in progress |
| `.fms-badge--draft` | Grey | Saved but not submitted |
| `.fms-badge--protected` | Red | Circuit or resource is protected; do not touch |

```html
<span class="fms-badge fms-badge--live">Live</span>
<span class="fms-badge fms-badge--planned">Planned</span>
<span class="fms-badge fms-badge--protected">Protected</span>
```

Do not use badges for counts or non-status information — use plain text for those.

---

## 5. Legend (`.fms-legend`)

The legend is an absolutely-positioned overlay for canvas views. It collapses on click.

**Rules:**
- Only include items that are currently visible on the canvas. If a filter hides all spliced strands, remove the "Spliced" entry from the legend.
- Group related items under `fms-legend__section` with a section title.
- Section ordering convention: **status items first** (live, planned, pending), then **structural items** (tubes, ribbons), then **interaction hints** (selected, hover).

**JS API:**

```js
FmsLegend.update(containerId, sections);
// sections: Array<{ title?: string, items: Array<{ type, color?, label }> }>
// item types: 'dot', 'line', 'line-dashed', 'swatches'
```

```html
<div class="fms-component">
  <div class="fms-legend" id="my-legend">
    <div class="fms-legend__header">
      <span class="fms-legend__title">Legend</span>
      <button class="fms-legend__toggle" aria-label="Toggle legend">▾</button>
    </div>
    <div class="fms-legend__body">
      <div class="fms-legend__section">
        <div class="fms-legend__section-title">Status</div>
        <div class="fms-legend__item">
          <span class="fms-legend__dot" style="background:#00cc66"></span>
          Live
        </div>
        <div class="fms-legend__item">
          <span class="fms-legend__line fms-legend__line--dashed" style="color:#ffaa00"></span>
          Planned
        </div>
      </div>
    </div>
  </div>
</div>
```

The `data-collapsed="true"` attribute is toggled by the header click handler (included in `fms-components.js` if present, or wire it manually).

---

## 6. Detail Panel (`.fms-detail-panel`)

A slide-in panel anchored to the right edge of the canvas container. On mobile it becomes a bottom sheet.

**Structure:**

```html
<div class="fms-detail-panel" id="detail-panel" role="complementary" aria-label="Details">
  <div class="fms-detail-panel__header">
    <span class="fms-detail-panel__title">Channel 1</span>
    <button class="fms-detail-panel__close" aria-label="Close panel">&times;</button>
  </div>
  <div class="fms-detail-panel__body">

    <!-- Card with rows -->
    <div class="fms-detail-card">
      <div class="fms-detail-card__heading">Wavelength</div>

      <!-- Text row -->
      <div class="fms-detail-card__row">
        <span class="fms-detail-card__label">Grid position</span>
        <span class="fms-detail-card__value">C32</span>
      </div>

      <!-- Link row -->
      <div class="fms-detail-card__row">
        <span class="fms-detail-card__label">Service</span>
        <a class="fms-link fms-detail-card__value" href="/services/12/">SVC-0012</a>
      </div>

      <!-- Badge row -->
      <div class="fms-detail-card__row">
        <span class="fms-detail-card__label">Status</span>
        <span class="fms-badge fms-badge--live">Live</span>
      </div>

      <!-- Color dot row -->
      <div class="fms-detail-card__row">
        <span class="fms-detail-card__label">Tube color</span>
        <span class="fms-legend__dot" style="background:#0057e7" title="Blue"></span>
      </div>
    </div>

  </div>
</div>
```

**JS API:**

```js
// Open panel (sets data-open="true", triggers CSS transition)
panel.dataset.open = 'true';

// Close panel
panel.dataset.open = 'false';
// or
delete panel.dataset.open;
```

**Escape key behavior:** Wire a `keydown` listener on `document` to close the panel when `key === 'Escape'` and the panel is open. Return focus to the element that triggered the open.

---

## 7. Toolbar (`.fms-toolbar`)

The toolbar sits above the canvas, below any page heading. It wraps at narrow widths.

**Structure rules:**
1. Start with pill groups (exclusive mode selectors).
2. Add a separator between groups of unrelated controls.
3. Place `fms-toolbar__spacer` to push right-side controls to the far right.
4. Search input goes last on the right.

```html
<div class="fms-toolbar fms-component">

  <!-- Exclusive mode group (only one active at a time) -->
  <div class="fms-pill-group" role="group" aria-label="View mode">
    <button class="fms-pill fms-pill--active" aria-pressed="true">Splice</button>
    <button class="fms-pill" aria-pressed="false">Map</button>
  </div>

  <!-- Separator -->
  <div class="fms-separator" role="separator"></div>

  <!-- Independent filter toggles (any combination allowed) -->
  <div class="fms-pill-filter" role="group" aria-label="Filters">
    <button class="fms-pill fms-pill--on" style="--pill-color:#00cc66" aria-pressed="true">Live</button>
    <button class="fms-pill fms-pill--off" style="--pill-color:#ffaa00" aria-pressed="false">Planned</button>
  </div>

  <!-- Spacer pushes the following to the right -->
  <div class="fms-toolbar__spacer"></div>

  <!-- Search -->
  <input class="fms-search" type="search" placeholder="Search…" aria-label="Search strands">

</div>
```

**Pill group (exclusive):** Only one pill has `fms-pill--active`. Clicking another deactivates the current one. Use `aria-pressed` to reflect state.

**Pill filter (independent):** Each pill toggles on/off independently. Use `fms-pill--on` / `fms-pill--off` modifier and set `--pill-color` to the associated status color. Use `aria-pressed` on each button.

---

## 8. Stats Bar (`.fms-stats-bar`)

A slim (28px) bar pinned to the bottom of the canvas. Surfaces aggregate counts.

**Stat ordering:** Essential counts left (total strands, active circuits), secondary/contextual counts right.

Mark the most important stats with `fms-stat--essential` — these remain visible on mobile when non-essential stats are hidden.

```html
<div class="fms-stats-bar fms-component">
  <div class="fms-stats-bar__left">
    <!-- Essential stat -->
    <span class="fms-stat fms-stat--essential">
      <span class="fms-stat__label">Strands:</span> 144
    </span>
    <span class="fms-stats-bar__dot" aria-hidden="true">·</span>
    <span class="fms-stat fms-stat--live">
      <span class="fms-stat__label">Live:</span> 88
    </span>
    <span class="fms-stats-bar__dot" aria-hidden="true">·</span>
    <span class="fms-stat fms-stat--planned">
      <span class="fms-stat__label">Planned:</span> 12
    </span>
  </div>
  <div class="fms-stats-bar__right">
    <!-- Flash message appears here temporarily via JS -->
    <span id="status-msg"></span>
  </div>
</div>
```

**Flash messages:** Insert a temporary message into `fms-stats-bar__right` using JS, then clear it after 3 seconds. Do not use alerts or toasts for minor status updates from canvas actions.

---

## 9. Theme Integration

The library automatically responds to Bootstrap's `data-bs-theme` attribute. No extra work is needed if your page already sets this.

**Rules:**
- Always use `--fms-*` variables for colors inside `.fms-component`.
- Never hardcode hex values for backgrounds, text, or borders.
- For SVG `fill` and `stroke`, use Bootstrap variables (`var(--bs-body-color)`, `var(--bs-primary)`) since SVG elements live inside the canvas, not inside `.fms-component`.

```css
/* Correct */
.my-element {
  color: var(--fms-text);
  border-color: var(--fms-border);
}

/* Wrong */
.my-element {
  color: #ccc;
  border-color: #444;
}
```

---

## 10. Responsive Design

### Breakpoints

| Breakpoint | Width | Behavior |
|---|---|---|
| Desktop | > 991px | Full layout, panel slides in from right |
| Tablet | ≤ 991px | Panel overlays canvas (absolute, full height, shadow) |
| Mobile | ≤ 767px | Panel becomes bottom sheet (50vh max), toolbar compacts, legend hidden, non-essential stats hidden |

### Component behavior at each breakpoint

**Detail panel:**
- Desktop: side-by-side with canvas, no shadow.
- Tablet: overlays canvas, `box-shadow: -4px 0 16px rgba(0,0,0,0.3)`.
- Mobile: fixed bottom sheet, slides up from bottom, swipe-down to dismiss.

**Toolbar:**
- Desktop: single row, full labels.
- Mobile: smaller padding and font (10px), search wraps to its own row (`order: 99`).

**Stats bar:**
- Mobile: only `fms-stat--essential` stats are visible. Mark secondary stats without this class.

**Legend:**
- Mobile: hidden entirely (`display: none`). Canvas space is too limited.

---

## 11. Touch & Accessibility

### Touch targets

All interactive elements must have a minimum tap target of **44×44px**, even if the visual element is smaller. Use padding to expand the hit area without changing the visual size.

```css
/* Expanding a small button's hit area */
.fms-detail-panel__close {
  padding: 12px;
  margin: -8px;
}
```

### Swipe-to-dismiss (mobile bottom sheet)

Wire `touchstart` / `touchmove` / `touchend` on the panel header. If the user drags down more than 60px, close the panel.

### Focus states

Every interactive element must have a visible focus ring. The library provides `:focus-visible` styles on `.fms-pill`, `.fms-link`, `.fms-legend__toggle`, and `.fms-detail-panel__close`. Do not override these with `outline: none`.

### ARIA labels

| Element | Required attribute |
|---|---|
| `.fms-detail-panel` | `role="complementary"`, `aria-label="Details"` |
| `.fms-detail-panel__close` | `aria-label="Close panel"` |
| `.fms-legend__toggle` | `aria-label="Toggle legend"` |
| Pill group | `role="group"`, `aria-label="<group name>"` |
| Each pill | `aria-pressed="true|false"` |
| `.fms-separator` | `role="separator"` |
| Dot separators in stats bar | `aria-hidden="true"` |

### Keyboard navigation

- **Escape** — close the open detail panel.
- **Tab** — move through toolbar controls, close button, and panel rows in DOM order.
- Pill groups should support **Left/Right arrow** keys to move between pills in the group (implement with a `keydown` handler; the CSS does not do this automatically).
