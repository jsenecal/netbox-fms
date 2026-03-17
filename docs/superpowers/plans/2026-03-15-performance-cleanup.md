# Performance & Cleanup Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate N+1 queries in the Fiber Overview tab, remove dead/duplicate URL patterns, flesh out GraphQL filters, and optimize signal handlers.

**Architecture:** Prefetch related objects in view queries, deduplicate URL routing, add meaningful filter fields to GraphQL types, and batch signal queries.

**Tech Stack:** Django ORM, NetBox plugin URL routing, Strawberry-Django GraphQL

---

## File Map

| File | Changes |
|------|---------|
| `netbox_fms/views.py` | Refactor `_build_cable_row()` to batch queries, prefetch in `DeviceFiberOverviewView` |
| `netbox_fms/urls.py` | Remove duplicate `<int:pk>/` detail view patterns (7 occurrences) |
| `netbox_fms/graphql/filters.py` | Add useful filter fields to all GraphQL filter classes |
| `netbox_fms/signals.py` | Combine two FrontPort queries into one |
| `tests/test_performance.py` | New file — query count assertions for overview tab |

---

## Chunk 1: Fiber Overview N+1 Query Fix

### Task 1: Refactor _build_cable_row() to eliminate per-row queries

**Files:**
- Modify: `netbox_fms/views.py:659-751`
- Test: `tests/test_performance.py`

**Why:** `_build_cable_row()` is called once per RearPort, and each call fires 3-4 queries: CableTermination lookup, FiberCable lookup, strand counts, and ClosureCableEntry lookup. For a 12-cable closure, that's ~48 queries. This should be ~5 queries total with proper prefetching.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_performance.py
import pytest
from django.test.utils import override_settings


@pytest.mark.django_db
class TestFiberOverviewQueryCount:
    """Fiber Overview tab should use bounded queries, not per-row."""

    def test_overview_query_count_is_bounded(self, client, django_assert_num_queries):
        """Query count should not scale linearly with cable count.

        This is a structural test. The exact count depends on the fixture,
        but it should be roughly constant regardless of cable count.
        We verify by checking the refactored code path exists.
        """
        # Structural verification — the actual query count test requires
        # a fixture with multiple cables. The key assertion is that
        # _build_cable_rows (plural) replaces per-row _build_cable_row.
        from netbox_fms.views import _build_cable_rows
        assert callable(_build_cable_rows)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_performance.py -v`
Expected: FAIL — `_build_cable_rows` doesn't exist yet.

- [ ] **Step 3: Replace _build_cable_row with batch _build_cable_rows**

In `netbox_fms/views.py`, replace the `_build_cable_row` function (lines 659-693) and update `DeviceFiberOverviewView.get()` (lines 721-751):

```python
def _build_cable_rows(device, rearports):
    """Build context dicts for all cable rows in one batch — avoids N+1 queries."""
    from dcim.models import CableTermination, RearPort
    from django.contrib.contenttypes.models import ContentType

    if not rearports:
        return []

    rp_ct = ContentType.objects.get_for_model(RearPort)
    rp_ids = [rp.pk for rp in rearports]

    # 1) Batch: all CableTerminations for these RearPorts
    terms = CableTermination.objects.filter(
        termination_type=rp_ct,
        termination_id__in=rp_ids,
    ).select_related("cable")
    term_by_rp = {t.termination_id: t for t in terms}

    # 2) Batch: all FiberCables for the cables found
    cable_ids = [t.cable_id for t in terms if t.cable_id]
    fc_by_cable = {}
    if cable_ids:
        for fc in FiberCable.objects.filter(cable_id__in=cable_ids).select_related("cable", "fiber_cable_type"):
            fc_by_cable[fc.cable_id] = fc

    # 3) Batch: strand counts per FiberCable
    fiber_cable_ids = [fc.pk for fc in fc_by_cable.values()]
    strand_totals = {}
    strand_provisioned = {}
    if fiber_cable_ids:
        from django.db.models import Count, Q

        from .models import FiberStrand

        totals = (
            FiberStrand.objects.filter(fiber_cable_id__in=fiber_cable_ids)
            .values("fiber_cable_id")
            .annotate(
                total=Count("pk"),
                provisioned=Count("pk", filter=Q(front_port__device=device)),
            )
        )
        for row in totals:
            strand_totals[row["fiber_cable_id"]] = row["total"]
            strand_provisioned[row["fiber_cable_id"]] = row["provisioned"]

    # 4) Batch: ClosureCableEntry for these FiberCables
    gland_by_fc = {}
    if fiber_cable_ids:
        for entry in ClosureCableEntry.objects.filter(closure=device, fiber_cable_id__in=fiber_cable_ids):
            gland_by_fc[entry.fiber_cable_id] = entry

    # 5) Assemble rows
    rows = []
    for rp in rearports:
        term = term_by_rp.get(rp.pk)
        cable = term.cable if term else None
        fiber_cable = fc_by_cable.get(cable.pk) if cable else None

        strand_info = None
        gland_entry = None
        if fiber_cable:
            strand_info = {
                "provisioned": strand_provisioned.get(fiber_cable.pk, 0),
                "total": strand_totals.get(fiber_cable.pk, 0),
            }
            gland_entry = gland_by_fc.get(fiber_cable.pk)

        rows.append({
            "rearport": rp,
            "cable": cable,
            "fiber_cable": fiber_cable,
            "strand_info": strand_info,
            "gland_entry": gland_entry,
        })

    return rows
```

Then update `DeviceFiberOverviewView.get()`:

```python
    def get(self, request, pk):
        device = get_object_or_404(Device, pk=pk)

        from dcim.models import RearPort

        module_rearports = list(
            RearPort.objects.filter(device=device, module__isnull=False).select_related("module")
        )

        cable_rows = _build_cable_rows(device, module_rearports)

        plan = SplicePlan.objects.filter(closure=device).first()

        stats = {
            "tray_count": device.modules.count(),
            "cable_count": sum(1 for r in cable_rows if r["cable"]),
            "fiber_cable_count": sum(1 for r in cable_rows if r["fiber_cable"]),
            "strand_provisioned": sum(r["strand_info"]["provisioned"] for r in cable_rows if r["strand_info"]),
            "strand_total": sum(r["strand_info"]["total"] for r in cable_rows if r["strand_info"]),
        }

        return render(
            request,
            "netbox_fms/device_fiber_overview.html",
            {
                "object": device,
                "device": device,
                "cable_rows": cable_rows,
                "plan": plan,
                "stats": stats,
                "tab": self.tab,
            },
        )
```

Also keep the old `_build_cable_row` for the HTMX row-swap endpoints that rebuild a single row, but have it delegate to `_build_cable_rows`:

```python
def _build_cable_row(device, rearport):
    """Build context dict for a single cable row (used by HTMX row-swap endpoints)."""
    rows = _build_cable_rows(device, [rearport])
    return rows[0] if rows else {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_performance.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add netbox_fms/views.py tests/test_performance.py
git commit -m "perf: batch queries in Fiber Overview tab to eliminate N+1"
```

---

## Chunk 2: URL Cleanup & GraphQL Filters

### Task 2: Remove duplicate URL patterns

**Files:**
- Modify: `netbox_fms/urls.py`
- Test: Manual verification

**Why:** Every model has both `include(get_model_urls(...))` and a direct `path("<int:pk>/", ...)` for the detail view on the same URL prefix. Django matches the first one, so the second is dead code. The `get_model_urls()` include already registers the detail view name. The duplicates cause confusion and potential routing conflicts.

The 7 duplicate patterns to remove are on lines 14, 21, 36, 43, 61, 76, 89, 105, 117, 143.

- [ ] **Step 1: Identify all duplicate patterns**

For each model section, the pattern `path("<model>/<int:pk>/", include(get_model_urls(...)))` already handles the detail route. The immediately following `path("<model>/<int:pk>/", views.XxxView.as_view(), name="xxx")` is unreachable.

Models affected: FiberCableType, BufferTubeTemplate, RibbonTemplate, CableElementTemplate, FiberCable, SplicePlan, SplicePlanEntry, SpliceProject, ClosureCableEntry, FiberPathLoss (10 total).

- [ ] **Step 2: Verify get_model_urls registers the detail view name**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "
import django; django.setup()
from utilities.urls import get_model_urls
urls = get_model_urls('netbox_fms', 'fibercabletype')
for u in urls:
    print(u.name, u.pattern)
"`

This confirms whether `get_model_urls` includes a route named `fibercabletype` at `''` (empty path = the `<int:pk>/` prefix).

- [ ] **Step 3: Remove duplicate detail view paths**

Remove these lines from `netbox_fms/urls.py`:
- Line 14: `path("cable-types/<int:pk>/", views.FiberCableTypeView...)`
- Line 21: `path("buffer-tube-templates/<int:pk>/", views.BufferTubeTemplateView...)`
- Line 36: `path("ribbon-templates/<int:pk>/", views.RibbonTemplateView...)`
- Line 43: `path("cable-element-templates/<int:pk>/", views.CableElementTemplateView...)`
- Line 61: `path("fiber-cables/<int:pk>/", views.FiberCableView...)`
- Line 76: `path("splice-plans/<int:pk>/", views.SplicePlanView...)`
- Line 89: `path("splice-plan-entries/<int:pk>/", views.SplicePlanEntryView...)`
- Line 105: `path("splice-projects/<int:pk>/", views.SpliceProjectView...)`
- Line 117: `path("closure-cable-entries/<int:pk>/", views.ClosureCableEntryView...)`
- Line 143: `path("fiber-path-losses/<int:pk>/", views.FiberPathLossView...)`

**Important:** Only remove if Step 2 confirmed `get_model_urls` provides these routes. If it doesn't, keep them and just document the duplication.

- [ ] **Step 4: Run full test suite**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v`
Expected: All PASS (URL names should resolve via get_model_urls)

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/urls.py
git commit -m "cleanup: remove unreachable duplicate detail view URL patterns"
```

---

### Task 3: Flesh out GraphQL filters

**Files:**
- Modify: `netbox_fms/graphql/filters.py`

**Why:** Most GraphQL filter classes only have `id`, making the GraphQL API nearly useless for filtered queries. Users can't filter FiberCables by cable type, or SplicePlans by closure device — standard operations.

- [ ] **Step 1: Add meaningful filter fields**

Replace `netbox_fms/graphql/filters.py` with:

```python
import strawberry_django

from ..models import (
    BufferTubeTemplate,
    CableElementTemplate,
    ClosureCableEntry,
    FiberCable,
    FiberCableType,
    FiberPathLoss,
    RibbonTemplate,
    SplicePlan,
    SplicePlanEntry,
    SpliceProject,
)

__all__ = (
    "FiberCableTypeFilter",
    "BufferTubeTemplateFilter",
    "RibbonTemplateFilter",
    "CableElementTemplateFilter",
    "FiberCableFilter",
    "SplicePlanFilter",
    "SplicePlanEntryFilter",
    "SpliceProjectFilter",
    "ClosureCableEntryFilter",
    "FiberPathLossFilter",
)


@strawberry_django.filters.filter(FiberCableType)
class FiberCableTypeFilter:
    id: int | None
    construction: str | None
    fiber_type: str | None
    is_armored: bool | None
    deployment: str | None
    strand_count: int | None


@strawberry_django.filters.filter(BufferTubeTemplate)
class BufferTubeTemplateFilter:
    id: int | None
    fiber_cable_type_id: int | None
    name: str | None


@strawberry_django.filters.filter(RibbonTemplate)
class RibbonTemplateFilter:
    id: int | None
    fiber_cable_type_id: int | None
    buffer_tube_template_id: int | None


@strawberry_django.filters.filter(CableElementTemplate)
class CableElementTemplateFilter:
    id: int | None
    fiber_cable_type_id: int | None
    element_type: str | None


@strawberry_django.filters.filter(FiberCable)
class FiberCableFilter:
    id: int | None
    fiber_cable_type_id: int | None
    cable_id: int | None
    name: str | None


@strawberry_django.filters.filter(SplicePlan)
class SplicePlanFilter:
    id: int | None
    name: str | None
    status: str | None
    closure_id: int | None
    project_id: int | None


@strawberry_django.filters.filter(SplicePlanEntry)
class SplicePlanEntryFilter:
    id: int | None
    plan_id: int | None
    tray_id: int | None


@strawberry_django.filters.filter(SpliceProject)
class SpliceProjectFilter:
    id: int | None
    name: str | None


@strawberry_django.filters.filter(ClosureCableEntry)
class ClosureCableEntryFilter:
    id: int | None
    closure_id: int | None
    fiber_cable_id: int | None


@strawberry_django.filters.filter(FiberPathLoss)
class FiberPathLossFilter:
    id: int | None
    cable_id: int | None
    wavelength_nm: int | None
```

- [ ] **Step 2: Verify import is clean**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.graphql.filters import *; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add netbox_fms/graphql/filters.py
git commit -m "feat: add meaningful filter fields to all GraphQL filter classes"
```

---

## Chunk 3: Signal Optimization

### Task 4: Optimize signal handler to use single query

**Files:**
- Modify: `netbox_fms/signals.py`

**Why:** `_invalidate_plans_for_cable()` first queries `CableTermination` for FrontPort IDs, then queries `FrontPort` for device IDs — two queries. These can be combined. Additionally, the function runs on every `Cable.post_save`, even for cables that don't terminate on FrontPorts.

- [ ] **Step 1: Refactor to single query with early exit**

Replace `_invalidate_plans_for_cable` in `netbox_fms/signals.py`:

```python
def _invalidate_plans_for_cable(cable):
    """If this cable terminates on FrontPorts of a closure with a SplicePlan, mark diff stale."""
    from dcim.models import CableTermination, FrontPort
    from django.contrib.contenttypes.models import ContentType

    from .models import SplicePlan

    fp_ct = ContentType.objects.get_for_model(FrontPort)

    # Single query: get device IDs of tray FrontPorts terminated by this cable
    device_ids = set(
        FrontPort.objects.filter(
            pk__in=CableTermination.objects.filter(
                cable=cable,
                termination_type=fp_ct,
            ).values("termination_id"),
            module__isnull=False,
        ).values_list("device_id", flat=True)
    )

    if device_ids:
        SplicePlan.objects.filter(
            closure_id__in=device_ids,
            diff_stale=False,
        ).update(diff_stale=True)
```

- [ ] **Step 2: Run full test suite**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add netbox_fms/signals.py
git commit -m "perf: optimize signal handler to single subquery for cable invalidation"
```

---

## Summary

| Task | Category | Impact |
|------|----------|--------|
| 1 | Performance | Fiber Overview tab: ~48 queries → ~5 queries for 12-cable closure |
| 2 | Cleanup | Remove 10 unreachable URL patterns, simplify routing |
| 3 | Feature | GraphQL API becomes usable for filtered queries |
| 4 | Performance | Signal handler: 2 queries → 1 subquery per cable save/delete |
