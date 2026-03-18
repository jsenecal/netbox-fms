# FiberCableType Tabbed Navigation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring FiberCableType detail pages in line with NetBox's DeviceType by adding tabbed navigation, counter cache fields, "Add Components" dropdown, and bulk actions on child template tables.

**Architecture:** Use `@register_model_view` + `ViewTab` to register child template views as tabs on FiberCableType. Add `CounterCacheField`s for badge counts (requires `TrackingModelMixin` on child models and `connect_counters` in `ready()`). Add bulk edit forms and views for the three template types.

**Tech Stack:** NetBox 4.5+ plugin API — `ViewTab`, `register_model_view`, `CounterCacheField`, `TrackingModelMixin`, `ObjectChildrenView`, `ObjectAction`s.

---

### Task 1: Add TrackingModelMixin to child template models

**Files:**
- Modify: `netbox_fms/models.py:1-6` (imports), `netbox_fms/models.py:194` (BufferTubeTemplate), `netbox_fms/models.py:276` (RibbonTemplate), `netbox_fms/models.py:358` (CableElementTemplate)

- [ ] **Step 1: Add TrackingModelMixin import**

In `netbox_fms/models.py`, add to imports:

```python
from utilities.tracking import TrackingModelMixin
```

- [ ] **Step 2: Add TrackingModelMixin to BufferTubeTemplate**

Change line 194 from:
```python
class BufferTubeTemplate(NetBoxModel):
```
to:
```python
class BufferTubeTemplate(TrackingModelMixin, NetBoxModel):
```

- [ ] **Step 3: Add TrackingModelMixin to RibbonTemplate**

Change line 276 from:
```python
class RibbonTemplate(NetBoxModel):
```
to:
```python
class RibbonTemplate(TrackingModelMixin, NetBoxModel):
```

- [ ] **Step 4: Add TrackingModelMixin to CableElementTemplate**

Change line 358 from:
```python
class CableElementTemplate(NetBoxModel):
```
to:
```python
class CableElementTemplate(TrackingModelMixin, NetBoxModel):
```

- [ ] **Step 5: Verify imports work**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.models import BufferTubeTemplate, RibbonTemplate, CableElementTemplate; print('OK')"
```
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add netbox_fms/models.py
git commit -m "refactor: add TrackingModelMixin to template models for counter cache support"
```

---

### Task 2: Add CounterCacheFields and connect_counters

**Files:**
- Modify: `netbox_fms/models.py:1-6` (imports), `netbox_fms/models.py:46-192` (FiberCableType model)
- Modify: `netbox_fms/__init__.py:17-23` (ready method)

- [ ] **Step 1: Add CounterCacheField import**

In `netbox_fms/models.py`, add to imports:

```python
from utilities.fields import ColorField, CounterCacheField
```

(Add `CounterCacheField` to the existing `from utilities.fields import ColorField` line.)

- [ ] **Step 2: Add counter cache fields to FiberCableType**

Add these three fields to the `FiberCableType` model, after the `notes` field and before the `clone_fields` declaration:

```python
    buffer_tube_template_count = CounterCacheField(
        to_model="netbox_fms.BufferTubeTemplate",
        to_field="fiber_cable_type",
    )
    ribbon_template_count = CounterCacheField(
        to_model="netbox_fms.RibbonTemplate",
        to_field="fiber_cable_type",
    )
    cable_element_template_count = CounterCacheField(
        to_model="netbox_fms.CableElementTemplate",
        to_field="fiber_cable_type",
    )
```

- [ ] **Step 3: Add connect_counters to ready()**

In `netbox_fms/__init__.py`, modify the `ready()` method:

```python
    def ready(self):
        super().ready()
        from .signals import connect_signals

        connect_signals()

        from utilities.counters import connect_counters

        from .models import FiberCableType

        connect_counters(FiberCableType)
```

- [ ] **Step 4: Generate migration**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py makemigrations netbox_fms
```
Expected: Migration created for the three new fields.

- [ ] **Step 5: Apply migration**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py migrate
```
Expected: Migration applied successfully.

- [ ] **Step 6: Verify counter fields work**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "
import django; django.setup()
from netbox_fms.models import FiberCableType
fct = FiberCableType.objects.first()
if fct:
    print(f'buffer_tube_template_count={fct.buffer_tube_template_count}')
    print(f'ribbon_template_count={fct.ribbon_template_count}')
    print(f'cable_element_template_count={fct.cable_element_template_count}')
else:
    print('No FiberCableType objects, but fields exist OK')
"
```

- [ ] **Step 7: Commit**

```bash
git add netbox_fms/models.py netbox_fms/__init__.py netbox_fms/migrations/
git commit -m "feat: add counter cache fields for template component counts"
```

---

### Task 3: Add bulk edit forms for template models

**Files:**
- Modify: `netbox_fms/forms.py` (add 3 new form classes after existing template forms)

- [ ] **Step 1: Add CableElementTypeChoices import**

In `netbox_fms/forms.py`, add `CableElementTypeChoices` to the choices import:

```python
from .choices import (
    CableElementTypeChoices,
    ConstructionChoices,
    ...
)
```

- [ ] **Step 2: Add BufferTubeTemplateBulkEditForm**

Add after `BufferTubeTemplateForm` (after line 177):

```python
class BufferTubeTemplateBulkEditForm(NetBoxModelBulkEditForm):
    model = BufferTubeTemplate

    color = ColorField(required=False)
    stripe_color = ColorField(required=False)
    fiber_count = forms.IntegerField(required=False)

    fieldsets = (FieldSet("color", "stripe_color", "fiber_count"),)
    nullable_fields = ("color", "stripe_color")
```

- [ ] **Step 3: Add RibbonTemplateBulkEditForm**

Add after `RibbonTemplateForm` (after line 225):

```python
class RibbonTemplateBulkEditForm(NetBoxModelBulkEditForm):
    model = RibbonTemplate

    color = ColorField(required=False)
    stripe_color = ColorField(required=False)
    fiber_count = forms.IntegerField(required=False)

    fieldsets = (FieldSet("color", "stripe_color", "fiber_count"),)
    nullable_fields = ("color", "stripe_color")
```

- [ ] **Step 4: Add CableElementTemplateBulkEditForm**

Add after `CableElementTemplateForm` (after line 246):

```python
class CableElementTemplateBulkEditForm(NetBoxModelBulkEditForm):
    model = CableElementTemplate

    element_type = forms.ChoiceField(choices=CableElementTypeChoices, required=False)

    fieldsets = (FieldSet("element_type"),)
    nullable_fields = ()
```

- [ ] **Step 5: Verify forms import**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "
import django; django.setup()
from netbox_fms.forms import BufferTubeTemplateBulkEditForm, RibbonTemplateBulkEditForm, CableElementTemplateBulkEditForm
print('OK')
"
```
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add netbox_fms/forms.py
git commit -m "feat: add bulk edit forms for template models"
```

---

### Task 4: Add tab views and bulk views

**Files:**
- Modify: `netbox_fms/views.py:1-14` (imports), `netbox_fms/views.py:98-112` (FiberCableTypeView)

- [ ] **Step 1: Add new imports to views.py**

Add to existing imports in `netbox_fms/views.py`:

```python
from netbox.object_actions import EditObject, DeleteObject, BulkEdit, BulkDelete
```

Add to the `.forms` import block:

```python
    BufferTubeTemplateBulkEditForm,
    CableElementTemplateBulkEditForm,
    RibbonTemplateBulkEditForm,
```

(Note: `reverse`, `ViewTab`, and `register_model_view` are already imported.)

- [ ] **Step 2: Decorate FiberCableTypeView with register_model_view**

Change:
```python
class FiberCableTypeView(generic.ObjectView):
    queryset = FiberCableType.objects.all()
```
to:
```python
@register_model_view(FiberCableType)
class FiberCableTypeView(generic.ObjectView):
    queryset = FiberCableType.objects.all()
```

- [ ] **Step 3: Remove child tables from FiberCableTypeView**

Remove the entire `get_extra_context` method from `FiberCableTypeView` (lines 101-112). The view should just be:

```python
@register_model_view(FiberCableType)
class FiberCableTypeView(generic.ObjectView):
    queryset = FiberCableType.objects.all()
```

- [ ] **Step 4: Add base FiberCableTypeComponentsView and three tab views**

Add after `FiberCableTypeBulkDeleteView` (after line 139), before the BufferTubeTemplate section:

```python
# ---------------------------------------------------------------------------
# FiberCableType component tab views
# ---------------------------------------------------------------------------


class FiberCableTypeComponentsView(generic.ObjectChildrenView):
    queryset = FiberCableType.objects.all()
    actions = (EditObject, DeleteObject, BulkEdit, BulkDelete)
    viewname = None

    def get_children(self, request, parent):
        return self.child_model.objects.restrict(request.user, "view").filter(
            fiber_cable_type=parent
        )

    def get_extra_context(self, request, instance):
        return {
            "return_url": reverse(self.viewname, kwargs={"pk": instance.pk}),
        }


@register_model_view(FiberCableType, "buffertubes", path="buffer-tubes")
class FiberCableTypeBufferTubesView(FiberCableTypeComponentsView):
    child_model = BufferTubeTemplate
    table = BufferTubeTemplateTable
    filterset = BufferTubeTemplateFilterSet
    viewname = "plugins:netbox_fms:fibercabletype_buffertubes"
    tab = ViewTab(
        label=_("Buffer Tubes"),
        badge=lambda obj: obj.buffer_tube_template_count,
        permission="netbox_fms.view_buffertubetemplate",
        weight=500,
        hide_if_empty=True,
    )


@register_model_view(FiberCableType, "ribbons", path="ribbons")
class FiberCableTypeRibbonsView(FiberCableTypeComponentsView):
    child_model = RibbonTemplate
    table = RibbonTemplateTable
    filterset = RibbonTemplateFilterSet
    viewname = "plugins:netbox_fms:fibercabletype_ribbons"
    tab = ViewTab(
        label=_("Ribbons"),
        badge=lambda obj: obj.ribbon_template_count,
        permission="netbox_fms.view_ribbontemplate",
        weight=510,
        hide_if_empty=True,
    )


@register_model_view(FiberCableType, "cableelements", path="cable-elements")
class FiberCableTypeCableElementsView(FiberCableTypeComponentsView):
    child_model = CableElementTemplate
    table = CableElementTemplateTable
    filterset = CableElementTemplateFilterSet
    viewname = "plugins:netbox_fms:fibercabletype_cableelements"
    tab = ViewTab(
        label=_("Cable Elements"),
        badge=lambda obj: obj.cable_element_template_count,
        permission="netbox_fms.view_cableelementtemplate",
        weight=520,
        hide_if_empty=True,
    )
```

- [ ] **Step 5: Add bulk edit/delete views for template models**

Add after the tab views, before the existing `BufferTubeTemplateListView`:

```python
class BufferTubeTemplateBulkEditView(generic.BulkEditView):
    queryset = BufferTubeTemplate.objects.all()
    filterset = BufferTubeTemplateFilterSet
    table = BufferTubeTemplateTable
    form = BufferTubeTemplateBulkEditForm


class BufferTubeTemplateBulkDeleteView(generic.BulkDeleteView):
    queryset = BufferTubeTemplate.objects.all()
    filterset = BufferTubeTemplateFilterSet
    table = BufferTubeTemplateTable


class RibbonTemplateBulkEditView(generic.BulkEditView):
    queryset = RibbonTemplate.objects.all()
    filterset = RibbonTemplateFilterSet
    table = RibbonTemplateTable
    form = RibbonTemplateBulkEditForm


class RibbonTemplateBulkDeleteView(generic.BulkDeleteView):
    queryset = RibbonTemplate.objects.all()
    filterset = RibbonTemplateFilterSet
    table = RibbonTemplateTable


class CableElementTemplateBulkEditView(generic.BulkEditView):
    queryset = CableElementTemplate.objects.all()
    filterset = CableElementTemplateFilterSet
    table = CableElementTemplateTable
    form = CableElementTemplateBulkEditForm


class CableElementTemplateBulkDeleteView(generic.BulkDeleteView):
    queryset = CableElementTemplate.objects.all()
    filterset = CableElementTemplateFilterSet
    table = CableElementTemplateTable
```

- [ ] **Step 6: Verify views import**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "
import django; django.setup()
from netbox_fms.views import FiberCableTypeBufferTubesView, FiberCableTypeRibbonsView, FiberCableTypeCableElementsView
print('OK')
"
```
Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add netbox_fms/views.py
git commit -m "feat: add tabbed component views and bulk edit/delete views for FiberCableType"
```

---

### Task 5: Add bulk URL patterns for template models

**Files:**
- Modify: `netbox_fms/urls.py`

**Note:** Tab URLs (e.g., `cable-types/<pk>/buffer-tubes/`) are auto-registered by the `@register_model_view` decorators via the existing `get_model_urls("netbox_fms", "fibercabletype")` on `urls.py:13`. No manual URL entries are needed for tabs. This task only adds **bulk action** URLs for the template models.

- [ ] **Step 1: Add bulk edit/delete URLs for BufferTubeTemplate**

After line 19 (`buffer-tube-templates/add/`), add:

```python
    path("buffer-tube-templates/edit/", views.BufferTubeTemplateBulkEditView.as_view(), name="buffertubetemplate_bulk_edit"),
    path("buffer-tube-templates/delete/", views.BufferTubeTemplateBulkDeleteView.as_view(), name="buffertubetemplate_bulk_delete"),
```

- [ ] **Step 2: Add bulk edit/delete URLs for RibbonTemplate**

After `ribbon-templates/add/` (line 34), add:

```python
    path("ribbon-templates/edit/", views.RibbonTemplateBulkEditView.as_view(), name="ribbontemplate_bulk_edit"),
    path("ribbon-templates/delete/", views.RibbonTemplateBulkDeleteView.as_view(), name="ribbontemplate_bulk_delete"),
```

- [ ] **Step 3: Add bulk edit/delete URLs for CableElementTemplate**

After `cable-element-templates/add/` (line 41), add:

```python
    path("cable-element-templates/edit/", views.CableElementTemplateBulkEditView.as_view(), name="cableelementtemplate_bulk_edit"),
    path("cable-element-templates/delete/", views.CableElementTemplateBulkDeleteView.as_view(), name="cableelementtemplate_bulk_delete"),
```

- [ ] **Step 4: Verify URL resolution**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "
import django; django.setup()
from django.urls import reverse
print(reverse('plugins:netbox_fms:buffertubetemplate_bulk_edit'))
print(reverse('plugins:netbox_fms:ribbontemplate_bulk_edit'))
print(reverse('plugins:netbox_fms:cableelementtemplate_bulk_edit'))
print('OK')
"
```
Expected: Three URLs printed, then `OK`

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/urls.py
git commit -m "feat: add bulk edit/delete URL patterns for template models"
```

---

### Task 6: Update template with "Add Components" dropdown and remove inline tables

**Files:**
- Modify: `netbox_fms/templates/netbox_fms/fibercabletype.html`

- [ ] **Step 1: Rewrite fibercabletype.html**

Replace the entire template content with the following (keeps the two property cards, removes inline child tables, adds "Add Components" dropdown):

```html
{% extends 'generic/object.html' %}
{% load helpers %}
{% load plugins %}
{% load i18n %}

{% block extra_controls %}
  {% if perms.netbox_fms.add_buffertubetemplate or perms.netbox_fms.add_ribbontemplate or perms.netbox_fms.add_cableelementtemplate %}
    <div class="dropdown">
      <button type="button" class="btn btn-primary dropdown-toggle" data-bs-toggle="dropdown" aria-expanded="false">
        <i class="mdi mdi-plus-thick" aria-hidden="true"></i> {% trans "Add Components" %}
      </button>
      <ul class="dropdown-menu">
        {% if perms.netbox_fms.add_buffertubetemplate %}
          <li>
            <a class="dropdown-item" href="{% url 'plugins:netbox_fms:buffertubetemplate_add' %}?fiber_cable_type={{ object.pk }}&return_url={% url 'plugins:netbox_fms:fibercabletype_buffertubes' pk=object.pk %}">
              {% trans "Buffer Tube Templates" %}
            </a>
          </li>
        {% endif %}
        {% if perms.netbox_fms.add_ribbontemplate %}
          <li>
            <a class="dropdown-item" href="{% url 'plugins:netbox_fms:ribbontemplate_add' %}?fiber_cable_type={{ object.pk }}&return_url={% url 'plugins:netbox_fms:fibercabletype_ribbons' pk=object.pk %}">
              {% trans "Ribbon Templates" %}
            </a>
          </li>
        {% endif %}
        {% if perms.netbox_fms.add_cableelementtemplate %}
          <li>
            <a class="dropdown-item" href="{% url 'plugins:netbox_fms:cableelementtemplate_add' %}?fiber_cable_type={{ object.pk }}&return_url={% url 'plugins:netbox_fms:fibercabletype_cableelements' pk=object.pk %}">
              {% trans "Cable Element Templates" %}
            </a>
          </li>
        {% endif %}
      </ul>
    </div>
  {% endif %}
{% endblock extra_controls %}

{% block content %}
<div class="row mb-3">
    <div class="col col-md-6">
        <div class="card">
            <h5 class="card-header">{% trans "Cable Type" %}</h5>
            <table class="table table-hover attr-table">
                <tr>
                    <th scope="row">{% trans "Manufacturer" %}</th>
                    <td>{{ object.manufacturer|linkify }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Model" %}</th>
                    <td>{{ object.model }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Part Number" %}</th>
                    <td>{{ object.part_number|placeholder }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Construction" %}</th>
                    <td>{{ object.get_construction_display }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Fiber Type" %}</th>
                    <td>{{ object.get_fiber_type_display }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Strand Count" %}</th>
                    <td>{{ object.strand_count }}</td>
                </tr>
            </table>
        </div>
    </div>
    <div class="col col-md-6">
        <div class="card">
            <h5 class="card-header">{% trans "Physical Properties" %}</h5>
            <table class="table table-hover attr-table">
                <tr>
                    <th scope="row">{% trans "Sheath Material" %}</th>
                    <td>{{ object.get_sheath_material_display|placeholder }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Jacket Color" %}</th>
                    <td>
                        {% if object.jacket_color %}
                            <span class="color-label" style="background-color: #{{ object.jacket_color }}">&nbsp;</span>
                            {{ object.jacket_color }}
                        {% else %}
                            {{ ''|placeholder }}
                        {% endif %}
                    </td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Armored" %}</th>
                    <td>{% if object.is_armored %}<span class="text-success"><i class="mdi mdi-check-bold"></i></span>{% else %}<span class="text-muted">&mdash;</span>{% endif %}</td>
                </tr>
                {% if object.is_armored %}
                <tr>
                    <th scope="row">{% trans "Armor Type" %}</th>
                    <td>{{ object.get_armor_type_display }}</td>
                </tr>
                {% endif %}
                <tr>
                    <th scope="row">{% trans "Deployment" %}</th>
                    <td>{{ object.get_deployment_display|placeholder }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Fire Rating" %}</th>
                    <td>{{ object.get_fire_rating_display|placeholder }}</td>
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

- [ ] **Step 2: Verify template renders (manual check)**

Start the dev server and visit a FiberCableType detail page. Verify:
- Property cards render correctly
- "Add Components" dropdown appears in the header
- Tabs appear for component types that have entries
- Clicking a tab shows the child table with bulk action checkboxes

- [ ] **Step 3: Commit**

```bash
git add netbox_fms/templates/netbox_fms/fibercabletype.html
git commit -m "feat: add 'Add Components' dropdown and remove inline child tables from FiberCableType detail"
```

---

### Task 7: Run tests and verify

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v
```
Expected: All tests pass.

- [ ] **Step 2: Run linting**

Run:
```bash
cd /opt/netbox-fms && ruff check netbox_fms/ && ruff format --check netbox_fms/
```
Expected: No errors.

- [ ] **Step 3: Fix any lint or test issues**

If any issues, fix and re-run.

- [ ] **Step 4: Verify all modules import cleanly**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.models import *; from netbox_fms.forms import *; from netbox_fms.filters import *; from netbox_fms.views import *; print('All imports OK')"
```
Expected: `All imports OK`

- [ ] **Step 5: Final commit if needed**

```bash
git add -A && git commit -m "fix: address lint and test issues"
```
