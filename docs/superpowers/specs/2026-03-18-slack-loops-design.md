# Slack Loops Design Spec

## Overview

Add a `SlackLoop` model to track fiber cable slack loops — coils of spare cable left at specific locations along a route for future access, re-splicing, or mid-span maintenance. Each slack loop is tied to a single `FiberCable`, located at a `Site` (with optional `Location`), and records start/end sheath meter marks for length tracking.

Additionally, provide an "Insert into Splice Closure" workflow that converts a slack loop into a mid-span splice point by splitting the cable at the loop location and connecting both halves through an existing closure device.

---

## Model: `SlackLoop`

### Fields

| Field | Type | Constraints |
|-------|------|-------------|
| `fiber_cable` | FK → `FiberCable` | CASCADE, required, `related_name="slack_loops"` |
| `site` | FK → `dcim.Site` | PROTECT, required, `related_name="+"` |
| `location` | FK → `dcim.Location` | PROTECT, nullable, `related_name="+"` |
| `start_mark` | DecimalField(10, 2) | required, >= 0 |
| `end_mark` | DecimalField(10, 2) | required, >= 0 |
| `length_unit` | CharField(10) | choices=`CableLengthUnitChoices` (from `dcim.choices`), required |
| `storage_method` | CharField(50) | choices=`StorageMethodChoices`, blank |
| `notes` | TextField | blank |

All FK fields include `verbose_name=_("...")` and `help_text` following the pattern in existing models (e.g., `ClosureCableEntry`).

### Behavior

- **Auto-normalize marks in `save()`**: if `end_mark < start_mark`, swap them.
- **Validation in `clean()`**: both `start_mark` and `end_mark` must be >= 0.
- **Computed property `loop_length`**: returns `end_mark - start_mark` in the stored unit.
- **`get_absolute_url()`**: returns `reverse("plugins:netbox_fms:slackloop", args=[self.pk])`.
- **No status field**: a slack loop either exists or is deleted (replaced by a splice closure).

### Meta

- `ordering`: `("fiber_cable", "start_mark")`
- `verbose_name`: "slack loop"
- `unique_together`: `("fiber_cable", "start_mark", "end_mark")` — prevent duplicate entries for the same span

### `__str__`

`f"{self.fiber_cable} @ {self.start_mark}–{self.end_mark} {self.length_unit}"`

### URL patterns

`plugins:netbox_fms:slackloop` (detail), `slackloop_list`, `slackloop_add`, `slackloop_edit`, `slackloop_delete`

---

## Model Change: `SplicePlanEntry`

### New Field

| Field | Type | Constraints |
|-------|------|-------------|
| `is_express` | BooleanField | default=False |

**Purpose:** Distinguishes physical splices from express (pass-through) fibers at a closure. Express fibers are buffer tubes or individual strands that are coiled inside the splice tray and routed through the closure without being cut.

**Express entries use the same `fiber_a`/`fiber_b` semantics** as regular splice entries — they still connect FrontPort A to FrontPort B at the closure. The `is_express` flag simply documents that no physical splice was performed; the fiber passes through continuously. The existing `unique_together` constraints on `(plan, fiber_a)` and `(plan, fiber_b)` apply normally — a fiber cannot appear in multiple entries within the same plan.

Industry terminology:
- **Express Tubes/Fibers**: Untouched buffer tubes or fibers that pass through a closure without being cut.
- **Branch/Drop Splice**: Splicing fibers from a single cut tube to a new cable (e.g., a drop cable) without affecting other fibers.
- **Oval Port/Express Port**: The closure port designed for mid-span cables, sealing the cable without cutting all fibers.

---

## Choices: `StorageMethodChoices`

```python
class StorageMethodChoices(ChoiceSet):
    COIL = "coil"
    FIGURE_8 = "figure_8"
    IN_TRAY = "in_tray"
    ON_POLE = "on_pole"
    IN_VAULT = "in_vault"

    CHOICES = (
        (COIL, _("Coil")),
        (FIGURE_8, _("Figure-8")),
        (IN_TRAY, _("In Tray")),
        (ON_POLE, _("On Pole")),
        (IN_VAULT, _("In Vault")),
    )
```

---

## Workflow: Insert into Splice Closure

Converts a slack loop into a mid-span splice point. The original cable is split at the loop location, and both halves are connected through an existing closure device.

### Preconditions

1. The target `dcim.Device` (closure) must already exist with the correct RearPorts and Modules/FrontPorts configured.
2. The closure must have enough available RearPorts to accept two cable terminations (one per new cable segment).

### User Interface

A dedicated view accessible from the SlackLoop detail page: **"Insert into Splice Closure"** button.

The form collects:
- **Closure**: `dcim.Device` selector (existing closure)
- **A-side RearPorts**: Which closure RearPorts the A-side cable segment terminates at
- **B-side RearPorts**: Which closure RearPorts the B-side cable segment terminates at
- **Express selection**: Per-tube or per-strand toggle for which fibers are express (pass-through) vs. physically spliced

### Operation Sequence

All operations run inside `transaction.atomic()` within the view's HTTP request context (so `event_tracking` and change logging are active automatically).

```
transaction.atomic():
  1. Capture state
     - old_cable = slack_loop.fiber_cable.cable
     - old_cable.snapshot()                          # change logging pre-state
     - Record A-side and B-side termination endpoints
     - Record FiberCableType for re-instantiation
     - Record old FiberCable metadata (serial_number, install_date, notes)

  2. Handle FiberCircuit references (if FiberCircuitNode exists)
     - Query FiberCircuitNodes referencing the old dcim.Cable or any
       objects that will be CASCADE-deleted (FiberCable, FiberStrands,
       BufferTubes, CableElements)
     - For each node, store a re-wiring record:
       {path_id, position, field_name, old_value, strand_position (if fiber_strand)}
     - DELETE these FiberCircuitNode rows (cannot nullify — the
       `fibercircuitnode_exactly_one_ref` CHECK constraint requires
       exactly one FK to be non-null at all times)
     - Nodes will be recreated in step 9 with correct new FK values
     - NOTE: The original A-side/B-side termination endpoint objects
       (Devices, Interfaces, FrontPorts on OTHER devices) survive the
       cable deletion — only CableTerminations (the join table) are
       removed by cascade.

  3. Delete old cable
     - old_cable.delete()
     - Cascades: CableTerminations → triggers nullify_connected_endpoints()
     - Cascades: FiberCable → BufferTubes, Ribbons, FiberStrands, CableElements
     - Fires: post_delete → retrace_cable_paths()

  4. Create Cable A (original A-side endpoint → closure RearPorts)
     - new_cable_a = dcim.Cable(...)
     - Set terminations: original A-side endpoints + selected closure RearPorts
     - new_cable_a.save()                            # triggers trace_paths signal

  5. Create Cable B (closure RearPorts → original B-side endpoint)
     - new_cable_b = dcim.Cable(...)
     - Set terminations: selected closure RearPorts + original B-side endpoints
     - new_cable_b.save()                            # triggers trace_paths signal

  6. Create FiberCable instances
     - FiberCable A (cable=new_cable_a, fiber_cable_type=original_type)
       → save() auto-instantiates BufferTubes, FiberStrands, CableElements
     - FiberCable B (cable=new_cable_b, fiber_cable_type=original_type)
       → save() auto-instantiates BufferTubes, FiberStrands, CableElements

  7. Create SplicePlan + SplicePlanEntries at the closure
     - Create SplicePlan for closure (or use existing if one exists)
     - For each strand position N:
       - Find FrontPort N on Cable A's closure-side
       - Find FrontPort N on Cable B's closure-side
       - Create SplicePlanEntry(fiber_a=fp_a, fiber_b=fp_b,
           is_express=<per user selection>)

  8. Create ClosureCableEntry records
     - Create ClosureCableEntry for FiberCable A at the closure
     - Create ClosureCableEntry for FiberCable B at the closure

  9. Recreate FiberCircuitNodes (if any were deleted in step 2)
     - For each stored re-wiring record from step 2, create a new
       FiberCircuitNode with the mapped FK value:
       a. cable: map to new_cable_a or new_cable_b based on
          which side of the original cable the node was on
       b. fiber_strand: map old strand position to the
          corresponding new FiberStrand (same position) on the
          correct new FiberCable (A or B)
       c. front_port / rear_port: if these referenced ports on
          the closure side, map to the new closure RearPorts/
          FrontPorts; if they referenced far-end endpoints, those
          objects survived deletion and can be referenced directly
       d. splice_entry: if the node referenced a splice entry
          that was on the old cable, map to the new corresponding
          SplicePlanEntry created in step 7

  10. Delete the SlackLoop record

  11. Redirect to closure detail page (SplicePlan view)
```

### Signal and Context Manager Summary

| Mechanism | How it's handled |
|-----------|-----------------|
| `transaction.atomic()` | Wraps entire operation — all-or-nothing |
| `snapshot()` | Called on old cable before deletion for change logging |
| `event_tracking` context | Active automatically (view runs inside HTTP request) |
| `trace_paths` signal | Fires automatically on each new Cable.save() |
| `post_delete` (Cable) | Fires automatically, retraces CablePaths |
| `post_delete` (CableTermination) | Fires via cascade, nullifies connected endpoints |
| ObjectChange records | Created automatically by core signal handlers |
| Webhooks / Event Rules | Queued automatically via events_queue, flushed on request exit |

### Edge Cases

1. **FiberCircuitNode PROTECT + CHECK constraint**: If `FiberCircuitNode` models reference the old cable (or its FiberStrands, etc.) via PROTECT FKs, `.delete()` will raise `ProtectedError`. The `fibercircuitnode_exactly_one_ref` CHECK constraint prevents nullifying FKs as a workaround. Step 2 handles this by deleting the affected nodes (after capturing re-wiring records), and step 9 recreates them with the correct new FK values.
2. **Existing SplicePlan on closure**: If the closure already has a SplicePlan, add entries to it rather than creating a new one. The view must verify no `unique_together` conflicts arise (e.g., if the closure FrontPorts are already used in existing splice entries).
3. **Strand count mismatch**: Both cable segments use the same FiberCableType, so strand counts match by definition.
4. **Endpoint objects survive cable deletion**: When the old `dcim.Cable` is deleted, only `CableTermination` join-table rows are cascade-deleted. The actual endpoint objects (Devices, Interfaces, FrontPorts on far-end devices) remain intact and are available for re-termination in steps 4–5.

---

## Full Stack Registration

All files updated per the standard "Adding a New Model" checklist:

| File | Addition |
|------|----------|
| `models.py` | `SlackLoop` model, added to `__all__`; `is_express` field on `SplicePlanEntry` |
| `choices.py` | `StorageMethodChoices` |
| `forms.py` | `SlackLoopForm`, `SlackLoopImportForm`, `SlackLoopBulkEditForm`, `SlackLoopFilterForm`, `InsertSlackLoopForm` |
| `filters.py` | `SlackLoopFilterSet` — filter by `fiber_cable`, `site`, `location`, `storage_method`, `length_unit` |
| `tables.py` | `SlackLoopTable` — columns: fiber_cable, site, location, start_mark, end_mark, loop_length, length_unit, storage_method |
| `views.py` | `SlackLoopListView`, `SlackLoopView`, `SlackLoopEditView`, `SlackLoopDeleteView`, `SlackLoopBulkImportView`, `SlackLoopBulkDeleteView`, `SlackLoopInsertView` |
| `urls.py` | Standard CRUD URL patterns + `slackloop_insert` |
| `api/serializers.py` | `SlackLoopSerializer` |
| `api/views.py` | `SlackLoopViewSet` |
| `api/urls.py` | Router registration |
| `graphql/types.py`, `schema.py`, `filters.py` | GraphQL type and filter |
| `templates/netbox_fms/slackloop.html` | Detail template (with "Insert into Splice Closure" button) |
| `templates/netbox_fms/slackloop_insert.html` | Insert workflow form template |
| `search.py` | `SlackLoopIndex` — searchable by fiber_cable, site |
| `navigation.py` | Menu entry under existing menu structure |
| Migration | Auto-generated: adds `SlackLoop` table, adds `is_express` to `SplicePlanEntry` |

---

## Design Decisions

1. **Single `length_unit` field** — both marks share the same unit inherently; no need for per-mark units.
2. **Auto-swap in `save()`** — if user enters marks in reverse order, normalize silently rather than erroring.
3. **No status field** — slack loops are ephemeral documentation. They exist or they don't.
4. **`related_name="+"` on Site/Location FKs** — avoids cluttering the reverse relation on core NetBox models.
5. **Uses `CableLengthUnitChoices` from `dcim.choices`** — reuses existing NetBox unit vocabulary.
6. **`is_express` boolean on SplicePlanEntry** — simple flag to distinguish physical splices from pass-through fibers. Industry-standard "express" terminology.
7. **Cable split creates two new cables** — NetBox deletes cables when endpoints are disconnected, so we must create fresh cables rather than modifying the original.
8. **FiberCircuitNode re-wiring** — the insert operation updates any FiberCircuitNodes referencing the old cable to point to the correct new segment, maintaining circuit integrity through the split.
9. **Closure must pre-exist** — we don't scaffold the closure device; the user creates it with the right ports/modules beforehand.
