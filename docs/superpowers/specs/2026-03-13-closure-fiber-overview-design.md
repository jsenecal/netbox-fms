# Closure Fiber Overview Tab — Design Spec

> **Date:** 2026-03-13
> **Status:** Draft
> **Builds on:** Unified splice visualization (2026-03-13)

## Goal

Add a "Fiber Overview" tab to devices acting as splice closures. The tab surfaces the fiber management layer — FiberCable status, strand provisioning, gland labels, and splice plan status — with contextual modal actions. Simultaneously clean up the plugin navigation by removing items that are better accessed contextually.

## Architecture

A new device tab registered via `@register_model_view`. The view queries connected cables, FiberCables, FiberStrands, ClosureCableEntries, and SplicePlan to build a summary. Three modal actions (Create FiberCable, Provision Strands, Edit Gland Label) are powered by lightweight API endpoints that reuse existing business logic. The ClosureCableEntry model is simplified: `entrance_port` FK is replaced with a plain `entrance_label` CharField.

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

**Migration:** Drop `entrance_port` FK, add `entrance_label`. Update `unique_together` from `(closure, entrance_port)` to `(closure, fiber_cable)` (one entry per cable per closure). Update `ordering` to `(closure, entrance_label)`. Update `__str__` to use `entrance_label`.

**Forms:** Update `ClosureCableEntryForm` — remove `entrance_port`, add `entrance_label`. Keep the form for the standalone CRUD views (they stay functional, just removed from nav).

**Serializer:** Update `ClosureCableEntrySerializer` — same field swap.

### No new models.

---

## 2. Fiber Overview Tab

### View: `DeviceFiberOverviewView`

Registered as `@register_model_view(Device, "fiber_overview", path="fiber-overview")`.

**Tab config:**
- Label: "Fiber Overview"
- Visibility: same function as Splice Editor tab (`_device_has_splice_plan_or_fiber_cables`)
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

Each row represents a `dcim.Cable` connected to a RearPort on this device (specifically module-attached RearPorts, since those are tray attachment points).

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
| FiberCable exists, strands not provisioned | "Provision Strands" button |
| FiberCable exists, strands provisioned | Checkmark (done) |
| Any row | Pencil icon to edit gland label |

**Splice plan section** (bottom):
- If plan exists: name, status badge, entry count, link to plan detail, link to Splice Editor tab
- If no plan: "No splice plan" + "Create Plan" link (to standard SplicePlan add form with closure pre-filled)

---

## 3. View Implementation

### `DeviceFiberOverviewView.get()`

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

## 4. Modal Actions

All three modals use the same pattern: a Bootstrap 5 modal loaded inline on the overview page. Form submission via standard POST (not AJAX) that redirects back to the overview tab on success. This keeps things simple — no custom JS needed, just Django form handling.

### 4.1 Create FiberCable

**Trigger:** "Create FiberCable" button on a cable row.

**URL:** `POST /plugins/netbox-fms/fiber-overview/<device_pk>/create-fiber-cable/`

**Form fields:**
- `cable_id` — hidden, pre-filled from the row
- `fiber_cable_type` — DynamicModelChoiceField (FiberCableType)
- `name` — CharField, pre-filled with cable label

**Logic:**
1. Validate FiberCableType selected
2. Create `FiberCable(cable=cable, fiber_cable_type=type, name=name)`
3. FiberCable's `save()` auto-instantiates strands via `_instantiate_components()`
4. Redirect back to fiber overview tab

**View:** `CreateFiberCableFromCableView(View)` — handles GET (return form HTML fragment for modal) and POST.

### 4.2 Provision Strands

**Trigger:** "Provision Strands" button on a FiberCable row.

**URL:** `POST /plugins/netbox-fms/fiber-overview/<device_pk>/provision-strands/`

**Form fields:**
- `fiber_cable_id` — hidden, pre-filled from the row
- `target_module` — DynamicModelChoiceField (Module, filtered to this device)
- `port_type` — ChoiceField (LC, SC, MPO, etc.), default "splice"

**Logic:** Reuses `ProvisionPortsView._provision()` logic — creates RearPort on target module, FrontPorts per strand, PortMappings, links FiberStrand.front_port.

**Note:** The existing `_provision()` creates ports on the device level. For the overview modal, we should provision ports on the **module** (tray) instead. This means FrontPorts get `module=target_module` set. The existing logic needs a small modification to accept an optional module parameter.

**View:** `ProvisionStrandsView(View)` — handles GET and POST.

### 4.3 Edit Gland Label

**Trigger:** Pencil icon on any row with a FiberCable.

**URL:** `POST /plugins/netbox-fms/fiber-overview/<device_pk>/update-gland/`

**Form fields:**
- `fiber_cable_id` — hidden
- `entrance_label` — CharField

**Logic:** Creates or updates `ClosureCableEntry` for this closure+fiber_cable pair.

**View:** `UpdateGlandLabelView(View)` — handles POST only.

---

## 5. Template Structure

### `device_fiber_overview.html`

```
{% extends 'dcim/device/base.html' %}

Card: "Fiber Management Summary"
├── Stats bar: trays | cables | fiber cables | strands | plan status
├── Table: cable rows with status and action buttons
│   └── Each action button opens a Bootstrap modal (pre-rendered in template)
└── Splice Plan section: status + links

Modal: #createFiberCableModal
├── Form with fiber_cable_type + name fields
└── Submit → POST to create-fiber-cable view

Modal: #provisionStrandsModal
├── Form with target_module + port_type fields
└── Submit → POST to provision-strands view

Modal: #editGlandModal
├── Form with entrance_label field
└── Submit → POST to update-gland view
```

Modals are standard Bootstrap 5 modals rendered in the template. Each action button sets hidden field values via `data-*` attributes and a small inline script before showing the modal.

---

## 6. URL Patterns

### New plugin URLs (`urls.py`)

| URL | View | Name |
|-----|------|------|
| `fiber-overview/<int:pk>/create-fiber-cable/` | `CreateFiberCableFromCableView` | `fiber_overview_create_fibercable` |
| `fiber-overview/<int:pk>/provision-strands/` | `ProvisionStrandsView` | `fiber_overview_provision_strands` |
| `fiber-overview/<int:pk>/update-gland/` | `UpdateGlandLabelView` | `fiber_overview_update_gland` |

The overview tab itself is auto-registered by `@register_model_view`.

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

- **Create FiberCable:** If FiberCable already exists for that cable, show error message and redirect back.
- **Provision Strands:** If strands already provisioned on this device, show error. If no strands on the FiberCable, show error.
- **Edit Gland Label:** Simple upsert, unlikely to fail. Validate label length.
- **Tab visibility:** If device has no modules and no fiber cables, tab doesn't appear. Once user adds a module or connects a fiber cable, tab becomes visible.

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
- Modal open/close/submit flow
- Redirect back to overview tab after each action
