# Closure Fiber Overview Tab — Design Spec

> **Date:** 2026-03-13
> **Status:** Draft
> **Builds on:** Unified splice visualization (2026-03-13)

## Goal

Add a "Fiber Overview" tab to devices acting as splice closures. The tab surfaces the fiber management layer — FiberCable status, strand provisioning, gland labels, and splice plan status — with contextual modal actions. Simultaneously clean up the plugin navigation by removing items that are better accessed contextually.

## Architecture

A new device tab registered via `@register_model_view`. The view queries connected cables, FiberCables, FiberStrands, ClosureCableEntries, and SplicePlan to build a summary. Three modal actions (Create FiberCable, Provision Strands, Edit Gland Label) use HTMX — modals are loaded on demand via `hx-get`, forms submit via `hx-post`. NetBox 4.x ships HTMX, so no extra dependency. The ClosureCableEntry model is simplified: `entrance_port` FK is replaced with a plain `entrance_label` CharField.

---

## 1. Data Model Changes

### Modified: `ClosureCableEntry`

| Field | Before | After |
|-------|--------|-------|
| `closure` | FK to Device | *unchanged* |
| `fiber_cable` | FK to FiberCable | *unchanged* |
| `entrance_port` | FK to RearPort | **removed** |
| `entrance_label` | — | **new** CharField(max_length=100, blank=True) — free-text gland name |
| `notes` | TextField | *unchanged* |

**Migration:** Three-step migration:
1. **Schema migration:** Add `entrance_label` CharField while keeping `entrance_port` FK.
2. **Data migration:** For each existing `ClosureCableEntry` with `entrance_port` set, copy `entrance_port.name` into `entrance_label`.
3. **Schema migration:** Drop `entrance_port` FK. Update `unique_together` from `(closure, entrance_port)` to `(closure, fiber_cable)`. Update `ordering` to `(closure, entrance_label)`. Update `__str__` to use `entrance_label`.

**Forms:** Update `ClosureCableEntryForm` — remove `entrance_port`, add `entrance_label`. Keep the form for the standalone CRUD views (they stay functional, just removed from nav).

**Serializer:** Update `ClosureCableEntrySerializer` — same field swap.

### No new models.

---

## 2. Fiber Overview Tab

### View: `DeviceFiberOverviewView`

Registered as `@register_model_view(Device, "fiber_overview", path="fiber-overview")`.

**Tab config:**
- Label: "Fiber Overview"
- Visibility: new function `_device_has_modules_or_fiber_cables` — returns True if device has any modules (trays) OR any FiberCables connected via cables on its RearPorts. This differs from the Splice Editor's visibility function because the Fiber Overview is specifically about the module/tray-based fiber management layer.
- Weight: 1400 (before Splice Editor at 1500)

**Template:** `netbox_fms/templates/netbox_fms/device_fiber_overview.html`

### What it shows

**Summary stats bar** (top of card):
- Trays: count of Modules on device
- Cables connected: count of dcim.Cables terminating on device RearPorts
- FiberCables: count linked to those cables
- Strands provisioned: count of FiberStrands with `front_port` set on this device
- Splice plan: status badge or "None"

**Cable/Fiber status table:**

Each row represents a `dcim.Cable` connected to a RearPort on this device (specifically module-attached RearPorts, since those are tray attachment points). Device-level RearPorts (without a module) are not part of the fiber management layer and are excluded.

| Column | Source |
|--------|--------|
| Cable | `dcim.Cable` label, link to cable detail |
| Tray (RearPort) | Module name + RearPort name the cable connects to |
| FiberCable | Link to FiberCable if exists, or "—" |
| Gland | `ClosureCableEntry.entrance_label` if set, or "—" |
| Strands | "X/Y provisioned" (FiberStrands with front_port set / total strands) |
| Actions | Contextual buttons based on state |

**Action logic per row:**

| State | Action shown |
|-------|-------------|
| Cable connected, no FiberCable | "Create FiberCable" button |
| FiberCable exists, strands not provisioned on this device | "Provision Strands" button |
| FiberCable exists, strands provisioned | Checkmark (done) |
| Any row with a FiberCable | Pencil icon to edit gland label |

**Splice plan section** (bottom):
- If plan exists: name, status badge, entry count, link to plan detail, link to Splice Editor tab
- If no plan: "No splice plan" + "Create Plan" link (to standard SplicePlan add form with closure pre-filled)

---

## 3. View Implementation

### `DeviceFiberOverviewView.get()` — Reference Implementation

```python
def get(self, request, pk):
    device = get_object_or_404(Device, pk=pk)

    # Get cables connected to module RearPorts on this device
    from dcim.models import CableTermination, RearPort
    from django.contrib.contenttypes.models import ContentType

    rp_ct = ContentType.objects.get_for_model(RearPort)
    module_rearports = RearPort.objects.filter(
        device=device, module__isnull=False
    ).select_related("module")

    # For each RearPort, find connected cable
    cable_rows = []
    for rp in module_rearports:
        term = CableTermination.objects.filter(
            termination_type=rp_ct,
            termination_id=rp.pk,
        ).select_related("cable").first()

        cable = term.cable if term else None
        fiber_cable = None
        strand_info = None
        gland_entry = None

        if cable:
            fiber_cable = FiberCable.objects.filter(cable=cable).first()
            if fiber_cable:
                total = fiber_cable.fiber_strands.count()
                provisioned = fiber_cable.fiber_strands.filter(
                    front_port__device=device
                ).count()
                strand_info = {"provisioned": provisioned, "total": total}
                gland_entry = ClosureCableEntry.objects.filter(
                    closure=device, fiber_cable=fiber_cable
                ).first()

        cable_rows.append({
            "rearport": rp,
            "cable": cable,
            "fiber_cable": fiber_cable,
            "strand_info": strand_info,
            "gland_entry": gland_entry,
        })

    # SplicePlan.closure is a OneToOneField — at most one plan per device
    plan = SplicePlan.objects.filter(closure=device).first()

    # Summary stats
    stats = {
        "tray_count": device.modules.count(),
        "cable_count": sum(1 for r in cable_rows if r["cable"]),
        "fiber_cable_count": sum(1 for r in cable_rows if r["fiber_cable"]),
        "strand_provisioned": sum(
            r["strand_info"]["provisioned"] for r in cable_rows if r["strand_info"]
        ),
        "strand_total": sum(
            r["strand_info"]["total"] for r in cable_rows if r["strand_info"]
        ),
    }

    return render(request, "netbox_fms/device_fiber_overview.html", {
        "object": device,
        "device": device,
        "cable_rows": cable_rows,
        "plan": plan,
        "stats": stats,
        "tab": self.tab,
    })
```

---

## 4. Modal Actions (HTMX)

All three modals use HTMX. Action buttons use `hx-get` to fetch a modal form fragment from the server. The form inside the modal submits via `hx-post`. No modals are pre-rendered in the page template — they are loaded on demand into a shared `<div id="modal-container">` target.

**HTMX pattern:**
- Button: `hx-get="<form-url>?cable_id=X"` `hx-target="#modal-container"` `hx-swap="innerHTML"`
- Server GET returns: a complete Bootstrap 5 modal `<div class="modal">` with form inside
- Form: `hx-post="<action-url>"` with `{% csrf_token %}`
- A small inline script at the end of the fragment calls `new bootstrap.Modal(el).show()`

**Post-action response strategy:**
- **Create FiberCable / Provision Strands:** These change multiple pieces of state (stats, row status, new objects). Server returns `HX-Redirect` header pointing to the overview tab — full page reload guarantees consistent state.
- **Edit Gland Label:** Only changes one cell. Server returns the updated table row HTML fragment. The form uses `hx-target="closest tr"` `hx-swap="outerHTML"` to swap the row in-place (no page reload). This requires a row partial template.

**Permissions:** All action views require `LoginRequiredMixin`. Create FiberCable requires `netbox_fms.add_fibercable`. Provision Strands requires `dcim.add_frontport`. Edit Gland Label requires `netbox_fms.add_closurecableentry` and `netbox_fms.change_closurecableentry`. Action buttons are hidden in the template when the user lacks the corresponding permission.

**Error handling in modals:** For Create FiberCable and Provision Strands, the form's `hx-post` targets `#modal-container` (same as the GET). On validation error, the POST view re-renders the modal form HTML with error messages and returns it (200, not redirect). HTMX swaps the modal content, keeping the modal open with errors visible.

For Edit Gland Label, the form's `hx-post` targets `closest tr` on success, which conflicts with error responses. To handle this: on validation error, return the modal form fragment with `HX-Retarget: #modal-container` and `HX-Reswap: innerHTML` response headers. HTMX will override the form's target and swap the error form back into the modal container. On success, return the row fragment normally (targeting `closest tr`).

### 4.1 Create FiberCable

**Trigger:** "Create FiberCable" button on a cable row.

**GET URL:** `/plugins/netbox-fms/fiber-overview/<device_pk>/create-fiber-cable/?cable_id=<id>`
**POST URL:** `/plugins/netbox-fms/fiber-overview/<device_pk>/create-fiber-cable/`

**Form fields:**
- `cable_id` — hidden, pre-filled from query param
- `fiber_cable_type` — DynamicModelChoiceField (FiberCableType)

**Logic:**
1. **Pre-condition check (GET):** If a FiberCable already exists for this cable, the GET view returns the modal with an info message ("FiberCable already exists for this cable") and no form. This prevents the user from submitting a duplicate.
2. Validate FiberCableType selected
3. Wrap in `@transaction.atomic`: Create `FiberCable(cable=cable, fiber_cable_type=type, name=name)`. FiberCable's `save()` auto-instantiates strands via `_instantiate_components()`. If instantiation fails, the entire transaction rolls back.
4. Return `HX-Redirect` to fiber overview tab

**View:** `CreateFiberCableFromCableView(LoginRequiredMixin, View)` — GET returns modal fragment, POST processes form.

**Template:** `netbox_fms/htmx/create_fiber_cable_modal.html` — modal with form.

### 4.2 Provision Strands

**Trigger:** "Provision Strands" button on a FiberCable row.

**GET URL:** `/plugins/netbox-fms/fiber-overview/<device_pk>/provision-strands/?fiber_cable_id=<id>`
**POST URL:** `/plugins/netbox-fms/fiber-overview/<device_pk>/provision-strands/`

**Form fields:**
- `fiber_cable_id` — hidden, pre-filled from query param
- `target_module` — DynamicModelChoiceField (Module, filtered to this device). Pre-filled with the module of the RearPort the cable terminates on (if any). The user may select a different module if they want strands provisioned on a different tray than where the cable physically connects.
- `port_type` — ChoiceField (LC, SC, MPO, etc.), default "splice"

**Logic:** Wrapped in `@transaction.atomic`. Reuses the provisioning logic from `ProvisionPortsView.post()`. That method must be refactored: extract the core logic into a helper function (e.g., `_provision_strands(fiber_cable, device, module, port_type)`) that both the existing view and this new view can call. The helper creates a RearPort on the target module, FrontPorts per strand, PortMappings, and links `FiberStrand.front_port`.

**Note:** The existing logic creates ports at device level. For the overview modal, when `module` is provided, all created objects — RearPort, FrontPorts, and PortMappings — should be created with `module=target_module` (in addition to `device=device`, which NetBox requires regardless). The refactored helper accepts an optional `module` parameter.

**Post-action:** Return `HX-Redirect` to fiber overview tab.

**View:** `ProvisionStrandsView(LoginRequiredMixin, View)` — GET returns modal fragment, POST processes form.

**Template:** `netbox_fms/htmx/provision_strands_modal.html` — modal with form.

### 4.3 Edit Gland Label

**Trigger:** Pencil icon on any row with a FiberCable.

**GET URL:** `/plugins/netbox-fms/fiber-overview/<device_pk>/update-gland/?fiber_cable_id=<id>`
**POST URL:** `/plugins/netbox-fms/fiber-overview/<device_pk>/update-gland/`

**Form fields:**
- `fiber_cable_id` — hidden, pre-filled from query param
- `entrance_label` — CharField, pre-filled with current value if exists

**Logic:** Creates or updates `ClosureCableEntry` for this closure+fiber_cable pair.

**Post-action:** Dismiss modal (via `HX-Trigger: modalClose` event + listener) and return the updated table row HTML using the row partial template. The `hx-post` on the form uses `hx-target="closest tr"` `hx-swap="outerHTML"` to swap in-place.

**View:** `UpdateGlandLabelView(LoginRequiredMixin, View)` — GET returns modal fragment, POST returns updated row.

**Templates:**
- `netbox_fms/htmx/edit_gland_modal.html` — modal with form
- `netbox_fms/htmx/fiber_overview_row.html` — single `<tr>` partial, shared with the main table rendering

---

## 5. Template Structure

### `device_fiber_overview.html`

```
{% extends 'dcim/device/base.html' %}

Card: "Fiber Management Summary"
├── Stats bar: trays | cables | fiber cables | strands | plan status
├── Table: cable rows (each row uses fiber_overview_row.html partial via {% include %})
│   └── Action buttons with hx-get to load modal forms on demand
├── Splice Plan section: status + links
└── <div id="modal-container"></div>  ← HTMX modal target
```

### `htmx/fiber_overview_row.html`

Single `<tr>` partial template. Used by:
- The main table (via `{% include %}` in a loop)
- The gland label update response (returned directly to swap a row in-place)

**Required context:** The row partial needs `device`, `row` (dict with `rearport`, `cable`, `fiber_cable`, `strand_info`, `gland_entry`), and `perms` (user permissions). Both the main view and `UpdateGlandLabelView.post()` must provide this context. Extract a shared helper `_build_cable_row(device, rearport)` that returns the row dict, used by both views.

### `htmx/create_fiber_cable_modal.html`
### `htmx/provision_strands_modal.html`
### `htmx/edit_gland_modal.html`

Each is a complete Bootstrap 5 `<div class="modal">` with a form inside. Loaded into `#modal-container` via `hx-get`. Includes a small `<script>` at the bottom to auto-show the modal on load. Forms use `hx-post` for submission.

---

## 6. URL Patterns

### New plugin URLs (`urls.py`)

| URL | Methods | View | Name |
|-----|---------|------|------|
| `fiber-overview/<int:pk>/create-fiber-cable/` | GET, POST | `CreateFiberCableFromCableView` | `fiber_overview_create_fibercable` |
| `fiber-overview/<int:pk>/provision-strands/` | GET, POST | `ProvisionStrandsView` | `fiber_overview_provision_strands` |
| `fiber-overview/<int:pk>/update-gland/` | GET, POST | `UpdateGlandLabelView` | `fiber_overview_update_gland` |

The overview tab itself is auto-registered by `@register_model_view`.

**Note:** These URL names are feature-namespaced (`fiber_overview_*`) rather than model-namespaced (`fibercable_*`) because they are contextual actions on a device tab, not standard model CRUD operations.

---

## 7. Navigation Changes

### Remove from plugin menu (`navigation.py`):

- "Splice Entries" (`spliceplanentry_list`)
- "Cable Entries" (`closurecableentry_list`)
- "Provision Ports" (`provision_ports`)

### Keep:

- Cable Types → Fiber Cable Types
- Fiber Cables → Fiber Cables
- Splice Planning → Splice Projects, Splice Plans
- Loss Budget → Fiber Path Losses

### Resulting menu structure:

```
FMS
├── Cable Types
│   └── Fiber Cable Types [List, +Add, +Import]
├── Fiber Cables
│   └── Fiber Cables [List, +Add, +Import]
├── Splice Planning
│   ├── Splice Projects [List, +Add]
│   └── Splice Plans [List, +Add]
└── Loss Budget
    └── Fiber Path Losses [List, +Add]
```

The removed views/URLs remain functional for direct linking and API access. Only the menu entries are removed.

---

## 8. Error Handling

- **Create FiberCable:** Pre-condition checked on GET — if FiberCable already exists, modal shows info message with no form (prevents duplicate submission).
- **Provision Strands:** If strands already provisioned on this device, show error. If no strands on the FiberCable, show error.
- **Edit Gland Label:** Simple upsert, unlikely to fail. Validate label length.
- **Tab visibility:** Controlled by `_device_has_modules_or_fiber_cables` — if device has no modules and no connected fiber cables, tab doesn't appear.

**Note on "strands provisioned":** This count reflects FiberStrand.front_port assignment (port provisioning), which is distinct from the live splice state tracked in the unified splice visualization spec. Provisioning means strands have FrontPorts on this device; splicing means those FrontPorts are connected to each other.

---

## 9. Testing Strategy

### Python tests

- `test_fiber_overview_tab_visibility` — tab shows for closures, hidden for plain devices
- `test_fiber_overview_stats` — correct counts for trays, cables, strands
- `test_create_fiber_cable_action` — creates FiberCable from connected cable
- `test_provision_strands_action` — provisions FrontPorts on target module
- `test_update_gland_label` — creates/updates ClosureCableEntry
- `test_closure_cable_entry_migration` — entrance_port dropped, entrance_label added
- `test_navigation_cleanup` — removed items not in menu

### Manual verification

- Visual check of summary table states and action buttons
- HTMX modal load/submit flow (verify modal appears, form submits)
- Create/Provision: verify HX-Redirect reloads the page with updated state
- Edit Gland Label: verify row swaps in-place without page reload
- Error state: verify modal stays open with validation errors on bad input
