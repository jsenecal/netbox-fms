# FiberCableType Tabbed Navigation & Component Management

**Date:** 2026-03-18
**Status:** Draft

## Problem

FiberCableType detail pages display all child template tables (Buffer Tubes, Ribbons, Cable Elements) inline on a single page. This differs from NetBox's DeviceType pattern which uses tabbed navigation with badge counts, an "Add Components" dropdown, and bulk actions on child tables. The current UX is cluttered and inconsistent with the rest of NetBox.

## Solution

Adopt the DeviceType pattern for FiberCableType: tabbed child views via `@register_model_view` + `ViewTab`, counter cache fields for badge counts, an "Add Components" dropdown, and bulk edit/delete on child template tables.

## Design

### 1. Counter Cache Fields on FiberCableType

Add three `CounterCacheField`s to `FiberCableType`:

| Field | Target Model | Target FK |
|-------|-------------|-----------|
| `buffer_tube_template_count` | `BufferTubeTemplate` | `fiber_cable_type` |
| `ribbon_template_count` | `RibbonTemplate` | `fiber_cable_type` |
| `cable_element_template_count` | `CableElementTemplate` | `fiber_cable_type` |

Requires a new migration. Counter values are auto-maintained by NetBox's `CounterCacheField` on create/delete of child objects.

### 2. Tab Views

Create a base view and three registered tab views in `views.py`:

```python
class FiberCableTypeComponentsView(generic.ObjectChildrenView):
    queryset = FiberCableType.objects.all()
    template_name = "netbox_fms/fibercabletype/base.html"

    def get_children(self, request, parent):
        return self.child_model.objects.restrict(request.user, "view").filter(
            fiber_cable_type=parent
        )
```

Registered views:

| View Class | `register_model_view` name | path | child_model | table | weight | badge field |
|------------|---------------------------|------|-------------|-------|--------|-------------|
| `FiberCableTypeBufferTubesView` | `buffertubes` | `buffer-tubes` | `BufferTubeTemplate` | `BufferTubeTemplateTable` | 500 | `buffer_tube_template_count` |
| `FiberCableTypeRibbonsView` | `ribbons` | `ribbons` | `RibbonTemplate` | `RibbonTemplateTable` | 510 | `ribbon_template_count` |
| `FiberCableTypeCableElementsView` | `cableelements` | `cable-elements` | `CableElementTemplate` | `CableElementTemplateTable` | 520 | `cable_element_template_count` |

All tabs use `hide_if_empty=True` so tabs only appear when the cable type has that component.

### 3. Template Restructure

Move `fibercabletype.html` to `fibercabletype/base.html` (directory-based, matching DeviceType pattern).

Remove the inline Buffer Tubes, Ribbons, and Cable Elements cards from the main detail view. These are now served by the tab views using `generic/object_children.html`.

Add `{% block extra_controls %}` with an "Add Components" dropdown:

```html
{% block extra_controls %}
  {% if perms.netbox_fms.add_buffertubetemplate or perms.netbox_fms.add_ribbontemplate or perms.netbox_fms.add_cableelementtemplate %}
    <div class="dropdown">
      <button type="button" class="btn btn-primary dropdown-toggle" data-bs-toggle="dropdown">
        <i class="mdi mdi-plus-thick"></i> Add Components
      </button>
      <ul class="dropdown-menu">
        {% if perms.netbox_fms.add_buffertubetemplate %}
          <li><a class="dropdown-item" href="...?fiber_cable_type={{ object.pk }}&return_url=...">Buffer Tube Templates</a></li>
        {% endif %}
        {% if perms.netbox_fms.add_ribbontemplate %}
          <li><a class="dropdown-item" href="...?fiber_cable_type={{ object.pk }}&return_url=...">Ribbon Templates</a></li>
        {% endif %}
        {% if perms.netbox_fms.add_cableelementtemplate %}
          <li><a class="dropdown-item" href="...?fiber_cable_type={{ object.pk }}&return_url=...">Cable Element Templates</a></li>
        {% endif %}
      </ul>
    </div>
  {% endif %}
{% endblock %}
```

### 4. Bulk Edit/Delete Forms

Add bulk edit forms for child templates:

| Form | Editable Fields |
|------|----------------|
| `BufferTubeTemplateBulkEditForm` | `color`, `stripe_color`, `fiber_count` |
| `RibbonTemplateBulkEditForm` | `color`, `stripe_color`, `fiber_count` |
| `CableElementTemplateBulkEditForm` | `element_type` |

Add corresponding bulk edit and bulk delete views for each template type.

### 5. Detail View Cleanup

`FiberCableTypeView.get_extra_context()` — remove the three child table constructions (`tubes_table`, `ribbons_table`, `elements_table`). The main detail tab now shows only the Cable Type properties and Physical Properties cards.

### 6. URL Routing

Tab URLs are auto-registered by `@register_model_view` via NetBox's `get_model_urls()` (already included in the FiberCableType URL pattern). No manual URL additions needed for the tabs.

Bulk edit/delete URLs for child templates use existing patterns or are added alongside existing CRUD URLs.

## Files Changed

| File | Change |
|------|--------|
| `models.py` | Add 3 `CounterCacheField`s to `FiberCableType` |
| `views.py` | Add `FiberCableTypeComponentsView` base + 3 tab views; add bulk edit/delete views for templates; clean up `FiberCableTypeView` |
| `forms.py` | Add 3 bulk edit forms for template types |
| `templates/netbox_fms/fibercabletype.html` | Move to `fibercabletype/base.html`; remove inline child tables; add "Add Components" dropdown |
| `urls.py` | Add bulk edit/delete URL patterns for child templates |
| Migration | New migration for counter cache fields |

## Out of Scope

- Changes to FiberCable (instance) detail page
- Changes to the template model definitions themselves
- New permissions beyond what already exists
