# Fiber Circuits Design Spec

**Date:** 2026-03-17
**Status:** Draft

## Overview

Fiber Circuits document end-to-end paths of fiber strands through cables and splices. A circuit contains one or more parallel paths (e.g., 2-strand TX/RX pair, 12-strand ribbon), each tracing a single strand's journey across multiple cable segments and splice closures. Circuits protect their underlying infrastructure — cables, ports, strands, and splices — from accidental modification or deletion.

This feature subsumes the existing `FiberPathLoss` stub model, as loss budgeting is a property of a circuit path.

## Data Model

### FiberCircuit

Top-level object representing a logical fiber service.

| Field | Type | Notes |
|-------|------|-------|
| `name` | CharField | Templated with auto-increment for bulk creation (e.g., `"DT-CTR-{n}"`) |
| `cid` | CharField | Optional. External circuit identifier (carrier-assigned or operator-internal) |
| `status` | CharField | NetBox standard status choices: planned, staged, active, decommissioned |
| `description` | TextField | Optional |
| `strand_count` | PositiveIntegerField | Declared target — number of parallel paths this circuit is designed to carry. Validated: `paths.count() <= strand_count` on path creation |
| `tenant` | FK → tenancy.Tenant | Optional. For customer/billing assignment |
| `comments` | TextField | Optional, NetBox standard |
| (NetBoxModel fields) | | tags, custom fields, journal, etc. |

### FiberCircuitPath

One strand's end-to-end journey through cables and splices.

| Field | Type | Notes |
|-------|------|-------|
| `circuit` | FK → FiberCircuit | CASCADE |
| `position` | PositiveIntegerField | 1-based ordering within circuit |
| `origin` | FK → dcim.FrontPort | Start of this strand's path |
| `destination` | FK → dcim.FrontPort | Nullable — incomplete paths |
| `path` | JSONField | Ordered node list (see Path JSON Schema below) |
| `is_complete` | BooleanField | True if path reaches a valid endpoint |
| `calculated_loss_db` | DecimalField | Nullable. Theoretical loss at `wavelength_nm` |
| `actual_loss_db` | DecimalField | Nullable. Measured result (OTDR/power meter) at `wavelength_nm` |
| `wavelength_nm` | PositiveIntegerField | Nullable. Wavelength for loss values (e.g., 1310, 1550). Required when either loss field is set (validated in `clean()`) |

**Constraints:**
- `unique_together = ('circuit', 'position')`

### FiberCircuitNode

Relational index of all objects in a path, used for deletion protection via Django `PROTECT` FKs.

| Field | Type | Notes |
|-------|------|-------|
| `path` | FK → FiberCircuitPath | CASCADE |
| `position` | PositiveIntegerField | Order in path |
| `cable` | FK → dcim.Cable | PROTECT, nullable |
| `front_port` | FK → dcim.FrontPort | PROTECT, nullable |
| `rear_port` | FK → dcim.RearPort | PROTECT, nullable |
| `fiber_strand` | FK → FiberStrand | PROTECT, nullable |
| `splice_entry` | FK → SplicePlanEntry | PROTECT, nullable |

**Constraints:**
- `unique_together = ('path', 'position')`
- `CheckConstraint`: exactly one of `cable`, `front_port`, `rear_port`, `fiber_strand`, `splice_entry` is non-null per row (count of non-null fields == 1).

Nodes are only present for circuits with status != decommissioned.

### Path JSON Schema

The `FiberCircuitPath.path` field uses a plugin-owned JSON format, decoupled from CablePath's internal `PathField`:

```json
[
  {"type": "front_port", "id": 10},
  {"type": "rear_port", "id": 5},
  {"type": "cable", "id": 7},
  {"type": "rear_port", "id": 12},
  {"type": "front_port", "id": 20},
  {"type": "splice_entry", "id": 3},
  {"type": "front_port", "id": 21},
  {"type": "rear_port", "id": 13},
  {"type": "cable", "id": 8},
  {"type": "rear_port", "id": 14},
  {"type": "front_port", "id": 30}
]
```

Each entry is a `{"type": <string>, "id": <int>}` dict. Types: `front_port`, `rear_port`, `cable`, `splice_entry`. Note: `fiber_strand` is **not** stored in the path JSON — it is derived by `rebuild_nodes()` via FrontPort FK lookups. This format is stable across NetBox versions and trivially walked by `rebuild_nodes()`.

## Protection System

### Database-level protection

Django's `PROTECT` on FiberCircuitNode FKs prevents deletion of any referenced object — from NetBox core UI, API, or plugin — raising `ProtectedError`.

### Lifecycle

- **Status != decommissioned:** nodes exist, protection active.
- **Status → decommissioned:** nodes deleted, all PROTECT holds released.
- **Status decommissioned → any other:** nodes rebuilt from JSON path, protection re-engaged.

### Splice editor integration

- Protected splices rendered with lock icon and tooltip showing circuit name.
- Protected splices are non-interactive (no drag, no delete).
- Splice editor apply action checks FiberCircuitNode before modifying splices.

### User-facing errors

When deletion is blocked, the error identifies which circuit(s) protect the object:
*"Cannot delete Cable #42 — it is part of active Fiber Circuit 'Downtown-Central-1'"*

## Trace Engine

### `FiberCircuitPath.from_origin(front_port)` — classmethod

Adapted from `CablePath.from_origin()`, stripped of wireless/power/circuit/split logic, accepting FrontPort as origin.

**Algorithm — explicit ingress/egress through each closure:**

```
Given: origin FrontPort (on the ingress tray module of first closure)

LOOP:
  1. INGRESS — Record the current FrontPort (ingress port).
     Follow PortMapping: FrontPort → RearPort (front-to-rear, into the device).
     Record the RearPort.

  2. CABLE CROSSING — Find Cable attached to this RearPort via CableTermination.
     Record the Cable.
     Follow Cable to the far-end RearPort via CableTermination on the opposite side.
     Record the far-end RearPort.

  3. EGRESS — Follow PortMapping: far-end RearPort → FrontPort (rear-to-front, out of the device).
     Record the egress FrontPort.

  4. SPLICE CHECK — Does this egress FrontPort have a 0-length cable
     to another FrontPort (splice)?
     - YES: Record the splice (SplicePlanEntry). The far-side FrontPort
       becomes the new ingress FrontPort. Go to step 1.
     - NO: Path terminates at this FrontPort. Mark as destination.

END LOOP
```

**Example — 2-closure path:**
```
Closure A                    Cable 1              Closure B                    Cable 2              Closure C
FP:10 → RP:5 ──────────── [Cable 7] ──────────── RP:12 → FP:20
                                                  FP:20 ══splice══ FP:21
                                                  FP:21 → RP:13 ──────────── [Cable 8] ──────────── RP:14 → FP:30
```
Path JSON: `[FP:10, RP:5, Cable:7, RP:12, FP:20, Splice:3, FP:21, RP:13, Cable:8, RP:14, FP:30]`

**Output:** FiberCircuitPath instance with `path` JSON, `origin`, `destination`, `is_complete` populated. Caller saves and calls `rebuild_nodes()`.

### `retrace()` — instance method

Re-runs `from_origin(self.origin)`, updates JSON path, and atomically rebuilds nodes within a single transaction. Callable on any status — old nodes are deleted and replaced. If the retrace discovers a broken path (missing splice, removed cable), `is_complete` is set to `False`. For decommissioned circuits, `retrace()` updates the JSON path but does **not** create nodes, preserving the lifecycle invariant that decommissioned circuits have no protection nodes.

### `rebuild_nodes()` — instance method

Walks the JSON path and creates FiberCircuitNode rows with correct PROTECT FKs:
- `front_port` / `rear_port` / `cable` / `splice_entry` — resolved directly from the `{"type", "id"}` entries in the JSON path.
- `fiber_strand` — derived by lookup from FrontPort FKs: `FiberStrand.objects.filter(Q(front_port_a=fp) | Q(front_port_b=fp))`. One additional FiberCircuitNode is created per FrontPort pair (ingress/egress) to protect the strand traversing that cable segment.

## Provisioning Engine

### `FiberCircuit.find_paths(origin_device, destination_device, strand_count, priorities)` — classmethod

Given endpoints and requirements, finds or proposes contiguous fiber paths through the closure network.

**DAG construction:**

1. Query all cables between origin and destination via CableTermination → Device.
2. Build directed graph: nodes = devices (closures), edges = individual cables (not aggregated). Multiple cables between the same pair of closures are separate edges, each with their own available strand counts.

**Scoring — user-configurable priority ordering from:**

| Priority | Description |
|----------|-------------|
| `hop_count` | Fewer intermediate closures preferred |
| `new_splices` | Fewer new splices required (prefer already-spliced paths) |
| `strand_adjacency` | Prefer strands in same tube/ribbon (easier field work) |
| `lowest_strand` | First-fit, predictable allocation |

**Algorithm:**

1. Find all simple paths through the DAG from origin to destination.
2. For each route, find available strand groups of size `strand_count` that are contiguous across all hops — all strands must traverse the same sequence of closures using the same cables.
3. Score each candidate by the user-ordered priorities (first priority breaks ties, second priority breaks remaining ties, etc.).
4. Return top N candidates ranked by score.

**Output:** List of proposed path sets, each containing `strand_count` paths with intermediate closures, strand assignments, and counts of existing vs. new splices needed.

### `FiberCircuit.create_from_proposal(proposal, name_template)` — classmethod

Takes a selected proposal and in one transaction:

1. Creates FiberCircuit with name from template. Auto-increment `{n}` is scoped per-prefix: queries `FiberCircuit.objects.filter(name__startswith=prefix)` to find the next available number. Uses `select_for_update()` to handle concurrent creation.
2. Creates FiberCircuitPath per strand.
3. Creates FiberCircuitNode rows for protection.
4. For new splices: creates SplicePlanEntry rows in the relevant SplicePlans and directly creates the 0-length cables between FrontPort pairs (same as the splice plan `apply` action). Sets `diff_stale=True` on affected SplicePlans so their cached diffs are recomputed on next access.

## UI & Views

### Standard CRUD

- FiberCircuitListView, FiberCircuitDetailView, FiberCircuitEditView, FiberCircuitDeleteView
- FiberCircuitBulkEditView, FiberCircuitBulkDeleteView

### Detail view

- **Overview tab** — circuit metadata, status, strand count, tenant, cid.
- **Paths tab** — table of FiberCircuitPaths with origin, destination, wavelength, calculated_loss_db, actual_loss_db, is_complete.
- **Path detail** — expandable view showing full hop sequence: strand → splice → strand → ...
- **Protection tab** — list of all protected objects (cables, ports, splices) via FiberCircuitNodes.

### Circuit creation

- **Manual** — standard form, then add paths individually by selecting origin FrontPort; system traces and populates.
- **Bulk/Find** — form with origin device, destination device, strand count, name template, priority ordering. Calls `find_paths()`, presents candidates, user selects, circuits created.

### Splice editor integration

- Lock icon on protected splices with circuit name tooltip.
- Non-interactive (no drag/delete).
- Optional filter toggle: "Show protected splices."

### Cable/Port detail pages

- Info panel: "Part of Fiber Circuit: X" when referenced by FiberCircuitNode.
- Link to circuit detail view.

## API

### ViewSets

**FiberCircuitViewSet** — full CRUD + custom actions:

| Action | Method | Description |
|--------|--------|-------------|
| `find_paths` | POST | origin_device, destination_device, strand_count, priorities → scored candidates |
| `create_from_proposal` | POST | selected proposal + name template → creates circuit, paths, nodes, splice entries |
| `retrace` | POST | re-traces all paths, rebuilds nodes atomically |

**FiberCircuitPathViewSet** — CRUD, nested under circuit.

**FiberCircuitNodeViewSet** — read-only, nested under path.

### Protection query

`GET /api/plugins/netbox-fms/fiber-circuits/protecting/?cable=42&front_port=1,2,3`

Returns circuits protecting the given objects. Supports batch queries (comma-separated IDs per parameter) for all node FK types: `cable`, `front_port`, `rear_port`, `fiber_strand`, `splice_entry`. Used by splice editor for pre-modification checks.

### Serializers

- **FiberCircuitSerializer** — includes nested path summary (count, complete/incomplete).
- **FiberCircuitPathSerializer** — origin/destination port representations, both loss fields, wavelength, hop count.
- **FiberCircuitNodeSerializer** — read-only, protected object type and link.

## Testing Strategy

### Model tests

- FiberCircuit creation with all status transitions.
- FiberCircuitPath.from_origin() trace across 1, 2, 3+ cable segments with splices.
- Incomplete path detection (missing splice mid-chain).
- Node table rebuild from JSON path — verify correct FKs populated.
- `strand_count` validation — cannot add more paths than declared count.
- `unique_together` constraints on path position and node position.
- `CheckConstraint` on FiberCircuitNode — exactly one FK set.

### Protection tests

- Delete Cable referenced by active circuit → `ProtectedError`.
- Delete FrontPort referenced by active circuit → `ProtectedError`.
- Delete RearPort referenced by active circuit → `ProtectedError`.
- Delete FiberStrand referenced by active circuit → `ProtectedError`.
- Delete SplicePlanEntry referenced by active circuit → `ProtectedError`.
- Decommission circuit → nodes deleted → deletion succeeds.
- Status change from decommissioned to planned → nodes rebuilt → protection re-engaged.

### Trace engine tests

- Simple 1-cable path (FrontPort → RearPort → Cable → RearPort → FrontPort).
- Multi-hop path through 2+ closures with splices.
- Path with missing intermediate splice → incomplete.
- Verify ingress/egress direction: FrontPort→RearPort (into device), RearPort→FrontPort (out of device).
- Retrace on active circuit — verify atomic node replacement.
- Retrace on broken path — verify `is_complete=False`.

### Provisioning engine tests

- find_paths with single available route.
- find_paths with multiple routes, verify scoring by each priority.
- find_paths with partial existing splices → prefer fewer new splices.
- find_paths with multiple cables between same closure pair — treated as separate edges.
- Bulk creation with name template auto-increment.
- Concurrent bulk creation — verify `select_for_update` prevents duplicate names.
- Contiguity constraint — all strands must traverse same closures and cables.
- create_from_proposal creates splice entries, 0-length cables, and sets `diff_stale`.

### API tests

- CRUD operations on all three models.
- find_paths endpoint returns valid candidates.
- create_from_proposal creates correct objects.
- protecting query endpoint returns correct circuits (single and batch).
- Splice editor apply blocked when splice is protected.

### Splice editor integration tests

- Protected splices marked correctly in API response.
- Attempt to delete protected splice via editor → blocked with error.

### Performance tests

- **Trace performance** — trace through 10, 50, 100 cable hops; target: 100-hop trace < 500ms.
- **find_paths on large DAG** — 50+ closures, 100+ cables, multiple routes; target: < 2s for 12-strand search.
- **Node rebuild at scale** — circuit with 12 paths × 100 hops each; target: < 1s.
- **Protection check queries** — 1000+ FiberCircuitNodes in DB, verify single-cable lookup < 10ms (indexed FK).
- **Bulk creation** — 48-strand circuit in one transaction; target: < 3s.
- **Concurrent protection checks** — multiple simultaneous delete attempts on protected objects.

## GraphQL

Add GraphQL types, schema entries, and filter classes for all three new models (`FiberCircuit`, `FiberCircuitPath`, `FiberCircuitNode`) in `graphql/types.py`, `graphql/schema.py`, and `graphql/filters.py`, following existing patterns.

## Migration Notes

- `FiberPathLoss` model is replaced by `FiberCircuitPath` (calculated_loss_db, actual_loss_db, wavelength_nm). Since `FiberPathLoss` is a stub with no production data, it will be removed. This is a full-stack removal touching: models.py, forms.py, filters.py, tables.py, views.py, urls.py, api/serializers.py, api/views.py, api/urls.py, graphql/types.py, graphql/schema.py, graphql/filters.py, search.py, navigation.py, and the template file.
- Three new models: `FiberCircuit`, `FiberCircuitPath`, `FiberCircuitNode`.
