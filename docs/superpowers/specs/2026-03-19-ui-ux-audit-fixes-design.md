# UI/UX Audit Fixes — Design Spec

**Date:** 2026-03-19
**Scope:** Bug fixes, detail page improvements, navigation polish, JS cleanup

---

## 1. Bug Fixes

### 1a. SplicePlanEntry detail template (`spliceplanentry.html`)

**Problem:** Template references `mode_override` and `cable` fields that no longer exist on the model. Missing actual fields `tray` and `is_express`.

**Fix:**
- Remove `mode_override` row and `cable` row
- Add `tray` row (linkify to Module)
- Add `is_express` row (yes/no boolean display)
- Move `notes` to right column card (conditionally shown)

### 1b. Splice plan status badges

**Problem:** `device_fiber_overview.html` uses `bg-{{ plan.status }}` which resolves to invalid Bootstrap classes like `bg-draft`, `bg-pending_review`. Badges render with no background color.

**Fix:** Create `templates/netbox_fms/inc/splice_plan_status_badge.html` include that maps:
- `draft` → `bg-secondary`
- `pending_review` → `bg-warning text-dark`
- `ready_to_apply` → `bg-info`
- `applied` → `bg-success`

Use in:
- `device_fiber_overview.html` (lines 31, 78)
- `device_splice_editor.html` (line 22)

Note: `spliceplan.html` uses `{{ object.get_status_display }}` as plain text and does NOT need this fix.

### 1c. FiberStrand detail template (`fiberstrand.html`)

**Problem:** Missing `ribbon`, `front_port_a`, `front_port_b` fields — the most operationally important fields.

**Fix:** Add rows for:
- `ribbon` (linkify with placeholder)
- `front_port_a` (linkify with placeholder)
- `front_port_b` (linkify with placeholder)

### 1d. FiberCable detail — tabbed component views

**Problem:** All 4 component tables (tubes, ribbons, strands, elements) are dumped on a single page. Empty tables shown for irrelevant construction types.

**Fix:** Use NetBox's `@register_model_view` + `ViewTab` + `ObjectChildrenView` pattern — the same architecture already used for FiberCableType component tabs (lines 153-209 in `views.py`).

**Prerequisite:** Add `@register_model_view(FiberCable)` decorator to `FiberCableView` (currently missing — tabs won't work without it). Compare with `FiberCableTypeView` which already has this decorator.

**New imports needed in views.py:** `BufferTubeFilterSet`, `RibbonFilterSet`, `CableElementFilterSet` (already exist in `filters.py` but not imported in `views.py`).

**New base class** (mirrors existing `FiberCableTypeComponentsView` exactly):
```python
class FiberCableComponentsView(generic.ObjectChildrenView):
    queryset = FiberCable.objects.all()
    actions = (EditObject, DeleteObject, BulkDelete)
    viewname = None

    def get_children(self, request, parent):
        return self.child_model.objects.restrict(request.user, "view").filter(fiber_cable=parent)

    def get_extra_context(self, request, instance):
        return {
            "return_url": reverse(self.viewname, kwargs={"pk": instance.pk}),
        }
```

**New registered views:**
```python
@register_model_view(FiberCable, "buffertubes", path="buffer-tubes")
class FiberCableBufferTubesView(FiberCableComponentsView):
    child_model = BufferTube
    table = BufferTubeTable
    filterset = BufferTubeFilterSet
    viewname = "plugins:netbox_fms:fibercable_buffertubes"
    tab = ViewTab(
        label=_("Buffer Tubes"),
        badge=lambda obj: obj.buffer_tubes.count(),
        permission="netbox_fms.view_buffertube",
        weight=500,
        hide_if_empty=True,
    )

@register_model_view(FiberCable, "ribbons", path="ribbons")
class FiberCableRibbonsView(FiberCableComponentsView):
    child_model = Ribbon
    table = RibbonTable
    filterset = RibbonFilterSet
    viewname = "plugins:netbox_fms:fibercable_ribbons"
    tab = ViewTab(
        label=_("Ribbons"),
        badge=lambda obj: obj.ribbons.count(),
        permission="netbox_fms.view_ribbon",
        weight=510,
        hide_if_empty=True,
    )

@register_model_view(FiberCable, "strands", path="strands")
class FiberCableStrandsView(FiberCableComponentsView):
    child_model = FiberStrand
    table = FiberStrandTable
    filterset = FiberStrandFilterSet
    viewname = "plugins:netbox_fms:fibercable_strands"
    tab = ViewTab(
        label=_("Fiber Strands"),
        badge=lambda obj: obj.fiber_strands.count(),
        permission="netbox_fms.view_fiberstrand",
        weight=520,
    )

@register_model_view(FiberCable, "cableelements", path="cable-elements")
class FiberCableCableElementsView(FiberCableComponentsView):
    child_model = CableElement
    table = CableElementTable
    filterset = CableElementFilterSet
    viewname = "plugins:netbox_fms:fibercable_cableelements"
    tab = ViewTab(
        label=_("Cable Elements"),
        badge=lambda obj: obj.cable_elements.count(),
        permission="netbox_fms.view_cableelement",
        weight=530,
        hide_if_empty=True,
    )
```

**Template change:** `fibercable.html` is simplified — remove the 4 inline table sections. The detail page shows only the two-column card layout (Cable info + Identification). Tabs are auto-generated by NetBox's `@register_model_view`.

**URL change:** None needed — the existing `path("fiber-cables/<int:pk>/", include(get_model_urls("netbox_fms", "fibercable")))` already handles registered views.

**View cleanup:** Remove the `tubes_table`, `ribbons_table`, `strands_table`, `elements_table` from `FiberCableView.get_extra_context` (no longer needed — each tab has its own view).

---

## 2. UX Improvements — Detail Pages

### 2a. Sparse detail pages — add right-column content

| Template | Right column additions |
|---|---|
| `buffertube.html` | Fiber strands table (children of this tube) |
| `fiberstrand.html` | Port assignments section (front_port_a/b with device links) |
| `cableelement.html` | Parent FiberCable link in right column |
| `spliceplanentry.html` | Notes card (if present) |
| `closurecableentry.html` | Strand summary card (linked/total count for strands of this fiber cable at the closure) — added above the existing notes card |

**View changes needed:**
- `BufferTubeView` — Override `get_extra_context` to pass `strands_table` (FiberStrandTable filtered to this tube).
- `ClosureCableEntryView` — Override `get_extra_context` to pass strand count data (avoids N+1 template queries).
- No view change needed for `fiberstrand`, `cableelement`, `spliceplanentry` — data available via `object` relations in template.

### 2b. FiberCableType detail — instances tab

**Problem:** Type detail shows blueprint properties but no table of FiberCable instances using that type.

**Fix:** Register a new child tab view using the existing `ObjectChildrenView` pattern (consistent with the Buffer Tubes / Ribbons / Cable Elements tabs already on FiberCableType):

```python
@register_model_view(FiberCableType, "instances", path="instances")
class FiberCableTypeInstancesView(generic.ObjectChildrenView):
    queryset = FiberCableType.objects.all()
    child_model = FiberCable
    table = FiberCableTable
    tab = ViewTab(
        label=_("Instances"),
        badge=lambda obj: FiberCable.objects.filter(fiber_cable_type=obj).count(),
        weight=530,
        hide_if_empty=True,
    )

    def get_children(self, request, parent):
        return FiberCable.objects.restrict(request.user, "view").filter(fiber_cable_type=parent)
```

No template change needed — `ObjectChildrenView` auto-renders the table.

### 2c. "Provision Ports" button on FiberCable detail

Add button in `{% block extra_controls %}` on `fibercable.html`:
```html
{% if perms.dcim.add_frontport %}
<a href="{% url 'plugins:netbox_fms:provision_ports' %}?fiber_cable={{ object.pk }}"
   class="btn btn-outline-primary">
    <i class="mdi mdi-ethernet"></i> Provision Ports
</a>
{% endif %}
```

---

## 3. Navigation & Polish

### 3a. Navigation menu — add missing entries

Add to `navigation.py`:

**Cable Types group:**
- Buffer Tube Templates (`link="plugins:netbox_fms:buffertubetemplate_list"`, `permissions=["netbox_fms.view_buffertubetemplate"]`, add button)
- Ribbon Templates (`link="plugins:netbox_fms:ribbontemplate_list"`, `permissions=["netbox_fms.view_ribbontemplate"]`, add button)
- Cable Element Templates (`link="plugins:netbox_fms:cableelementtemplate_list"`, `permissions=["netbox_fms.view_cableelementtemplate"]`, add button)

**Splice Planning group:**
- Splice Plan Entries (`link="plugins:netbox_fms:spliceplanentry_list"`, `permissions=["netbox_fms.view_spliceplanentry"]`, no add button)
- Closure Cable Entries (`link="plugins:netbox_fms:closurecableentry_list"`, `permissions=["netbox_fms.view_closurecableentry"]`, add button)

**Circuits group:**
- Fiber Circuit Paths (`link="plugins:netbox_fms:fibercircuitpath_list"`, `permissions=["netbox_fms.view_fibercircuitpath"]`, no add button)

### 3b. Status badge template include

Create `templates/netbox_fms/inc/splice_plan_status_badge.html`:
```html
{% if status == 'draft' %}
<span class="badge bg-secondary">Draft</span>
{% elif status == 'pending_review' %}
<span class="badge bg-warning text-dark">Pending Review</span>
{% elif status == 'ready_to_apply' %}
<span class="badge bg-info">Ready to Apply</span>
{% elif status == 'applied' %}
<span class="badge bg-success">Applied</span>
{% endif %}
```

### 3c. Clean up trace-view.ts

Remove all `console.log` statements from `trace-view.ts`. Rebuild the minified bundle.

### 3d. Normalize D3 CDN source

Use `https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js` consistently in:
- `fibercircuitpath.html` (currently uses `https://d3js.org/d3.v7.min.js`)
- `device_splice_editor.html` (already correct)
- `splice_editor.html` (already correct)

---

## Files Modified

| File | Changes |
|---|---|
| `views.py` | Add `@register_model_view(FiberCable)` to FiberCableView; add FiberCableComponentsView base + 4 registered tab views; add FiberCableTypeInstancesView; simplify FiberCableView (remove component tables); override BufferTubeView and ClosureCableEntryView with `get_extra_context`; add missing filter imports |
| `urls.py` | No changes needed (get_model_urls already handles registered views) |
| `templates/netbox_fms/spliceplanentry.html` | Fix stale fields, add tray/is_express, right column with notes |
| `templates/netbox_fms/fiberstrand.html` | Add ribbon, front_port_a/b fields, port assignments right column |
| `templates/netbox_fms/fibercable.html` | Remove inline component tables (now tab views), add provision ports button |
| `templates/netbox_fms/buffertube.html` | Add strands table in right column |
| `templates/netbox_fms/cableelement.html` | Add parent FiberCable link in right column |
| `templates/netbox_fms/closurecableentry.html` | Add strand summary to right column |
| `templates/netbox_fms/device_fiber_overview.html` | Fix status badges using include |
| `templates/netbox_fms/device_splice_editor.html` | Fix status badge using include |
| `templates/netbox_fms/inc/splice_plan_status_badge.html` | New include |
| `templates/netbox_fms/fibercircuitpath.html` | Normalize D3 CDN |
| `navigation.py` | Add 6 missing menu entries |
| `static/netbox_fms/src/trace-view.ts` | Remove 8 console.log statements |
| `static/netbox_fms/dist/trace-view.min.js` | Rebuild |

## Files NOT Modified

- `models.py` — No schema changes
- `forms.py` — No form changes needed
- `tables.py` — No table changes needed
- `filters.py` — No filter changes needed
- `api/` — No API changes needed
