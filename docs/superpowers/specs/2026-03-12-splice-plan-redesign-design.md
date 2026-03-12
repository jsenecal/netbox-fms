# Splice Plan Redesign — Design Spec

## Problem

The current splice planning system (`SplicePlan` / `SplicePlanEntry`) is disconnected from reality. It creates splice entries from scratch rather than reflecting what's actually wired on a closure. There's no way to import existing connections, no versioning, no diff, no useful export, and no way to group plans across a route.

## Goals

1. Splice plans reflect the **desired state** of a closure's tray connections
2. **Current state** is always derived live from NetBox's actual FrontPort↔FrontPort connections
3. **Diff** is computed dynamically (desired vs. live), cached, and invalidated via signals
4. Plans can be **imported** (bootstrap from live state), **edited**, and **applied** (write diff to NetBox)
5. NetBox's built-in **changelog** handles version history — no custom versioning
6. Plans can be **grouped** into a `SpliceProject` spanning multiple closures along a route
7. **Export** as draw.io XML diagrams with visual splice tray layouts and color-coded diffs

## Non-Goals

- End-to-end fiber trace visualization (future — data model supports it)
- Custom versioning system (NetBox changelog is sufficient)
- Server-side PDF rendering (users export from draw.io)

---

## Data Model

### SpliceProject

Groups multiple closure-level splice plans into a single route/job scope.

| Field       | Type                          | Notes                              |
|-------------|-------------------------------|------------------------------------|
| name        | CharField(100)                | e.g., "Main St CO → Elm St Drop"  |
| description | TextField (blank)             |                                    |
| plans       | M2M → SplicePlan              | Ordered                            |

Status is computed from child plans (all applied = complete).

### SplicePlan

One per closure (Device). Represents the desired state of all splice connections within that closure.

| Field        | Type                          | Notes                                        |
|--------------|-------------------------------|----------------------------------------------|
| closure      | FK → dcim.Device              | The splice closure                           |
| group        | FK → SpliceProject (nullable) | Parent project, if part of a route           |
| name         | CharField(100)                |                                              |
| description  | TextField (blank)             |                                              |
| status       | ChoiceField                   | draft, pending_review, ready_to_apply        |
| cached_diff  | JSONField (nullable)          | Cached diff per tray, invalidated by signals |
| diff_stale   | BooleanField (default=True)   | Set by signal, cleared on recompute          |

Constraint: one plan per closure (unique on `closure`).

### SplicePlanEntry

A single desired FrontPort↔FrontPort connection within a plan. Each entry represents one splice or inter-platter route.

| Field          | Type                          | Notes                                           |
|----------------|-------------------------------|-------------------------------------------------|
| plan           | FK → SplicePlan               |                                                 |
| tray           | FK → dcim.Module              | The tray this entry belongs to                  |
| fiber_a        | FK → dcim.FrontPort           | A-side fiber position on tray                   |
| fiber_b        | FK → dcim.FrontPort           | B-side fiber position (same or different tray)  |
| is_inter_platter | BooleanField (computed)     | True if fiber_a and fiber_b are on different trays |
| notes          | TextField (blank)             | Per-splice crew instructions                    |

### ClosureCableEntry

Tracks which physical port/gland on the closure each cable enters through.

| Field          | Type                          | Notes                                    |
|----------------|-------------------------------|------------------------------------------|
| closure        | FK → dcim.Device              |                                          |
| fiber_cable    | FK → FiberCable               |                                          |
| entrance_port  | FK → dcim.RearPort            | The gland/port on the closure device     |
| notes          | TextField (blank)             |                                          |

---

## Models to Remove / Rework

### Remove from SplicePlan
- `mode` field (was: passthrough/sequential/manual)
- `tray` FK (moves to entry level)
- `implement()` method
- `rollback()` method
- `validate_for_implement()` method

### Remove from SplicePlanEntry
- `cable` FK (was: reference to created 0-length cable)
- `mode_override` field
- `fiber_a` / `fiber_b` change from FiberStrand FKs to FrontPort FKs

### Remove from choices.py
- `SplicePlanModeChoices` (passthrough/sequential/manual — no longer needed)
- Update `SplicePlanStatusChoices` to: draft, pending_review, ready_to_apply

---

## Diff Computation + Caching

### Live State Reader

Reads the current actual connections on a closure's trays:

1. Find all tray Modules on the closure Device
2. For each tray, find all FrontPorts
3. For each FrontPort, check if it's connected via a 0-length cable to another FrontPort on a tray of the same closure
4. Return: `{tray_id: set((port_a_id, port_b_id), ...)}`

### Desired State

Read from `SplicePlanEntry` rows:
- `{tray_id: set((fiber_a_id, fiber_b_id), ...)}`

### Diff (per tray)

Simple set operations:
- **To add** = desired − live
- **To remove** = live − desired
- **Unchanged** = desired ∩ live

Inter-platter entries appear on both trays' pages.

### Caching

- `cached_diff`: JSON blob with the diff per tray, stored on `SplicePlan`
- `diff_stale`: boolean flag
- On view: if `diff_stale` is True, recompute diff and store in `cached_diff`, set `diff_stale = False`
- On view: if `diff_stale` is False, serve `cached_diff`

### Signal-Based Invalidation

Django signals on `Cable` and `CableTermination` (`post_save`, `post_delete`):

1. Check: does this cable terminate on a FrontPort belonging to a closure that has a SplicePlan?
2. If yes: set `diff_stale = True` on that closure's plan

This ensures any external changes to connections (manual edits, other plugins, API calls) are reflected in the diff.

---

## Core Operations

### Import

"Import from device" — bootstraps a plan from the closure's current live state.

1. Read the live state (all FrontPort↔FrontPort connections on the closure's trays)
2. Create `SplicePlanEntry` rows for each existing connection
3. Result: plan's desired state = current live state → diff is empty
4. Engineer can now modify the plan (add/remove/change splices)

Precondition: no existing plan for this closure (or user confirms overwrite).

### Apply

Executes the diff against NetBox.

1. Recompute diff if stale
2. **"To remove"** entries: delete the 0-length cables between those FrontPorts
3. **"To add"** entries: create 0-length cables with CableTerminations on the FrontPort pairs
4. NetBox changelog automatically records all cable creates/deletes
5. Recompute diff (should now be empty — desired = live)
6. Update plan status

Apply is an atomic operation (wrapped in a transaction).

### Edit

Standard NetBox CRUD on `SplicePlanEntry` rows. The plan page shows:
- Per-tray tabs/pages
- Current live connections
- Desired connections (plan entries)
- The diff (what will change on apply)
- Inter-platter routes highlighted

---

## Export — Draw.io XML

### Per-Closure Export

Generates a `.drawio` file (mxGraph XML) with:
- One page/tab per tray
- Visual splice tray layout:
  - A-side fibers on left, B-side fibers on right
  - Fibers drawn with EIA-598 colors
  - Connection lines between spliced pairs
- Diff annotations:
  - **Green** = to be added
  - **Red / strikethrough** = to be removed
  - **Black** = unchanged
- Header: closure name, tray ID, cable entrances
- Notes per splice shown as annotations

### Project-Level Export

Multi-page `.drawio` file:
- Cover page with project name and closure list
- Then per-closure pages (each with per-tray sub-pages)

### Why Draw.io

- Open standard (mxGraph XML) — not locked to any vendor
- Visually editable — engineers and crews can annotate
- Exportable to PDF/PNG/SVG from draw.io itself
- Embeddable in Confluence, SharePoint, wikis
- Programmatically generated (it's just XML)

---

## SpliceProject — Cross-Closure Grouping

A `SpliceProject` links multiple `SplicePlan` objects (one per closure) into a route-level job.

- Project status is computed: if all child plans are applied, project is complete
- Project-level diff: aggregated view of all pending changes across closures
- Project-level export: combined draw.io with all closures
- Each plan can be applied independently (crew works closure by closure)
- Plans can exist standalone (no project) for single-closure work

---

## Integration Points

### NetBox Changelog
- All cable creates/deletes from Apply are captured by NetBox's `ObjectChange` system
- No custom versioning needed — changelog is the audit trail
- Journal entries on the closure Device can annotate apply events

### Signals
- `post_save` / `post_delete` on `Cable` and `CableTermination` for diff cache invalidation
- Scoped to closures that have a SplicePlan to avoid performance impact

### Existing FMS Models
- `FiberCable` — used by `ClosureCableEntry` to track which cables enter which closure ports
- `FiberStrand` — not directly referenced by splice plan entries (plan works at FrontPort level), but strand→FrontPort mapping provides the color/tube/cable context for export rendering

---

## Migration Path

1. Drop `SplicePlanModeChoices`
2. Alter `SplicePlanStatusChoices` → draft, pending_review, ready_to_apply
3. Remove `SplicePlan.mode`, `SplicePlan.tray` fields
4. Add `SplicePlan.cached_diff`, `SplicePlan.diff_stale`, `SplicePlan.group`
5. Add unique constraint on `SplicePlan.closure`
6. Change `SplicePlanEntry.fiber_a` / `fiber_b` from FiberStrand FK → FrontPort FK
7. Remove `SplicePlanEntry.cable`, `SplicePlanEntry.mode_override`
8. Add `SplicePlanEntry.tray`, `SplicePlanEntry.notes`
9. Create `SpliceProject` model
10. Create `ClosureCableEntry` model

**Note:** This is a breaking migration — existing SplicePlan/SplicePlanEntry data is not preservable since the FK targets change. The plugin is pre-release so this is acceptable.
