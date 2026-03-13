# Unified Splice Visualization & Editor — Design Spec

> **Date:** 2026-03-13
> **Status:** Draft
> **Builds on:** 2026-03-12-splice-plan-redesign

## Goal

Replace the plan-only splice editor on the device tab with a unified visualization that always shows live splice state, supports ad-hoc editing without a pre-existing plan, and uses a pending-changes-then-save workflow. Rewrite the JavaScript in TypeScript (esbuild/IIFE, mirroring netbox-pathways). Both the device tab and standalone plan editor share the same component.

## Architecture

The splice editor becomes a single TypeScript component with three context modes (`view`, `edit`, `plan-edit`). All splice changes are buffered in-memory as pending changes. A "Save" button commits them — either creating a new plan via a quick-add modal or bulk-updating an existing plan via API. Existing splices render at full color until changed, at which point they become ghost lines with colored overlays indicating the pending action.

## Tech Stack

- TypeScript 5.8+, esbuild (IIFE bundle), D3.js v7 (external)
- Django REST Framework (new API actions)
- Django template form rendering (quick-add modal)

---

## 1. TypeScript Source Structure

**Source directory:** `netbox_fms/static/netbox_fms/src/`

| File | Responsibility |
|------|---------------|
| `splice-editor.ts` | Entry point. Reads `SPLICE_EDITOR_CONFIG`, initializes state, renderer, interactions. |
| `types.ts` | Interfaces: `Strand`, `Tube`, `CableGroup`, `Splice`, `PendingChange`, `EditorConfig`, `ContextMode`. |
| `state.ts` | State store. Holds strands, live splices, plan entries, pending changes (add/remove). Exposes methods: `addPendingSplice()`, `removePendingSplice()`, `hasPendingChanges()`, `getPendingChanges()`, `clearPending()`. |
| `renderer.ts` | D3 rendering. Two-column SVG layout (left/right cables). Strand dots with EIA-598 colors, tube grouping with collapse/expand, bezier splice lines. Renders pending changes as overlays. |
| `interactions.ts` | Click handlers for single/sequential/delete modes. Toolbar button wiring. Column scroll/drag. Sequential count selector. |
| `modal.ts` | Save-to-plan modal. Fetches form HTML from Django endpoint, renders in Bootstrap modal, submits via API. |
| `api.ts` | API client. Functions for: fetch strands, quick-add plan, bulk-update plan entries. CSRF handling. |

**Build output:** `netbox_fms/static/netbox_fms/dist/splice-editor.min.js` + `.map`

**Build tooling (in `netbox_fms/static/netbox_fms/`):**

| File | Purpose |
|------|---------|
| `package.json` | Dependencies: `typescript`, `esbuild`, `@types/d3`. Scripts: `build`, `watch`, `typecheck`. |
| `tsconfig.json` | Target `ES2016`, module `ESNext`, strict, noEmit, moduleResolution `bundler`. |
| `bundle.cjs` | esbuild config: entry `src/splice-editor.ts`, out `dist/splice-editor.min.js`, format `iife`, external `d3`, minify, sourcemap. |

---

## 2. Context Modes

| Mode | When | Behavior |
|------|------|----------|
| `view` | Device tab, no plan exists | Read-only visualization of live FrontPort↔FrontPort connections. Editing allowed — changes buffered in-memory. Save opens quick-add modal to create plan. |
| `edit` | Device tab, plan exists | Shows live splices + plan entries. Editing allowed. Save bulk-updates plan via API. |
| `plan-edit` | Standalone plan editor page | Same as `edit`, accessed from SplicePlan detail page. |

---

## 3. Visual States

| State | Rendering |
|-------|-----------|
| Existing splice (unchanged) | Normal EIA-598 color, solid bezier line, standard stroke weight |
| Existing splice (pending delete) | Ghost (low opacity, thin stroke) + dashed red overlay line |
| Existing splice (pending re-splice to new target) | Ghost on old connection + solid green line to new target |
| Pending new splice | Solid green line, normal stroke weight |
| Unspliced strand | Normal dot (unchanged from current behavior) |

**Ghost style:** opacity ~0.2, stroke-width reduced to 1px, color preserved but faded.

---

## 4. Save Flow

### All modes — pending change tracking

- Every splice create/delete action is added to an in-memory pending changes list.
- A "Save" button appears in the toolbar when `state.hasPendingChanges()` is true.
- `window.onbeforeunload` warns when pending changes exist.

### `view` mode — no plan exists

1. User clicks "Save".
2. Modal opens with rendered `SplicePlanForm` fieldsets (fetched from `quick-add-form` endpoint).
3. `closure` field is pre-filled with current device (read-only/hidden).
4. User fills in `name`, `status`, `description`, `project`, `tags`.
5. Submit → `POST quick-add/` creates the plan → `POST bulk-update/` creates all pending entries.
6. Editor transitions to `edit` mode. Config updated with new `planId` and `bulkUpdateUrl`.

### `edit` / `plan-edit` mode — plan exists

1. User clicks "Save".
2. `POST bulk-update/` sends all pending add/remove pairs.
3. Pending changes cleared. Splices re-rendered as normal (no longer ghost/overlay).

---

## 5. Sequential Mode Redesign

**Current:** Click A, click B → unknown number of sequential splices.

**New:**
- When sequential mode is active, an inline count selector appears in the toolbar.
- Count selector: `[-]` button | number input (editable) | `[+]` button.
- Default: 12. Range: 1–144. Step: 1.
- Click strand A, click strand B → creates N pending splices: A+0↔B+0, A+1↔B+1, ..., A+(N−1)↔B+(N−1).
- Strands are ordered by position within their respective tubes/cable groups.
- If fewer than N strands remain in either direction from the clicked starting points, splice as many as possible and show a status bar message: "Spliced X of Y requested (not enough strands)".

---

## 6. Template Changes

### `device_splice_editor.html`

- Remove the `{% if plan %}` / `{% else %}` conditional split.
- Always render the splice editor canvas and toolbar.
- Config object:

```javascript
window.SPLICE_EDITOR_CONFIG = {
    deviceId: {{ device.pk }},
    planId: {{ plan.pk|default:"null" }},
    contextMode: "{{ context_mode }}",  // "view" or "edit"
    planStatus: {{ plan.status|default:"null"|safe }},
    strandsUrl: "{% url 'plugins-api:netbox_fms-api:closure_strands' device_id=device.pk %}",
    bulkUpdateUrl: {% if plan %}"{% url 'plugins-api:netbox_fms-api:spliceplan-bulk-update' pk=plan.pk %}"{% else %}null{% endif %},
    quickAddFormUrl: "{% url 'plugins:netbox_fms:spliceplan_quick_add_form' %}?closure_id={{ device.pk }}",
    quickAddApiUrl: "{% url 'plugins-api:netbox_fms-api:spliceplan-quick-add' %}",
    diffUrl: {% if plan %}"{% url 'plugins-api:netbox_fms-api:spliceplan-get-diff' pk=plan.pk %}"{% else %}null{% endif %},
    csrfToken: "{{ csrf_token }}",
};
```

- Script tag references `dist/splice-editor.min.js` instead of `js/splice_editor.js`.
- D3 loaded from CDN as before (external in esbuild config).

### `splice_editor.html` (standalone plan editor)

- Same refactored JS, `contextMode` always `"plan-edit"`.
- Gets save button, ghost lines, sequential count selector.
- Config object similar but without `quickAddFormUrl`/`quickAddApiUrl` (plan always exists).

---

## 7. Django View Changes

### Modified: `DeviceSpliceEditorView`

- No longer requires a plan to render.
- Always passes `device`, conditionally passes `plan`.
- Passes `context_mode`: `"view"` if no plan, `"edit"` if plan exists.

### Modified: `SplicePlanSpliceEditorView`

- References new dist JS path.
- Passes `context_mode: "plan-edit"`.

### New: `SplicePlanQuickAddFormView`

- `GET /plugins/netbox-fms/splice-plans/quick-add-form/?closure_id=<id>`
- Returns rendered `SplicePlanForm` HTML (fieldsets only, no page chrome).
- `closure` field pre-filled from query parameter.
- Uses Django's `render_to_string` or a minimal template that renders just the form.

---

## 8. API Changes

### New: Quick Add (action on SplicePlanViewSet)

- **URL:** `POST /api/plugins/netbox-fms/splice-plans/quick-add/`
- **Body:** `{ "name": "...", "closure": <device_id>, "status": "...", "description": "...", "project": <id|null>, "tags": [...] }`
- **Response:** `{ "id": <new_plan_id>, "name": "...", "url": "...", ... }` (SplicePlanSerializer)
- **Logic:** Creates SplicePlan. Returns serialized plan.

### New: Bulk Update (action on SplicePlanViewSet)

- **URL:** `POST /api/plugins/netbox-fms/splice-plans/<id>/bulk-update/`
- **Body:**
```json
{
    "add": [
        {"fiber_a": <front_port_id>, "fiber_b": <front_port_id>, "tray": <module_id>}
    ],
    "remove": [
        {"fiber_a": <front_port_id>, "fiber_b": <front_port_id>}
    ]
}
```
- **Logic:** Wrapped in `transaction.atomic()`. Creates SplicePlanEntry for each `add`, deletes matching entries for each `remove`. Returns updated list of plan entries.
- **Response:** `{ "entries": [<SplicePlanEntrySerializer>, ...] }`

### Modified: `ClosureStrandsAPIView`

- Accept optional query param `?plan_id=<id>`.
- When provided, include `plan_entry_id` and `plan_spliced_to` per strand (from plan entries), in addition to existing `splice_entry_id` and `spliced_to` (from live connections).
- When not provided, only return live splice info (current behavior).

### Removed

- Dead `bulkSpliceUrl` references in JS (already non-functional).

---

## 9. URL Patterns

### New plugin URLs (`urls.py`)

| URL | View | Name |
|-----|------|------|
| `splice-plans/quick-add-form/` | `SplicePlanQuickAddFormView` | `spliceplan_quick_add_form` |

### New API URLs (`api/urls.py`)

| URL | Action | Name |
|-----|--------|------|
| `splice-plans/quick-add/` | `SplicePlanViewSet.quick_add` | `spliceplan-quick-add` |
| `splice-plans/<pk>/bulk-update/` | `SplicePlanViewSet.bulk_update` | `spliceplan-bulk-update` |

---

## 10. Error Handling

- **Bulk update validation:** If any add/remove pair is invalid (e.g., strand doesn't exist, already spliced in plan), the entire transaction rolls back. Return 400 with per-item error details.
- **Sequential overflow:** If fewer strands exist than requested count, splice what's available and return actual count in status bar (not an error).
- **Quick-add failure:** If plan creation fails (e.g., closure already has a plan), return 400. Modal shows inline validation errors.
- **Network errors:** JS shows error in status bar. Pending changes are preserved in memory (not lost).

---

## 11. Testing Strategy

### Python tests

- `test_bulk_update_api` — add/remove entries atomically, verify rollback on error.
- `test_quick_add_api` — create plan via API, verify response.
- `test_quick_add_form_view` — form HTML returned with pre-filled closure.
- `test_closure_strands_with_plan_id` — verify plan entry fields included when `plan_id` param provided.
- `test_device_splice_editor_no_plan` — view renders without a plan.
- `test_device_splice_editor_with_plan` — view renders with plan context.

### TypeScript (manual verification)

- Build produces `splice-editor.min.js` without errors.
- `tsc --noEmit` passes (type checking).
- Visual verification of all states: live splices, ghost lines, pending add/delete, sequential mode count selector, save modal.
