# UI/UX Audit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 3 template bugs (stale fields, broken badges, missing strand fields) and implement 7 UX improvements (tabbed FiberCable detail, instances tab, provision button, navigation, JS cleanup) across the netbox-fms plugin.

**Architecture:** All changes follow existing NetBox plugin patterns. Tab views use `@register_model_view` + `ViewTab` + `ObjectChildrenView` (same pattern as FiberCableType tabs in `views.py:153-209`). Template fixes are straightforward field corrections. Navigation additions follow existing `PluginMenuItem` pattern.

**Tech Stack:** NetBox 4.5+ plugin API, Django templates, TypeScript/D3.js.

**Worktree:** `/opt/netbox-fms/.worktrees/ui-ux-fixes` (branch: `feature/ui-ux-audit-fixes`)

**Spec:** `docs/superpowers/specs/2026-03-19-ui-ux-audit-fixes-design.md`

**Test command:** `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/.worktrees/ui-ux-fixes/tests/ -v`

**Import verification:** `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.models import *; from netbox_fms.forms import *; from netbox_fms.filters import *; from netbox_fms.views import *"`

---

### Task 1: Fix SplicePlanEntry detail template

**Files:**
- Modify: `netbox_fms/templates/netbox_fms/spliceplanentry.html`

The current template references `mode_override` and `cable` fields that don't exist on the model. The actual model fields are: `plan`, `tray`, `fiber_a`, `fiber_b`, `is_express`, `notes`.

- [ ] **Step 1: Replace the template content**

Replace the entire content of `netbox_fms/templates/netbox_fms/spliceplanentry.html` with:

```html
{% extends 'generic/object.html' %}
{% load helpers %}
{% load plugins %}
{% load i18n %}

{% block content %}
<div class="row mb-3">
    <div class="col col-md-6">
        <div class="card">
            <h5 class="card-header">{% trans "Splice Entry" %}</h5>
            <table class="table table-hover attr-table">
                <tr>
                    <th scope="row">{% trans "Plan" %}</th>
                    <td>{{ object.plan|linkify }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Tray" %}</th>
                    <td>{{ object.tray|linkify }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Fiber A" %}</th>
                    <td>{{ object.fiber_a|linkify }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Fiber B" %}</th>
                    <td>{{ object.fiber_b|linkify }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Express" %}</th>
                    <td>{% if object.is_express %}<span class="text-success"><i class="mdi mdi-check-bold"></i></span>{% else %}<span class="text-muted">&mdash;</span>{% endif %}</td>
                </tr>
            </table>
        </div>
    </div>
    <div class="col col-md-6">
        {% if object.notes %}
        <div class="card">
            <h5 class="card-header">{% trans "Notes" %}</h5>
            <div class="card-body">{{ object.notes|markdown }}</div>
        </div>
        {% endif %}
        {% include 'inc/panels/comments.html' %}
    </div>
</div>
{% plugin_full_width_page object %}
{% endblock %}
```

- [ ] **Step 2: Verify import and template render**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "
import django; django.setup()
from django.template.loader import get_template
t = get_template('netbox_fms/spliceplanentry.html')
print('Template loaded OK')
"
```

Expected: `Template loaded OK`

- [ ] **Step 3: Run tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/.worktrees/ui-ux-fixes/tests/ -v --tb=short`

Expected: All 198 tests pass.

- [ ] **Step 4: Commit**

```bash
cd /opt/netbox-fms/.worktrees/ui-ux-fixes
git add netbox_fms/templates/netbox_fms/spliceplanentry.html
git commit -m "fix: replace stale mode_override/cable fields with tray/is_express in splice entry detail"
```

---

### Task 2: Create splice plan status badge include

**Files:**
- Create: `netbox_fms/templates/netbox_fms/inc/splice_plan_status_badge.html`
- Modify: `netbox_fms/templates/netbox_fms/device_fiber_overview.html`
- Modify: `netbox_fms/templates/netbox_fms/device_splice_editor.html`

The current templates use `bg-{{ plan.status }}` which maps to non-existent Bootstrap classes. SplicePlanStatusChoices values are: `draft`, `pending_review`, `ready_to_apply`, `applied`.

- [ ] **Step 1: Create the badge include template**

Create `netbox_fms/templates/netbox_fms/inc/splice_plan_status_badge.html`:

```html
{% if status == 'draft' %}<span class="badge bg-secondary">Draft</span>{% elif status == 'pending_review' %}<span class="badge bg-warning text-dark">Pending Review</span>{% elif status == 'ready_to_apply' %}<span class="badge bg-info">Ready to Apply</span>{% elif status == 'applied' %}<span class="badge bg-success">Applied</span>{% else %}<span class="badge bg-secondary">{{ status }}</span>{% endif %}
```

- [ ] **Step 2: Fix device_fiber_overview.html — stats bar badge (line 31)**

In `netbox_fms/templates/netbox_fms/device_fiber_overview.html`, replace:

```html
                            <h4><span class="badge bg-{{ plan.status }}">{{ plan.get_status_display }}</span></h4>
```

with:

```html
                            <h4>{% include "netbox_fms/inc/splice_plan_status_badge.html" with status=plan.status %}</h4>
```

- [ ] **Step 3: Fix device_fiber_overview.html — plan card badge (line 78)**

In `netbox_fms/templates/netbox_fms/device_fiber_overview.html`, replace:

```html
                        <span class="badge bg-{{ plan.status }}">{{ plan.get_status_display }}</span>
```

with:

```html
                        {% include "netbox_fms/inc/splice_plan_status_badge.html" with status=plan.status %}
```

- [ ] **Step 4: Fix device_splice_editor.html badge (line 22)**

In `netbox_fms/templates/netbox_fms/device_splice_editor.html`, replace:

```html
                <span class="badge bg-{{ plan.status }}">{{ plan.get_status_display }}</span>
```

with:

```html
                {% include "netbox_fms/inc/splice_plan_status_badge.html" with status=plan.status %}
```

- [ ] **Step 5: Run tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/.worktrees/ui-ux-fixes/tests/ -v --tb=short`

Expected: All 198 tests pass.

- [ ] **Step 6: Commit**

```bash
cd /opt/netbox-fms/.worktrees/ui-ux-fixes
git add netbox_fms/templates/netbox_fms/inc/splice_plan_status_badge.html
git add netbox_fms/templates/netbox_fms/device_fiber_overview.html
git add netbox_fms/templates/netbox_fms/device_splice_editor.html
git commit -m "fix: use proper Bootstrap badge colors for splice plan status"
```

---

### Task 3: Fix FiberStrand detail template

**Files:**
- Modify: `netbox_fms/templates/netbox_fms/fiberstrand.html`

Missing `ribbon`, `front_port_a`, `front_port_b` — the most operationally important fields showing which ports this strand connects to.

- [ ] **Step 1: Replace the template content**

Replace the entire content of `netbox_fms/templates/netbox_fms/fiberstrand.html` with:

```html
{% extends 'generic/object.html' %}
{% load helpers %}
{% load plugins %}
{% load i18n %}

{% block content %}
<div class="row mb-3">
    <div class="col col-md-6">
        <div class="card">
            <h5 class="card-header">{% trans "Fiber Strand" %}</h5>
            <table class="table table-hover attr-table">
                <tr>
                    <th scope="row">{% trans "Fiber Cable" %}</th>
                    <td>{{ object.fiber_cable|linkify }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Buffer Tube" %}</th>
                    <td>{{ object.buffer_tube|linkify|placeholder }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Ribbon" %}</th>
                    <td>{{ object.ribbon|linkify|placeholder }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Name" %}</th>
                    <td>{{ object.name }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Position" %}</th>
                    <td>{{ object.position }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Color" %}</th>
                    <td>
                        {% if object.color %}
                            <span class="color-label" style="background-color: #{{ object.color }}">&nbsp;</span>
                            {{ object.color }}
                        {% else %}
                            {{ ''|placeholder }}
                        {% endif %}
                    </td>
                </tr>
            </table>
        </div>
    </div>
    <div class="col col-md-6">
        <div class="card">
            <h5 class="card-header">{% trans "Port Assignments" %}</h5>
            <table class="table table-hover attr-table">
                <tr>
                    <th scope="row">{% trans "Front Port (A-side)" %}</th>
                    <td>
                        {% if object.front_port_a %}
                            {{ object.front_port_a|linkify }}
                            {% if object.front_port_a.device %}
                                <br><small class="text-muted">{{ object.front_port_a.device|linkify }}</small>
                            {% endif %}
                        {% else %}
                            {{ ''|placeholder }}
                        {% endif %}
                    </td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Front Port (B-side)" %}</th>
                    <td>
                        {% if object.front_port_b %}
                            {{ object.front_port_b|linkify }}
                            {% if object.front_port_b.device %}
                                <br><small class="text-muted">{{ object.front_port_b.device|linkify }}</small>
                            {% endif %}
                        {% else %}
                            {{ ''|placeholder }}
                        {% endif %}
                    </td>
                </tr>
            </table>
        </div>
    </div>
</div>
{% plugin_full_width_page object %}
{% endblock %}
```

- [ ] **Step 2: Run tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/.worktrees/ui-ux-fixes/tests/ -v --tb=short`

Expected: All 198 tests pass.

- [ ] **Step 3: Commit**

```bash
cd /opt/netbox-fms/.worktrees/ui-ux-fixes
git add netbox_fms/templates/netbox_fms/fiberstrand.html
git commit -m "fix: add ribbon and front_port_a/b fields to fiber strand detail"
```

---

### Task 4: Add FiberCable tabbed component views

**Files:**
- Modify: `netbox_fms/views.py` (add imports, decorator, base class, 4 tab views, simplify FiberCableView)
- Modify: `netbox_fms/templates/netbox_fms/fibercable.html` (remove inline tables)

This is the largest task. It converts the FiberCable detail page from 4 inline tables to proper NetBox tabbed views using `@register_model_view` + `ViewTab`.

- [ ] **Step 1: Add missing filter imports to views.py**

In `netbox_fms/views.py`, find the imports from `.filters` (lines 16-29) and add the missing filtersets. Replace:

```python
from .filters import (
    BufferTubeTemplateFilterSet,
    CableElementTemplateFilterSet,
    ClosureCableEntryFilterSet,
    FiberCableFilterSet,
    FiberCableTypeFilterSet,
    FiberCircuitFilterSet,
    FiberCircuitPathFilterSet,
    RibbonTemplateFilterSet,
    SlackLoopFilterSet,
    SplicePlanEntryFilterSet,
    SplicePlanFilterSet,
    SpliceProjectFilterSet,
)
```

with:

```python
from .filters import (
    BufferTubeFilterSet,
    BufferTubeTemplateFilterSet,
    CableElementFilterSet,
    CableElementTemplateFilterSet,
    ClosureCableEntryFilterSet,
    FiberCableFilterSet,
    FiberCableTypeFilterSet,
    FiberCircuitFilterSet,
    FiberCircuitPathFilterSet,
    FiberStrandFilterSet,
    RibbonFilterSet,
    RibbonTemplateFilterSet,
    SlackLoopFilterSet,
    SplicePlanEntryFilterSet,
    SplicePlanFilterSet,
    SpliceProjectFilterSet,
)
```

- [ ] **Step 2: Add missing model imports to views.py**

In `netbox_fms/views.py`, find the imports from `.models` (lines 69-83) and add the missing models. Replace:

```python
from .models import (
    BufferTubeTemplate,
    CableElementTemplate,
    ClosureCableEntry,
    FiberCable,
    FiberCableType,
    FiberCircuit,
    FiberCircuitPath,
    FiberStrand,
    RibbonTemplate,
    SlackLoop,
    SplicePlan,
    SplicePlanEntry,
    SpliceProject,
)
```

with:

```python
from .models import (
    BufferTube,
    BufferTubeTemplate,
    CableElement,
    CableElementTemplate,
    ClosureCableEntry,
    FiberCable,
    FiberCableType,
    FiberCircuit,
    FiberCircuitPath,
    FiberStrand,
    Ribbon,
    RibbonTemplate,
    SlackLoop,
    SplicePlan,
    SplicePlanEntry,
    SpliceProject,
)
```

- [ ] **Step 3: Add missing table imports to views.py**

In `netbox_fms/views.py`, the table imports (lines 85-101) are missing `RibbonTable`. Add it to the import block. Find:

```python
from .tables import (
    BufferTubeTable,
    BufferTubeTemplateTable,
    CableElementTable,
    CableElementTemplateTable,
    ClosureCableEntryTable,
    FiberCableTable,
    FiberCableTypeTable,
    FiberCircuitPathTable,
    FiberCircuitTable,
    FiberStrandTable,
    RibbonTable,
    RibbonTemplateTable,
    SlackLoopTable,
    SplicePlanEntryTable,
    SplicePlanTable,
```

Verify `RibbonTable` is already there. If not, add it. (It is already present — just verify.)

- [ ] **Step 4: Add @register_model_view decorator to FiberCableView**

In `netbox_fms/views.py`, find `FiberCableView` (around line 340). Add the decorator. Change:

```python
class FiberCableView(generic.ObjectView):
    queryset = FiberCable.objects.all()
```

to:

```python
@register_model_view(FiberCable)
class FiberCableView(generic.ObjectView):
    queryset = FiberCable.objects.all()
```

Note: The explicit URL pattern on urls.py line 83 (`name="fibercable"`) coexists with `get_model_urls` on line 82. This is the same pattern used for FiberCableType (lines 13-14) and works correctly — do NOT remove it.

- [ ] **Step 5: Simplify FiberCableView.get_extra_context**

Remove the component tables from `FiberCableView.get_extra_context` since they'll now be separate tab views. Replace the entire `get_extra_context` method:

```python
    def get_extra_context(self, request, instance):
        tubes_table = BufferTubeTable(instance.buffer_tubes.all())
        tubes_table.configure(request)
        ribbons_table = RibbonTable(instance.ribbons.all())
        ribbons_table.configure(request)
        strands_table = FiberStrandTable(instance.fiber_strands.all())
        strands_table.configure(request)
        elements_table = CableElementTable(instance.cable_elements.all())
        elements_table.configure(request)
        return {
            "tubes_table": tubes_table,
            "ribbons_table": ribbons_table,
            "strands_table": strands_table,
            "elements_table": elements_table,
        }
```

with nothing — delete the entire `get_extra_context` method so it becomes:

```python
@register_model_view(FiberCable)
class FiberCableView(generic.ObjectView):
    queryset = FiberCable.objects.all()
```

- [ ] **Step 6: Add FiberCableComponentsView base class and 4 tab views**

Insert the following after the `FiberCableBulkDeleteView` class (after line ~384) and before the SplicePlan section:

```python
# ---------------------------------------------------------------------------
# FiberCable component tab views
# ---------------------------------------------------------------------------


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

- [ ] **Step 7: Simplify fibercable.html template**

Replace the entire content of `netbox_fms/templates/netbox_fms/fibercable.html` with:

```html
{% extends 'generic/object.html' %}
{% load helpers %}
{% load plugins %}
{% load i18n %}

{% block extra_controls %}
    {% if perms.dcim.add_frontport %}
    <a href="{% url 'plugins:netbox_fms:provision_ports' %}?fiber_cable={{ object.pk }}" class="btn btn-outline-primary">
        <i class="mdi mdi-ethernet"></i> {% trans "Provision Ports" %}
    </a>
    {% endif %}
{% endblock extra_controls %}

{% block content %}
<div class="row mb-3">
    <div class="col col-md-6">
        <div class="card">
            <h5 class="card-header">{% trans "Fiber Cable" %}</h5>
            <table class="table table-hover attr-table">
                <tr>
                    <th scope="row">{% trans "Cable" %}</th>
                    <td>{{ object.cable|linkify }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Fiber Cable Type" %}</th>
                    <td>{{ object.fiber_cable_type|linkify }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Manufacturer" %}</th>
                    <td>{{ object.fiber_cable_type.manufacturer|linkify }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Construction" %}</th>
                    <td>{{ object.fiber_cable_type.get_construction_display }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Fiber Type" %}</th>
                    <td>{{ object.fiber_cable_type.get_fiber_type_display }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Strand Count" %}</th>
                    <td>{{ object.fiber_cable_type.strand_count }}</td>
                </tr>
            </table>
        </div>
    </div>
    <div class="col col-md-6">
        <div class="card">
            <h5 class="card-header">{% trans "Identification" %}</h5>
            <table class="table table-hover attr-table">
                <tr>
                    <th scope="row">{% trans "Serial Number" %}</th>
                    <td>{{ object.serial_number|placeholder }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Install Date" %}</th>
                    <td>{{ object.install_date|placeholder }}</td>
                </tr>
            </table>
        </div>
    </div>
</div>
{% if object.notes %}
<div class="row mb-3">
    <div class="col col-md-12">
        <div class="card">
            <h5 class="card-header">{% trans "Notes" %}</h5>
            <div class="card-body">{{ object.notes|markdown }}</div>
        </div>
    </div>
</div>
{% endif %}
{% plugin_full_width_page object %}
{% endblock %}
```

- [ ] **Step 8: Verify imports**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.views import *; print('OK')"
```

Expected: `OK`

- [ ] **Step 9: Run tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/.worktrees/ui-ux-fixes/tests/ -v --tb=short`

Expected: All tests pass.

- [ ] **Step 10: Commit**

```bash
cd /opt/netbox-fms/.worktrees/ui-ux-fixes
git add netbox_fms/views.py netbox_fms/templates/netbox_fms/fibercable.html
git commit -m "feat: add tabbed component views to FiberCable detail page"
```

---

### Task 5: Add FiberCableType instances tab

**Files:**
- Modify: `netbox_fms/views.py` (add instances tab view)

- [ ] **Step 1: Add FiberCableTypeInstancesView**

In `netbox_fms/views.py`, after the existing `FiberCableTypeCableElementsView` (around line 209), add:

```python
@register_model_view(FiberCableType, "instances", path="instances")
class FiberCableTypeInstancesView(generic.ObjectChildrenView):
    queryset = FiberCableType.objects.all()
    child_model = FiberCable
    table = FiberCableTable
    viewname = "plugins:netbox_fms:fibercabletype_instances"
    tab = ViewTab(
        label=_("Instances"),
        badge=lambda obj: FiberCable.objects.filter(fiber_cable_type=obj).count(),
        weight=530,
        hide_if_empty=True,
    )

    def get_children(self, request, parent):
        return FiberCable.objects.restrict(request.user, "view").filter(fiber_cable_type=parent)

    def get_extra_context(self, request, instance):
        return {
            "return_url": reverse(self.viewname, kwargs={"pk": instance.pk}),
        }
```

- [ ] **Step 2: Verify imports**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.views import FiberCableTypeInstancesView; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Run tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/.worktrees/ui-ux-fixes/tests/ -v --tb=short`

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
cd /opt/netbox-fms/.worktrees/ui-ux-fixes
git add netbox_fms/views.py
git commit -m "feat: add Instances tab to FiberCableType detail page"
```

---

### Task 6: Improve sparse detail pages

**Files:**
- Modify: `netbox_fms/views.py` (override BufferTubeView, ClosureCableEntryView)
- Modify: `netbox_fms/templates/netbox_fms/buffertube.html`
- Modify: `netbox_fms/templates/netbox_fms/cableelement.html`
- Modify: `netbox_fms/templates/netbox_fms/closurecableentry.html`

- [ ] **Step 1: Override BufferTubeView with get_extra_context**

In `netbox_fms/views.py`, find `BufferTubeView` (the generic.ObjectView). It's not currently defined as a class — it may be auto-generated. Check: if there is a `BufferTubeView` class, modify it. If not, there are no standalone views for BufferTube (they're only shown as children). In that case, skip this step — the buffer tube detail is only reachable via the FiberCable tab.

Actually, looking at the codebase: BufferTube, Ribbon, FiberStrand, and CableElement do NOT have standalone list/detail/edit/delete views. They are only accessed as children of FiberCable. The detail templates exist but there are no URL patterns or views for them individually (no `buffertube_list`, `buffertube` URL patterns in urls.py).

**Skip this step** — BufferTube, Ribbon, FiberStrand, and CableElement are only shown inline on FiberCable detail. Their templates are used by the ObjectChildrenView infrastructure. The template improvements from Tasks 1 and 3 are sufficient.

- [ ] **Step 2: Override ClosureCableEntryView with get_extra_context**

In `netbox_fms/views.py`, find `ClosureCableEntryView` (around line 556) and add strand summary data:

```python
class ClosureCableEntryView(generic.ObjectView):
    queryset = ClosureCableEntry.objects.all()

    def get_extra_context(self, request, instance):
        strand_info = None
        if instance.fiber_cable:
            from django.db.models import Count, Q

            total = instance.fiber_cable.fiber_strands.count()
            linked = instance.fiber_cable.fiber_strands.filter(
                Q(front_port_a__device=instance.closure) | Q(front_port_b__device=instance.closure)
            ).count()
            strand_info = {"linked": linked, "total": total}
        return {"strand_info": strand_info}
```

- [ ] **Step 3: Update closurecableentry.html — add strand summary**

Replace the entire content of `netbox_fms/templates/netbox_fms/closurecableentry.html` with:

```html
{% extends 'generic/object.html' %}
{% load helpers %}
{% load plugins %}
{% load i18n %}

{% block content %}
<div class="row mb-3">
    <div class="col col-md-6">
        <div class="card">
            <h5 class="card-header">{% trans "Cable Entry" %}</h5>
            <table class="table table-hover attr-table">
                <tr>
                    <th scope="row">{% trans "Closure" %}</th>
                    <td>{{ object.closure|linkify }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Fiber Cable" %}</th>
                    <td>{{ object.fiber_cable|linkify }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Entrance Label" %}</th>
                    <td>{{ object.entrance_label|default:"—" }}</td>
                </tr>
            </table>
        </div>
    </div>
    <div class="col col-md-6">
        {% if strand_info %}
        <div class="card">
            <h5 class="card-header">{% trans "Strand Summary" %}</h5>
            <table class="table table-hover attr-table">
                <tr>
                    <th scope="row">{% trans "Strands Linked" %}</th>
                    <td>{{ strand_info.linked }}/{{ strand_info.total }}</td>
                </tr>
            </table>
        </div>
        {% endif %}
        {% if object.notes %}
        <div class="card{% if strand_info %} mt-3{% endif %}">
            <h5 class="card-header">{% trans "Notes" %}</h5>
            <div class="card-body">{{ object.notes|markdown }}</div>
        </div>
        {% endif %}
    </div>
</div>
{% plugin_full_width_page object %}
{% endblock %}
```

- [ ] **Step 4: Update cableelement.html — add parent link in right column**

Replace the entire content of `netbox_fms/templates/netbox_fms/cableelement.html` with:

```html
{% extends 'generic/object.html' %}
{% load helpers %}
{% load plugins %}
{% load i18n %}

{% block content %}
<div class="row mb-3">
    <div class="col col-md-6">
        <div class="card">
            <h5 class="card-header">{% trans "Cable Element" %}</h5>
            <table class="table table-hover attr-table">
                <tr>
                    <th scope="row">{% trans "Fiber Cable" %}</th>
                    <td>{{ object.fiber_cable|linkify }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Name" %}</th>
                    <td>{{ object.name }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Type" %}</th>
                    <td>{{ object.get_element_type_display }}</td>
                </tr>
            </table>
        </div>
    </div>
    <div class="col col-md-6">
        {% include 'inc/panels/comments.html' %}
    </div>
</div>
{% plugin_full_width_page object %}
{% endblock %}
```

- [ ] **Step 5: Run tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/.worktrees/ui-ux-fixes/tests/ -v --tb=short`

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
cd /opt/netbox-fms/.worktrees/ui-ux-fixes
git add netbox_fms/views.py
git add netbox_fms/templates/netbox_fms/closurecableentry.html
git add netbox_fms/templates/netbox_fms/cableelement.html
git commit -m "feat: improve sparse detail pages with right-column content"
```

---

### Task 7: Add missing navigation menu entries

**Files:**
- Modify: `netbox_fms/navigation.py`

- [ ] **Step 1: Replace navigation.py content**

Replace the entire content of `netbox_fms/navigation.py` with:

```python
from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem

menu = PluginMenu(
    label="FMS",
    groups=(
        (
            "Cable Types",
            (
                PluginMenuItem(
                    link="plugins:netbox_fms:fibercabletype_list",
                    link_text="Fiber Cable Types",
                    permissions=["netbox_fms.view_fibercabletype"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_fms:fibercabletype_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_fms.add_fibercabletype"],
                        ),
                        PluginMenuButton(
                            link="plugins:netbox_fms:fibercabletype_import",
                            title="Import",
                            icon_class="mdi mdi-upload",
                            permissions=["netbox_fms.add_fibercabletype"],
                        ),
                    ),
                ),
                PluginMenuItem(
                    link="plugins:netbox_fms:buffertubetemplate_list",
                    link_text="Buffer Tube Templates",
                    permissions=["netbox_fms.view_buffertubetemplate"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_fms:buffertubetemplate_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_fms.add_buffertubetemplate"],
                        ),
                    ),
                ),
                PluginMenuItem(
                    link="plugins:netbox_fms:ribbontemplate_list",
                    link_text="Ribbon Templates",
                    permissions=["netbox_fms.view_ribbontemplate"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_fms:ribbontemplate_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_fms.add_ribbontemplate"],
                        ),
                    ),
                ),
                PluginMenuItem(
                    link="plugins:netbox_fms:cableelementtemplate_list",
                    link_text="Cable Element Templates",
                    permissions=["netbox_fms.view_cableelementtemplate"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_fms:cableelementtemplate_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_fms.add_cableelementtemplate"],
                        ),
                    ),
                ),
            ),
        ),
        (
            "Fiber Cables",
            (
                PluginMenuItem(
                    link="plugins:netbox_fms:fibercable_list",
                    link_text="Fiber Cables",
                    permissions=["netbox_fms.view_fibercable"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_fms:fibercable_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_fms.add_fibercable"],
                        ),
                        PluginMenuButton(
                            link="plugins:netbox_fms:fibercable_import",
                            title="Import",
                            icon_class="mdi mdi-upload",
                            permissions=["netbox_fms.add_fibercable"],
                        ),
                    ),
                ),
            ),
        ),
        (
            "Slack Loops",
            (
                PluginMenuItem(
                    link="plugins:netbox_fms:slackloop_list",
                    link_text="Slack Loops",
                    permissions=["netbox_fms.view_slackloop"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_fms:slackloop_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_fms.add_slackloop"],
                        ),
                        PluginMenuButton(
                            link="plugins:netbox_fms:slackloop_import",
                            title="Import",
                            icon_class="mdi mdi-upload",
                            permissions=["netbox_fms.add_slackloop"],
                        ),
                    ),
                ),
            ),
        ),
        (
            "Circuits",
            (
                PluginMenuItem(
                    link="plugins:netbox_fms:fibercircuit_list",
                    link_text="Fiber Circuits",
                    permissions=["netbox_fms.view_fibercircuit"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_fms:fibercircuit_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_fms.add_fibercircuit"],
                        ),
                        PluginMenuButton(
                            link="plugins:netbox_fms:fibercircuit_import",
                            title="Import",
                            icon_class="mdi mdi-upload",
                            permissions=["netbox_fms.add_fibercircuit"],
                        ),
                    ),
                ),
                PluginMenuItem(
                    link="plugins:netbox_fms:fibercircuitpath_list",
                    link_text="Fiber Circuit Paths",
                    permissions=["netbox_fms.view_fibercircuitpath"],
                ),
            ),
        ),
        (
            "Splice Planning",
            (
                PluginMenuItem(
                    link="plugins:netbox_fms:spliceproject_list",
                    link_text="Splice Projects",
                    permissions=["netbox_fms.view_spliceproject"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_fms:spliceproject_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_fms.add_spliceproject"],
                        ),
                    ),
                ),
                PluginMenuItem(
                    link="plugins:netbox_fms:spliceplan_list",
                    link_text="Splice Plans",
                    permissions=["netbox_fms.view_spliceplan"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_fms:spliceplan_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_fms.add_spliceplan"],
                        ),
                    ),
                ),
                PluginMenuItem(
                    link="plugins:netbox_fms:spliceplanentry_list",
                    link_text="Splice Plan Entries",
                    permissions=["netbox_fms.view_spliceplanentry"],
                ),
                PluginMenuItem(
                    link="plugins:netbox_fms:closurecableentry_list",
                    link_text="Closure Cable Entries",
                    permissions=["netbox_fms.view_closurecableentry"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_fms:closurecableentry_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_fms.add_closurecableentry"],
                        ),
                    ),
                ),
            ),
        ),
    ),
    icon_class="mdi mdi-arrow-decision-outline",
)
```

- [ ] **Step 2: Verify navigation loads**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.navigation import menu; print(f'Menu loaded: {len(menu.groups)} groups')"
```

Expected: `Menu loaded: 5 groups`

- [ ] **Step 3: Run tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/.worktrees/ui-ux-fixes/tests/ -v --tb=short`

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
cd /opt/netbox-fms/.worktrees/ui-ux-fixes
git add netbox_fms/navigation.py
git commit -m "feat: add missing navigation entries for sub-models"
```

---

### Task 8: Clean up trace-view.ts and normalize D3 CDN

**Files:**
- Modify: `netbox_fms/static/netbox_fms/src/trace-view.ts`
- Modify: `netbox_fms/templates/netbox_fms/fibercircuitpath.html`
- Rebuild: `netbox_fms/static/netbox_fms/dist/trace-view.min.js`

- [ ] **Step 1: Remove console.log statements from trace-view.ts**

In `netbox_fms/static/netbox_fms/src/trace-view.ts`, remove all lines containing `console.log`. There are statements at lines 8, 21, 24, 29, 33, 38, 43, 46. After removal the file should look like:

```typescript
import type { TraceConfig, TraceResponse } from './trace-types';
import { TraceRenderer } from './trace-renderer';

declare const d3: typeof import('d3');
declare const htmx: any;

const config = (window as unknown as { TRACE_VIEW_CONFIG?: TraceConfig }).TRACE_VIEW_CONFIG;
if (config) {
  initTraceView(config);
}

let activeRenderer: TraceRenderer | null = null;

async function initTraceView(config: TraceConfig): Promise<void> {
  const container = document.getElementById('trace-canvas-container');
  if (!container) return;

  // Wait for tab activation before initializing
  const tabBtn = document.getElementById('trace-tab-btn');
  if (tabBtn) {
    tabBtn.addEventListener('shown.bs.tab', () => {
      loadAndRender();
    }, { once: true });
    // If trace tab is directly activated via URL hash
    if (window.location.hash === '#trace') {
      tabBtn.click();
    }
  } else {
    await loadAndRender();
  }

  async function loadAndRender(): Promise<void> {
    try {
      const resp = await fetch(config.traceUrl, {
        headers: { 'Accept': 'application/json' },
      });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data: TraceResponse = await resp.json();

      // Clear loading spinner safely
      while (container.firstChild) {
        container.removeChild(container.firstChild);
      }

      if (data.hops.length === 0) {
        const msg = document.createElement('div');
        msg.className = 'trace-loading';
        const p = document.createElement('p');
        p.className = 'text-muted';
        p.textContent = 'No trace data available';
        msg.appendChild(p);
        container.appendChild(msg);
        return;
      }

      activeRenderer = new TraceRenderer(container, data, config);
      activeRenderer.render();
    } catch (err) {
      while (container.firstChild) {
        container.removeChild(container.firstChild);
      }
      const msg = document.createElement('div');
      msg.className = 'trace-loading';
      const p = document.createElement('p');
      p.className = 'text-danger';
      p.textContent = 'Error: ' + (err as Error).message;
      msg.appendChild(p);
      container.appendChild(msg);
    }
  }
}

/** Called from HTMX back button in sidebar templates. */
export function deselectNode(): void {
  const panel = document.getElementById('trace-detail-panel');
  if (panel) {
    const wrapper = document.createElement('div');
    wrapper.className = 'trace-sidebar-empty';
    const p = document.createElement('p');
    p.textContent = 'Click a node to view details';
    wrapper.appendChild(p);
    while (panel.firstChild) {
      panel.removeChild(panel.firstChild);
    }
    panel.appendChild(wrapper);
  }
  document.dispatchEvent(new CustomEvent('trace:deselect'));
}
```

- [ ] **Step 2: Normalize D3 CDN in fibercircuitpath.html**

In `netbox_fms/templates/netbox_fms/fibercircuitpath.html`, replace:

```html
<script src="https://d3js.org/d3.v7.min.js"></script>
```

with:

```html
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
```

- [ ] **Step 3: Rebuild the minified JS bundle**

Check if there's a build script:
```bash
cd /opt/netbox-fms/.worktrees/ui-ux-fixes && ls package.json tsconfig.json Makefile 2>/dev/null
```

If a build toolchain exists, run it. If not, check if `esbuild` or `tsc` is available:
```bash
which esbuild 2>/dev/null || which npx 2>/dev/null
```

Build with whatever is available. If no build toolchain, note in the commit message that the minified bundle needs rebuilding.

- [ ] **Step 4: Run tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/.worktrees/ui-ux-fixes/tests/ -v --tb=short`

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
cd /opt/netbox-fms/.worktrees/ui-ux-fixes
git add netbox_fms/static/netbox_fms/src/trace-view.ts
git add netbox_fms/templates/netbox_fms/fibercircuitpath.html
git add netbox_fms/static/netbox_fms/dist/trace-view.min.js 2>/dev/null  # if rebuilt
git commit -m "chore: remove debug console.logs from trace-view, normalize D3 CDN"
```

---

### Task 9: Final verification

**Files:** None (verification only)

- [ ] **Step 1: Run full import verification**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "
import django; django.setup()
from netbox_fms.models import *
from netbox_fms.forms import *
from netbox_fms.filters import *
from netbox_fms.views import *
from netbox_fms.navigation import menu
print(f'All imports OK. Menu: {len(menu.groups)} groups')
"
```

Expected: `All imports OK. Menu: 5 groups`

- [ ] **Step 2: Run full test suite**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/.worktrees/ui-ux-fixes/tests/ -v --tb=short
```

Expected: All 198+ tests pass.

- [ ] **Step 3: Run linter**

```bash
cd /opt/netbox-fms/.worktrees/ui-ux-fixes && ruff check --fix netbox_fms/ && ruff format netbox_fms/
```

Expected: No errors. If formatting changes were made, commit them:

```bash
git add -u && git commit -m "style: apply ruff formatting"
```
