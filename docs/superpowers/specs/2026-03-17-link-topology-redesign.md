# Link/Define Cable Topology — Fiber Overview Redesign

## Problem

The Fiber Overview tab assumes a greenfield workflow: create FiberCable, then provision strands (creating new FrontPorts). This breaks on existing closures that already have FrontPorts on their tray modules — provisioning creates duplicate ports, collides on unique names, and corrupts the device's port layout.

Additionally, the current model uses one RearPort per cable (single-connector profile), which doesn't represent real fiber cable topology. A 12-tube × 12F cable should be modeled as 12 RearPorts (one per tube), each with 12 positions. This matches the trunk cable profile model and renders correctly in NetBox's trace SVG.

The plugin needs to **adopt** existing NetBox infrastructure rather than duplicate it, and model cable topology accurately at the tube level.

## Design Decisions

Decisions made during brainstorming (not open for re-evaluation):

1. **Adopt existing ports** — When a closure already has FrontPorts on a module, the plugin links FiberStrands to them rather than creating duplicates. When no ports exist (greenfield), new ports are created.
2. **Single action** — "Create FiberCable" and "Provision Strands" merge into one "Link Topology" action. One intent ("manage this cable with the plugin") = one button.
3. **Position-based matching with confirmation** — Strands map to FrontPorts by `rear_port_position` in PortMapping. If counts match, show the mapping for confirmation. If counts don't match, show manual mapping UI.
4. **Cable profile derived from topology** — `FiberCableType.get_cable_profile()` reads the BufferTubeTemplates to determine the correct profile key. No new model field.
5. **Expanded hardcoded profile set** — Add trunk profiles (multi-connector) alongside existing single-connector profiles. Curated list, expanded over time.
6. **Missing profile = warning, not blocker** — If no profile matches, show a strong red warning but allow proceeding. Leave `Cable.profile` blank to avoid data loss.
7. **Per-cable first, bulk later** — Single "Link Topology" button per cable row ships first. Bulk "Link All Cables" button is Phase 3.
8. **DRY** — One `link_cable_topology()` service function used by per-cable modal and future bulk action.
9. **One RearPort per tube** — A cable's tubes are modeled as separate RearPorts, each with positions matching the tube's fiber count. This enables trunk cable profiles and accurate trace SVG rendering (fan-in/fan-out lines per tube).
10. **Tray assignment is separate** — Assigning tube RearPorts to specific tray modules is a distinct concern handled in Phase 2. Phase 1 creates the ports; tray assignment can be done manually in NetBox's native UI until Phase 2 is built.
11. **Both cable ends tracked on FiberStrand** — `FiberStrand` gets `front_port_a` and `front_port_b` FKs, aligned to the cable's A-side and B-side CableTerminations. Avoids expensive trace queries to find a strand's port on the far end. Existing `front_port` field is renamed to `front_port_a` via migration; `front_port_b` is added as a new nullable FK.
12. **Port type selector for greenfield** — The Link Topology modal includes a port type dropdown (defaulting to `splice`) shown only in the greenfield path (no existing ports to adopt). This covers edge cases like patch panels using LC/SC connectors.

## Cable Topology Model

### How a fiber cable is represented in NetBox

A 12-tube × 12F loose tube cable (144 fibers total) entering a closure:

```
dcim.Cable (profile: trunk-12c12p)
  └─ 12 CableTerminations (one per tube, per side)
       └─ each terminates on a dcim.RearPort (12 positions)
            └─ dcim.PortMapping maps each position to a dcim.FrontPort
                 └─ FrontPort lives on a tray Module (splice position)
```

Plugin layer adds:
```
netbox_fms.FiberCable (1:1 with dcim.Cable)
  └─ netbox_fms.BufferTube instances (one per tube)
       └─ netbox_fms.FiberStrand instances (one per fiber)
            ├─ FiberStrand.front_port_a FK → dcim.FrontPort (A-side of cable)
            └─ FiberStrand.front_port_b FK → dcim.FrontPort (B-side of cable)
```

### Trunk vs. Single-connector profiles

The profile determines how NetBox's trace SVG renders the cable:

- **Trunk (e.g., `trunk-12c12p`):** 12 CableTerminations per side → 12 boxes in the SVG, fan-in/fan-out lines from cable center. Each tube is independently traceable. Tubes from one cable can land on different tray modules.
- **Single (e.g., `single-1c144p`):** 1 CableTermination per side → 1 box in the SVG, straight line. All 144 positions multiplex through one port. Only appropriate for tight-buffer / drop cables with no tube structure.

`get_cable_profile()` derives trunk profiles for cables with tubes, single-connector for cables without.

### When tubes land on different trays

A tray (Module) has a fixed splice capacity defined by its ModuleType (e.g., 48 FrontPort templates). Tubes from multiple cables can be assigned to the same tray:

```
Tray A (48 positions):
  ├─ Cable #1, Tube 1 (RearPort, 12 positions) → FrontPorts 1-12
  ├─ Cable #1, Tube 2 (RearPort, 12 positions) → FrontPorts 13-24
  ├─ Cable #2, Tube 1 (RearPort, 12 positions) → FrontPorts 25-36
  └─ Cable #2, Tube 2 (RearPort, 12 positions) → FrontPorts 37-48

Tray B (48 positions):
  ├─ Cable #1, Tube 3 (RearPort, 12 positions) → FrontPorts 1-12
  └─ ... etc.
```

Tray assignment (which tube RearPort goes on which tray Module) is Phase 2 scope. Phase 1 creates the RearPorts on the device without module assignment; users assign trays manually via NetBox UI.

## Architecture

### Cable Profile Registry

Expand `cable_profiles.py` with trunk profiles. All profiles (both `single-1cXp` above 16P and all `trunk-*` profiles) are plugin-defined and registered at startup via `monkey_patches.py`, which already extends `CableProfileChoices.CHOICES`, patches `Cable._meta.get_field("profile").choices`, and monkey-patches `Cable.profile_class` to include our profile classes. This mechanism is proven and in production.

```
Plugin-registered (single-connector, beyond NetBox's built-in 1-16P):
  single-1c24p, single-1c48p, single-1c72p, single-1c96p,
  single-1c144p, single-1c216p, single-1c288p, single-1c432p

New (multi-connector / trunk):
  trunk-2c12p, trunk-4c12p, trunk-6c12p, trunk-8c12p,
  trunk-12c12p, trunk-18c12p, trunk-24c12p
  trunk-2c24p, trunk-4c24p, trunk-6c24p, trunk-12c24p
```

Single-connector profiles define `a_connectors = {1: N}` (one connector, N positions).
Trunk profiles define `a_connectors = {1: P, 2: P, ..., C: P}` (C connectors, P positions each). `b_connectors = a_connectors` for all profiles (symmetric).

### FiberCableType.get_cable_profile()

Derives the profile key from the type's template topology. Uses `self.strand_count` (the declared model field) for types without tubes.

```
Template topology              →  Profile key
─────────────────────────────────────────────
No tubes, strand_count=6       →  "single-1c6p" (built-in NetBox)
No tubes, strand_count=48      →  "single-1c48p" (plugin-registered)
Central-core ribbon, no tubes  →  "single-1c{strand_count}p"
12 tubes × 12F each            →  "trunk-12c12p"
4 tubes × 12F each             →  "trunk-4c12p"
6 tubes × 24F each (ribbon)    →  "trunk-6c24p"
Topology not in registry       →  None
```

Logic:
1. Get all BufferTubeTemplates for this type.
2. If no tubes exist → `single-1c{self.strand_count}p` (covers tight-buffer and central-core ribbon).
3. If tubes exist → resolve each tube's effective fiber count using the per-tube `BufferTubeTemplate.get_total_fiber_count()` method (NOT the type-level `get_strand_count_from_templates()` which has a known bug with ribbon-in-tube — it sums only `fiber_count` and returns 0 for NULL values).
4. Check all tubes have equal effective fiber count. If yes → `trunk-{tube_count}c{fiber_count}p`.
5. If tubes have mixed effective fiber counts → `None` (no matching profile).
6. Look up result in `FIBER_CABLE_PROFILES` registry. Return key if found, `None` otherwise.

**Prerequisite fix:** `FiberCableType.get_strand_count_from_templates()` should be updated to use per-tube `get_total_fiber_count()` instead of `Sum("fiber_count")`, so it correctly counts ribbon-in-tube fibers. This affects the `clean()` validation. Include this fix in the implementation plan.

**Known gap:** The trunk profile list does not cover all real-world tube sizes (e.g., 6F or 8F micro-tubes). Per design decision #6, missing profiles produce a warning, not a blocker. The registry is expanded over time as needed.

### link_cable_topology() Service Function

Located in `services.py`. Single function used by both per-cable modal and future bulk action. Handles the core logic; the view layer handles confirmation UX separately.

```python
def link_cable_topology(cable, fiber_cable_type, device, port_type="splice", port_mapping=None):
    """
    Create FiberCable from a dcim.Cable and FiberCableType.
    Adopt existing RearPorts/FrontPorts or create new ones.
    Set cable profile if available.

    Args:
        cable: dcim.Cable instance
        fiber_cable_type: FiberCableType instance
        device: dcim.Device (the closure)
        port_type: port type for greenfield FrontPort/RearPort creation (default: "splice").
                   Ignored when adopting existing ports.
        port_mapping: optional dict {strand_position: frontport_id} for confirmed mapping.
                      If None and existing ports found, raises NeedsMappingConfirmation.

    Returns: (fiber_cable, warnings: list[str])
    Raises: NeedsMappingConfirmation (with proposed_mapping attribute) if existing
            ports found and no port_mapping provided.
    """
```

**Steps (execution order matters):**

1. **Detect pre-existing ports** — BEFORE creating anything, check if RearPorts on `device` are already terminated by this `cable` (via CableTermination → RearPort). If found, collect them and their mapped FrontPorts (via PortMapping, ordered by `rear_port_position`). These are ports from before the plugin — candidates for adoption.

2. **Handle confirmation gate** (adopt path only):
   - **Pre-existing ports found, no `port_mapping` provided:** Build a proposed position-based mapping (FiberStrand position → FrontPort by `rear_port_position`). Raise `NeedsMappingConfirmation(proposed_mapping=...)`. Nothing is created yet — the view shows the confirmation step.
   - **Pre-existing ports found, `port_mapping` provided:** Proceed with adoption (step 3+).
   - **No pre-existing ports (greenfield):** Proceed with creation (step 3+).

3. **Create FiberCable** linked to `cable` with the given `fiber_cable_type`. This triggers `_instantiate_components()` which creates BufferTubes, FiberStrands, etc.

4. **Set cable profile** — call `fiber_cable_type.get_cable_profile()`. If result is not None, set `cable.profile` and save. If None, add warning to return value.

5. **Determine cable side** — check which CableTermination side(s) for this `cable` terminate on `device`. This determines whether to set `front_port_a` or `front_port_b` on each strand (or both for loopback cables).

6. **Create or adopt ports:**
   - **Adopt path (pre-existing ports + confirmed `port_mapping`):** Link each FiberStrand to the FrontPort specified in `port_mapping` via the appropriate FK (`front_port_a` or `front_port_b` based on cable side). Do not create new RearPorts or FrontPorts. For count mismatches: surplus strands (more strands than FrontPorts) are left with the FK as NULL; surplus FrontPorts (more ports than strands) are ignored.
   - **Greenfield path (no pre-existing ports):** Create RearPorts — one per BufferTube (trunk), or one for the whole cable (no tubes / tight-buffer):
     - **Tubes exist:** For each BufferTube, create a RearPort on `device` (no module — Phase 2). Name: `#{cable.pk}:T{tube.position}`. Type: `port_type`. Positions: tube's fiber count.
     - **No tubes:** Create a single RearPort. Name: `#{cable.pk}`. Type: `port_type`. Positions: `strand_count`.
     - Create CableTerminations linking each new RearPort to the `dcim.Cable` on the appropriate side (A or B).
     - Create FrontPorts and PortMappings for each RearPort. Name: `#{cable.pk}:T{tube.position}:F{strand.position}` (or `#{cable.pk}:F{strand.position}` for no-tube cables). Type: `port_type`. Link each FiberStrand to its FrontPort via the appropriate FK.

   RearPort names use `cable.pk` (not `str(cable)`) to guarantee uniqueness per device — `Cable.__str__()` is not unique.

7. **Return** `(fiber_cable, warnings)`.

The function is wrapped in `@transaction.atomic` so partial failures roll back cleanly.

Note: when `NeedsMappingConfirmation` is raised in step 2, nothing has been created yet — no rollback needed. The view re-calls with `port_mapping` to execute steps 3-6.

### Confirmation Flow (View Layer)

The two-step confirmation lives entirely in the view, not the service function:

1. View calls `link_cable_topology(cable, fct, device)` — no `port_mapping`.
2. If `NeedsMappingConfirmation` is raised → render confirmation template with the proposed mapping. The FiberCable creation is rolled back (atomic transaction).
3. User confirms/adjusts mapping → view calls `link_cable_topology(cable, fct, device, port_mapping={...})` with the confirmed mapping.
4. If no existing ports (greenfield) → function completes in one call, no confirmation needed.

This keeps the service function clean and the confirmation UX in the view where it belongs.

### Fiber Overview Tab Changes

**Row grouping:** Currently one row per RearPort. With the tube-per-RearPort model, a single cable may have 12 RearPorts. The overview should group by **cable**, not by RearPort. Each row shows:
- Cable name/link
- FiberCable (if linked) with type
- Tube count / strand count
- Gland label
- Provisioning status (how many strands linked to FrontPorts)
- "Link Topology" button (if no FiberCable)

The `_build_cable_rows()` function changes from querying module-attached RearPorts to querying cables terminated on the device and looking up their FiberCable status.

### Fiber Overview Modal Flow

**Button:** "Link Topology" — shown on rows where cable exists but no FiberCable.

**Step 1 — Select FiberCableType (and port type if greenfield):**
- Dropdown to pick FiberCableType
- On selection, show: strand count, tube layout summary
- If no pre-existing ports detected (greenfield): show port type dropdown (default: `splice`). Hidden when adopting existing ports.
- If `get_cable_profile()` returns None: **red warning banner** — "No cable profile exists for this topology ({tube_count} tubes x {fiber_count} fibers). Cable trace will not work correctly — strand-level routing will be unavailable and trace diagrams may fail to render. Consider adding a matching profile before proceeding."
- Submit button: normal blue "Link" if profile exists, orange/red "Proceed Without Profile" if not

**Step 2 — Port mapping (conditional, only if pre-existing FrontPorts found for this cable):**
- Table showing: Strand position | Strand name | → | FrontPort name (matched by `rear_port_position`)
- Pre-filled by position matching
- User confirms or adjusts
- If count mismatch: warning + manual assignment UI

**On submit:** Calls `link_cable_topology()` with confirmed mapping. On success, row swaps in-place via HTMX.

### Permissions

`LinkTopologyView` requires `LoginRequiredMixin` and checks:
- `netbox_fms.add_fibercable` — to create the FiberCable
- `dcim.add_frontport` and `dcim.add_rearport` — for greenfield port creation

Same pattern as the current views.

### Unlink / Redo

If a user links the wrong FiberCableType, they delete the FiberCable via the standard NetBox delete view. On deletion:
- `FiberStrand.front_port_a` and `front_port_b` FKs are `SET_NULL` — adopted FrontPorts remain on the device untouched.
- `BufferTube`, `FiberStrand`, `Ribbon`, `CableElement` instances are cascade-deleted with the FiberCable.
- The `dcim.Cable`, its CableTerminations, and RearPorts/FrontPorts are NOT deleted (they're dcim objects, not owned by the plugin).
- The cable row returns to the "Link Topology" state.

No special "Unlink" button needed — standard delete handles it.

### ClosureCableEntry

The Link Topology flow does NOT create a `ClosureCableEntry`. Gland label assignment remains a separate action via the "Edit Gland Label" modal (kept unchanged). This keeps the Link Topology action focused on one concern.

### Cable Sides (A/B)

A cable has two termination sides. Link Topology operates **per-device** — it creates/adopts ports on the current closure only. The same cable's other end may be on a different closure, which gets its own Link Topology action when viewed from that device's Fiber Overview tab.

A single `FiberCable` instance covers both sides (it's linked to the `dcim.Cable`, not to a device). `FiberStrand` has two FKs — `front_port_a` and `front_port_b` — aligned to the cable's A-side and B-side CableTerminations respectively. Both are nullable SET_NULL FKs. When Link Topology runs on a device:

1. Determine which cable side(s) terminate on this device by checking CableTerminations.
2. If A-side terminates here → set `front_port_a` on each strand.
3. If B-side terminates here → set `front_port_b` on each strand.

This means a FiberCable can be "half-linked" — topology defined on one closure but not yet on the other. The Fiber Overview tab should show this state clearly (e.g., "A-side linked, B-side pending").

For loopback cables (both ends on the same device), both `front_port_a` and `front_port_b` are set in a single Link Topology action.

## Implementation Phases

### Phase 1: Link Topology (this spec)
- Cable profile registry expansion (trunk profiles)
- `FiberCableType.get_cable_profile()` method
- `link_cable_topology()` service function
- `LinkTopologyView` + modal templates
- Fiber Overview tab row changes (group by cable)
- Remove old Create FiberCable / Provision Strands views
- RearPorts created without module assignment

### Phase 2: Tray Assignment
- UI for assigning tube RearPorts to specific tray modules
- Tray capacity awareness (ModuleType defines splice capacity)
- Validation that tray isn't over-subscribed
- Separate spec

### Phase 3: Bulk "Link All Cables"
- Top-level button on Fiber Overview tab
- Table of all unlinked cables with FiberCableType dropdown per row
- Calls `link_cable_topology()` per cable with auto-apply
- Separate spec

## What Changes (Phase 1)

### New
- `FiberStrand.front_port_a` and `front_port_b` FKs (rename existing `front_port` → `front_port_a`, add `front_port_b`) + migration
- Trunk cable profile classes in `cable_profiles.py`
- `FiberCableType.get_cable_profile()` method on model
- `NeedsMappingConfirmation` exception class
- `link_cable_topology()` service function in `services.py`
- `propose_port_mapping()` helper (builds position-based mapping proposal)
- `LinkTopologyView` — HTMX modal view replacing old create/provision views
- `LinkTopologyForm` — form for FiberCableType selection
- `link_topology_modal.html` — modal template with profile warning
- `link_topology_confirm.html` — port mapping confirmation template (step 2)

### Modified
- `models.py` — `FiberCableType.get_strand_count_from_templates()` fixed to handle ribbon-in-tube (prerequisite)
- `models.py` — all references to `front_port` updated to `front_port_a` / `front_port_b`
- `cable_profiles.py` — expanded registry with trunk profiles
- `monkey_patches.py` — registers trunk profiles alongside single-connector ones
- `fiber_overview_row.html` — single "Link Topology" button replaces two old buttons
- `device_fiber_overview.html` — row grouping by cable instead of by RearPort
- `urls.py` — new URL for link-topology action, remove old create-fibercable and provision-strands URLs
- `_build_cable_rows()` in `views.py` — rewritten to group by cable, detect FiberCable status

### Removed
- `CreateFiberCableFromCableView`
- `ProvisionStrandsFromOverviewView`
- `CreateFiberCableFromCableForm`
- `ProvisionStrandsFromOverviewForm`
- `create_fiber_cable_modal.html`
- `provision_strands_modal.html`

### Kept (unchanged)
- Standalone `/provision-ports/` page and `ProvisionPortsView` — retained for non-closure devices (patch panels, etc.) that don't have pre-existing FrontPorts
- `provision_strands()` helper function (used by standalone page)
- Edit Gland Label modal
- All existing model classes

## Testing Strategy

- **Unit tests for `get_cable_profile()`** — verify derivation for all topology patterns: loose tube, ribbon-in-tube (tubes with `fiber_count=None` and child RibbonTemplates), central-core ribbon, tight buffer, mixed tube sizes, topology not in registry
- **Unit tests for trunk profile classes** — verify `a_connectors` / `b_connectors` match expected shape
- **Unit tests for `link_cable_topology()`** — test adopt path (existing ports), greenfield path (no ports), count mismatch, profile-not-found warning, `NeedsMappingConfirmation` raise, multi-tube RearPort creation
- **Integration tests for the modal** — test the full HTMX flow with authenticated user: step 1 submission, step 2 confirmation, greenfield (no step 2)
- **Integration tests for profile registration** — verify monkey-patch registers all trunk profiles correctly at startup
- **Regression** — verify standalone provision-ports page still works
