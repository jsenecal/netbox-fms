# Splice Plan Redesign Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign splice planning to use desired-state model with live diff, signal-based cache invalidation, import/apply workflow, cross-closure project grouping, and draw.io export.

**Architecture:** SplicePlan (one per closure Device) stores desired FrontPort↔FrontPort state as SplicePlanEntry rows. "Current" is always read live from NetBox. Diff = desired − live, cached on the plan and invalidated via Django signals on Cable. SpliceProject groups plans across a route. ClosureCableEntry tracks cable entrances. Apply writes the diff to NetBox atomically.

**Tech Stack:** Django 4.2+, NetBox 4.5+ plugin API, Django signals, JSON caching, mxGraph XML generation for draw.io export.

**Spec:** `docs/superpowers/specs/2026-03-12-splice-plan-redesign-design.md`

**Test command:** `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v`

**Lint command:** `ruff check --fix netbox_fms/ && ruff format netbox_fms/`

**Migration command:** `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py makemigrations netbox_fms`

---

## Implementation Notes (MUST READ)

These corrections apply across multiple tasks. The implementer MUST apply them:

### 1. FrontPort creation in tests requires RearPort + valid port type

NetBox `FrontPort` requires a `rear_port` FK, `rear_port_position`, and a valid `PortTypeChoices` value (e.g., `"lc"`, `"sc"` — NOT `"splice"`). Similarly for `RearPort`. **The conftest.py in Task 1 provides a `make_front_port()` helper — ALL test code that creates FrontPorts MUST use this helper instead of direct `FrontPort.objects.create()` calls.** The helper auto-creates the backing RearPort.

Every occurrence of `FrontPort.objects.create(device=X, module=Y, name=Z, type="splice")` in the plan has been replaced with:
```python
fp = make_front_port(device=X, module=Y, name=Z)
```

**CRITICAL:** Every test file that uses `make_front_port` must add this import at the top:
```python
from tests.conftest import make_front_port
```
This applies to: `test_models.py`, `test_services.py`, `test_signals.py`, `test_export.py`. The code blocks in the plan omit this import for brevity — **the implementer must add it.**

Every occurrence of `RearPort.objects.create(device=X, name=Y, type="splice", positions=N)` must be replaced with:
```python
rp = RearPort.objects.create(device=X, name=Y, type="lc", positions=N)
```

This affects Tasks 3, 4, 5, 6, 7, 13, 21 — all test fixtures.

### 2. FrontPort may not have a `color` field

NetBox's `FrontPort` model does not have a `color` field. The draw.io export (Task 21) should look up fiber color via `FiberStrand.objects.filter(front_port=port).values_list("color", flat=True).first()`, falling back to `"#CCCCCC"`. Do NOT pass `color=` when creating FrontPorts in tests.

### 3. Diff key types — int internally, string for JSON

`compute_diff()` and all callers use **integer** tray_id keys. `get_or_recompute_diff()` converts to string keys for JSON storage and back to int when reading from cache. This is already handled in the code blocks.

### 4. Inter-platter deduplication in apply_diff

Inter-platter pairs appear on both trays' diffs. `apply_diff` must deduplicate before executing. **Fix:** Before the per-tray loop in `apply_diff`, collect all unique add/remove pairs across trays into two flat sets, then iterate those sets instead of per-tray:

```python
all_adds = set()
all_removes = set()
for tray_id, tray_diff in diff.items():
    for pair in tray_diff["add"]:
        all_adds.add(tuple(pair))
    for pair in tray_diff["remove"]:
        all_removes.add(tuple(pair))
# Then process all_adds and all_removes (not per-tray)
```

### 5. import_live_state tray assignment

`import_live_state` normalizes pairs as `(min_id, max_id)`. The port with `min_id` may not be on the "correct" tray for the `tray` FK. **Fix:** Look up the actual module_id for the `min_id` port and use that as the tray. This will satisfy the `clean()` constraint.

### 6. bulk_create skips clean()

`import_live_state` uses `bulk_create` which skips `clean()`. This is acceptable for the import path (we control the data), but document this in the code with a comment.

### 7. pre_delete vs post_delete for Cable signals

The plan uses `pre_delete` (so terminations still exist for lookup). This is correct behavior but deviates from the spec's `post_delete`. Add a code comment explaining why `pre_delete` is used.

### 8. related_name change: splice_plans → splice_plan

`SplicePlan.closure` changes from FK (`related_name="splice_plans"`) to OneToOneField (`related_name="splice_plan"`). Grep for `splice_plans` across all templates, views, and API code and update to `splice_plan`.

### 9. Duplicate URL patterns

The existing codebase registers both `include(get_model_urls(...))` and a manual detail view on the same `<int:pk>/` path. This is intentional — `get_model_urls` handles changelog/journal tabs while the manual path handles the primary detail page. Django matches the first pattern, so the manual detail path must come AFTER the `get_model_urls` include (which is already the case in existing patterns). Follow this same convention for new models.

### 10. Project-level export deferred

The spec describes project-level draw.io export. This is deferred to a follow-up — implement per-closure export only in this plan.

---

## File Structure

### Files to Create
- `netbox_fms/services.py` — Diff computation engine (live state reader, desired state reader, diff calculator, cache management)
- `netbox_fms/signals.py` — Cable post_save/post_delete handlers for diff cache invalidation
- `netbox_fms/export.py` — Draw.io XML generator
- `netbox_fms/templates/netbox_fms/spliceproject.html` — SpliceProject detail template
- `netbox_fms/templates/netbox_fms/closurecableentry.html` — ClosureCableEntry detail template
- `netbox_fms/templates/netbox_fms/spliceplan_apply_confirm.html` — Apply confirmation page (replaces implement confirm)
- `tests/test_models.py` — Model tests (SpliceProject, SplicePlan, SplicePlanEntry, ClosureCableEntry)
- `tests/test_services.py` — Diff engine tests
- `tests/test_signals.py` — Signal invalidation tests
- `tests/test_export.py` — Draw.io export tests
- `tests/test_views.py` — View tests (import, apply, export endpoints)
- `tests/conftest.py` — Shared fixtures (closure device, trays, FrontPorts, cables)

### Files to Modify
- `netbox_fms/models.py` — Rework SplicePlan/SplicePlanEntry, add SpliceProject + ClosureCableEntry
- `netbox_fms/choices.py` — Remove SplicePlanModeChoices, update SplicePlanStatusChoices
- `netbox_fms/forms.py` — New forms for SpliceProject, ClosureCableEntry; rework SplicePlan/Entry forms
- `netbox_fms/filters.py` — New filtersets for SpliceProject, ClosureCableEntry; rework existing
- `netbox_fms/tables.py` — New tables for SpliceProject, ClosureCableEntry; rework existing
- `netbox_fms/views.py` — Replace implement/rollback with import/apply/export; add SpliceProject + ClosureCableEntry views
- `netbox_fms/urls.py` — New URL patterns for SpliceProject, ClosureCableEntry, import/apply/export
- `netbox_fms/navigation.py` — Add SpliceProject and ClosureCableEntry menu items
- `netbox_fms/search.py` — Add SpliceProject search index
- `netbox_fms/api/serializers.py` — New serializers; rework existing
- `netbox_fms/api/views.py` — Replace implement/rollback actions with import/apply/diff; add new ViewSets
- `netbox_fms/api/urls.py` — Register new ViewSets
- `netbox_fms/graphql/types.py` — Add SpliceProject, ClosureCableEntry types; update existing
- `netbox_fms/graphql/schema.py` — Add new query fields
- `netbox_fms/graphql/filters.py` — Add new filters
- `netbox_fms/__init__.py` — Register signals in ready()
- `netbox_fms/templates/netbox_fms/spliceplan.html` — Rework for diff view, import/apply buttons

### Files to Delete
- `netbox_fms/templates/netbox_fms/spliceplan_implement_confirm.html` — Replaced by apply confirm

---

## Chunk 1: Models + Choices + Migration

### Task 1: Update choices.py

**Files:**
- Modify: `netbox_fms/choices.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write failing test for new status choices**

Create `tests/__init__.py` and `tests/conftest.py`:

```python
# tests/__init__.py
# (empty)
```

```python
# tests/conftest.py
from dcim.models import FrontPort, RearPort

# Counter to ensure unique RearPort names across tests
_rp_counter = 0


def make_front_port(device, name, module=None, port_type="lc"):
    """
    Create a FrontPort with its required backing RearPort.
    NetBox FrontPort requires rear_port + rear_port_position.
    """
    global _rp_counter
    _rp_counter += 1
    rp = RearPort.objects.create(
        device=device, name=f"_RP-{_rp_counter}", type=port_type, positions=1,
    )
    kwargs = dict(
        device=device, name=name, type=port_type,
        rear_port=rp, rear_port_position=1,
    )
    if module is not None:
        kwargs["module"] = module
    return FrontPort.objects.create(**kwargs)
```

Create `tests/test_models.py`:

```python
# tests/test_models.py
from django.test import TestCase

from netbox_fms.choices import SplicePlanStatusChoices


class TestSplicePlanStatusChoices(TestCase):
    def test_has_draft(self):
        assert SplicePlanStatusChoices.DRAFT == "draft"

    def test_has_pending_review(self):
        assert SplicePlanStatusChoices.PENDING_REVIEW == "pending_review"

    def test_has_ready_to_apply(self):
        assert SplicePlanStatusChoices.READY_TO_APPLY == "ready_to_apply"

    def test_has_applied(self):
        assert SplicePlanStatusChoices.APPLIED == "applied"

    def test_mode_choices_removed(self):
        """SplicePlanModeChoices should no longer exist."""
        import netbox_fms.choices as ch
        assert not hasattr(ch, "SplicePlanModeChoices")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_models.py::TestSplicePlanStatusChoices -v`
Expected: FAIL — `PENDING_REVIEW`, `READY_TO_APPLY`, `APPLIED` don't exist; `SplicePlanModeChoices` still exists.

- [ ] **Step 3: Update choices.py**

Remove `SplicePlanModeChoices` class entirely. Replace `SplicePlanStatusChoices`:

```python
class SplicePlanStatusChoices(ChoiceSet):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    READY_TO_APPLY = "ready_to_apply"
    APPLIED = "applied"

    CHOICES = (
        (DRAFT, "Draft"),
        (PENDING_REVIEW, "Pending Review"),
        (READY_TO_APPLY, "Ready to Apply"),
        (APPLIED, "Applied"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_models.py::TestSplicePlanStatusChoices -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/choices.py tests/
git commit -m "refactor: update splice plan status choices, remove mode choices"
```

---

### Task 2: Add SpliceProject model

**Files:**
- Modify: `netbox_fms/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_models.py`:

```python
from netbox_fms.models import SpliceProject


class TestSpliceProject(TestCase):
    def test_create_project(self):
        project = SpliceProject.objects.create(
            name="Main St CO → Elm St Drop",
            description="Route fiber project",
        )
        assert project.pk is not None
        assert str(project) == "Main St CO → Elm St Drop"

    def test_get_absolute_url(self):
        project = SpliceProject.objects.create(name="Test Project")
        assert "/splice-projects/" in project.get_absolute_url()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_models.py::TestSpliceProject -v`
Expected: FAIL — `SpliceProject` does not exist.

- [ ] **Step 3: Add SpliceProject model to models.py**

Add to `models.py` before the existing SplicePlan class, and add to `__all__`:

```python
class SpliceProject(NetBoxModel):
    """Groups multiple closure-level splice plans into a route/job scope."""

    name = models.CharField(
        verbose_name=_("name"),
        max_length=100,
    )
    description = models.TextField(
        verbose_name=_("description"),
        blank=True,
    )

    class Meta:
        ordering = ("name",)
        verbose_name = _("splice project")
        verbose_name_plural = _("splice projects")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_fms:spliceproject", args=[self.pk])
```

- [ ] **Step 4: Run test to verify it passes (after migration)**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py makemigrations netbox_fms
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py migrate
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_models.py::TestSpliceProject -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/models.py netbox_fms/migrations/
git commit -m "feat: add SpliceProject model"
```

---

### Task 3: Rework SplicePlan model

**Files:**
- Modify: `netbox_fms/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write failing test**

```python
from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site


class TestSplicePlanRework(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Test Site", slug="test-site")
        manufacturer = Manufacturer.objects.create(name="Test Mfr", slug="test-mfr")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="Closure", slug="closure")
        role = DeviceRole.objects.create(name="Splice Closure", slug="splice-closure")
        cls.closure = Device.objects.create(
            name="Closure-1", site=site, device_type=device_type, role=role
        )
        cls.project = SpliceProject.objects.create(name="Test Project")

    def test_create_plan_with_new_fields(self):
        from netbox_fms.choices import SplicePlanStatusChoices
        plan = SplicePlan.objects.create(
            closure=self.closure,
            name="Plan 1",
            status=SplicePlanStatusChoices.DRAFT,
        )
        assert plan.pk is not None
        assert plan.cached_diff is None
        assert plan.diff_stale is True
        assert plan.project is None

    def test_plan_with_project(self):
        plan = SplicePlan.objects.create(
            closure=self.closure,
            name="Plan 1",
            project=self.project,
        )
        assert plan.project == self.project
        assert self.project.plans.count() == 1

    def test_unique_closure_constraint(self):
        SplicePlan.objects.create(closure=self.closure, name="Plan 1")
        with self.assertRaises(Exception):
            SplicePlan.objects.create(closure=self.closure, name="Plan 2")

    def test_no_mode_field(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Plan 1")
        assert not hasattr(plan, "mode")

    def test_no_tray_field(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Plan 1")
        # tray is no longer a direct FK on SplicePlan (moved to entry level)
        assert not hasattr(SplicePlan, "tray")

    def test_no_implement_method(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Plan 1")
        assert not hasattr(plan, "implement")

    def test_no_rollback_method(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Plan 1")
        assert not hasattr(plan, "rollback")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_models.py::TestSplicePlanRework -v`
Expected: FAIL — `cached_diff`, `diff_stale`, `project` don't exist; `mode`, `tray`, `implement`, `rollback` still exist.

- [ ] **Step 3: Rework SplicePlan model**

Replace the SplicePlan class in `models.py`:

```python
class SplicePlan(NetBoxModel):
    """
    A splice plan represents the desired state of all splice connections
    within a closure (Device). One plan per closure.
    """

    closure = models.OneToOneField(
        to="dcim.Device",
        on_delete=models.CASCADE,
        related_name="splice_plan",
        verbose_name=_("closure"),
    )
    project = models.ForeignKey(
        to="netbox_fms.SpliceProject",
        on_delete=models.SET_NULL,
        related_name="plans",
        verbose_name=_("project"),
        blank=True,
        null=True,
    )
    name = models.CharField(
        verbose_name=_("name"),
        max_length=100,
    )
    description = models.TextField(
        verbose_name=_("description"),
        blank=True,
    )
    status = models.CharField(
        verbose_name=_("status"),
        max_length=50,
        choices=SplicePlanStatusChoices,
        default=SplicePlanStatusChoices.DRAFT,
    )
    cached_diff = models.JSONField(
        verbose_name=_("cached diff"),
        blank=True,
        null=True,
    )
    diff_stale = models.BooleanField(
        verbose_name=_("diff stale"),
        default=True,
    )

    class Meta:
        ordering = ("closure", "name")
        verbose_name = _("splice plan")
        verbose_name_plural = _("splice plans")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_fms:spliceplan", args=[self.pk])
```

Remove the old `import` of `SplicePlanModeChoices` from the top of models.py.
Remove the `validate_for_implement`, `implement`, and `rollback` methods.

- [ ] **Step 4: Generate migration and run tests**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py makemigrations netbox_fms
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py migrate
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_models.py::TestSplicePlanRework -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/models.py netbox_fms/migrations/
git commit -m "refactor: rework SplicePlan — add project FK, cached_diff, diff_stale; remove mode/tray/implement/rollback"
```

---

### Task 4: Rework SplicePlanEntry model

**Files:**
- Modify: `netbox_fms/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write failing test**

```python
from dcim.models import FrontPort, Module, ModuleBay, ModuleType, RearPort


class TestSplicePlanEntryRework(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Test Site 2", slug="test-site-2")
        manufacturer = Manufacturer.objects.create(name="Test Mfr 2", slug="test-mfr-2")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="Closure 2", slug="closure-2")
        role = DeviceRole.objects.create(name="Splice Closure 2", slug="splice-closure-2")
        cls.closure = Device.objects.create(
            name="Closure-2", site=site, device_type=device_type, role=role
        )
        cls.plan = SplicePlan.objects.create(closure=cls.closure, name="Plan")

        # Create a tray (Module) on the closure
        module_type = ModuleType.objects.create(manufacturer=manufacturer, model="Tray-12")
        bay = ModuleBay.objects.create(device=cls.closure, name="Tray Slot 1")
        cls.tray = Module.objects.create(device=cls.closure, module_bay=bay, module_type=module_type)

        # Create FrontPorts on the tray module
        cls.fp_a = make_front_port(device=cls.closure, module=cls.tray, name="F1")
        cls.fp_b = make_front_port(device=cls.closure, module=cls.tray, name="F2")

    def test_create_entry_with_frontports(self):
        entry = SplicePlanEntry.objects.create(
            plan=self.plan,
            tray=self.tray,
            fiber_a=self.fp_a,
            fiber_b=self.fp_b,
        )
        assert entry.pk is not None

    def test_entry_notes_field(self):
        entry = SplicePlanEntry.objects.create(
            plan=self.plan,
            tray=self.tray,
            fiber_a=self.fp_a,
            fiber_b=self.fp_b,
            notes="Splice with blue heat-shrink",
        )
        assert entry.notes == "Splice with blue heat-shrink"

    def test_no_cable_field(self):
        assert not hasattr(SplicePlanEntry, "cable")

    def test_no_mode_override_field(self):
        entry = SplicePlanEntry.objects.create(
            plan=self.plan, tray=self.tray, fiber_a=self.fp_a, fiber_b=self.fp_b
        )
        assert not hasattr(entry, "mode_override")

    def test_unique_fiber_a_per_plan(self):
        """Each FrontPort can appear as fiber_a at most once per plan."""
        fp_c = make_front_port(device=self.closure, module=self.tray, name="F3")
        SplicePlanEntry.objects.create(plan=self.plan, tray=self.tray, fiber_a=self.fp_a, fiber_b=fp_c)
        with self.assertRaises(Exception):
            SplicePlanEntry.objects.create(plan=self.plan, tray=self.tray, fiber_a=self.fp_a, fiber_b=self.fp_b)

    def test_unique_fiber_b_per_plan(self):
        """Each FrontPort can appear as fiber_b at most once per plan."""
        fp_c = make_front_port(device=self.closure, module=self.tray, name="F4")
        SplicePlanEntry.objects.create(plan=self.plan, tray=self.tray, fiber_a=self.fp_a, fiber_b=self.fp_b)
        with self.assertRaises(Exception):
            SplicePlanEntry.objects.create(plan=self.plan, tray=self.tray, fiber_a=fp_c, fiber_b=self.fp_b)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_models.py::TestSplicePlanEntryRework -v`
Expected: FAIL — SplicePlanEntry still has FiberStrand FKs, cable field, mode_override.

- [ ] **Step 3: Rework SplicePlanEntry model**

Replace in `models.py`:

```python
class SplicePlanEntry(NetBoxModel):
    """
    A single desired FrontPort↔FrontPort connection within a splice plan.
    Each entry represents one splice or inter-platter route.
    """

    plan = models.ForeignKey(
        to="netbox_fms.SplicePlan",
        on_delete=models.CASCADE,
        related_name="entries",
    )
    tray = models.ForeignKey(
        to="dcim.Module",
        on_delete=models.CASCADE,
        related_name="splice_plan_entries",
        verbose_name=_("tray"),
        help_text=_("Tray owning fiber_a (canonical tray for this entry)."),
    )
    fiber_a = models.ForeignKey(
        to="dcim.FrontPort",
        on_delete=models.CASCADE,
        related_name="splice_entries_a",
        verbose_name=_("fiber A"),
    )
    fiber_b = models.ForeignKey(
        to="dcim.FrontPort",
        on_delete=models.CASCADE,
        related_name="splice_entries_b",
        verbose_name=_("fiber B"),
    )
    notes = models.TextField(
        verbose_name=_("notes"),
        blank=True,
    )

    class Meta:
        ordering = ("plan", "pk")
        unique_together = (
            ("plan", "fiber_a"),
            ("plan", "fiber_b"),
        )
        verbose_name = _("splice plan entry")
        verbose_name_plural = _("splice plan entries")

    def __str__(self):
        return f"{self.fiber_a} → {self.fiber_b}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_fms:spliceplanentry", args=[self.pk])

    @property
    def is_inter_platter(self):
        """True if fiber_a and fiber_b are on different tray modules."""
        return self.fiber_a.module_id != self.fiber_b.module_id

    def clean(self):
        super().clean()
        # Validate both FrontPorts belong to the plan's closure Device
        if self.fiber_a.device_id != self.plan.closure_id:
            raise ValidationError(
                {"fiber_a": _("FrontPort must belong to the plan's closure device.")}
            )
        if self.fiber_b.device_id != self.plan.closure_id:
            raise ValidationError(
                {"fiber_b": _("FrontPort must belong to the plan's closure device.")}
            )
        # Validate tray matches fiber_a's module
        if self.fiber_a.module_id != self.tray_id:
            raise ValidationError(
                {"tray": _("Tray must match fiber_a's parent module.")}
            )
```

- [ ] **Step 4: Generate migration and run tests**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py makemigrations netbox_fms
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py migrate
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_models.py::TestSplicePlanEntryRework -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/models.py netbox_fms/migrations/
git commit -m "refactor: rework SplicePlanEntry — FrontPort FKs, tray, notes, uniqueness constraints, validation"
```

---

### Task 5: Add ClosureCableEntry model

**Files:**
- Modify: `netbox_fms/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write failing test**

```python
from netbox_fms.models import ClosureCableEntry, FiberCable, FiberCableType


class TestClosureCableEntry(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Test Site 3", slug="test-site-3")
        manufacturer = Manufacturer.objects.create(name="Test Mfr 3", slug="test-mfr-3")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="Closure 3", slug="closure-3")
        role = DeviceRole.objects.create(name="Splice Closure 3", slug="splice-closure-3")
        cls.closure = Device.objects.create(
            name="Closure-3", site=site, device_type=device_type, role=role
        )
        fct = FiberCableType.objects.create(
            manufacturer=manufacturer,
            model="Test Cable Type",
            construction="loose_tube",
            fiber_type="smf_os2",
            strand_count=12,
        )
        from dcim.models import Cable
        cable = Cable.objects.create()
        cls.fiber_cable = FiberCable.objects.create(cable=cable, fiber_cable_type=fct)
        cls.rear_port = RearPort.objects.create(
            device=cls.closure, name="Port 1", type="lc", positions=12
        )

    def test_create_entry(self):
        entry = ClosureCableEntry.objects.create(
            closure=self.closure,
            fiber_cable=self.fiber_cable,
            entrance_port=self.rear_port,
        )
        assert entry.pk is not None

    def test_unique_entrance_port(self):
        ClosureCableEntry.objects.create(
            closure=self.closure,
            fiber_cable=self.fiber_cable,
            entrance_port=self.rear_port,
        )
        from dcim.models import Cable
        cable2 = Cable.objects.create()
        fct = self.fiber_cable.fiber_cable_type
        fc2 = FiberCable.objects.create(cable=cable2, fiber_cable_type=fct)
        with self.assertRaises(Exception):
            ClosureCableEntry.objects.create(
                closure=self.closure, fiber_cable=fc2, entrance_port=self.rear_port
            )

    def test_get_absolute_url(self):
        entry = ClosureCableEntry.objects.create(
            closure=self.closure,
            fiber_cable=self.fiber_cable,
            entrance_port=self.rear_port,
        )
        assert "/closure-cable-entries/" in entry.get_absolute_url()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_models.py::TestClosureCableEntry -v`
Expected: FAIL — `ClosureCableEntry` does not exist.

- [ ] **Step 3: Add ClosureCableEntry model**

Add to `models.py` and `__all__`:

```python
class ClosureCableEntry(NetBoxModel):
    """Tracks which port/gland on a closure each cable enters through."""

    closure = models.ForeignKey(
        to="dcim.Device",
        on_delete=models.CASCADE,
        related_name="cable_entries",
        verbose_name=_("closure"),
    )
    fiber_cable = models.ForeignKey(
        to="netbox_fms.FiberCable",
        on_delete=models.CASCADE,
        related_name="closure_entries",
        verbose_name=_("fiber cable"),
    )
    entrance_port = models.ForeignKey(
        to="dcim.RearPort",
        on_delete=models.CASCADE,
        related_name="closure_cable_entries",
        verbose_name=_("entrance port"),
    )
    notes = models.TextField(
        verbose_name=_("notes"),
        blank=True,
    )

    class Meta:
        ordering = ("closure", "entrance_port")
        unique_together = (("closure", "entrance_port"),)
        verbose_name = _("closure cable entry")
        verbose_name_plural = _("closure cable entries")

    def __str__(self):
        return f"{self.closure} → {self.entrance_port.name} ({self.fiber_cable})"

    def get_absolute_url(self):
        return reverse("plugins:netbox_fms:closurecableentry", args=[self.pk])
```

- [ ] **Step 4: Generate migration and run tests**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py makemigrations netbox_fms
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py migrate
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_models.py::TestClosureCableEntry -v
```
Expected: PASS

- [ ] **Step 5: Run all model tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_models.py -v`
Expected: ALL PASS

- [ ] **Step 6: Lint**

Run: `cd /opt/netbox-fms && ruff check --fix netbox_fms/ && ruff format netbox_fms/`

- [ ] **Step 7: Commit**

```bash
git add netbox_fms/models.py netbox_fms/migrations/ tests/
git commit -m "feat: add ClosureCableEntry model for tracking cable entrances on closures"
```

---

## Chunk 2: Diff Engine + Signals

### Task 6: Implement diff computation service

**Files:**
- Create: `netbox_fms/services.py`
- Test: `tests/test_services.py`

- [ ] **Step 1: Write failing tests for live state reader**

Create `tests/test_services.py`:

```python
from django.test import TestCase
from dcim.models import (
    Cable, CableTermination, Device, DeviceRole, DeviceType,
    FrontPort, Manufacturer, Module, ModuleBay, ModuleType, RearPort, Site,
)

from netbox_fms.services import get_live_state, get_desired_state, compute_diff


class TestLiveStateReader(TestCase):
    """Test reading current FrontPort↔FrontPort connections from NetBox."""

    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Svc Site", slug="svc-site")
        mfr = Manufacturer.objects.create(name="Svc Mfr", slug="svc-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Closure", slug="svc-closure")
        role = DeviceRole.objects.create(name="Svc Role", slug="svc-role")
        cls.closure = Device.objects.create(name="C1", site=site, device_type=dt, role=role)

        mt = ModuleType.objects.create(manufacturer=mfr, model="Tray-12")
        bay1 = ModuleBay.objects.create(device=cls.closure, name="Bay 1")
        cls.tray1 = Module.objects.create(device=cls.closure, module_bay=bay1, module_type=mt)
        bay2 = ModuleBay.objects.create(device=cls.closure, name="Bay 2")
        cls.tray2 = Module.objects.create(device=cls.closure, module_bay=bay2, module_type=mt)

        # FrontPorts on tray1
        cls.fp1 = make_front_port(device=cls.closure, module=cls.tray1, name="T1-F1")
        cls.fp2 = make_front_port(device=cls.closure, module=cls.tray1, name="T1-F2")
        # FrontPorts on tray2
        cls.fp3 = make_front_port(device=cls.closure, module=cls.tray2, name="T2-F1")
        cls.fp4 = make_front_port(device=cls.closure, module=cls.tray2, name="T2-F2")

    def _connect(self, port_a, port_b):
        """Create a 0-length cable between two FrontPorts."""
        cable = Cable.objects.create(length=0, length_unit="m")
        CableTermination.objects.create(cable=cable, cable_end="A", termination=port_a)
        CableTermination.objects.create(cable=cable, cable_end="B", termination=port_b)
        return cable

    def test_empty_closure(self):
        state = get_live_state(self.closure)
        assert state == {}

    def test_single_splice_on_tray(self):
        self._connect(self.fp1, self.fp2)
        state = get_live_state(self.closure)
        assert self.tray1.pk in state
        assert (self.fp1.pk, self.fp2.pk) in state[self.tray1.pk] or \
               (self.fp2.pk, self.fp1.pk) in state[self.tray1.pk]

    def test_inter_platter_connection(self):
        self._connect(self.fp1, self.fp3)
        state = get_live_state(self.closure)
        # Should appear on both trays
        assert self.tray1.pk in state
        assert self.tray2.pk in state
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_services.py::TestLiveStateReader -v`
Expected: FAIL — `netbox_fms.services` does not exist.

- [ ] **Step 3: Implement services.py — live state reader**

Create `netbox_fms/services.py`:

```python
"""Diff computation engine for splice plans."""

from dcim.models import Cable, CableTermination, FrontPort


def get_live_state(closure):
    """
    Read current FrontPort↔FrontPort connections on a closure's tray modules.

    Returns: {tray_module_id: set((port_a_id, port_b_id), ...)}

    A "splice cable" is identified by: both terminations are FrontPorts on
    modules of the same closure Device.
    """
    # Find all FrontPorts on tray modules of this closure
    tray_frontport_ids = set(
        FrontPort.objects.filter(
            device=closure,
            module__isnull=False,
        ).values_list("pk", flat=True)
    )

    if not tray_frontport_ids:
        return {}

    # Build a map of FrontPort ID → module ID
    port_to_module = dict(
        FrontPort.objects.filter(pk__in=tray_frontport_ids).values_list("pk", "module_id")
    )

    # Find cables where both ends terminate on our closure's tray FrontPorts
    # Get all CableTerminations for our FrontPorts
    from django.contrib.contenttypes.models import ContentType

    fp_ct = ContentType.objects.get_for_model(FrontPort)
    terminations = CableTermination.objects.filter(
        termination_type=fp_ct,
        termination_id__in=tray_frontport_ids,
    ).values_list("cable_id", "termination_id", "cable_end")

    # Group by cable
    cable_terms = {}
    for cable_id, term_id, cable_end in terminations:
        cable_terms.setdefault(cable_id, {})[cable_end] = term_id

    # Build state dict
    state = {}
    for cable_id, ends in cable_terms.items():
        if "A" not in ends or "B" not in ends:
            continue
        port_a_id, port_b_id = ends["A"], ends["B"]
        # Both must be in our tray FrontPorts
        if port_a_id not in tray_frontport_ids or port_b_id not in tray_frontport_ids:
            continue

        # Normalize pair ordering (smaller ID first)
        pair = (min(port_a_id, port_b_id), max(port_a_id, port_b_id))

        # Add to each tray the pair appears on
        mod_a = port_to_module[port_a_id]
        mod_b = port_to_module[port_b_id]
        state.setdefault(mod_a, set()).add(pair)
        if mod_a != mod_b:
            state.setdefault(mod_b, set()).add(pair)

    return state
```

- [ ] **Step 4: Run live state tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_services.py::TestLiveStateReader -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/services.py tests/test_services.py
git commit -m "feat: add live state reader for splice diff engine"
```

- [ ] **Step 6: Write failing tests for desired state + diff**

Append to `tests/test_services.py`:

```python
from netbox_fms.models import SplicePlan, SplicePlanEntry


class TestDesiredStateAndDiff(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Diff Site", slug="diff-site")
        mfr = Manufacturer.objects.create(name="Diff Mfr", slug="diff-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Closure", slug="diff-closure")
        role = DeviceRole.objects.create(name="Diff Role", slug="diff-role")
        cls.closure = Device.objects.create(name="C-Diff", site=site, device_type=dt, role=role)

        mt = ModuleType.objects.create(manufacturer=mfr, model="Tray")
        bay = ModuleBay.objects.create(device=cls.closure, name="Bay 1")
        cls.tray = Module.objects.create(device=cls.closure, module_bay=bay, module_type=mt)

        cls.fp1 = make_front_port(device=cls.closure, module=cls.tray, name="F1")
        cls.fp2 = make_front_port(device=cls.closure, module=cls.tray, name="F2")
        cls.fp3 = make_front_port(device=cls.closure, module=cls.tray, name="F3")
        cls.fp4 = make_front_port(device=cls.closure, module=cls.tray, name="F4")

        cls.plan = SplicePlan.objects.create(closure=cls.closure, name="Test Plan")

    def test_desired_state_empty_plan(self):
        state = get_desired_state(self.plan)
        assert state == {}

    def test_desired_state_with_entries(self):
        SplicePlanEntry.objects.create(
            plan=self.plan, tray=self.tray, fiber_a=self.fp1, fiber_b=self.fp2
        )
        state = get_desired_state(self.plan)
        pair = (min(self.fp1.pk, self.fp2.pk), max(self.fp1.pk, self.fp2.pk))
        assert self.tray.pk in state
        assert pair in state[self.tray.pk]

    def test_diff_add_only(self):
        """Plan has entries, live has nothing → all adds."""
        SplicePlanEntry.objects.create(
            plan=self.plan, tray=self.tray, fiber_a=self.fp1, fiber_b=self.fp2
        )
        diff = compute_diff(self.plan)
        tray_diff = diff[self.tray.pk]
        assert len(tray_diff["add"]) == 1
        assert len(tray_diff["remove"]) == 0

    def test_diff_remove_only(self):
        """Live has connections, plan is empty → all removes."""
        cable = Cable.objects.create(length=0, length_unit="m")
        CableTermination.objects.create(cable=cable, cable_end="A", termination=self.fp1)
        CableTermination.objects.create(cable=cable, cable_end="B", termination=self.fp2)
        diff = compute_diff(self.plan)
        tray_diff = diff[self.tray.pk]
        assert len(tray_diff["add"]) == 0
        assert len(tray_diff["remove"]) == 1

    def test_diff_unchanged(self):
        """Live and plan match → no changes."""
        cable = Cable.objects.create(length=0, length_unit="m")
        CableTermination.objects.create(cable=cable, cable_end="A", termination=self.fp1)
        CableTermination.objects.create(cable=cable, cable_end="B", termination=self.fp2)
        SplicePlanEntry.objects.create(
            plan=self.plan, tray=self.tray, fiber_a=self.fp1, fiber_b=self.fp2
        )
        diff = compute_diff(self.plan)
        tray_diff = diff[self.tray.pk]
        assert len(tray_diff["add"]) == 0
        assert len(tray_diff["remove"]) == 0
        assert len(tray_diff["unchanged"]) == 1
```

- [ ] **Step 7: Run desired state + diff tests to verify they fail**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_services.py::TestDesiredStateAndDiff -v`
Expected: FAIL — `get_desired_state` and `compute_diff` not defined.

- [ ] **Step 8: Implement get_desired_state and compute_diff**

Append to `netbox_fms/services.py`:

```python
def get_desired_state(plan):
    """
    Read desired FrontPort↔FrontPort connections from a SplicePlan's entries.

    Returns: {tray_module_id: set((port_a_id, port_b_id), ...)}
    """
    state = {}
    for entry in plan.entries.values_list("tray_id", "fiber_a_id", "fiber_b_id"):
        tray_id, fa_id, fb_id = entry
        pair = (min(fa_id, fb_id), max(fa_id, fb_id))
        state.setdefault(tray_id, set()).add(pair)

        # For inter-platter: also add to fiber_b's tray
        # (fiber_b may be on a different module)
        from dcim.models import FrontPort

        fb_module_id = FrontPort.objects.filter(pk=fb_id).values_list("module_id", flat=True).first()
        if fb_module_id and fb_module_id != tray_id:
            state.setdefault(fb_module_id, set()).add(pair)

    return state


def compute_diff(plan):
    """
    Compute the diff between desired and live state for a splice plan.

    Returns: {tray_module_id: {"add": set, "remove": set, "unchanged": set}}
    """
    live = get_live_state(plan.closure)
    desired = get_desired_state(plan)

    all_tray_ids = set(live.keys()) | set(desired.keys())

    diff = {}
    for tray_id in all_tray_ids:
        live_pairs = live.get(tray_id, set())
        desired_pairs = desired.get(tray_id, set())
        # Use int keys in compute_diff; get_or_recompute_diff converts to str for JSON
        diff[tray_id] = {
            "add": [list(p) for p in (desired_pairs - live_pairs)],
            "remove": [list(p) for p in (live_pairs - desired_pairs)],
            "unchanged": [list(p) for p in (desired_pairs & live_pairs)],
        }

    return diff


def get_or_recompute_diff(plan):
    """
    Return cached diff if fresh, otherwise recompute and cache.
    Always returns dict with int tray_id keys and list values.
    """
    if not plan.diff_stale and plan.cached_diff is not None:
        # JSON stores keys as strings; convert back to int
        return {int(k): v for k, v in plan.cached_diff.items()}

    diff = compute_diff(plan)

    # JSON requires string keys
    plan.cached_diff = {str(k): v for k, v in diff.items()}
    plan.diff_stale = False
    plan.save(update_fields=["cached_diff", "diff_stale"])

    return diff
```

- [ ] **Step 9: Run all service tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_services.py -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add netbox_fms/services.py tests/test_services.py
git commit -m "feat: add desired state reader and diff computation for splice plans"
```

---

### Task 7: Implement signal-based cache invalidation

**Files:**
- Create: `netbox_fms/signals.py`
- Modify: `netbox_fms/__init__.py`
- Test: `tests/test_signals.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_signals.py`:

```python
from django.test import TestCase
from dcim.models import (
    Cable, CableTermination, Device, DeviceRole, DeviceType,
    FrontPort, Manufacturer, Module, ModuleBay, ModuleType, Site,
)

from netbox_fms.models import SplicePlan


class TestDiffCacheInvalidation(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Sig Site", slug="sig-site")
        mfr = Manufacturer.objects.create(name="Sig Mfr", slug="sig-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Closure", slug="sig-closure")
        role = DeviceRole.objects.create(name="Sig Role", slug="sig-role")
        cls.closure = Device.objects.create(name="C-Sig", site=site, device_type=dt, role=role)

        mt = ModuleType.objects.create(manufacturer=mfr, model="Tray")
        bay = ModuleBay.objects.create(device=cls.closure, name="Bay 1")
        cls.tray = Module.objects.create(device=cls.closure, module_bay=bay, module_type=mt)

        cls.fp1 = make_front_port(device=cls.closure, module=cls.tray, name="F1")
        cls.fp2 = make_front_port(device=cls.closure, module=cls.tray, name="F2")

    def test_cable_create_invalidates_cache(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Plan")
        plan.diff_stale = False
        plan.cached_diff = {"some": "data"}
        plan.save(update_fields=["diff_stale", "cached_diff"])

        # Create a cable on the closure's FrontPorts
        cable = Cable.objects.create(length=0, length_unit="m")
        CableTermination.objects.create(cable=cable, cable_end="A", termination=self.fp1)
        CableTermination.objects.create(cable=cable, cable_end="B", termination=self.fp2)
        cable.save()  # Trigger post_save again after terminations exist

        plan.refresh_from_db()
        assert plan.diff_stale is True

    def test_cable_delete_invalidates_cache(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Plan")
        cable = Cable.objects.create(length=0, length_unit="m")
        CableTermination.objects.create(cable=cable, cable_end="A", termination=self.fp1)
        CableTermination.objects.create(cable=cable, cable_end="B", termination=self.fp2)

        plan.diff_stale = False
        plan.cached_diff = {"some": "data"}
        plan.save(update_fields=["diff_stale", "cached_diff"])

        cable.delete()

        plan.refresh_from_db()
        assert plan.diff_stale is True

    def test_unrelated_cable_does_not_invalidate(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Plan")
        plan.diff_stale = False
        plan.cached_diff = {"some": "data"}
        plan.save(update_fields=["diff_stale", "cached_diff"])

        # Create a cable NOT on this closure
        cable = Cable.objects.create(length=10, length_unit="m")
        # No terminations on our closure — just save
        cable.save()

        plan.refresh_from_db()
        assert plan.diff_stale is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_signals.py -v`
Expected: FAIL — signals not connected, cache not invalidated.

- [ ] **Step 3: Implement signals.py**

Create `netbox_fms/signals.py`:

```python
"""Signal handlers for splice plan diff cache invalidation."""

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver


def _invalidate_plans_for_cable(cable):
    """If this cable terminates on FrontPorts of a closure with a SplicePlan, mark diff stale."""
    from django.contrib.contenttypes.models import ContentType

    from dcim.models import CableTermination, FrontPort

    from .models import SplicePlan

    fp_ct = ContentType.objects.get_for_model(FrontPort)

    # Get FrontPort IDs from this cable's terminations
    fp_ids = list(
        CableTermination.objects.filter(
            cable=cable,
            termination_type=fp_ct,
        ).values_list("termination_id", flat=True)
    )

    if not fp_ids:
        return

    # Find which devices these FrontPorts belong to
    device_ids = set(
        FrontPort.objects.filter(
            pk__in=fp_ids,
            module__isnull=False,
        ).values_list("device_id", flat=True)
    )

    if not device_ids:
        return

    # Mark plans stale
    SplicePlan.objects.filter(
        closure_id__in=device_ids,
        diff_stale=False,
    ).update(diff_stale=True)


def connect_signals():
    """Connect cable signals. Called from AppConfig.ready()."""
    from dcim.models import Cable

    @receiver(post_save, sender=Cable)
    def cable_post_save(sender, instance, **kwargs):
        _invalidate_plans_for_cable(instance)

    # Use pre_delete (not post_delete) so cable terminations still exist
    # for the device lookup. After delete, terminations are cascade-deleted.
    @receiver(pre_delete, sender=Cable)
    def cable_pre_delete(sender, instance, **kwargs):
        _invalidate_plans_for_cable(instance)
```

- [ ] **Step 4: Register signals in __init__.py**

Read the current `__init__.py` first, then modify the `PluginConfig` class to add a `ready()` method. The NetBox plugin `PluginConfig` inherits from Django `AppConfig`, so `ready()` works:

```python
# In the PluginConfig class in __init__.py, add:
def ready(self):
    super().ready()
    from .signals import connect_signals
    connect_signals()
```

- [ ] **Step 5: Run signal tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_signals.py -v`
Expected: PASS

- [ ] **Step 6: Run all tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v`
Expected: ALL PASS

- [ ] **Step 7: Lint**

Run: `cd /opt/netbox-fms && ruff check --fix netbox_fms/ && ruff format netbox_fms/`

- [ ] **Step 8: Commit**

```bash
git add netbox_fms/signals.py netbox_fms/__init__.py tests/test_signals.py
git commit -m "feat: add signal-based diff cache invalidation on Cable save/delete"
```

---

## Chunk 3: Forms, Filters, Tables for New/Reworked Models

### Task 8: Update forms.py

**Files:**
- Modify: `netbox_fms/forms.py`

- [ ] **Step 1: Add SpliceProject forms**

Add to `forms.py`:

```python
from .models import ClosureCableEntry, SpliceProject

# --- SpliceProject ---

class SpliceProjectForm(NetBoxModelForm):
    class Meta:
        model = SpliceProject
        fields = ("name", "description", "tags")

class SpliceProjectImportForm(NetBoxModelImportForm):
    class Meta:
        model = SpliceProject
        fields = ("name", "description")

class SpliceProjectBulkEditForm(NetBoxModelBulkEditForm):
    model = SpliceProject
    nullable_fields = ("description",)

class SpliceProjectFilterForm(NetBoxModelFilterSetForm):
    model = SpliceProject
```

- [ ] **Step 2: Add ClosureCableEntry forms**

```python
# --- ClosureCableEntry ---

class ClosureCableEntryForm(NetBoxModelForm):
    closure = DynamicModelChoiceField(queryset=Device.objects.all())
    fiber_cable = DynamicModelChoiceField(queryset=FiberCable.objects.all())
    entrance_port = DynamicModelChoiceField(queryset=RearPort.objects.all())

    class Meta:
        model = ClosureCableEntry
        fields = ("closure", "fiber_cable", "entrance_port", "notes", "tags")

class ClosureCableEntryFilterForm(NetBoxModelFilterSetForm):
    model = ClosureCableEntry
```

- [ ] **Step 3: Rework SplicePlan forms**

Update `SplicePlanForm` to remove `mode` and `tray` fields, add `project`:

```python
class SplicePlanForm(NetBoxModelForm):
    closure = DynamicModelChoiceField(queryset=Device.objects.all())
    project = DynamicModelChoiceField(queryset=SpliceProject.objects.all(), required=False)

    class Meta:
        model = SplicePlan
        fields = ("closure", "project", "name", "description", "status", "tags")
```

Update `SplicePlanImportForm` similarly. Update `SplicePlanBulkEditForm` to remove `mode`, add `project`, `status`.

- [ ] **Step 4: Rework SplicePlanEntry forms**

Update `SplicePlanEntryForm` to use FrontPort fields instead of FiberStrand:

```python
class SplicePlanEntryForm(NetBoxModelForm):
    fiber_a = DynamicModelChoiceField(queryset=FrontPort.objects.all())
    fiber_b = DynamicModelChoiceField(queryset=FrontPort.objects.all())
    tray = DynamicModelChoiceField(queryset=Module.objects.all())

    class Meta:
        model = SplicePlanEntry
        fields = ("plan", "tray", "fiber_a", "fiber_b", "notes", "tags")
```

- [ ] **Step 5: Verify imports compile**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.forms import *"`
Expected: No errors.

- [ ] **Step 6: Commit**

```bash
git add netbox_fms/forms.py
git commit -m "refactor: update forms for splice plan redesign — add SpliceProject, ClosureCableEntry; rework SplicePlan/Entry"
```

---

### Task 9: Update filters.py

**Files:**
- Modify: `netbox_fms/filters.py`

- [ ] **Step 1: Add SpliceProject and ClosureCableEntry filtersets**

```python
from .models import ClosureCableEntry, SpliceProject

class SpliceProjectFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = SpliceProject
        fields = ("id", "name")

class ClosureCableEntryFilterSet(NetBoxModelFilterSet):
    closure = django_filters.ModelMultipleChoiceFilter(
        queryset=Device.objects.all(),
    )

    class Meta:
        model = ClosureCableEntry
        fields = ("id", "closure", "fiber_cable", "entrance_port")
```

- [ ] **Step 2: Rework SplicePlanFilterSet**

Remove `mode` filter, add `project` and `status`:

```python
class SplicePlanFilterSet(NetBoxModelFilterSet):
    closure = django_filters.ModelMultipleChoiceFilter(queryset=Device.objects.all())
    project = django_filters.ModelMultipleChoiceFilter(queryset=SpliceProject.objects.all())
    status = django_filters.MultipleChoiceFilter(choices=SplicePlanStatusChoices)

    class Meta:
        model = SplicePlan
        fields = ("id", "closure", "project", "status")
```

- [ ] **Step 3: Rework SplicePlanEntryFilterSet**

Update to use FrontPort and Module:

```python
class SplicePlanEntryFilterSet(NetBoxModelFilterSet):
    plan = django_filters.ModelMultipleChoiceFilter(queryset=SplicePlan.objects.all())
    tray = django_filters.ModelMultipleChoiceFilter(queryset=Module.objects.all())

    class Meta:
        model = SplicePlanEntry
        fields = ("id", "plan", "tray")
```

- [ ] **Step 4: Verify imports compile**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.filters import *"`
Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/filters.py
git commit -m "refactor: update filters for splice plan redesign"
```

---

### Task 10: Update tables.py

**Files:**
- Modify: `netbox_fms/tables.py`

- [ ] **Step 1: Add SpliceProject and ClosureCableEntry tables**

```python
from .models import ClosureCableEntry, SpliceProject

class SpliceProjectTable(NetBoxTable):
    name = tables.Column(linkify=True)
    plan_count = LinkedCountColumn(
        viewname="plugins:netbox_fms:spliceplan_list",
        url_params={"project_id": "pk"},
        verbose_name="Plans",
    )

    class Meta(NetBoxTable.Meta):
        model = SpliceProject
        fields = ("pk", "id", "name", "description", "plan_count", "actions")
        default_columns = ("name", "plan_count")

class ClosureCableEntryTable(NetBoxTable):
    closure = tables.Column(linkify=True)
    fiber_cable = tables.Column(linkify=True)
    entrance_port = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = ClosureCableEntry
        fields = ("pk", "id", "closure", "fiber_cable", "entrance_port", "notes", "actions")
        default_columns = ("closure", "fiber_cable", "entrance_port")
```

- [ ] **Step 2: Rework SplicePlanTable**

Remove `mode` column, add `project` and `status`:

```python
class SplicePlanTable(NetBoxTable):
    name = tables.Column(linkify=True)
    closure = tables.Column(linkify=True)
    project = tables.Column(linkify=True)
    status = tables.Column()
    entry_count = LinkedCountColumn(
        viewname="plugins:netbox_fms:spliceplanentry_list",
        url_params={"plan_id": "pk"},
        verbose_name="Entries",
    )

    class Meta(NetBoxTable.Meta):
        model = SplicePlan
        fields = ("pk", "id", "name", "closure", "project", "status", "entry_count", "actions")
        default_columns = ("name", "closure", "project", "status", "entry_count")
```

- [ ] **Step 3: Rework SplicePlanEntryTable**

Update to show FrontPorts instead of FiberStrands:

```python
class SplicePlanEntryTable(NetBoxTable):
    plan = tables.Column(linkify=True)
    tray = tables.Column(linkify=True)
    fiber_a = tables.Column(linkify=True)
    fiber_b = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = SplicePlanEntry
        fields = ("pk", "id", "plan", "tray", "fiber_a", "fiber_b", "notes", "actions")
        default_columns = ("plan", "tray", "fiber_a", "fiber_b")
```

- [ ] **Step 4: Verify imports compile**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.tables import *"`
Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/tables.py
git commit -m "refactor: update tables for splice plan redesign"
```

---

## Chunk 4: Views, URLs, Templates

### Task 11: Add SpliceProject and ClosureCableEntry views

**Files:**
- Modify: `netbox_fms/views.py`

- [ ] **Step 1: Add standard CRUD views for SpliceProject**

```python
# SpliceProject views
class SpliceProjectListView(generic.ObjectListView):
    queryset = SpliceProject.objects.annotate(plan_count=models.Count("plans"))
    table = SpliceProjectTable
    filterset = SpliceProjectFilterSet
    filterset_form = SpliceProjectFilterForm

class SpliceProjectView(generic.ObjectView):
    queryset = SpliceProject.objects.all()

    def get_extra_context(self, request, instance):
        plans_table = SplicePlanTable(instance.plans.all())
        plans_table.configure(request)
        return {"plans_table": plans_table}

class SpliceProjectEditView(generic.ObjectEditView):
    queryset = SpliceProject.objects.all()
    form = SpliceProjectForm

class SpliceProjectDeleteView(generic.ObjectDeleteView):
    queryset = SpliceProject.objects.all()

class SpliceProjectBulkDeleteView(generic.BulkDeleteView):
    queryset = SpliceProject.objects.all()
    filterset = SpliceProjectFilterSet
    table = SpliceProjectTable
```

- [ ] **Step 2: Add standard CRUD views for ClosureCableEntry**

```python
class ClosureCableEntryListView(generic.ObjectListView):
    queryset = ClosureCableEntry.objects.select_related("closure", "fiber_cable", "entrance_port")
    table = ClosureCableEntryTable
    filterset = ClosureCableEntryFilterSet
    filterset_form = ClosureCableEntryFilterForm

class ClosureCableEntryView(generic.ObjectView):
    queryset = ClosureCableEntry.objects.all()

class ClosureCableEntryEditView(generic.ObjectEditView):
    queryset = ClosureCableEntry.objects.all()
    form = ClosureCableEntryForm

class ClosureCableEntryDeleteView(generic.ObjectDeleteView):
    queryset = ClosureCableEntry.objects.all()

class ClosureCableEntryBulkDeleteView(generic.BulkDeleteView):
    queryset = ClosureCableEntry.objects.all()
    filterset = ClosureCableEntryFilterSet
    table = ClosureCableEntryTable
```

- [ ] **Step 3: Commit**

```bash
git add netbox_fms/views.py
git commit -m "feat: add SpliceProject and ClosureCableEntry views"
```

---

### Task 12: Replace implement/rollback views with import/apply

**Files:**
- Modify: `netbox_fms/views.py`

- [ ] **Step 1: Remove old implement/rollback views**

Delete `SplicePlanImplementView` and `SplicePlanRollbackView` classes from `views.py`.

- [ ] **Step 2: Add import view**

```python
class SplicePlanImportFromDeviceView(View):
    """Import current live connections into a splice plan."""

    def post(self, request, pk):
        plan = get_object_or_404(SplicePlan, pk=pk)
        from .services import import_live_state
        try:
            count = import_live_state(plan)
            messages.success(
                request,
                _('Imported {count} connections into "{plan}".').format(count=count, plan=plan),
            )
        except Exception as e:
            messages.error(request, str(e))
        return redirect(plan.get_absolute_url())
```

- [ ] **Step 3: Add apply view**

```python
class SplicePlanApplyView(View):
    """Preview and apply a splice plan's diff to NetBox."""

    def get(self, request, pk):
        plan = get_object_or_404(SplicePlan, pk=pk)
        from .services import get_or_recompute_diff
        diff = get_or_recompute_diff(plan)
        return render(
            request,
            "netbox_fms/spliceplan_apply_confirm.html",
            {"object": plan, "diff": diff},
        )

    @transaction.atomic
    def post(self, request, pk):
        plan = get_object_or_404(SplicePlan, pk=pk)
        from .services import apply_diff
        try:
            result = apply_diff(plan)
            messages.success(
                request,
                _('Applied {added} additions and {removed} removals for "{plan}".').format(
                    added=result["added"], removed=result["removed"], plan=plan
                ),
            )
        except Exception as e:
            messages.error(request, str(e))
        return redirect(plan.get_absolute_url())
```

- [ ] **Step 4: Add export view**

```python
class SplicePlanExportDrawioView(View):
    """Export splice plan as draw.io XML."""

    def get(self, request, pk):
        from django.http import HttpResponse
        from .export import generate_drawio
        plan = get_object_or_404(SplicePlan, pk=pk)
        xml_content = generate_drawio(plan)
        response = HttpResponse(xml_content, content_type="application/xml")
        response["Content-Disposition"] = f'attachment; filename="{plan.name}.drawio"'
        return response
```

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/views.py
git commit -m "refactor: replace implement/rollback with import/apply/export views"
```

---

### Task 13: Implement import_live_state and apply_diff services

**Files:**
- Modify: `netbox_fms/services.py`
- Test: `tests/test_services.py`

- [ ] **Step 1: Write failing test for import_live_state**

Append to `tests/test_services.py`:

```python
from netbox_fms.services import import_live_state, apply_diff


class TestImportLiveState(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Imp Site", slug="imp-site")
        mfr = Manufacturer.objects.create(name="Imp Mfr", slug="imp-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Closure", slug="imp-closure")
        role = DeviceRole.objects.create(name="Imp Role", slug="imp-role")
        cls.closure = Device.objects.create(name="C-Imp", site=site, device_type=dt, role=role)

        mt = ModuleType.objects.create(manufacturer=mfr, model="Tray")
        bay = ModuleBay.objects.create(device=cls.closure, name="Bay 1")
        cls.tray = Module.objects.create(device=cls.closure, module_bay=bay, module_type=mt)

        cls.fp1 = make_front_port(device=cls.closure, module=cls.tray, name="F1")
        cls.fp2 = make_front_port(device=cls.closure, module=cls.tray, name="F2")

    def test_import_creates_entries(self):
        # Create a live connection
        cable = Cable.objects.create(length=0, length_unit="m")
        CableTermination.objects.create(cable=cable, cable_end="A", termination=self.fp1)
        CableTermination.objects.create(cable=cable, cable_end="B", termination=self.fp2)

        plan = SplicePlan.objects.create(closure=self.closure, name="Import Plan")
        count = import_live_state(plan)
        assert count == 1
        assert plan.entries.count() == 1
        entry = plan.entries.first()
        assert {entry.fiber_a_id, entry.fiber_b_id} == {self.fp1.pk, self.fp2.pk}

    def test_import_empty_closure(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Empty Plan")
        count = import_live_state(plan)
        assert count == 0


class TestApplyDiff(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="App Site", slug="app-site")
        mfr = Manufacturer.objects.create(name="App Mfr", slug="app-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Closure", slug="app-closure")
        role = DeviceRole.objects.create(name="App Role", slug="app-role")
        cls.closure = Device.objects.create(name="C-App", site=site, device_type=dt, role=role)

        mt = ModuleType.objects.create(manufacturer=mfr, model="Tray")
        bay = ModuleBay.objects.create(device=cls.closure, name="Bay 1")
        cls.tray = Module.objects.create(device=cls.closure, module_bay=bay, module_type=mt)

        cls.fp1 = make_front_port(device=cls.closure, module=cls.tray, name="F1")
        cls.fp2 = make_front_port(device=cls.closure, module=cls.tray, name="F2")
        cls.fp3 = make_front_port(device=cls.closure, module=cls.tray, name="F3")
        cls.fp4 = make_front_port(device=cls.closure, module=cls.tray, name="F4")

    def test_apply_creates_cables(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Apply Plan")
        SplicePlanEntry.objects.create(
            plan=plan, tray=self.tray, fiber_a=self.fp1, fiber_b=self.fp2
        )
        result = apply_diff(plan)
        assert result["added"] == 1
        assert result["removed"] == 0

        # Verify cable exists
        from django.contrib.contenttypes.models import ContentType
        fp_ct = ContentType.objects.get_for_model(FrontPort)
        terms = CableTermination.objects.filter(termination_type=fp_ct, termination_id=self.fp1.pk)
        assert terms.exists()

    def test_apply_removes_cables(self):
        # Create a live connection that's NOT in the plan
        cable = Cable.objects.create(length=0, length_unit="m")
        CableTermination.objects.create(cable=cable, cable_end="A", termination=self.fp3)
        CableTermination.objects.create(cable=cable, cable_end="B", termination=self.fp4)

        plan = SplicePlan.objects.create(closure=self.closure, name="Remove Plan")
        # Plan is empty → live connection should be removed
        result = apply_diff(plan)
        assert result["removed"] == 1
        assert not Cable.objects.filter(pk=cable.pk).exists()

    def test_apply_sets_status_to_applied(self):
        from netbox_fms.choices import SplicePlanStatusChoices
        plan = SplicePlan.objects.create(closure=self.closure, name="Status Plan")
        apply_diff(plan)
        plan.refresh_from_db()
        assert plan.status == SplicePlanStatusChoices.APPLIED
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_services.py::TestImportLiveState -v`
Expected: FAIL — `import_live_state` not defined.

- [ ] **Step 3: Implement import_live_state and apply_diff**

Append to `netbox_fms/services.py`:

```python
def import_live_state(plan):
    """
    Bootstrap a plan from the closure's current live connections.
    Creates SplicePlanEntry rows for each existing FrontPort↔FrontPort pair.
    Returns the number of entries created.
    """
    from dcim.models import FrontPort

    from .models import SplicePlanEntry

    live = get_live_state(plan.closure)

    # Collect unique pairs across all trays
    all_pairs = set()
    for pairs in live.values():
        all_pairs.update(pairs)

    # Build port → module lookup
    port_ids = set()
    for pa, pb in all_pairs:
        port_ids.add(pa)
        port_ids.add(pb)
    port_to_module = dict(
        FrontPort.objects.filter(pk__in=port_ids).values_list("pk", "module_id")
    )

    entries = []
    for port_a_id, port_b_id in all_pairs:
        tray_id = port_to_module.get(port_a_id)
        if tray_id is None:
            continue
        entries.append(
            SplicePlanEntry(
                plan=plan,
                tray_id=tray_id,
                fiber_a_id=port_a_id,
                fiber_b_id=port_b_id,
            )
        )

    # Note: bulk_create skips clean() validation. This is acceptable here
    # because we control the data (sourced from live NetBox state).
    SplicePlanEntry.objects.bulk_create(entries)
    plan.diff_stale = True
    plan.save(update_fields=["diff_stale"])
    return len(entries)


def apply_diff(plan):
    """
    Execute the diff: create cables for "add", delete cables for "remove".
    Returns {"added": int, "removed": int}.
    """
    from django.contrib.contenttypes.models import ContentType
    from django.db import transaction

    from dcim.models import Cable, CableTermination, FrontPort

    from .choices import SplicePlanStatusChoices

    diff = compute_diff(plan)

    fp_ct = ContentType.objects.get_for_model(FrontPort)
    added = 0
    removed = 0

    # Deduplicate inter-platter pairs (same pair appears on both trays)
    all_adds = set()
    all_removes = set()
    for tray_id, tray_diff in diff.items():
        for pair in tray_diff["add"]:
            all_adds.add(tuple(pair))
        for pair in tray_diff["remove"]:
            all_removes.add(tuple(pair))

    with transaction.atomic():
        # Process removals
        for port_a_id, port_b_id in all_removes:
            cable_ids_a = set(
                CableTermination.objects.filter(
                    termination_type=fp_ct, termination_id=port_a_id
                ).values_list("cable_id", flat=True)
            )
            cable_ids_b = set(
                CableTermination.objects.filter(
                    termination_type=fp_ct, termination_id=port_b_id
                ).values_list("cable_id", flat=True)
            )
            common = cable_ids_a & cable_ids_b
            for cable_id in common:
                Cable.objects.filter(pk=cable_id).delete()
                removed += 1

        # Process additions
        for port_a_id, port_b_id in all_adds:
            cable = Cable(length=0, length_unit="m")
            cable.save()
            CableTermination.objects.create(
                cable=cable, cable_end="A",
                termination_type=fp_ct, termination_id=port_a_id,
            )
            CableTermination.objects.create(
                cable=cable, cable_end="B",
                termination_type=fp_ct, termination_id=port_b_id,
            )
            added += 1

        plan.status = SplicePlanStatusChoices.APPLIED
        plan.diff_stale = True
        plan.save(update_fields=["status", "diff_stale"])

    return {"added": added, "removed": removed}
```

- [ ] **Step 4: Run all service tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_services.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/services.py tests/test_services.py
git commit -m "feat: add import_live_state and apply_diff services"
```

---

### Task 14: Update URLs

**Files:**
- Modify: `netbox_fms/urls.py`

- [ ] **Step 1: Add SpliceProject URL patterns**

```python
# SpliceProject
path("splice-projects/", views.SpliceProjectListView.as_view(), name="spliceproject_list"),
path("splice-projects/add/", views.SpliceProjectEditView.as_view(), name="spliceproject_add"),
path("splice-projects/delete/", views.SpliceProjectBulkDeleteView.as_view(), name="spliceproject_bulk_delete"),
path("splice-projects/<int:pk>/", include(get_model_urls("netbox_fms", "spliceproject"))),
path("splice-projects/<int:pk>/", views.SpliceProjectView.as_view(), name="spliceproject"),
path("splice-projects/<int:pk>/edit/", views.SpliceProjectEditView.as_view(), name="spliceproject_edit"),
path("splice-projects/<int:pk>/delete/", views.SpliceProjectDeleteView.as_view(), name="spliceproject_delete"),
```

- [ ] **Step 2: Add ClosureCableEntry URL patterns**

```python
# ClosureCableEntry
path("closure-cable-entries/", views.ClosureCableEntryListView.as_view(), name="closurecableentry_list"),
path("closure-cable-entries/add/", views.ClosureCableEntryEditView.as_view(), name="closurecableentry_add"),
path("closure-cable-entries/delete/", views.ClosureCableEntryBulkDeleteView.as_view(), name="closurecableentry_bulk_delete"),
path("closure-cable-entries/<int:pk>/", include(get_model_urls("netbox_fms", "closurecableentry"))),
path("closure-cable-entries/<int:pk>/", views.ClosureCableEntryView.as_view(), name="closurecableentry"),
path("closure-cable-entries/<int:pk>/edit/", views.ClosureCableEntryEditView.as_view(), name="closurecableentry_edit"),
path("closure-cable-entries/<int:pk>/delete/", views.ClosureCableEntryDeleteView.as_view(), name="closurecableentry_delete"),
```

- [ ] **Step 3: Replace implement/rollback URLs with import/apply/export**

Remove:
```python
path("splice-plans/<int:pk>/implement/", ...),
path("splice-plans/<int:pk>/rollback/", ...),
```

Add:
```python
path("splice-plans/<int:pk>/import/", views.SplicePlanImportFromDeviceView.as_view(), name="spliceplan_import_device"),
path("splice-plans/<int:pk>/apply/", views.SplicePlanApplyView.as_view(), name="spliceplan_apply"),
path("splice-plans/<int:pk>/export/", views.SplicePlanExportDrawioView.as_view(), name="spliceplan_export"),
```

- [ ] **Step 4: Verify URL patterns load**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.urls import urlpatterns; print(f'{len(urlpatterns)} URL patterns loaded')"`
Expected: No errors, pattern count printed.

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/urls.py
git commit -m "refactor: update URLs for splice plan redesign"
```

---

### Task 15: Create/update templates

**Files:**
- Create: `netbox_fms/templates/netbox_fms/spliceproject.html`
- Create: `netbox_fms/templates/netbox_fms/closurecableentry.html`
- Create: `netbox_fms/templates/netbox_fms/spliceplan_apply_confirm.html`
- Modify: `netbox_fms/templates/netbox_fms/spliceplan.html`
- Delete: `netbox_fms/templates/netbox_fms/spliceplan_implement_confirm.html`

- [ ] **Step 1: Create SpliceProject detail template**

Follow existing template patterns (e.g., `spliceplan.html`). Show project name, description, and plans table.

- [ ] **Step 2: Create ClosureCableEntry detail template**

Show closure, fiber cable, entrance port, notes.

- [ ] **Step 3: Create apply confirmation template**

Show the diff per tray: additions in green, removals in red, unchanged in gray. Apply button at bottom.

- [ ] **Step 4: Update spliceplan.html**

Remove "Implement Plan" and "Rollback" buttons. Add:
- "Import from Device" button (POST)
- "Apply" button (links to apply confirmation)
- "Export Draw.io" button (links to export URL)
- Show diff summary (X additions, Y removals) if available
- Show project link if plan has one

- [ ] **Step 5: Delete old implement confirmation template**

```bash
rm netbox_fms/templates/netbox_fms/spliceplan_implement_confirm.html
```

- [ ] **Step 6: Commit**

```bash
git add netbox_fms/templates/
git commit -m "refactor: update templates for splice plan redesign"
```

---

### Task 16: Update navigation and search

**Files:**
- Modify: `netbox_fms/navigation.py`
- Modify: `netbox_fms/search.py`

- [ ] **Step 1: Add SpliceProject and ClosureCableEntry to navigation**

Add menu items in the "Splice Planning" group:

```python
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
    link="plugins:netbox_fms:closurecableentry_list",
    link_text="Cable Entries",
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
```

- [ ] **Step 2: Add SpliceProject search index**

```python
@register_search
class SpliceProjectIndex(SearchIndex):
    model = SpliceProject
    fields = (
        ("name", 100),
        ("description", 500),
    )
    display_attrs = ("description",)
```

- [ ] **Step 3: Verify imports**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.navigation import menu; from netbox_fms.search import *"`

- [ ] **Step 4: Commit**

```bash
git add netbox_fms/navigation.py netbox_fms/search.py
git commit -m "feat: add SpliceProject and ClosureCableEntry to navigation and search"
```

---

## Chunk 5: API, GraphQL, Device Tab Rework

### Task 17: Update API serializers

**Files:**
- Modify: `netbox_fms/api/serializers.py`

- [ ] **Step 1: Add SpliceProject and ClosureCableEntry serializers**

```python
from netbox_fms.models import ClosureCableEntry, SpliceProject

class SpliceProjectSerializer(NetBoxModelSerializer):
    class Meta:
        model = SpliceProject
        fields = ("id", "url", "display", "name", "description", "tags", "created", "last_updated")

class ClosureCableEntrySerializer(NetBoxModelSerializer):
    class Meta:
        model = ClosureCableEntry
        fields = ("id", "url", "display", "closure", "fiber_cable", "entrance_port", "notes", "tags", "created", "last_updated")
```

- [ ] **Step 2: Rework SplicePlanSerializer**

Remove `mode`, `tray`; add `project`, `cached_diff`, `diff_stale`:

```python
class SplicePlanSerializer(NetBoxModelSerializer):
    class Meta:
        model = SplicePlan
        fields = ("id", "url", "display", "closure", "project", "name", "description", "status", "cached_diff", "diff_stale", "tags", "created", "last_updated")
```

- [ ] **Step 3: Rework SplicePlanEntrySerializer**

Change `fiber_a`/`fiber_b` to FrontPort, add `tray`, `notes`, remove `cable`/`mode_override`:

```python
class SplicePlanEntrySerializer(NetBoxModelSerializer):
    class Meta:
        model = SplicePlanEntry
        fields = ("id", "url", "display", "plan", "tray", "fiber_a", "fiber_b", "notes", "tags", "created", "last_updated")
```

- [ ] **Step 4: Remove BulkSpliceInputSerializer** (no longer needed — bulk ops go through standard API).

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/api/serializers.py
git commit -m "refactor: update API serializers for splice plan redesign"
```

---

### Task 18: Update API views and URLs

**Files:**
- Modify: `netbox_fms/api/views.py`
- Modify: `netbox_fms/api/urls.py`

- [ ] **Step 1: Add SpliceProject and ClosureCableEntry ViewSets**

```python
class SpliceProjectViewSet(NetBoxModelViewSet):
    queryset = SpliceProject.objects.prefetch_related("tags").annotate(plan_count=Count("plans"))
    serializer_class = SpliceProjectSerializer
    filterset_class = SpliceProjectFilterSet

class ClosureCableEntryViewSet(NetBoxModelViewSet):
    queryset = ClosureCableEntry.objects.prefetch_related("closure", "fiber_cable", "entrance_port", "tags")
    serializer_class = ClosureCableEntrySerializer
    filterset_class = ClosureCableEntryFilterSet
```

- [ ] **Step 2: Replace implement/rollback/bulk_splice actions with import/apply/diff**

```python
class SplicePlanViewSet(NetBoxModelViewSet):
    queryset = SplicePlan.objects.prefetch_related("closure", "project", "tags").annotate(entry_count=Count("entries"))
    serializer_class = SplicePlanSerializer
    filterset_class = SplicePlanFilterSet

    @action(detail=True, methods=["post"], url_path="import-from-device")
    def import_from_device(self, request, pk=None):
        plan = self.get_object()
        from netbox_fms.services import import_live_state
        try:
            count = import_live_state(plan)
            return Response({"imported": count})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="apply")
    def apply_plan(self, request, pk=None):
        plan = self.get_object()
        from netbox_fms.services import apply_diff
        try:
            result = apply_diff(plan)
            return Response(result)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["get"], url_path="diff")
    def get_diff(self, request, pk=None):
        plan = self.get_object()
        from netbox_fms.services import get_or_recompute_diff
        diff = get_or_recompute_diff(plan)
        return Response(diff)
```

- [ ] **Step 3: Register new ViewSets in api/urls.py**

```python
router.register("splice-projects", views.SpliceProjectViewSet)
router.register("closure-cable-entries", views.ClosureCableEntryViewSet)
```

- [ ] **Step 4: Verify API imports**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.api.views import *; from netbox_fms.api.urls import urlpatterns"`

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/api/views.py netbox_fms/api/urls.py
git commit -m "refactor: update API views for splice plan redesign — import/apply/diff endpoints"
```

---

### Task 19: Update GraphQL layer

**Files:**
- Modify: `netbox_fms/graphql/types.py`
- Modify: `netbox_fms/graphql/schema.py`
- Modify: `netbox_fms/graphql/filters.py`

- [ ] **Step 1: Add types for SpliceProject and ClosureCableEntry**

```python
@strawberry_django.type(SpliceProject, fields="__all__")
class SpliceProjectType(NetBoxObjectType):
    pass

@strawberry_django.type(ClosureCableEntry, fields="__all__")
class ClosureCableEntryType(NetBoxObjectType):
    pass
```

- [ ] **Step 2: Update SplicePlanType and SplicePlanEntryType**

Remove references to old fields (`mode`, `cable`, `mode_override`). Ensure new fields (`project`, `cached_diff`, `diff_stale`, `tray`, `notes`) are exposed.

- [ ] **Step 3: Add query fields to schema.py**

```python
splice_project: SpliceProjectType = strawberry_django.field()
splice_project_list: list[SpliceProjectType] = strawberry_django.field()
closure_cable_entry: ClosureCableEntryType = strawberry_django.field()
closure_cable_entry_list: list[ClosureCableEntryType] = strawberry_django.field()
```

- [ ] **Step 4: Add filters to graphql/filters.py**

```python
@strawberry_django.filters.filter(SpliceProject)
class SpliceProjectFilter(NetBoxModelFilterSet):
    pass

@strawberry_django.filters.filter(ClosureCableEntry)
class ClosureCableEntryFilter(NetBoxModelFilterSet):
    pass
```

- [ ] **Step 5: Verify GraphQL imports**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.graphql.types import *; from netbox_fms.graphql.schema import *"`

- [ ] **Step 6: Commit**

```bash
git add netbox_fms/graphql/
git commit -m "feat: add SpliceProject and ClosureCableEntry to GraphQL schema"
```

---

### Task 20: Update Device tab splice editor

**Files:**
- Modify: `netbox_fms/views.py` (DeviceSpliceEditorView)

- [ ] **Step 1: Update DeviceSpliceEditorView**

Update to use the new SplicePlan model (one per closure, no `mode` field). The view should show the diff summary and provide import/apply/export actions:

```python
@register_model_view(Device, "splice_editor", path="splice-editor")
class DeviceSpliceEditorView(View):
    tab = ViewTab(
        label=_("Splice Editor"),
        visible=_device_has_fiber_cables,
        weight=1500,
    )

    def get(self, request, pk):
        device = get_object_or_404(Device, pk=pk)
        plan = SplicePlan.objects.filter(closure=device).first()

        diff = None
        if plan:
            from .services import get_or_recompute_diff
            diff = get_or_recompute_diff(plan)

        return render(
            request,
            "netbox_fms/device_splice_editor.html",
            {
                "object": device,
                "device": device,
                "plan": plan,
                "diff": diff,
                "tab": self.tab,
            },
        )
```

- [ ] **Step 2: Commit**

```bash
git add netbox_fms/views.py
git commit -m "refactor: update Device splice editor tab for new plan model"
```

---

## Chunk 6: Draw.io Export + Final Integration

### Task 21: Implement draw.io export

**Files:**
- Create: `netbox_fms/export.py`
- Test: `tests/test_export.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_export.py`:

```python
from django.test import TestCase
from dcim.models import (
    Cable, CableTermination, Device, DeviceRole, DeviceType,
    FrontPort, Manufacturer, Module, ModuleBay, ModuleType, Site,
)

from netbox_fms.export import generate_drawio
from netbox_fms.models import SplicePlan, SplicePlanEntry


class TestDrawioExport(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Exp Site", slug="exp-site")
        mfr = Manufacturer.objects.create(name="Exp Mfr", slug="exp-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Closure", slug="exp-closure")
        role = DeviceRole.objects.create(name="Exp Role", slug="exp-role")
        cls.closure = Device.objects.create(name="C-Exp", site=site, device_type=dt, role=role)

        mt = ModuleType.objects.create(manufacturer=mfr, model="Tray")
        bay = ModuleBay.objects.create(device=cls.closure, name="Bay 1")
        cls.tray = Module.objects.create(device=cls.closure, module_bay=bay, module_type=mt)

        cls.fp1 = make_front_port(device=cls.closure, module=cls.tray, name="F1")
        cls.fp2 = make_front_port(device=cls.closure, module=cls.tray, name="F2")

    def test_generates_valid_xml(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Export Plan")
        SplicePlanEntry.objects.create(plan=plan, tray=self.tray, fiber_a=self.fp1, fiber_b=self.fp2)
        xml = generate_drawio(plan)
        assert xml.startswith("<?xml") or xml.startswith("<mxfile")
        assert "mxGraphModel" in xml

    def test_empty_plan_generates_xml(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Empty Export Plan")
        xml = generate_drawio(plan)
        assert "mxGraphModel" in xml

    def test_contains_fiber_names(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Name Plan")
        SplicePlanEntry.objects.create(plan=plan, tray=self.tray, fiber_a=self.fp1, fiber_b=self.fp2)
        xml = generate_drawio(plan)
        assert "F1" in xml
        assert "F2" in xml

    def test_diff_annotations(self):
        """Entries to add should be annotated green in the export."""
        plan = SplicePlan.objects.create(closure=self.closure, name="Diff Plan")
        SplicePlanEntry.objects.create(plan=plan, tray=self.tray, fiber_a=self.fp1, fiber_b=self.fp2)
        xml = generate_drawio(plan)
        # Green color for additions (#00CC00 or similar)
        assert "#00CC00" in xml or "green" in xml.lower() or "strokeColor=#00" in xml
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_export.py -v`
Expected: FAIL — `netbox_fms.export` does not exist.

- [ ] **Step 3: Implement export.py**

Create `netbox_fms/export.py`:

```python
"""Generate draw.io (mxGraph XML) diagrams for splice plans."""

import xml.etree.ElementTree as ET

from .services import compute_diff


def generate_drawio(plan):
    """
    Generate a draw.io XML file for a splice plan.
    One page/tab per tray. Fibers colored by EIA-598, diff annotations.
    """
    diff = compute_diff(plan)

    mxfile = ET.Element("mxfile", host="netbox-fms")

    # Get all trays on the closure
    from dcim.models import FrontPort, Module

    trays = Module.objects.filter(device=plan.closure).order_by("module_bay__name")

    if not trays.exists():
        # Empty diagram
        diagram = ET.SubElement(mxfile, "diagram", name=plan.name)
        model = ET.SubElement(diagram, "mxGraphModel")
        ET.SubElement(model, "root")
        return ET.tostring(mxfile, encoding="unicode", xml_declaration=True)

    for tray in trays:
        tray_diff = diff.get(tray.pk, {"add": [], "remove": [], "unchanged": []})
        diagram = ET.SubElement(mxfile, "diagram", name=f"Tray: {tray}")

        model = ET.SubElement(diagram, "mxGraphModel")
        root = ET.SubElement(model, "root")

        # Required mxGraph root cells
        ET.SubElement(root, "mxCell", id="0")
        ET.SubElement(root, "mxCell", id="1", parent="0")

        # Get FrontPorts on this tray, grouped by cable entrance
        ports = FrontPort.objects.filter(
            device=plan.closure, module=tray
        ).order_by("name")

        # Layout: ports on left side, connections drawn between pairs
        y_offset = 40
        cell_id = 2
        port_cells = {}

        # Header
        header = ET.SubElement(root, "mxCell", id=str(cell_id), value=f"Tray: {tray}", style="text;fontStyle=1;fontSize=14", vertex="1", parent="1")
        ET.SubElement(header, "mxGeometry", x="10", y="10", width="400", height="20", **{"as": "geometry"})
        cell_id += 1

        # Look up fiber strand colors via FiberStrand.front_port FK
        from netbox_fms.models import FiberStrand
        strand_colors = dict(
            FiberStrand.objects.filter(
                front_port__in=ports
            ).values_list("front_port_id", "color")
        )

        for port in ports:
            color = f"#{strand_colors[port.pk]}" if port.pk in strand_colors else "#CCCCCC"
            style = f"rounded=1;fillColor={color};fontColor=#000000;strokeColor=#333333"

            cell = ET.SubElement(root, "mxCell", id=str(cell_id), value=port.name, style=style, vertex="1", parent="1")
            ET.SubElement(cell, "mxGeometry", x="20", y=str(y_offset), width="120", height="24", **{"as": "geometry"})
            port_cells[port.pk] = str(cell_id)
            cell_id += 1
            y_offset += 30

        # Draw connections
        def _draw_edge(pair, color, style_extra=""):
            nonlocal cell_id
            pa, pb = pair
            src = port_cells.get(pa)
            tgt = port_cells.get(pb)
            if src and tgt:
                style = f"strokeColor={color};strokeWidth=2;{style_extra}"
                ET.SubElement(
                    root, "mxCell", id=str(cell_id), style=style,
                    edge="1", parent="1", source=src, target=tgt,
                )
                cell_id += 1

        for pair in tray_diff["unchanged"]:
            _draw_edge(pair, "#000000")

        for pair in tray_diff["add"]:
            _draw_edge(pair, "#00CC00", "dashed=1")

        for pair in tray_diff["remove"]:
            _draw_edge(pair, "#CC0000", "dashed=1")

    return ET.tostring(mxfile, encoding="unicode", xml_declaration=True)
```

- [ ] **Step 4: Run export tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_export.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/export.py tests/test_export.py
git commit -m "feat: add draw.io XML export for splice plans"
```

---

### Task 22: Run full test suite and lint

**Files:** All

- [ ] **Step 1: Run all tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v`
Expected: ALL PASS

- [ ] **Step 2: Run lint**

Run: `cd /opt/netbox-fms && ruff check --fix netbox_fms/ && ruff format netbox_fms/`
Expected: Clean

- [ ] **Step 3: Verify all modules import**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.models import *; from netbox_fms.forms import *; from netbox_fms.filters import *; from netbox_fms.services import *; from netbox_fms.export import *"`
Expected: No errors

- [ ] **Step 4: Run migrations from scratch**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py showmigrations netbox_fms
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py migrate
```
Expected: All migrations applied

- [ ] **Step 5: Commit any remaining fixes**

```bash
git add -A
git commit -m "chore: final lint and import fixes for splice plan redesign"
```

---

## Task Dependency Summary

```
Task 1 (choices) → Task 2 (SpliceProject) → Task 3 (SplicePlan) → Task 4 (SplicePlanEntry) → Task 5 (ClosureCableEntry)
    ↓
Task 6 (diff engine) → Task 7 (signals)
    ↓
Task 8 (forms) ─┐
Task 9 (filters) ├→ Task 11 (views) → Task 12 (import/apply views) → Task 13 (import/apply services)
Task 10 (tables) ┘     ↓
                  Task 14 (URLs) → Task 15 (templates) → Task 16 (nav/search)
                        ↓
                  Task 17 (API serializers) → Task 18 (API views/URLs) → Task 19 (GraphQL) → Task 20 (device tab)
                        ↓
                  Task 21 (draw.io export) → Task 22 (final integration)
```

Tasks 8, 9, 10 can run in parallel. Tasks 17-19 can partially parallelize.
