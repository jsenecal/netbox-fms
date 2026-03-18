# Slack Loops Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `SlackLoop` model for tracking fiber cable slack loops at sites, plus an "Insert into Splice Closure" workflow that splits a cable at a slack loop location and connects both halves through a closure device. Also adds `is_express` boolean to `SplicePlanEntry`.

**Architecture:** `SlackLoop` is a standalone NetBoxModel with FKs to FiberCable, Site, and Location. The insert workflow is a custom view that atomically deletes the original cable, creates two new cables terminating at the closure, instantiates FiberCables with auto-generated strands, and creates SplicePlanEntries. The `is_express` field on SplicePlanEntry distinguishes physical splices from pass-through fibers.

**Tech Stack:** Django 5.x, NetBox 4.5+ plugin API, PostgreSQL, pytest

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `netbox_fms/choices.py` | Modify | Add `StorageMethodChoices` |
| `netbox_fms/models.py` | Modify | Add `SlackLoop` model, add `is_express` to `SplicePlanEntry`, update `__all__` |
| `netbox_fms/forms.py` | Modify | Add `SlackLoopForm`, `SlackLoopImportForm`, `SlackLoopBulkEditForm`, `SlackLoopFilterForm`, `InsertSlackLoopForm` |
| `netbox_fms/filters.py` | Modify | Add `SlackLoopFilterSet` |
| `netbox_fms/tables.py` | Modify | Add `SlackLoopTable` |
| `netbox_fms/views.py` | Modify | Add SlackLoop CRUD views + `SlackLoopInsertView` |
| `netbox_fms/urls.py` | Modify | Add SlackLoop URL patterns |
| `netbox_fms/api/serializers.py` | Modify | Add `SlackLoopSerializer` |
| `netbox_fms/api/views.py` | Modify | Add `SlackLoopViewSet` |
| `netbox_fms/api/urls.py` | Modify | Register slack-loops router |
| `netbox_fms/graphql/types.py` | Modify | Add `SlackLoopType` |
| `netbox_fms/graphql/schema.py` | Modify | Add slack_loop queries |
| `netbox_fms/graphql/filters.py` | Modify | Add `SlackLoopFilter` |
| `netbox_fms/search.py` | Modify | Add `SlackLoopIndex` |
| `netbox_fms/navigation.py` | Modify | Add menu entry |
| `netbox_fms/templates/netbox_fms/slackloop.html` | Create | Detail template |
| `netbox_fms/templates/netbox_fms/slackloop_insert.html` | Create | Insert workflow form template |
| `tests/test_slack_loops.py` | Create | SlackLoop model + CRUD tests |
| `tests/test_slack_loop_insert.py` | Create | Insert workflow tests |

---

## Task 1: Add `StorageMethodChoices` and `is_express` field on `SplicePlanEntry`

These are small, independent changes that other tasks depend on.

**Files:**
- Modify: `netbox_fms/choices.py`
- Modify: `netbox_fms/models.py` (SplicePlanEntry class, ~line 840)

- [ ] **Step 1: Write the failing test for StorageMethodChoices**

Create `tests/test_slack_loops.py`:

```python
from django.test import TestCase

from netbox_fms.choices import StorageMethodChoices


class TestStorageMethodChoices(TestCase):
    def test_has_coil(self):
        assert StorageMethodChoices.COIL == "coil"

    def test_has_figure_8(self):
        assert StorageMethodChoices.FIGURE_8 == "figure_8"

    def test_has_in_tray(self):
        assert StorageMethodChoices.IN_TRAY == "in_tray"

    def test_has_on_pole(self):
        assert StorageMethodChoices.ON_POLE == "on_pole"

    def test_has_in_vault(self):
        assert StorageMethodChoices.IN_VAULT == "in_vault"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_slack_loops.py::TestStorageMethodChoices -v
```

Expected: `ImportError: cannot import name 'StorageMethodChoices'`

- [ ] **Step 3: Implement StorageMethodChoices**

In `netbox_fms/choices.py`, add after `SplicePlanStatusChoices`:

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

Also add the `_` import at the top of `choices.py` if not already present:
```python
from django.utils.translation import gettext_lazy as _
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_slack_loops.py::TestStorageMethodChoices -v
```

Expected: All PASS.

- [ ] **Step 5: Write the failing test for is_express on SplicePlanEntry**

Add to `tests/test_slack_loops.py`:

```python
from dcim.models import Device, DeviceRole, DeviceType, FrontPort, Manufacturer, Module, ModuleBay, ModuleType, Site

from netbox_fms.models import SplicePlan, SplicePlanEntry


class TestSplicePlanEntryIsExpress(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="SL Test Site", slug="sl-test-site")
        mfr = Manufacturer.objects.create(name="SL Test Mfr", slug="sl-test-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Closure", slug="sl-closure")
        role = DeviceRole.objects.create(name="SL Splice Closure", slug="sl-splice-closure")
        cls.closure = Device.objects.create(name="SL-Closure-1", site=site, device_type=dt, role=role)

        # Create a module (tray) with FrontPorts
        mt = ModuleType.objects.create(manufacturer=mfr, model="SL Tray")
        mb = ModuleBay.objects.create(device=cls.closure, name="SL-Bay-1")
        cls.tray = Module.objects.create(device=cls.closure, module_bay=mb, module_type=mt)
        cls.fp_a = FrontPort.objects.create(device=cls.closure, module=cls.tray, name="SL-FP-A", type="lc")
        cls.fp_b = FrontPort.objects.create(device=cls.closure, module=cls.tray, name="SL-FP-B", type="lc")

        cls.plan = SplicePlan.objects.create(closure=cls.closure, name="SL Test Plan")

    def test_is_express_default_false(self):
        entry = SplicePlanEntry.objects.create(
            plan=self.plan,
            tray=self.tray,
            fiber_a=self.fp_a,
            fiber_b=self.fp_b,
        )
        assert entry.is_express is False

    def test_is_express_set_true(self):
        entry = SplicePlanEntry.objects.create(
            plan=self.plan,
            tray=self.tray,
            fiber_a=self.fp_a,
            fiber_b=self.fp_b,
            is_express=True,
        )
        assert entry.is_express is True
```

- [ ] **Step 6: Run test to verify it fails**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_slack_loops.py::TestSplicePlanEntryIsExpress -v
```

Expected: `TypeError: ... unexpected keyword argument 'is_express'`

- [ ] **Step 7: Add is_express field to SplicePlanEntry**

In `netbox_fms/models.py`, add to `SplicePlanEntry` class after the `notes` field (~line 871):

```python
    is_express = models.BooleanField(
        verbose_name=_("express"),
        default=False,
        help_text=_("Fiber passes through closure without being physically spliced."),
    )
```

- [ ] **Step 8: Generate and apply migration**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py makemigrations netbox_fms
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py migrate
```

Expected: Migration created that adds `is_express` to `SplicePlanEntry`.

- [ ] **Step 9: Run test to verify it passes**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_slack_loops.py -v
```

Expected: All PASS.

- [ ] **Step 10: Update existing SplicePlanEntry form, serializer, and table to include is_express**

In `netbox_fms/forms.py`, find `SplicePlanEntryForm.Meta.fields` and add `"is_express"` to the tuple.

In `netbox_fms/api/serializers.py`, find `SplicePlanEntrySerializer.Meta.fields` and add `"is_express"` to the tuple.

In `netbox_fms/tables.py`, find `SplicePlanEntryTable` and add:
```python
    is_express = columns.BooleanColumn(verbose_name=_("Express"))
```
Also add `"is_express"` to both `fields` and `default_columns` in the table's Meta.

- [ ] **Step 11: Commit**

```bash
git add netbox_fms/choices.py netbox_fms/models.py netbox_fms/migrations/ netbox_fms/forms.py netbox_fms/api/serializers.py netbox_fms/tables.py tests/test_slack_loops.py
git commit -m "feat: add StorageMethodChoices and is_express field on SplicePlanEntry"
```

---

## Task 2: Add `SlackLoop` model

**Files:**
- Modify: `netbox_fms/models.py`
- Test: `tests/test_slack_loops.py`

- [ ] **Step 1: Write the failing tests for SlackLoop model**

Add to `tests/test_slack_loops.py`:

```python
from decimal import Decimal

from dcim.choices import CableLengthUnitChoices
from dcim.models import Cable, Location

from netbox_fms.models import FiberCable, FiberCableType, SlackLoop


class TestSlackLoopModel(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name="SLM Test Site", slug="slm-test-site")
        cls.location = Location.objects.create(name="Vault-1", slug="vault-1", site=cls.site)
        mfr = Manufacturer.objects.create(name="SLM Mfr", slug="slm-mfr")
        cls.fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="SLM 12F",
            construction="loose_tube",
            fiber_type="smf_os2",
            strand_count=12,
        )
        cable = Cable(
            a_terminations=[],
            b_terminations=[],
            type="smf-os2",
            status="connected",
        )
        # Cable requires terminations to save — create bare cable via ORM
        cable.save_without_terminations = True
        # For testing we use a minimal approach:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO dcim_cable (type, status, created, last_updated) VALUES (%s, %s, NOW(), NOW()) RETURNING id",
                ["smf-os2", "connected"],
            )
            cable_id = cursor.fetchone()[0]
        cls.cable = Cable.objects.get(pk=cable_id)
        cls.fc = FiberCable.objects.create(cable=cls.cable, fiber_cable_type=cls.fct)

    def test_create_slack_loop(self):
        sl = SlackLoop.objects.create(
            fiber_cable=self.fc,
            site=self.site,
            start_mark=Decimal("500.00"),
            end_mark=Decimal("520.00"),
            length_unit=CableLengthUnitChoices.UNIT_METER,
        )
        assert sl.pk is not None
        assert sl.start_mark == Decimal("500.00")
        assert sl.end_mark == Decimal("520.00")

    def test_loop_length_property(self):
        sl = SlackLoop.objects.create(
            fiber_cable=self.fc,
            site=self.site,
            start_mark=Decimal("500.00"),
            end_mark=Decimal("520.00"),
            length_unit=CableLengthUnitChoices.UNIT_METER,
        )
        assert sl.loop_length == Decimal("20.00")

    def test_auto_swap_marks(self):
        sl = SlackLoop.objects.create(
            fiber_cable=self.fc,
            site=self.site,
            start_mark=Decimal("520.00"),
            end_mark=Decimal("500.00"),
            length_unit=CableLengthUnitChoices.UNIT_METER,
        )
        assert sl.start_mark == Decimal("500.00")
        assert sl.end_mark == Decimal("520.00")

    def test_negative_marks_rejected(self):
        from django.core.exceptions import ValidationError

        sl = SlackLoop(
            fiber_cable=self.fc,
            site=self.site,
            start_mark=Decimal("-10.00"),
            end_mark=Decimal("20.00"),
            length_unit=CableLengthUnitChoices.UNIT_METER,
        )
        with self.assertRaises(ValidationError):
            sl.full_clean()

    def test_with_location(self):
        sl = SlackLoop.objects.create(
            fiber_cable=self.fc,
            site=self.site,
            location=self.location,
            start_mark=Decimal("100.00"),
            end_mark=Decimal("115.00"),
            length_unit=CableLengthUnitChoices.UNIT_FOOT,
        )
        assert sl.location == self.location

    def test_with_storage_method(self):
        sl = SlackLoop.objects.create(
            fiber_cable=self.fc,
            site=self.site,
            start_mark=Decimal("200.00"),
            end_mark=Decimal("210.00"),
            length_unit=CableLengthUnitChoices.UNIT_METER,
            storage_method=StorageMethodChoices.FIGURE_8,
        )
        assert sl.storage_method == "figure_8"

    def test_str(self):
        sl = SlackLoop.objects.create(
            fiber_cable=self.fc,
            site=self.site,
            start_mark=Decimal("500.00"),
            end_mark=Decimal("520.00"),
            length_unit=CableLengthUnitChoices.UNIT_METER,
        )
        assert "500" in str(sl)
        assert "520" in str(sl)

    def test_get_absolute_url(self):
        sl = SlackLoop.objects.create(
            fiber_cable=self.fc,
            site=self.site,
            start_mark=Decimal("500.00"),
            end_mark=Decimal("520.00"),
            length_unit=CableLengthUnitChoices.UNIT_METER,
        )
        assert "/slack-loops/" in sl.get_absolute_url()

    def test_unique_together(self):
        SlackLoop.objects.create(
            fiber_cable=self.fc,
            site=self.site,
            start_mark=Decimal("500.00"),
            end_mark=Decimal("520.00"),
            length_unit=CableLengthUnitChoices.UNIT_METER,
        )
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            SlackLoop.objects.create(
                fiber_cable=self.fc,
                site=self.site,
                start_mark=Decimal("500.00"),
                end_mark=Decimal("520.00"),
                length_unit=CableLengthUnitChoices.UNIT_METER,
            )

    def test_cascade_delete_with_fiber_cable(self):
        """Deleting a FiberCable cascades to its SlackLoops. Uses own objects to avoid affecting other tests."""
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO dcim_cable (type, status, created, last_updated) VALUES (%s, %s, NOW(), NOW()) RETURNING id",
                ["smf-os2", "connected"],
            )
            cable_id = cursor.fetchone()[0]
        cable2 = Cable.objects.get(pk=cable_id)
        fc2 = FiberCable.objects.create(cable=cable2, fiber_cable_type=self.fct)
        sl = SlackLoop.objects.create(
            fiber_cable=fc2,
            site=self.site,
            start_mark=Decimal("500.00"),
            end_mark=Decimal("520.00"),
            length_unit=CableLengthUnitChoices.UNIT_METER,
        )
        sl_pk = sl.pk
        fc2.delete()
        assert not SlackLoop.objects.filter(pk=sl_pk).exists()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_slack_loops.py::TestSlackLoopModel -v
```

Expected: `ImportError: cannot import name 'SlackLoop'`

- [ ] **Step 3: Implement SlackLoop model**

In `netbox_fms/models.py`, add `SlackLoop` to imports and `__all__`:

```python
# In imports at top, add:
from dcim.choices import CableLengthUnitChoices

# In __all__, add "SlackLoop"

# In choices import, add StorageMethodChoices
```

Add the model after `ClosureCableEntry` (before the FiberCircuit section):

```python
class SlackLoop(NetBoxModel):
    """
    A coil of spare fiber cable left at a specific location along a route
    for future access, re-splicing, or mid-span maintenance.
    """

    fiber_cable = models.ForeignKey(
        to="netbox_fms.FiberCable",
        on_delete=models.CASCADE,
        related_name="slack_loops",
        verbose_name=_("fiber cable"),
    )
    site = models.ForeignKey(
        to="dcim.Site",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("site"),
    )
    location = models.ForeignKey(
        to="dcim.Location",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("location"),
        blank=True,
        null=True,
    )
    start_mark = models.DecimalField(
        verbose_name=_("start mark"),
        max_digits=10,
        decimal_places=2,
        help_text=_("Sheath distance mark where the loop begins."),
    )
    end_mark = models.DecimalField(
        verbose_name=_("end mark"),
        max_digits=10,
        decimal_places=2,
        help_text=_("Sheath distance mark where the loop ends."),
    )
    length_unit = models.CharField(
        verbose_name=_("length unit"),
        max_length=10,
        choices=CableLengthUnitChoices,
    )
    storage_method = models.CharField(
        verbose_name=_("storage method"),
        max_length=50,
        choices=StorageMethodChoices,
        blank=True,
    )
    notes = models.TextField(
        verbose_name=_("notes"),
        blank=True,
    )

    class Meta:
        ordering = ("fiber_cable", "start_mark")
        unique_together = ("fiber_cable", "start_mark", "end_mark")
        verbose_name = _("slack loop")
        verbose_name_plural = _("slack loops")

    def __str__(self):
        return f"{self.fiber_cable} @ {self.start_mark}\u2013{self.end_mark} {self.length_unit}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_fms:slackloop", args=[self.pk])

    @property
    def loop_length(self):
        return self.end_mark - self.start_mark

    def clean(self):
        super().clean()
        if self.start_mark is not None and self.start_mark < 0:
            raise ValidationError({"start_mark": _("Start mark must be non-negative.")})
        if self.end_mark is not None and self.end_mark < 0:
            raise ValidationError({"end_mark": _("End mark must be non-negative.")})

    def save(self, *args, **kwargs):
        # Auto-normalize: ensure start_mark <= end_mark
        if self.start_mark is not None and self.end_mark is not None and self.end_mark < self.start_mark:
            self.start_mark, self.end_mark = self.end_mark, self.start_mark
        super().save(*args, **kwargs)
```

- [ ] **Step 4: Generate and apply migration**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py makemigrations netbox_fms
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py migrate
```

Expected: Migration creates `SlackLoop` table.

- [ ] **Step 5: Run test to verify it passes**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_slack_loops.py::TestSlackLoopModel -v
```

Expected: All PASS.

- [ ] **Step 6: Run all existing tests to check for regressions**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v
```

Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add netbox_fms/models.py netbox_fms/migrations/ tests/test_slack_loops.py
git commit -m "feat: add SlackLoop model"
```

---

## Task 3: Add SlackLoop full-stack CRUD (forms, filters, tables, views, urls, templates)

**Files:**
- Modify: `netbox_fms/forms.py`
- Modify: `netbox_fms/filters.py`
- Modify: `netbox_fms/tables.py`
- Modify: `netbox_fms/views.py`
- Modify: `netbox_fms/urls.py`
- Create: `netbox_fms/templates/netbox_fms/slackloop.html`

- [ ] **Step 1: Add SlackLoop forms**

In `netbox_fms/forms.py`, add imports:

```python
from dcim.choices import CableLengthUnitChoices
from dcim.models import Location, Site
# ... (add Site, Location to existing dcim.models import)

from .choices import StorageMethodChoices
# ... (add to existing choices import)

from .models import SlackLoop
# ... (add to existing models import)
```

Add forms:

```python
# ---------------------------------------------------------------------------
# SlackLoop
# ---------------------------------------------------------------------------


class SlackLoopForm(NetBoxModelForm):
    fiber_cable = DynamicModelChoiceField(queryset=FiberCable.objects.all(), label=_("Fiber Cable"))
    site = DynamicModelChoiceField(queryset=Site.objects.all(), label=_("Site"))
    location = DynamicModelChoiceField(
        queryset=Location.objects.all(),
        label=_("Location"),
        required=False,
        query_params={"site_id": "$site"},
    )

    fieldsets = (
        FieldSet("fiber_cable", "site", "location", name=_("Slack Loop")),
        FieldSet("start_mark", "end_mark", "length_unit", name=_("Position")),
        FieldSet("storage_method", name=_("Storage")),
        FieldSet("notes", "tags", name=_("Additional")),
    )

    class Meta:
        model = SlackLoop
        fields = (
            "fiber_cable",
            "site",
            "location",
            "start_mark",
            "end_mark",
            "length_unit",
            "storage_method",
            "notes",
            "tags",
        )


class SlackLoopImportForm(NetBoxModelImportForm):
    class Meta:
        model = SlackLoop
        fields = (
            "fiber_cable",
            "site",
            "location",
            "start_mark",
            "end_mark",
            "length_unit",
            "storage_method",
            "notes",
        )


class SlackLoopBulkEditForm(NetBoxModelBulkEditForm):
    model = SlackLoop
    site = DynamicModelChoiceField(queryset=Site.objects.all(), required=False, label=_("Site"))
    location = DynamicModelChoiceField(queryset=Location.objects.all(), required=False, label=_("Location"))
    length_unit = forms.ChoiceField(choices=CableLengthUnitChoices, required=False, label=_("Length Unit"))
    storage_method = forms.ChoiceField(choices=StorageMethodChoices, required=False, label=_("Storage Method"))

    fieldsets = (
        FieldSet("site", "location", "length_unit", "storage_method"),
    )
    nullable_fields = ("location", "storage_method")


class SlackLoopFilterForm(NetBoxModelFilterSetForm):
    model = SlackLoop
    fiber_cable_id = DynamicModelChoiceField(
        queryset=FiberCable.objects.all(),
        required=False,
        label=_("Fiber Cable"),
    )
    site_id = DynamicModelChoiceField(
        queryset=Site.objects.all(),
        required=False,
        label=_("Site"),
    )
    location_id = DynamicModelChoiceField(
        queryset=Location.objects.all(),
        required=False,
        label=_("Location"),
    )
    length_unit = forms.MultipleChoiceField(
        choices=CableLengthUnitChoices,
        required=False,
        label=_("Length Unit"),
    )
    storage_method = forms.MultipleChoiceField(
        choices=StorageMethodChoices,
        required=False,
        label=_("Storage Method"),
    )
```

- [ ] **Step 2: Add SlackLoop filter set**

In `netbox_fms/filters.py`, add imports:

```python
from dcim.choices import CableLengthUnitChoices
from dcim.models import Location, Site
# ... (add Site, Location to existing dcim.models import)

from .choices import StorageMethodChoices
# ... (add to existing choices import)

from .models import SlackLoop
# ... (add to existing models import)
```

Add filter set:

```python
class SlackLoopFilterSet(NetBoxModelFilterSet):
    fiber_cable_id = django_filters.ModelMultipleChoiceFilter(
        queryset=FiberCable.objects.all(),
        field_name="fiber_cable",
        label=_("Fiber Cable (ID)"),
    )
    site_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Site.objects.all(),
        field_name="site",
        label=_("Site (ID)"),
    )
    location_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Location.objects.all(),
        field_name="location",
        label=_("Location (ID)"),
    )
    length_unit = django_filters.MultipleChoiceFilter(choices=CableLengthUnitChoices)
    storage_method = django_filters.MultipleChoiceFilter(choices=StorageMethodChoices)

    class Meta:
        model = SlackLoop
        fields = ("id", "fiber_cable_id", "site_id", "location_id", "length_unit", "storage_method")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(notes__icontains=value))
```

- [ ] **Step 3: Add SlackLoop table**

In `netbox_fms/tables.py`, add import:

```python
from .models import SlackLoop
# ... (add to existing models import)
```

Add table:

```python
class SlackLoopTable(NetBoxTable):
    pk = columns.ToggleColumn()
    fiber_cable = tables.Column(linkify=True, verbose_name=_("Fiber Cable"))
    site = tables.Column(linkify=True, verbose_name=_("Site"))
    location = tables.Column(linkify=True, verbose_name=_("Location"))
    start_mark = tables.Column(verbose_name=_("Start Mark"))
    end_mark = tables.Column(verbose_name=_("End Mark"))
    loop_length = tables.Column(verbose_name=_("Loop Length"), accessor="loop_length", orderable=False)
    length_unit = tables.Column(verbose_name=_("Unit"))
    storage_method = tables.Column(verbose_name=_("Storage Method"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = SlackLoop
        fields = (
            "pk",
            "id",
            "fiber_cable",
            "site",
            "location",
            "start_mark",
            "end_mark",
            "loop_length",
            "length_unit",
            "storage_method",
            "actions",
        )
        default_columns = (
            "pk",
            "fiber_cable",
            "site",
            "start_mark",
            "end_mark",
            "loop_length",
            "length_unit",
            "actions",
        )
```

- [ ] **Step 4: Add SlackLoop views**

In `netbox_fms/views.py`, add imports:

```python
from .filters import SlackLoopFilterSet
# ... (add to existing filters import)

from .forms import SlackLoopBulkEditForm, SlackLoopFilterForm, SlackLoopForm, SlackLoopImportForm
# ... (add to existing forms import)

from .models import SlackLoop
# ... (add to existing models import)

from .tables import SlackLoopTable
# ... (add to existing tables import)
```

Add views:

```python
# ---------------------------------------------------------------------------
# SlackLoop
# ---------------------------------------------------------------------------


class SlackLoopListView(generic.ObjectListView):
    queryset = SlackLoop.objects.prefetch_related("fiber_cable", "site", "location", "tags")
    filterset = SlackLoopFilterSet
    filterset_form = SlackLoopFilterForm
    table = SlackLoopTable


class SlackLoopView(generic.ObjectView):
    queryset = SlackLoop.objects.all()


class SlackLoopEditView(generic.ObjectEditView):
    queryset = SlackLoop.objects.all()
    form = SlackLoopForm


class SlackLoopDeleteView(generic.ObjectDeleteView):
    queryset = SlackLoop.objects.all()


class SlackLoopBulkImportView(generic.BulkImportView):
    queryset = SlackLoop.objects.all()
    model_form = SlackLoopImportForm


class SlackLoopBulkEditView(generic.BulkEditView):
    queryset = SlackLoop.objects.prefetch_related("fiber_cable", "site", "location", "tags")
    filterset = SlackLoopFilterSet
    table = SlackLoopTable
    form = SlackLoopBulkEditForm


class SlackLoopBulkDeleteView(generic.BulkDeleteView):
    queryset = SlackLoop.objects.all()
    filterset = SlackLoopFilterSet
    table = SlackLoopTable
```

- [ ] **Step 5: Add SlackLoop URL patterns**

In `netbox_fms/urls.py`, add before the `# Import/Apply/Export` comment:

```python
    # SlackLoop
    path("slack-loops/", views.SlackLoopListView.as_view(), name="slackloop_list"),
    path("slack-loops/add/", views.SlackLoopEditView.as_view(), name="slackloop_add"),
    path("slack-loops/import/", views.SlackLoopBulkImportView.as_view(), name="slackloop_import"),
    path("slack-loops/edit/", views.SlackLoopBulkEditView.as_view(), name="slackloop_bulk_edit"),
    path("slack-loops/delete/", views.SlackLoopBulkDeleteView.as_view(), name="slackloop_bulk_delete"),
    path("slack-loops/<int:pk>/", include(get_model_urls("netbox_fms", "slackloop"))),
    path("slack-loops/<int:pk>/", views.SlackLoopView.as_view(), name="slackloop"),
    path("slack-loops/<int:pk>/edit/", views.SlackLoopEditView.as_view(), name="slackloop_edit"),
    path("slack-loops/<int:pk>/delete/", views.SlackLoopDeleteView.as_view(), name="slackloop_delete"),
```

- [ ] **Step 6: Create detail template**

Create `netbox_fms/templates/netbox_fms/slackloop.html`:

```html
{% extends 'generic/object.html' %}
{% load helpers %}
{% load plugins %}
{% load i18n %}

{% block content %}
<div class="row mb-3">
    <div class="col col-md-6">
        <div class="card">
            <h5 class="card-header">{% trans "Slack Loop" %}</h5>
            <table class="table table-hover attr-table">
                <tr>
                    <th scope="row">{% trans "Fiber Cable" %}</th>
                    <td>{{ object.fiber_cable|linkify }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Site" %}</th>
                    <td>{{ object.site|linkify }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Location" %}</th>
                    <td>{{ object.location|linkify|default:"—" }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Storage Method" %}</th>
                    <td>{{ object.get_storage_method_display|default:"—" }}</td>
                </tr>
            </table>
        </div>
    </div>
    <div class="col col-md-6">
        <div class="card">
            <h5 class="card-header">{% trans "Position" %}</h5>
            <table class="table table-hover attr-table">
                <tr>
                    <th scope="row">{% trans "Start Mark" %}</th>
                    <td>{{ object.start_mark }} {{ object.get_length_unit_display }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "End Mark" %}</th>
                    <td>{{ object.end_mark }} {{ object.get_length_unit_display }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Loop Length" %}</th>
                    <td>{{ object.loop_length }} {{ object.get_length_unit_display }}</td>
                </tr>
            </table>
        </div>
    </div>
</div>
<div class="row mb-3">
    <div class="col col-md-12">
        {% if object.notes %}
        <div class="card">
            <h5 class="card-header">{% trans "Notes" %}</h5>
            <div class="card-body">{{ object.notes|markdown }}</div>
        </div>
        {% endif %}
    </div>
</div>
{% plugin_full_width_page object %}
{% endblock %}
```

- [ ] **Step 7: Verify imports are clean**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.models import *; from netbox_fms.forms import *; from netbox_fms.filters import *; from netbox_fms.tables import *"
```

Expected: No errors.

- [ ] **Step 8: Run all tests**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v
```

Expected: All PASS.

- [ ] **Step 9: Commit**

```bash
git add netbox_fms/forms.py netbox_fms/filters.py netbox_fms/tables.py netbox_fms/views.py netbox_fms/urls.py netbox_fms/templates/netbox_fms/slackloop.html
git commit -m "feat: add SlackLoop full-stack CRUD (forms, filters, tables, views, urls, template)"
```

---

## Task 4: Add SlackLoop API, GraphQL, search, navigation

**Files:**
- Modify: `netbox_fms/api/serializers.py`
- Modify: `netbox_fms/api/views.py`
- Modify: `netbox_fms/api/urls.py`
- Modify: `netbox_fms/graphql/types.py`
- Modify: `netbox_fms/graphql/schema.py`
- Modify: `netbox_fms/graphql/filters.py`
- Modify: `netbox_fms/search.py`
- Modify: `netbox_fms/navigation.py`

- [ ] **Step 1: Add SlackLoop API serializer**

In `netbox_fms/api/serializers.py`, add import and serializer:

```python
from netbox_fms.models import SlackLoop
# ... (add to existing import)
```

```python
class SlackLoopSerializer(NetBoxModelSerializer):
    loop_length = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = SlackLoop
        fields = (
            "id",
            "url",
            "display",
            "fiber_cable",
            "site",
            "location",
            "start_mark",
            "end_mark",
            "length_unit",
            "loop_length",
            "storage_method",
            "notes",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )

Note: `loop_length` is a `@property` on the model, not a field. DRF won't auto-serialize it, so the explicit `serializers.DecimalField(read_only=True)` declaration is required. Also add `from rest_framework import serializers` if not already imported.
```

- [ ] **Step 2: Add SlackLoop API viewset**

In `netbox_fms/api/views.py`, add import and viewset:

```python
from netbox_fms.filters import SlackLoopFilterSet
from netbox_fms.models import SlackLoop
# ... (add to existing imports)
```

```python
class SlackLoopViewSet(NetBoxModelViewSet):
    queryset = SlackLoop.objects.prefetch_related("fiber_cable", "site", "location", "tags")
    serializer_class = SlackLoopSerializer
    filterset_class = SlackLoopFilterSet
```

- [ ] **Step 3: Register SlackLoop API router**

In `netbox_fms/api/urls.py`, add:

```python
router.register("slack-loops", views.SlackLoopViewSet)
```

- [ ] **Step 4: Add SlackLoop GraphQL type**

In `netbox_fms/graphql/types.py`, add import and type:

```python
from ..models import SlackLoop
# ... (add to existing models import)

# Add to __all__:
# "SlackLoopType",
```

```python
@strawberry_django.type(SlackLoop, fields="__all__")
class SlackLoopType(NetBoxObjectType):
    pass
```

- [ ] **Step 5: Add SlackLoop GraphQL schema entries**

In `netbox_fms/graphql/schema.py`, add import and fields:

```python
from .types import SlackLoopType
# ... (add to existing import)
```

Add to `NetBoxFMSQuery`:

```python
    slack_loop: SlackLoopType = strawberry_django.field()
    slack_loop_list: list[SlackLoopType] = strawberry_django.field()
```

- [ ] **Step 6: Add SlackLoop GraphQL filter**

In `netbox_fms/graphql/filters.py`, add import and filter:

```python
from ..models import SlackLoop
# ... (add to existing models import)

# Add to __all__:
# "SlackLoopFilter",
```

```python
@strawberry_django.filters.filter(SlackLoop)
class SlackLoopFilter:
    id: int | None
    fiber_cable_id: int | None
    site_id: int | None
    location_id: int | None
    storage_method: str | None
    length_unit: str | None
```

- [ ] **Step 7: Add SlackLoop search index**

In `netbox_fms/search.py`, add:

```python
from .models import SlackLoop
# ... (add to existing import)


@register_search
class SlackLoopIndex(SearchIndex):
    model = SlackLoop
    fields = (
        ("notes", 5000),
    )
    display_attrs = ("fiber_cable", "site", "start_mark", "end_mark", "length_unit")
```

- [ ] **Step 8: Add SlackLoop navigation menu entry**

In `netbox_fms/navigation.py`, add a new group after "Fiber Cables":

```python
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
```

- [ ] **Step 9: Verify all imports are clean**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.models import *; from netbox_fms.forms import *; from netbox_fms.filters import *; from netbox_fms.tables import *; from netbox_fms.api.serializers import *; from netbox_fms.api.views import *; from netbox_fms.graphql.types import *; from netbox_fms.graphql.filters import *"
```

Expected: No errors.

- [ ] **Step 10: Run all tests**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v
```

Expected: All PASS.

- [ ] **Step 11: Commit**

```bash
git add netbox_fms/api/ netbox_fms/graphql/ netbox_fms/search.py netbox_fms/navigation.py
git commit -m "feat: add SlackLoop API, GraphQL, search, and navigation"
```

---

## Task 5: Insert into Splice Closure — form and view

This is the complex workflow task. It implements the "Insert into Splice Closure" action from the spec.

**Files:**
- Modify: `netbox_fms/forms.py` (add `InsertSlackLoopForm`)
- Modify: `netbox_fms/views.py` (add `SlackLoopInsertView`)
- Modify: `netbox_fms/urls.py` (add insert URL)
- Create: `netbox_fms/templates/netbox_fms/slackloop_insert.html`
- Modify: `netbox_fms/templates/netbox_fms/slackloop.html` (add "Insert" button)
- Create: `tests/test_slack_loop_insert.py`

- [ ] **Step 1: Write the failing test for the insert workflow**

Create `tests/test_slack_loop_insert.py`:

```python
from decimal import Decimal

from dcim.choices import CableLengthUnitChoices
from dcim.models import (
    Cable,
    Device,
    DeviceRole,
    DeviceType,
    FrontPort,
    Manufacturer,
    Module,
    ModuleBay,
    ModuleType,
    RearPort,
    Site,
)
from django.test import TestCase

from netbox_fms.models import (
    ClosureCableEntry,
    FiberCable,
    FiberCableType,
    SlackLoop,
    SplicePlan,
    SplicePlanEntry,
)
from netbox_fms.views import insert_slack_loop_into_closure


class TestInsertSlackLoopIntoClosure(TestCase):
    """Test the core insert_slack_loop_into_closure() service function."""

    @classmethod
    def setUpTestData(cls):
        # Sites
        cls.site_a = Site.objects.create(name="INS Site A", slug="ins-site-a")
        cls.site_b = Site.objects.create(name="INS Site B", slug="ins-site-b")
        cls.site_mid = Site.objects.create(name="INS Site Mid", slug="ins-site-mid")

        mfr = Manufacturer.objects.create(name="INS Mfr", slug="ins-mfr")
        dt_panel = DeviceType.objects.create(manufacturer=mfr, model="INS Panel", slug="ins-panel")
        dt_closure = DeviceType.objects.create(manufacturer=mfr, model="INS Closure", slug="ins-closure")
        role = DeviceRole.objects.create(name="INS Role", slug="ins-role")

        # Endpoint devices with RearPorts
        cls.dev_a = Device.objects.create(name="INS-Dev-A", site=cls.site_a, device_type=dt_panel, role=role)
        cls.dev_b = Device.objects.create(name="INS-Dev-B", site=cls.site_b, device_type=dt_panel, role=role)
        cls.rp_a = RearPort.objects.create(device=cls.dev_a, name="INS-RP-A1", type="lc", positions=1)
        cls.rp_b = RearPort.objects.create(device=cls.dev_b, name="INS-RP-B1", type="lc", positions=1)

        # Closure device with RearPorts and a tray with FrontPorts
        cls.closure = Device.objects.create(name="INS-Closure", site=cls.site_mid, device_type=dt_closure, role=role)
        cls.closure_rp_a = RearPort.objects.create(device=cls.closure, name="INS-CRP-A", type="lc", positions=1)
        cls.closure_rp_b = RearPort.objects.create(device=cls.closure, name="INS-CRP-B", type="lc", positions=1)

        mt = ModuleType.objects.create(manufacturer=mfr, model="INS Tray")
        mb = ModuleBay.objects.create(device=cls.closure, name="INS-Bay-1")
        cls.tray = Module.objects.create(device=cls.closure, module_bay=mb, module_type=mt)
        cls.closure_fp_a = FrontPort.objects.create(
            device=cls.closure, module=cls.tray, name="INS-CFP-A", type="lc",
        )
        cls.closure_fp_b = FrontPort.objects.create(
            device=cls.closure, module=cls.tray, name="INS-CFP-B", type="lc",
        )

        # NetBox 4.5+ uses PortMapping to connect FrontPort ↔ RearPort
        from dcim.models import PortMapping

        PortMapping.objects.create(
            device=cls.closure,
            front_port=cls.closure_fp_a,
            rear_port=cls.closure_rp_a,
        )
        PortMapping.objects.create(
            device=cls.closure,
            front_port=cls.closure_fp_b,
            rear_port=cls.closure_rp_b,
        )

        # FiberCableType: simple 1-strand cable for testing
        cls.fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="INS 1F",
            construction="tight_buffer",
            fiber_type="smf_os2",
            strand_count=1,
        )

    def _make_cable_and_loop(self):
        """Helper: create a Cable with RearPort terminations, FiberCable, and SlackLoop."""
        cable = Cable(
            a_terminations=[self.rp_a],
            b_terminations=[self.rp_b],
            type="smf-os2",
            status="connected",
        )
        cable.save()
        fc = FiberCable.objects.create(cable=cable, fiber_cable_type=self.fct)
        sl = SlackLoop.objects.create(
            fiber_cable=fc,
            site=self.site_mid,
            start_mark=Decimal("500.00"),
            end_mark=Decimal("520.00"),
            length_unit=CableLengthUnitChoices.UNIT_METER,
        )
        return cable, fc, sl

    def test_insert_creates_two_new_cables(self):
        old_cable, fc, sl = self._make_cable_and_loop()
        old_cable_pk = old_cable.pk

        insert_slack_loop_into_closure(
            slack_loop=sl,
            closure=self.closure,
            a_side_rear_ports=[self.closure_rp_a],
            b_side_rear_ports=[self.closure_rp_b],
            express_strand_positions=set(),
        )

        # Old cable should be gone
        assert not Cable.objects.filter(pk=old_cable_pk).exists()

        # Two new cables exist
        new_cables = Cable.objects.exclude(pk=old_cable_pk)
        assert new_cables.count() >= 2

    def test_insert_creates_fiber_cables(self):
        old_cable, fc, sl = self._make_cable_and_loop()

        insert_slack_loop_into_closure(
            slack_loop=sl,
            closure=self.closure,
            a_side_rear_ports=[self.closure_rp_a],
            b_side_rear_ports=[self.closure_rp_b],
            express_strand_positions=set(),
        )

        # Two new FiberCables exist (old one cascade-deleted)
        new_fcs = FiberCable.objects.filter(fiber_cable_type=self.fct)
        assert new_fcs.count() == 2

    def test_insert_creates_splice_plan_entries(self):
        old_cable, fc, sl = self._make_cable_and_loop()

        insert_slack_loop_into_closure(
            slack_loop=sl,
            closure=self.closure,
            a_side_rear_ports=[self.closure_rp_a],
            b_side_rear_ports=[self.closure_rp_b],
            express_strand_positions=set(),
        )

        plan = SplicePlan.objects.get(closure=self.closure)
        assert plan.entries.count() == 1  # 1-strand cable

    def test_insert_express_strands(self):
        old_cable, fc, sl = self._make_cable_and_loop()

        insert_slack_loop_into_closure(
            slack_loop=sl,
            closure=self.closure,
            a_side_rear_ports=[self.closure_rp_a],
            b_side_rear_ports=[self.closure_rp_b],
            express_strand_positions={1},  # strand 1 is express
        )

        plan = SplicePlan.objects.get(closure=self.closure)
        entry = plan.entries.first()
        assert entry.is_express is True

    def test_insert_creates_closure_cable_entries(self):
        old_cable, fc, sl = self._make_cable_and_loop()

        insert_slack_loop_into_closure(
            slack_loop=sl,
            closure=self.closure,
            a_side_rear_ports=[self.closure_rp_a],
            b_side_rear_ports=[self.closure_rp_b],
            express_strand_positions=set(),
        )

        entries = ClosureCableEntry.objects.filter(closure=self.closure)
        assert entries.count() == 2

    def test_insert_deletes_slack_loop(self):
        old_cable, fc, sl = self._make_cable_and_loop()
        sl_pk = sl.pk

        insert_slack_loop_into_closure(
            slack_loop=sl,
            closure=self.closure,
            a_side_rear_ports=[self.closure_rp_a],
            b_side_rear_ports=[self.closure_rp_b],
            express_strand_positions=set(),
        )

        assert not SlackLoop.objects.filter(pk=sl_pk).exists()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_slack_loop_insert.py -v
```

Expected: `ImportError: cannot import name 'insert_slack_loop_into_closure'`

- [ ] **Step 3: Implement `insert_slack_loop_into_closure` service function**

In `netbox_fms/views.py`, add the service function (it lives in views.py for now to keep things simple — it could be extracted to a services.py later):

```python
def insert_slack_loop_into_closure(slack_loop, closure, a_side_rear_ports, b_side_rear_ports, express_strand_positions):
    """
    Split a cable at a slack loop location and connect both halves through a closure.

    Args:
        slack_loop: SlackLoop instance to convert
        closure: dcim.Device (the closure)
        a_side_rear_ports: list of RearPort objects on the closure for the A-side cable
        b_side_rear_ports: list of RearPort objects on the closure for the B-side cable
        express_strand_positions: set of strand positions (1-indexed) that are express (pass-through)
    """
    from dcim.models import CableTermination

    old_fiber_cable = slack_loop.fiber_cable
    old_cable = old_fiber_cable.cable
    fct = old_fiber_cable.fiber_cable_type
    old_metadata = {
        "serial_number": old_fiber_cable.serial_number,
        "install_date": old_fiber_cable.install_date,
        "notes": old_fiber_cable.notes,
    }

    # Capture old cable's termination endpoint OBJECTS (not CableTermination rows,
    # which will be cascade-deleted). a_terminations/b_terminations return the actual
    # endpoint objects (RearPort, Interface, etc.) via CableTermination.termination.
    old_a_terms = list(old_cable.a_terminations)
    old_b_terms = list(old_cable.b_terminations)
    old_cable_attrs = {
        "type": old_cable.type,
        "status": old_cable.status,
        "label": old_cable.label,
        "color": old_cable.color,
    }

    with transaction.atomic():
        # Step 1: Snapshot for change logging
        old_cable.snapshot()

        # Step 2: Handle FiberCircuitNode references (if the model exists)
        rewiring_records = []
        try:
            from .models import FiberCircuitNode

            nodes = FiberCircuitNode.objects.filter(
                models.Q(cable=old_cable)
                | models.Q(fiber_strand__fiber_cable=old_fiber_cable)
            )
            for node in nodes:
                record = {
                    "path_id": node.path_id,
                    "position": node.position,
                }
                if node.cable_id:
                    record["field"] = "cable"
                elif node.fiber_strand_id:
                    record["field"] = "fiber_strand"
                    record["strand_position"] = node.fiber_strand.position
                rewiring_records.append(record)
            nodes.delete()
        except (ImportError, LookupError):
            pass  # FiberCircuitNode not yet implemented

        # Step 3: Delete old cable (cascades FiberCable, strands, etc.)
        old_cable.delete()

        # Step 4: Create Cable A (original A-side → closure)
        cable_a = Cable(
            a_terminations=old_a_terms,
            b_terminations=a_side_rear_ports,
            **old_cable_attrs,
        )
        cable_a.save()

        # Step 5: Create Cable B (closure → original B-side)
        cable_b = Cable(
            a_terminations=b_side_rear_ports,
            b_terminations=old_b_terms,
            **old_cable_attrs,
        )
        cable_b.save()

        # Step 6: Create FiberCable instances (auto-instantiates strands)
        fc_a = FiberCable.objects.create(
            cable=cable_a,
            fiber_cable_type=fct,
            **old_metadata,
        )
        fc_b = FiberCable.objects.create(
            cable=cable_b,
            fiber_cable_type=fct,
            **old_metadata,
        )

        # Step 7: Create SplicePlan + entries
        plan, _ = SplicePlan.objects.get_or_create(
            closure=closure,
            defaults={"name": f"Plan for {closure.name}"},
        )

        # Find FrontPorts on the closure mapped to our RearPorts
        # NetBox 4.5+ uses PortMapping (separate model) instead of direct FK
        from dcim.models import FrontPort as DcimFrontPort, PortMapping

        a_front_ports = list(
            DcimFrontPort.objects.filter(
                mappings__rear_port__in=a_side_rear_ports,
            ).order_by("mappings__rear_port_position")
        )
        b_front_ports = list(
            DcimFrontPort.objects.filter(
                mappings__rear_port__in=b_side_rear_ports,
            ).order_by("mappings__rear_port_position")
        )

        # Get the tray (module) from the first FrontPort
        tray = a_front_ports[0].module if a_front_ports and a_front_ports[0].module else None

        entries = []
        for i, (fp_a, fp_b) in enumerate(zip(a_front_ports, b_front_ports)):
            strand_pos = i + 1
            entry_tray = fp_a.module or tray
            entries.append(
                SplicePlanEntry(
                    plan=plan,
                    tray=entry_tray,
                    fiber_a=fp_a,
                    fiber_b=fp_b,
                    is_express=strand_pos in express_strand_positions,
                )
            )
        SplicePlanEntry.objects.bulk_create(entries)

        # Step 8: Create ClosureCableEntry records
        ClosureCableEntry.objects.create(closure=closure, fiber_cable=fc_a)
        ClosureCableEntry.objects.create(closure=closure, fiber_cable=fc_b)

        # Step 9: Re-wire FiberCircuitNodes (if any)
        if rewiring_records:
            try:
                from .models import FiberCircuitNode

                for record in rewiring_records:
                    kwargs = {"path_id": record["path_id"], "position": record["position"]}
                    if record["field"] == "cable":
                        # Determine which side — heuristic: check if original node's cable
                        # was the same as old_cable (it always is), map based on termination side
                        # For simplicity, map to cable_a (A-side)
                        kwargs["cable"] = cable_a
                    elif record["field"] == "fiber_strand":
                        strand_pos = record["strand_position"]
                        # Try A-side first, then B-side
                        strand = fc_a.fiber_strands.filter(position=strand_pos).first()
                        if not strand:
                            strand = fc_b.fiber_strands.filter(position=strand_pos).first()
                        if strand:
                            kwargs["fiber_strand"] = strand
                        else:
                            continue  # Skip if strand not found
                    FiberCircuitNode.objects.create(**kwargs)
            except (ImportError, LookupError):
                pass

        # Step 10: Delete the SlackLoop
        slack_loop.delete()

    return cable_a, cable_b, fc_a, fc_b, plan
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_slack_loop_insert.py -v
```

Expected: All PASS (or some failures that need debugging — iterate until all pass).

- [ ] **Step 5: Add InsertSlackLoopForm**

In `netbox_fms/forms.py`, add:

```python
from dcim.models import RearPort
# ... (add to existing dcim.models import)


class InsertSlackLoopForm(forms.Form):
    """Form for the 'Insert into Splice Closure' workflow."""

    closure = DynamicModelChoiceField(
        queryset=Device.objects.all(),
        label=_("Closure"),
        help_text=_("Target splice closure device."),
    )
    a_side_rear_ports = DynamicModelMultipleChoiceField(
        queryset=RearPort.objects.all(),
        label=_("A-side Rear Ports"),
        help_text=_("Closure RearPorts for the A-side cable segment."),
        query_params={"device_id": "$closure"},
    )
    b_side_rear_ports = DynamicModelMultipleChoiceField(
        queryset=RearPort.objects.all(),
        label=_("B-side Rear Ports"),
        help_text=_("Closure RearPorts for the B-side cable segment."),
        query_params={"device_id": "$closure"},
    )
    express_strand_positions = forms.CharField(
        required=False,
        label=_("Express Strand Positions"),
        help_text=_("Comma-separated list of strand positions that pass through without splicing (e.g., '1,2,3')."),
    )

    def clean_express_strand_positions(self):
        value = self.cleaned_data.get("express_strand_positions", "")
        if not value.strip():
            return set()
        try:
            return {int(x.strip()) for x in value.split(",") if x.strip()}
        except ValueError:
            raise forms.ValidationError(_("Enter comma-separated integers."))
```

- [ ] **Step 6: Add SlackLoopInsertView**

In `netbox_fms/views.py`, add:

```python
class SlackLoopInsertView(LoginRequiredMixin, View):
    """Insert a slack loop into a splice closure by splitting the cable."""

    def get(self, request, pk):
        slack_loop = get_object_or_404(SlackLoop, pk=pk)
        form = InsertSlackLoopForm()
        return render(request, "netbox_fms/slackloop_insert.html", {
            "object": slack_loop,
            "form": form,
        })

    def post(self, request, pk):
        slack_loop = get_object_or_404(SlackLoop, pk=pk)
        form = InsertSlackLoopForm(request.POST)

        if form.is_valid():
            try:
                cable_a, cable_b, fc_a, fc_b, plan = insert_slack_loop_into_closure(
                    slack_loop=slack_loop,
                    closure=form.cleaned_data["closure"],
                    a_side_rear_ports=list(form.cleaned_data["a_side_rear_ports"]),
                    b_side_rear_ports=list(form.cleaned_data["b_side_rear_ports"]),
                    express_strand_positions=form.cleaned_data["express_strand_positions"],
                )
                messages.success(request, f"Slack loop inserted into {form.cleaned_data['closure']}.")
                return redirect(plan.get_absolute_url())
            except Exception as e:
                messages.error(request, f"Failed to insert slack loop: {e}")

        return render(request, "netbox_fms/slackloop_insert.html", {
            "object": slack_loop,
            "form": form,
        })
```

Add import for `InsertSlackLoopForm` in the forms import block.

- [ ] **Step 7: Add insert URL**

In `netbox_fms/urls.py`, add after the slack-loops delete URL:

```python
    path("slack-loops/<int:pk>/insert/", views.SlackLoopInsertView.as_view(), name="slackloop_insert"),
```

- [ ] **Step 8: Create insert template**

Create `netbox_fms/templates/netbox_fms/slackloop_insert.html`:

```html
{% extends 'generic/object.html' %}
{% load helpers %}
{% load form_helpers %}
{% load i18n %}

{% block title %}{% trans "Insert into Splice Closure" %}: {{ object }}{% endblock %}

{% block content %}
<div class="row mb-3">
    <div class="col col-md-8">
        <div class="card">
            <h5 class="card-header">{% trans "Insert into Splice Closure" %}</h5>
            <div class="card-body">
                <p>
                    {% blocktrans with cable=object.fiber_cable %}
                    This will split cable <strong>{{ cable }}</strong> at the slack loop location
                    and connect both halves through the selected closure device.
                    The original cable will be deleted and replaced with two new cables.
                    {% endblocktrans %}
                </p>
                <form method="post">
                    {% csrf_token %}
                    {% render_form form %}
                    <div class="text-end">
                        <a href="{{ object.get_absolute_url }}" class="btn btn-outline-secondary">{% trans "Cancel" %}</a>
                        <button type="submit" class="btn btn-primary">{% trans "Insert" %}</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
    <div class="col col-md-4">
        <div class="card">
            <h5 class="card-header">{% trans "Slack Loop Details" %}</h5>
            <table class="table table-hover attr-table">
                <tr>
                    <th>{% trans "Fiber Cable" %}</th>
                    <td>{{ object.fiber_cable|linkify }}</td>
                </tr>
                <tr>
                    <th>{% trans "Site" %}</th>
                    <td>{{ object.site|linkify }}</td>
                </tr>
                <tr>
                    <th>{% trans "Start Mark" %}</th>
                    <td>{{ object.start_mark }} {{ object.get_length_unit_display }}</td>
                </tr>
                <tr>
                    <th>{% trans "End Mark" %}</th>
                    <td>{{ object.end_mark }} {{ object.get_length_unit_display }}</td>
                </tr>
                <tr>
                    <th>{% trans "Loop Length" %}</th>
                    <td>{{ object.loop_length }} {{ object.get_length_unit_display }}</td>
                </tr>
            </table>
        </div>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 9: Add "Insert into Splice Closure" button to detail template**

In `netbox_fms/templates/netbox_fms/slackloop.html`, add after the `<h5 class="card-header">{% trans "Slack Loop" %}</h5>` in the first card, before the closing `</div>` of the first column:

After the first card's closing `</div>`, add:

```html
        <div class="card mt-3">
            <div class="card-body text-end">
                <a href="{% url 'plugins:netbox_fms:slackloop_insert' object.pk %}" class="btn btn-warning">
                    <i class="mdi mdi-content-cut"></i> {% trans "Insert into Splice Closure" %}
                </a>
            </div>
        </div>
```

- [ ] **Step 10: Run all tests**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v
```

Expected: All PASS.

- [ ] **Step 11: Commit**

```bash
git add netbox_fms/forms.py netbox_fms/views.py netbox_fms/urls.py netbox_fms/templates/netbox_fms/ tests/test_slack_loop_insert.py
git commit -m "feat: add Insert into Splice Closure workflow for slack loops"
```

---

## Task 6: Final verification and lint

- [ ] **Step 1: Lint and format**

```bash
ruff check --fix netbox_fms/
ruff format netbox_fms/
```

- [ ] **Step 2: Verify all modules import cleanly**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.models import *; from netbox_fms.forms import *; from netbox_fms.filters import *; from netbox_fms.tables import *; from netbox_fms.api.serializers import *; from netbox_fms.api.views import *; from netbox_fms.graphql.types import *; from netbox_fms.graphql.filters import *"
```

- [ ] **Step 3: Run full test suite**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v
```

Expected: All PASS.

- [ ] **Step 4: Commit any lint fixes**

```bash
git add -A && git diff --cached --stat
# Only commit if there are changes
git commit -m "chore: lint and format slack loop code"
```
