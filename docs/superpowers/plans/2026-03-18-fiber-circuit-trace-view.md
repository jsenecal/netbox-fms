# Fiber Circuit Path Trace View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an interactive D3.js trace visualization tab to FiberCircuitPath detail pages, with an HTMX-powered detail sidebar.

**Architecture:** A new D3 TypeScript app renders the path as a vertical node chain (devices + cables). Clicking a node zooms in with smooth transitions and loads detail content via HTMX into a 340px sidebar. The trace data comes from a new `@action("trace")` API endpoint that transforms the raw path JSON into semantic hops with bulk-prefetched object data.

**Tech Stack:** D3.js v7, TypeScript, esbuild, HTMX, Django templates, Django REST Framework

**Spec:** `docs/superpowers/specs/2026-03-18-fiber-circuit-trace-view-design.md`

**Security note:** All dynamic text rendered via D3 uses `.text()` (safe, auto-escaped). Sidebar content is server-rendered Django templates. Breadcrumb updates use `textContent` or D3 `.text()`, never raw HTML insertion with user data.

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `netbox_fms/templates/netbox_fms/fibercircuitpath.html` | Detail page template with tabs (Details + Trace) |
| `netbox_fms/templates/netbox_fms/fibercircuitpath_trace_tab.html` | Trace tab content: D3 canvas + sidebar flex layout |
| `netbox_fms/templates/netbox_fms/htmx/trace_device_detail.html` | Sidebar partial for device/closure nodes |
| `netbox_fms/templates/netbox_fms/htmx/trace_cable_detail.html` | Sidebar partial for cable segments |
| `netbox_fms/templates/netbox_fms/htmx/trace_port_detail.html` | Sidebar partial for port pairs |
| `netbox_fms/templates/netbox_fms/htmx/trace_splice_detail.html` | Sidebar partial for splice entries |
| `netbox_fms/trace_hops.py` | Trace-to-hops transformation with bulk prefetch |
| `netbox_fms/static/netbox_fms/src/trace-types.ts` | TypeScript interfaces for trace API data |
| `netbox_fms/static/netbox_fms/src/trace-renderer.ts` | D3 SVG rendering: nodes, edges, zoom transitions |
| `netbox_fms/static/netbox_fms/src/trace-view.ts` | Entry point: init canvas, wire HTMX sidebar |
| `tests/test_trace_hops.py` | Unit tests for trace-to-hops transformation |
| `tests/test_trace_view.py` | Tests for trace API endpoint and HTMX views |

### Modified Files
| File | Change |
|------|--------|
| `netbox_fms/views.py` | Add FiberCircuitPath CRUD views + TraceDetailView |
| `netbox_fms/urls.py` | Add FiberCircuitPath CRUD routes + HTMX trace-detail route |
| `netbox_fms/filters.py` | Add FiberCircuitPathFilterSet |
| `netbox_fms/forms.py` | Add FiberCircuitPathForm, FiberCircuitPathFilterForm |
| `netbox_fms/tables.py` | Add FiberCircuitPathTable |
| `netbox_fms/api/views.py` | Add `@action("trace")` + filterset_class to FiberCircuitPathViewSet |
| `netbox_fms/static/netbox_fms/bundle.cjs` | Multi-entry build config |
| `netbox_fms/templates/netbox_fms/fibercircuit.html` | Add "Trace" link per path row |

---

## Task 1: FiberCircuitPath FilterSet & Forms (Prerequisite)

**Files:**
- Modify: `netbox_fms/filters.py`
- Modify: `netbox_fms/forms.py`
- Modify: `netbox_fms/tables.py`

- [ ] **Step 1: Add FiberCircuitPathFilterSet to filters.py**

Add after the existing `FiberCircuitFilterSet`:

```python
class FiberCircuitPathFilterSet(NetBoxModelFilterSet):
    circuit_id = django_filters.ModelMultipleChoiceFilter(
        queryset=FiberCircuit.objects.all(),
        field_name="circuit",
        label=_("Circuit (ID)"),
    )
    is_complete = django_filters.BooleanFilter()

    class Meta:
        model = FiberCircuitPath
        fields = ("id", "circuit", "position", "is_complete", "wavelength_nm")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            models.Q(circuit__name__icontains=value) | models.Q(circuit__cid__icontains=value)
        )
```

Import `FiberCircuitPath` at the top if not already imported.

- [ ] **Step 2: Add FiberCircuitPathForm to forms.py**

```python
class FiberCircuitPathForm(NetBoxModelForm):
    circuit = DynamicModelChoiceField(
        queryset=FiberCircuit.objects.all(),
        label=_("Circuit"),
    )

    fieldsets = (
        FieldSet("circuit", "position", "origin", "destination", name=_("Path")),
        FieldSet("calculated_loss_db", "actual_loss_db", "wavelength_nm", name=_("Optical Parameters")),
        FieldSet("tags", name=_("Additional")),
    )

    class Meta:
        model = FiberCircuitPath
        fields = (
            "circuit", "position", "origin", "destination",
            "calculated_loss_db", "actual_loss_db", "wavelength_nm", "tags",
        )


class FiberCircuitPathFilterForm(NetBoxModelFilterSetForm):
    model = FiberCircuitPath
    circuit_id = DynamicModelChoiceField(
        queryset=FiberCircuit.objects.all(),
        required=False,
        label=_("Circuit"),
    )
    is_complete = forms.NullBooleanField(required=False, label=_("Complete"))
```

- [ ] **Step 3: Add FiberCircuitPathTable to tables.py**

```python
class FiberCircuitPathTable(NetBoxTable):
    circuit = tables.Column(linkify=True)
    position = tables.Column()
    origin = tables.Column(linkify=True)
    destination = tables.Column(linkify=True)
    is_complete = columns.BooleanColumn()

    class Meta(NetBoxTable.Meta):
        model = FiberCircuitPath
        fields = (
            "pk", "id", "circuit", "position", "origin", "destination",
            "is_complete", "calculated_loss_db", "actual_loss_db", "wavelength_nm",
        )
        default_columns = ("circuit", "position", "origin", "destination", "is_complete")
```

- [ ] **Step 4: Verify imports compile**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.filters import FiberCircuitPathFilterSet; from netbox_fms.forms import FiberCircuitPathForm, FiberCircuitPathFilterForm; from netbox_fms.tables import FiberCircuitPathTable"`

Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/filters.py netbox_fms/forms.py netbox_fms/tables.py
git commit -m "feat: add FiberCircuitPath filterset, forms, and table"
```

---

## Task 2: FiberCircuitPath CRUD Views, URLs & Template (Prerequisite)

**Files:**
- Modify: `netbox_fms/views.py`
- Modify: `netbox_fms/urls.py`
- Create: `netbox_fms/templates/netbox_fms/fibercircuitpath.html`

- [ ] **Step 1: Add views to views.py**

Add after `FiberCircuitDeleteView`:

```python
class FiberCircuitPathListView(generic.ObjectListView):
    queryset = FiberCircuitPath.objects.select_related("circuit", "origin", "destination")
    table = FiberCircuitPathTable
    filterset = FiberCircuitPathFilterSet
    filterset_form = FiberCircuitPathFilterForm


class FiberCircuitPathView(generic.ObjectView):
    queryset = FiberCircuitPath.objects.select_related("circuit", "origin", "destination")


class FiberCircuitPathEditView(generic.ObjectEditView):
    queryset = FiberCircuitPath.objects.all()
    form = FiberCircuitPathForm


class FiberCircuitPathDeleteView(generic.ObjectDeleteView):
    queryset = FiberCircuitPath.objects.all()
```

Add the necessary imports at the top: `FiberCircuitPathFilterSet`, `FiberCircuitPathFilterForm`, `FiberCircuitPathForm`, `FiberCircuitPathTable`.

- [ ] **Step 2: Add URL patterns to urls.py**

Add in the urlpatterns list, following the existing convention:

```python
# FiberCircuitPath
path("fiber-circuit-paths/", views.FiberCircuitPathListView.as_view(), name="fibercircuitpath_list"),
path("fiber-circuit-paths/add/", views.FiberCircuitPathEditView.as_view(), name="fibercircuitpath_add"),
path("fiber-circuit-paths/<int:pk>/", include(get_model_urls("netbox_fms", "fibercircuitpath"))),
path("fiber-circuit-paths/<int:pk>/", views.FiberCircuitPathView.as_view(), name="fibercircuitpath"),
path("fiber-circuit-paths/<int:pk>/edit/", views.FiberCircuitPathEditView.as_view(), name="fibercircuitpath_edit"),
path("fiber-circuit-paths/<int:pk>/delete/", views.FiberCircuitPathDeleteView.as_view(), name="fibercircuitpath_delete"),
```

- [ ] **Step 3: Create detail template**

Create `netbox_fms/templates/netbox_fms/fibercircuitpath.html`:

```django
{% extends 'generic/object.html' %}
{% load helpers %}
{% load plugins %}
{% load i18n %}

{% block content %}
<div class="row mb-3">
    <div class="col col-md-6">
        <div class="card">
            <h5 class="card-header">{% trans "Fiber Circuit Path" %}</h5>
            <table class="table table-hover attr-table">
                <tr>
                    <th scope="row">{% trans "Circuit" %}</th>
                    <td>{{ object.circuit|linkify }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Position" %}</th>
                    <td>{{ object.position }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Origin" %}</th>
                    <td>{{ object.origin|linkify }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Destination" %}</th>
                    <td>{% if object.destination %}{{ object.destination|linkify }}{% else %}&mdash;{% endif %}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Complete" %}</th>
                    <td>{{ object.is_complete|yesno }}</td>
                </tr>
            </table>
        </div>
    </div>
    <div class="col col-md-6">
        <div class="card">
            <h5 class="card-header">{% trans "Optical Parameters" %}</h5>
            <table class="table table-hover attr-table">
                <tr>
                    <th scope="row">{% trans "Calculated Loss (dB)" %}</th>
                    <td>{% if object.calculated_loss_db is not None %}{{ object.calculated_loss_db }}{% else %}&mdash;{% endif %}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Actual Loss (dB)" %}</th>
                    <td>{% if object.actual_loss_db is not None %}{{ object.actual_loss_db }}{% else %}&mdash;{% endif %}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Wavelength (nm)" %}</th>
                    <td>{% if object.wavelength_nm %}{{ object.wavelength_nm }}{% else %}&mdash;{% endif %}</td>
                </tr>
            </table>
        </div>
    </div>
</div>
{% plugin_full_width_page object %}
{% endblock %}
```

- [ ] **Step 4: Verify the detail page loads**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.views import FiberCircuitPathView, FiberCircuitPathListView"`

Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/views.py netbox_fms/urls.py netbox_fms/templates/netbox_fms/fibercircuitpath.html
git commit -m "feat: add FiberCircuitPath CRUD views, URLs, and detail template"
```

---

## Task 3: Trace-to-Hops Transformation Engine

**Files:**
- Create: `netbox_fms/trace_hops.py`
- Create: `tests/test_trace_hops.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_trace_hops.py`:

```python
from django.test import TestCase
from dcim.models import (
    Cable, CableTermination, Device, DeviceRole, DeviceType,
    FrontPort, Manufacturer, Module, ModuleBay, ModuleType,
    PortMapping, RearPort, Site,
)

from netbox_fms.models import FiberCircuitPath, FiberCircuit, SplicePlan, SplicePlanEntry
from netbox_fms.trace_hops import build_hops


class TestBuildHops(TestCase):
    """Test trace-to-hops transformation."""

    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Test Site", slug="test-site")
        mfr = Manufacturer.objects.create(name="Mfr", slug="mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Dev", slug="dev")
        role = DeviceRole.objects.create(name="OLT", slug="olt")

        # Origin device
        cls.dev_a = Device.objects.create(name="OLT-01", site=site, device_type=dt, role=role)
        cls.fp_a = FrontPort.objects.create(device=cls.dev_a, name="FP-A", type="lc",
                                             rear_port=None)
        cls.rp_a = RearPort.objects.create(device=cls.dev_a, name="RP-A", type="lc", positions=1)
        PortMapping.objects.create(front_port=cls.fp_a, rear_port=cls.rp_a, rear_port_position=1)

        # Destination device
        cls.dev_b = Device.objects.create(name="ONT-01", site=site, device_type=dt, role=role)
        cls.fp_b = FrontPort.objects.create(device=cls.dev_b, name="FP-B", type="lc",
                                             rear_port=None)
        cls.rp_b = RearPort.objects.create(device=cls.dev_b, name="RP-B", type="lc", positions=1)
        PortMapping.objects.create(front_port=cls.fp_b, rear_port=cls.rp_b, rear_port_position=1)

        # Cable between A and B
        cls.cable = Cable.objects.create(label="Cable-001")
        CableTermination.objects.create(cable=cls.cable, cable_end="A",
                                         termination_type_id=cls._rp_ct_id(),
                                         termination_id=cls.rp_a.pk)
        CableTermination.objects.create(cable=cls.cable, cable_end="B",
                                         termination_type_id=cls._rp_ct_id(),
                                         termination_id=cls.rp_b.pk)

    @classmethod
    def _rp_ct_id(cls):
        from django.contrib.contenttypes.models import ContentType
        return ContentType.objects.get_for_model(RearPort).pk

    def test_simple_path_two_devices(self):
        """A -> cable -> B produces: device, cable, device."""
        path_entries = [
            {"type": "front_port", "id": self.fp_a.pk},
            {"type": "rear_port", "id": self.rp_a.pk},
            {"type": "cable", "id": self.cable.pk},
            {"type": "rear_port", "id": self.rp_b.pk},
            {"type": "front_port", "id": self.fp_b.pk},
        ]
        hops = build_hops(path_entries)

        assert len(hops) == 3
        assert hops[0]["type"] == "device"
        assert hops[0]["name"] == "OLT-01"
        assert "ports" in hops[0]
        assert hops[0]["ports"]["front_port"]["id"] == self.fp_a.pk

        assert hops[1]["type"] == "cable"
        assert hops[1]["label"] == "Cable-001"

        assert hops[2]["type"] == "device"
        assert hops[2]["name"] == "ONT-01"
        assert "ports" in hops[2]

    def test_empty_path(self):
        """Empty path list returns empty hops."""
        hops = build_hops([])
        assert hops == []

    def test_no_pending_device_id_in_output(self):
        """Internal _pending_device_id markers are cleaned up."""
        path_entries = [
            {"type": "front_port", "id": self.fp_a.pk},
            {"type": "rear_port", "id": self.rp_a.pk},
            {"type": "cable", "id": self.cable.pk},
            {"type": "rear_port", "id": self.rp_b.pk},
            {"type": "front_port", "id": self.fp_b.pk},
        ]
        hops = build_hops(path_entries)
        for h in hops:
            assert "_pending_device_id" not in h
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_trace_hops.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'netbox_fms.trace_hops'`

- [ ] **Step 3: Implement trace_hops.py**

Create `netbox_fms/trace_hops.py`:

```python
"""Transform flat trace path entries into semantic hop objects.

The trace engine (trace.py) produces a flat list of {"type": str, "id": int}
entries. This module groups them into device/cable hops suitable for the
trace visualization API.
"""

from dcim.models import Cable, FrontPort, RearPort
from django.db.models import Q

from .models import FiberStrand, SplicePlanEntry


def build_hops(path_entries):
    """Transform flat path entries into grouped hops.

    Args:
        path_entries: list of {"type": str, "id": int} dicts from trace.py

    Returns:
        list of hop dicts with type "device" or "cable"
    """
    if not path_entries:
        return []

    # Bulk prefetch all referenced objects
    fp_ids = [e["id"] for e in path_entries if e["type"] == "front_port"]
    rp_ids = [e["id"] for e in path_entries if e["type"] == "rear_port"]
    cable_ids = [e["id"] for e in path_entries if e["type"] == "cable"]
    splice_ids = [e["id"] for e in path_entries if e["type"] == "splice_entry"]

    fp_map = {}
    if fp_ids:
        fp_map = {
            fp.pk: fp
            for fp in FrontPort.objects.filter(pk__in=fp_ids).select_related(
                "device__role", "device__site"
            )
        }

    rp_map = {}
    if rp_ids:
        rp_map = {
            rp.pk: rp
            for rp in RearPort.objects.filter(pk__in=rp_ids).select_related(
                "device__role", "device__site"
            )
        }

    cable_map = {}
    if cable_ids:
        cable_map = {c.pk: c for c in Cable.objects.filter(pk__in=cable_ids)}

    splice_map = {}
    if splice_ids:
        splice_map = {
            se.pk: se
            for se in SplicePlanEntry.objects.filter(pk__in=splice_ids).select_related(
                "plan", "tray"
            )
        }

    # Prefetch strands for all FrontPorts in path
    strand_by_fp = {}
    if fp_ids:
        strands = FiberStrand.objects.filter(
            Q(front_port_a_id__in=fp_ids) | Q(front_port_b_id__in=fp_ids)
        ).select_related("fiber_cable__fiber_cable_type", "buffer_tube")
        for s in strands:
            if s.front_port_a_id:
                strand_by_fp[s.front_port_a_id] = s
            if s.front_port_b_id:
                strand_by_fp[s.front_port_b_id] = s

    hops = []
    i = 0

    while i < len(path_entries):
        entry = path_entries[i]

        if entry["type"] == "front_port":
            fp = fp_map.get(entry["id"])
            if not fp:
                i += 1
                continue
            device = fp.device

            if i + 1 < len(path_entries) and path_entries[i + 1]["type"] == "rear_port":
                rp = rp_map.get(path_entries[i + 1]["id"])

                # Check if closure completion (same device as previous hop)
                if hops and hops[-1].get("_pending_device_id") == device.pk:
                    closure_hop = hops[-1]
                    closure_hop["egress"] = {
                        "front_port": {"id": fp.pk, "name": fp.name},
                        "rear_port": {"id": rp.pk, "name": rp.name} if rp else None,
                    }
                    del closure_hop["_pending_device_id"]
                    i += 2
                    continue

                hop = _make_device_hop(device)
                hop["ports"] = {
                    "front_port": {"id": fp.pk, "name": fp.name},
                    "rear_port": {"id": rp.pk, "name": rp.name} if rp else None,
                }
                # Origin/destination hops get _pending_device_id set as a benign no-op;
                # only closures (where the device recurs) will trigger the completion logic above.
                hop["_pending_device_id"] = device.pk
                hops.append(hop)
                i += 2
            else:
                # Destination device (final front_port)
                hop = _make_device_hop(device)
                hop["ports"] = {
                    "front_port": {"id": fp.pk, "name": fp.name},
                }
                hops.append(hop)
                i += 1

        elif entry["type"] == "cable":
            cable = cable_map.get(entry["id"])
            prev_fp_id = _get_last_front_port_id(hops)
            strand = strand_by_fp.get(prev_fp_id)

            hop = {
                "type": "cable",
                "id": cable.pk if cable else entry["id"],
                "label": (cable.label or f"Cable #{cable.pk}") if cable else f"Cable #{entry['id']}",
            }
            if strand:
                fc = strand.fiber_cable
                fct = fc.fiber_cable_type if fc else None
                hop["fiber_type"] = fct.get_fiber_type_display() if fct else None
                hop["strand_count"] = fct.strand_count if fct else None
                hop["strand_position"] = strand.position
                hop["strand_color"] = strand.color
                hop["tube_name"] = strand.buffer_tube.name if strand.buffer_tube else None
                hop["tube_color"] = strand.buffer_tube.color if strand.buffer_tube else None
                hop["fiber_cable_id"] = fc.pk if fc else None
                hop["fiber_cable_url"] = fc.get_absolute_url() if fc else None
            hops.append(hop)
            i += 1

        elif entry["type"] == "rear_port":
            rp = rp_map.get(entry["id"])
            if not rp:
                i += 1
                continue
            device = rp.device

            if i + 1 < len(path_entries) and path_entries[i + 1]["type"] == "front_port":
                fp = fp_map.get(path_entries[i + 1]["id"])
                hop = _make_device_hop(device)
                hop["ingress"] = {
                    "rear_port": {"id": rp.pk, "name": rp.name},
                    "front_port": {"id": fp.pk, "name": fp.name} if fp else None,
                }
                hop["_pending_device_id"] = device.pk
                hops.append(hop)
                i += 2
            else:
                i += 1

        elif entry["type"] == "splice_entry":
            se = splice_map.get(entry["id"])
            if se:
                for h in reversed(hops):
                    if h["type"] == "device":
                        h["splice"] = {
                            "id": se.pk,
                            "plan_name": se.plan.name,
                            "tray": se.tray.name if se.tray else None,
                            "is_express": se.is_express,
                        }
                        break
            i += 1

        else:
            i += 1

    # Clean up internal markers
    for h in hops:
        h.pop("_pending_device_id", None)

    return hops


def _make_device_hop(device):
    """Create a base device hop dict."""
    return {
        "type": "device",
        "id": device.pk,
        "name": device.name,
        "role": device.role.name if device.role else None,
        "site": device.site.name if device.site else None,
        "url": device.get_absolute_url(),
    }


def _get_last_front_port_id(hops):
    """Extract the last FrontPort ID from the hops list."""
    for h in reversed(hops):
        if h["type"] == "device":
            if "egress" in h and h["egress"].get("front_port"):
                return h["egress"]["front_port"]["id"]
            if "ingress" in h and h["ingress"].get("front_port"):
                return h["ingress"]["front_port"]["id"]
            if "ports" in h and h["ports"].get("front_port"):
                return h["ports"]["front_port"]["id"]
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_trace_hops.py -v`

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/trace_hops.py tests/test_trace_hops.py
git commit -m "feat: add trace-to-hops transformation engine with bulk prefetch"
```

---

## Task 4: Trace API Endpoint

**Files:**
- Modify: `netbox_fms/api/views.py`
- Create: `tests/test_trace_view.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_trace_view.py`:

```python
from django.test import TestCase
from rest_framework.test import APIClient

from netbox_fms.models import FiberCircuit, FiberCircuitPath


class TestTraceAction(TestCase):
    @classmethod
    def setUpTestData(cls):
        from dcim.models import Device, DeviceRole, DeviceType, FrontPort, Manufacturer, RearPort, Site

        site = Site.objects.create(name="Trace Site", slug="trace-site")
        mfr = Manufacturer.objects.create(name="Trace Mfr", slug="trace-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Dev", slug="trace-dev")
        role = DeviceRole.objects.create(name="Trace Role", slug="trace-role")
        dev = Device.objects.create(name="Dev-T", site=site, device_type=dt, role=role)

        cls.fp = FrontPort.objects.create(device=dev, name="FP-T", type="lc", rear_port=None)

        cls.circuit = FiberCircuit.objects.create(name="Test Circuit", strand_count=1)
        cls.path = FiberCircuitPath.objects.create(
            circuit=cls.circuit,
            position=1,
            origin=cls.fp,
            path=[{"type": "front_port", "id": cls.fp.pk}],
            is_complete=False,
        )

    def setUp(self):
        from django.contrib.auth import get_user_model

        user_model = get_user_model()
        self.user = user_model.objects.create_superuser("traceadmin", "t@t.com", "password")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_trace_action_returns_hops(self):
        url = f"/api/plugins/fms/fiber-circuit-paths/{self.path.pk}/trace/"
        resp = self.client.get(url)
        assert resp.status_code == 200, resp.content
        data = resp.json()
        assert "hops" in data
        assert "circuit_name" in data
        assert data["circuit_name"] == "Test Circuit"
        assert data["is_complete"] is False
        assert len(data["hops"]) >= 1

    def test_trace_action_404_invalid_id(self):
        url = "/api/plugins/fms/fiber-circuit-paths/99999/trace/"
        resp = self.client.get(url)
        assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_trace_view.py -v`

Expected: FAIL (no `trace` action exists yet).

- [ ] **Step 3: Add @action("trace") to FiberCircuitPathViewSet**

In `netbox_fms/api/views.py`, modify `FiberCircuitPathViewSet`:

```python
from rest_framework.decorators import action
from rest_framework.response import Response

from ..filters import FiberCircuitPathFilterSet
from ..trace_hops import build_hops


class FiberCircuitPathViewSet(NetBoxModelViewSet):
    queryset = FiberCircuitPath.objects.prefetch_related("tags")
    serializer_class = FiberCircuitPathSerializer
    filterset_class = FiberCircuitPathFilterSet

    @action(detail=True, methods=["get"], url_path="trace")
    def trace(self, request, pk=None):
        path_obj = self.get_object()
        hops = build_hops(path_obj.path)
        return Response({
            "circuit_id": path_obj.circuit_id,
            "circuit_name": path_obj.circuit.name,
            "circuit_url": path_obj.circuit.get_absolute_url(),
            "path_position": path_obj.position,
            "is_complete": path_obj.is_complete,
            "total_calculated_loss_db": str(path_obj.calculated_loss_db) if path_obj.calculated_loss_db else None,
            "total_actual_loss_db": str(path_obj.actual_loss_db) if path_obj.actual_loss_db else None,
            "wavelength_nm": path_obj.wavelength_nm,
            "hops": hops,
        })
```

Add `FiberCircuitPathFilterSet` import at the top.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_trace_view.py -v`

Expected: All 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/api/views.py tests/test_trace_view.py
git commit -m "feat: add trace API endpoint on FiberCircuitPathViewSet"
```

---

## Task 5: HTMX Trace Detail View & Templates

**Files:**
- Modify: `netbox_fms/views.py`
- Modify: `netbox_fms/urls.py`
- Create: `netbox_fms/templates/netbox_fms/htmx/trace_device_detail.html`
- Create: `netbox_fms/templates/netbox_fms/htmx/trace_cable_detail.html`
- Create: `netbox_fms/templates/netbox_fms/htmx/trace_port_detail.html`
- Create: `netbox_fms/templates/netbox_fms/htmx/trace_splice_detail.html`

- [ ] **Step 1: Add TraceDetailView to views.py**

```python
from django.views import View
from django.shortcuts import get_object_or_404, render
from django.http import HttpResponse
from dcim.models import Cable, Device, FrontPort

from .models import FiberCircuitPath, SplicePlan, SplicePlanEntry


class TraceDetailView(LoginRequiredMixin, View):
    """HTMX partial view for trace sidebar detail panels."""

    def get(self, request, pk, node_type, object_id):
        if not request.user.has_perm("netbox_fms.view_fibercircuitpath"):
            return HttpResponse("Permission denied", status=403)

        path_obj = get_object_or_404(FiberCircuitPath, pk=pk)

        if node_type == "device":
            device = get_object_or_404(Device, pk=object_id)
            has_splice_plans = SplicePlan.objects.filter(closure=device).exists()
            return render(request, "netbox_fms/htmx/trace_device_detail.html", {
                "device": device,
                "path": path_obj,
                "has_splice_plans": has_splice_plans,
            })

        elif node_type == "cable":
            cable = get_object_or_404(Cable, pk=object_id)
            from .models import FiberCable
            fiber_cable = FiberCable.objects.filter(cable=cable).select_related("fiber_cable_type").first()
            return render(request, "netbox_fms/htmx/trace_cable_detail.html", {
                "cable": cable,
                "fiber_cable": fiber_cable,
                "path": path_obj,
            })

        elif node_type == "port":
            port = get_object_or_404(FrontPort, pk=object_id)
            from .models import FiberStrand
            from django.db import models as db_models
            strand = FiberStrand.objects.filter(
                db_models.Q(front_port_a=port) | db_models.Q(front_port_b=port)
            ).select_related("buffer_tube").first()
            return render(request, "netbox_fms/htmx/trace_port_detail.html", {
                "port": port,
                "strand": strand,
                "path": path_obj,
            })

        elif node_type == "splice":
            splice_entry = get_object_or_404(
                SplicePlanEntry.objects.select_related("plan", "tray", "fiber_a", "fiber_b"),
                pk=object_id,
            )
            return render(request, "netbox_fms/htmx/trace_splice_detail.html", {
                "splice_entry": splice_entry,
                "path": path_obj,
            })

        return HttpResponse("Unknown node type", status=400)
```

- [ ] **Step 2: Add URL pattern to urls.py**

```python
# Trace detail HTMX
path(
    "fiber-circuit-paths/<int:pk>/trace-detail/<str:node_type>/<int:object_id>/",
    views.TraceDetailView.as_view(),
    name="fibercircuitpath_trace_detail",
),
```

- [ ] **Step 3: Create trace_device_detail.html**

```django
{% load i18n %}
{% load helpers %}
<div class="trace-detail-header">
    <button class="btn btn-sm btn-outline-secondary trace-back-btn" onclick="TraceView.deselectNode()">
        <i class="mdi mdi-arrow-left"></i> {% trans "Back" %}
    </button>
</div>
<div class="trace-detail-body">
    <h6>{{ device.name }}</h6>
    {% if device.role %}
    <span class="badge bg-secondary">{{ device.role }}</span>
    {% endif %}
    <table class="table table-sm trace-detail-table mt-3">
        <tr>
            <th>{% trans "Site" %}</th>
            <td>{% if device.site %}{{ device.site.name }}{% else %}&mdash;{% endif %}</td>
        </tr>
        <tr>
            <th>{% trans "Location" %}</th>
            <td>{% if device.location %}{{ device.location }}{% else %}&mdash;{% endif %}</td>
        </tr>
        <tr>
            <th>{% trans "Device Type" %}</th>
            <td>{{ device.device_type }}</td>
        </tr>
        <tr>
            <th>{% trans "Role" %}</th>
            <td>{% if device.role %}{{ device.role }}{% else %}&mdash;{% endif %}</td>
        </tr>
    </table>
    <div class="mt-3">
        <a href="{{ device.get_absolute_url }}" class="btn btn-sm btn-outline-primary">
            {% trans "View Device" %} <i class="mdi mdi-open-in-new"></i>
        </a>
        {% if has_splice_plans %}
        <a href="{{ device.get_absolute_url }}splice-editor/" class="btn btn-sm btn-outline-info">
            {% trans "Splice Editor" %} <i class="mdi mdi-open-in-new"></i>
        </a>
        {% endif %}
    </div>
    <div class="trace-loss-summary mt-4 pt-3 border-top">
        <small class="text-muted">
            {% trans "Path Loss" %}:
            {% if path.calculated_loss_db is not None %}{{ path.calculated_loss_db }} dB{% else %}&mdash;{% endif %}
            {% if path.wavelength_nm %}@ {{ path.wavelength_nm }} nm{% endif %}
            &middot;
            {% if path.is_complete %}{% trans "Complete" %}{% else %}{% trans "Incomplete" %}{% endif %}
        </small>
    </div>
</div>
```

- [ ] **Step 4: Create trace_cable_detail.html**

```django
{% load i18n %}
{% load helpers %}
<div class="trace-detail-header">
    <button class="btn btn-sm btn-outline-secondary trace-back-btn" onclick="TraceView.deselectNode()">
        <i class="mdi mdi-arrow-left"></i> {% trans "Back" %}
    </button>
</div>
<div class="trace-detail-body">
    <h6>{{ cable.label|default:cable }}</h6>
    <span class="badge bg-info">{% trans "Cable" %}</span>
    <table class="table table-sm trace-detail-table mt-3">
        <tr>
            <th>{% trans "Status" %}</th>
            <td>{{ cable.get_status_display }}</td>
        </tr>
        {% if fiber_cable %}
        <tr>
            <th>{% trans "Fiber Cable Type" %}</th>
            <td>{{ fiber_cable.fiber_cable_type }}</td>
        </tr>
        <tr>
            <th>{% trans "Fiber Type" %}</th>
            <td>{{ fiber_cable.fiber_cable_type.get_fiber_type_display }}</td>
        </tr>
        <tr>
            <th>{% trans "Strand Count" %}</th>
            <td>{{ fiber_cable.fiber_cable_type.strand_count }}F</td>
        </tr>
        {% endif %}
        {% if cable.length %}
        <tr>
            <th>{% trans "Length" %}</th>
            <td>{{ cable.length }} {{ cable.get_length_unit_display }}</td>
        </tr>
        {% endif %}
    </table>
    <div class="mt-3">
        <a href="{{ cable.get_absolute_url }}" class="btn btn-sm btn-outline-primary">
            {% trans "View Cable" %} <i class="mdi mdi-open-in-new"></i>
        </a>
        {% if fiber_cable %}
        <a href="{{ fiber_cable.get_absolute_url }}" class="btn btn-sm btn-outline-primary">
            {% trans "View Fiber Cable" %} <i class="mdi mdi-open-in-new"></i>
        </a>
        {% endif %}
    </div>
    <div class="trace-loss-summary mt-4 pt-3 border-top">
        <small class="text-muted">
            {% trans "Path Loss" %}:
            {% if path.calculated_loss_db is not None %}{{ path.calculated_loss_db }} dB{% else %}&mdash;{% endif %}
            {% if path.wavelength_nm %}@ {{ path.wavelength_nm }} nm{% endif %}
            &middot;
            {% if path.is_complete %}{% trans "Complete" %}{% else %}{% trans "Incomplete" %}{% endif %}
        </small>
    </div>
</div>
```

- [ ] **Step 5: Create trace_port_detail.html**

```django
{% load i18n %}
{% load helpers %}
<div class="trace-detail-header">
    <button class="btn btn-sm btn-outline-secondary trace-back-btn" onclick="TraceView.deselectNode()">
        <i class="mdi mdi-arrow-left"></i> {% trans "Back" %}
    </button>
</div>
<div class="trace-detail-body">
    <h6>{{ port.name }}</h6>
    <span class="badge bg-success">{% trans "Port" %}</span>
    <table class="table table-sm trace-detail-table mt-3">
        <tr>
            <th>{% trans "Device" %}</th>
            <td>{{ port.device }}</td>
        </tr>
        <tr>
            <th>{% trans "Type" %}</th>
            <td>{{ port.get_type_display }}</td>
        </tr>
        {% if strand %}
        <tr>
            <th>{% trans "Strand Position" %}</th>
            <td>{{ strand.position }}</td>
        </tr>
        <tr>
            <th>{% trans "Strand Color" %}</th>
            <td>
                <span style="display:inline-block;width:12px;height:12px;background:#{{ strand.color }};border:1px solid #ccc;border-radius:2px;vertical-align:middle;"></span>
                {{ strand.color }}
            </td>
        </tr>
        {% if strand.buffer_tube %}
        <tr>
            <th>{% trans "Tube" %}</th>
            <td>
                <span style="display:inline-block;width:12px;height:12px;background:#{{ strand.buffer_tube.color }};border:1px solid #ccc;border-radius:2px;vertical-align:middle;"></span>
                {{ strand.buffer_tube.name }}
            </td>
        </tr>
        {% endif %}
        {% endif %}
    </table>
    <div class="mt-3">
        <a href="{{ port.get_absolute_url }}" class="btn btn-sm btn-outline-primary">
            {% trans "View Port" %} <i class="mdi mdi-open-in-new"></i>
        </a>
    </div>
</div>
```

- [ ] **Step 6: Create trace_splice_detail.html**

```django
{% load i18n %}
{% load helpers %}
<div class="trace-detail-header">
    <button class="btn btn-sm btn-outline-secondary trace-back-btn" onclick="TraceView.deselectNode()">
        <i class="mdi mdi-arrow-left"></i> {% trans "Back" %}
    </button>
</div>
<div class="trace-detail-body">
    <h6>{{ splice_entry.plan.name }}</h6>
    <span class="badge bg-warning text-dark">{% trans "Splice" %}</span>
    <table class="table table-sm trace-detail-table mt-3">
        <tr>
            <th>{% trans "Plan Status" %}</th>
            <td>{{ splice_entry.plan.get_status_display }}</td>
        </tr>
        {% if splice_entry.tray %}
        <tr>
            <th>{% trans "Tray" %}</th>
            <td>{{ splice_entry.tray.name }}</td>
        </tr>
        {% endif %}
        <tr>
            <th>{% trans "Fiber A" %}</th>
            <td>{{ splice_entry.fiber_a }}</td>
        </tr>
        <tr>
            <th>{% trans "Fiber B" %}</th>
            <td>{{ splice_entry.fiber_b }}</td>
        </tr>
        <tr>
            <th>{% trans "Type" %}</th>
            <td>{% if splice_entry.is_express %}{% trans "Express" %}{% else %}{% trans "Fusion" %}{% endif %}</td>
        </tr>
    </table>
    <div class="mt-3">
        <a href="{{ splice_entry.plan.get_absolute_url }}" class="btn btn-sm btn-outline-primary">
            {% trans "View Splice Plan" %} <i class="mdi mdi-open-in-new"></i>
        </a>
    </div>
</div>
```

- [ ] **Step 7: Verify imports compile**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.views import TraceDetailView"`

Expected: No errors.

- [ ] **Step 8: Commit**

```bash
git add netbox_fms/views.py netbox_fms/urls.py netbox_fms/templates/netbox_fms/htmx/trace_*.html
git commit -m "feat: add HTMX trace detail view and sidebar templates"
```

---

## Task 6: Trace Tab Template & Page Integration

**Files:**
- Create: `netbox_fms/templates/netbox_fms/fibercircuitpath_trace_tab.html`
- Modify: `netbox_fms/templates/netbox_fms/fibercircuitpath.html`
- Modify: `netbox_fms/templates/netbox_fms/fibercircuit.html`

- [ ] **Step 1: Create trace tab template**

Create `netbox_fms/templates/netbox_fms/fibercircuitpath_trace_tab.html`:

```django
{% load i18n %}
{% load static %}
<style>
.trace-container {
    display: flex;
    min-height: 500px;
    border: 1px solid var(--bs-border-color);
    border-radius: 0.375rem;
    overflow: hidden;
}
.trace-canvas {
    flex: 1;
    position: relative;
    overflow-y: auto;
}
.trace-sidebar {
    width: 340px;
    min-width: 340px;
    border-left: 1px solid var(--bs-border-color);
    display: flex;
    flex-direction: column;
    background: var(--bs-body-bg);
}
.trace-sidebar-empty {
    display: flex;
    align-items: center;
    justify-content: center;
    flex: 1;
    color: var(--bs-secondary-color);
}
.trace-detail-header {
    padding: 0.75rem;
    border-bottom: 1px solid var(--bs-border-color);
    flex-shrink: 0;
}
.trace-detail-body {
    flex: 1;
    overflow-y: auto;
    padding: 1rem;
}
.trace-detail-table th {
    width: 40%;
    font-weight: 600;
    font-size: 0.85rem;
}
.trace-detail-table td {
    font-size: 0.85rem;
}
.trace-loss-summary {
    flex-shrink: 0;
    padding: 0.75rem;
}
.trace-breadcrumb {
    padding: 0.5rem 1rem;
    font-size: 0.85rem;
    color: var(--bs-secondary-color);
    border-bottom: 1px solid var(--bs-border-color);
}
.trace-breadcrumb a {
    color: var(--bs-link-color);
    text-decoration: none;
}
.trace-loading {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 300px;
}
</style>

<div class="trace-breadcrumb" id="trace-breadcrumb">
    <a href="{{ object.circuit.get_absolute_url }}">{{ object.circuit.name }}</a>
    &rsaquo; {% trans "Path" %} #{{ object.position }}
</div>
<div class="trace-container">
    <div class="trace-canvas" id="trace-canvas-container">
        <div class="trace-loading">
            <div class="spinner-border text-secondary" role="status">
                <span class="visually-hidden">{% trans "Loading..." %}</span>
            </div>
        </div>
    </div>
    <div class="trace-sidebar" id="trace-sidebar">
        <div id="trace-detail-panel">
            <div class="trace-sidebar-empty">
                <p>{% trans "Click a node to view details" %}</p>
            </div>
        </div>
    </div>
</div>

<script>
window.TRACE_VIEW_CONFIG = {
    pathId: {{ object.pk }},
    traceUrl: '/api/plugins/fms/fiber-circuit-paths/{{ object.pk }}/trace/',
    detailBaseUrl: '/plugins/netbox-fms/fiber-circuit-paths/{{ object.pk }}/trace-detail/',
    circuitName: '{{ object.circuit.name|escapejs }}',
    pathPosition: {{ object.position }},
};
</script>
```

- [ ] **Step 2: Update fibercircuitpath.html to add Trace tab**

Replace the entire content of `netbox_fms/templates/netbox_fms/fibercircuitpath.html`:

```django
{% extends 'generic/object.html' %}
{% load helpers %}
{% load plugins %}
{% load i18n %}
{% load static %}

{% block content %}
<ul class="nav nav-tabs mb-3" role="tablist">
    <li class="nav-item" role="presentation">
        <button class="nav-link active" data-bs-toggle="tab" data-bs-target="#tab-details" type="button" role="tab">
            {% trans "Details" %}
        </button>
    </li>
    <li class="nav-item" role="presentation">
        <button class="nav-link" data-bs-toggle="tab" data-bs-target="#tab-trace" type="button" role="tab" id="trace-tab-btn">
            {% trans "Trace" %}
        </button>
    </li>
</ul>

<div class="tab-content">
    <div class="tab-pane fade show active" id="tab-details" role="tabpanel">
        <div class="row mb-3">
            <div class="col col-md-6">
                <div class="card">
                    <h5 class="card-header">{% trans "Fiber Circuit Path" %}</h5>
                    <table class="table table-hover attr-table">
                        <tr>
                            <th scope="row">{% trans "Circuit" %}</th>
                            <td>{{ object.circuit|linkify }}</td>
                        </tr>
                        <tr>
                            <th scope="row">{% trans "Position" %}</th>
                            <td>{{ object.position }}</td>
                        </tr>
                        <tr>
                            <th scope="row">{% trans "Origin" %}</th>
                            <td>{{ object.origin|linkify }}</td>
                        </tr>
                        <tr>
                            <th scope="row">{% trans "Destination" %}</th>
                            <td>{% if object.destination %}{{ object.destination|linkify }}{% else %}&mdash;{% endif %}</td>
                        </tr>
                        <tr>
                            <th scope="row">{% trans "Complete" %}</th>
                            <td>{{ object.is_complete|yesno }}</td>
                        </tr>
                    </table>
                </div>
            </div>
            <div class="col col-md-6">
                <div class="card">
                    <h5 class="card-header">{% trans "Optical Parameters" %}</h5>
                    <table class="table table-hover attr-table">
                        <tr>
                            <th scope="row">{% trans "Calculated Loss (dB)" %}</th>
                            <td>{% if object.calculated_loss_db is not None %}{{ object.calculated_loss_db }}{% else %}&mdash;{% endif %}</td>
                        </tr>
                        <tr>
                            <th scope="row">{% trans "Actual Loss (dB)" %}</th>
                            <td>{% if object.actual_loss_db is not None %}{{ object.actual_loss_db }}{% else %}&mdash;{% endif %}</td>
                        </tr>
                        <tr>
                            <th scope="row">{% trans "Wavelength (nm)" %}</th>
                            <td>{% if object.wavelength_nm %}{{ object.wavelength_nm }}{% else %}&mdash;{% endif %}</td>
                        </tr>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <div class="tab-pane fade" id="tab-trace" role="tabpanel">
        {% include "netbox_fms/fibercircuitpath_trace_tab.html" %}
    </div>
</div>

{% plugin_full_width_page object %}
{% endblock %}

{% block javascript %}
{{ block.super }}
<script src="https://d3js.org/d3.v7.min.js"></script>
<script src="{% static 'netbox_fms/dist/trace-view.min.js' %}"></script>
{% endblock %}
```

- [ ] **Step 3: Add Trace link to fibercircuit.html paths table**

In `netbox_fms/templates/netbox_fms/fibercircuit.html`, add a "Trace" column header after `Wavelength (nm)`:

```django
<th>{% trans "Trace" %}</th>
```

And in each path row, add a cell after the wavelength cell:

```django
<td><a href="{{ path.get_absolute_url }}#trace" class="btn btn-sm btn-outline-secondary">{% trans "Trace" %}</a></td>
```

- [ ] **Step 4: Verify templates are loadable**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from django.template.loader import get_template; get_template('netbox_fms/fibercircuitpath.html'); get_template('netbox_fms/fibercircuitpath_trace_tab.html'); print('OK')"`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/templates/netbox_fms/fibercircuitpath.html netbox_fms/templates/netbox_fms/fibercircuitpath_trace_tab.html netbox_fms/templates/netbox_fms/fibercircuit.html
git commit -m "feat: add trace tab to FiberCircuitPath detail page with sidebar layout"
```

---

## Task 7: esbuild Multi-Entry Config

**Files:**
- Modify: `netbox_fms/static/netbox_fms/bundle.cjs`

- [ ] **Step 1: Update bundle.cjs for multi-entry**

Replace the contents of `bundle.cjs`:

```javascript
const esbuild = require('esbuild');
const path = require('path');

const isWatch = process.argv.includes('--watch');

const shared = {
  bundle: true,
  minify: !isWatch,
  sourcemap: 'linked',
  target: 'es2016',
  external: ['d3'],
  format: 'iife',
  logLevel: 'info',
};

const entries = [
  {
    entryPoints: [path.join(__dirname, 'src', 'splice-editor.ts')],
    globalName: 'SpliceEditor',
    outfile: path.join(__dirname, 'dist', 'splice-editor.min.js'),
  },
  {
    entryPoints: [path.join(__dirname, 'src', 'trace-view.ts')],
    globalName: 'TraceView',
    outfile: path.join(__dirname, 'dist', 'trace-view.min.js'),
  },
];

async function main() {
  if (isWatch) {
    for (const entry of entries) {
      const ctx = await esbuild.context({ ...shared, ...entry });
      await ctx.watch();
    }
    console.log('Watching for changes...');
  } else {
    await Promise.all(entries.map((entry) => esbuild.build({ ...shared, ...entry })));
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
```

- [ ] **Step 2: Verify existing splice-editor still builds**

Run: `cd /opt/netbox-fms/netbox_fms/static/netbox_fms && node bundle.cjs`

Expected: Build succeeds for `splice-editor.min.js`. The `trace-view` entry will fail until we create the TypeScript source — that is expected.

- [ ] **Step 3: Commit**

```bash
git add netbox_fms/static/netbox_fms/bundle.cjs
git commit -m "chore: update esbuild config for multi-entry (splice-editor + trace-view)"
```

---

## Task 8: TypeScript Interfaces & Entry Point

**Files:**
- Create: `netbox_fms/static/netbox_fms/src/trace-types.ts`
- Create: `netbox_fms/static/netbox_fms/src/trace-view.ts`

- [ ] **Step 1: Create trace-types.ts**

```typescript
/** Configuration injected by Django template via window.TRACE_VIEW_CONFIG. */
export interface TraceConfig {
  pathId: number;
  traceUrl: string;
  detailBaseUrl: string;
  circuitName: string;
  pathPosition: number;
}

/** Port reference in a device hop. */
export interface PortRef {
  id: number;
  name: string;
}

/** Port pair (front_port + rear_port). */
export interface PortPair {
  front_port: PortRef;
  rear_port?: PortRef | null;
}

/** Splice info attached to a closure hop. */
export interface SpliceInfo {
  id: number;
  plan_name: string;
  tray: string | null;
  is_express: boolean;
}

/** A device hop (endpoint or closure). */
export interface DeviceHop {
  type: 'device';
  id: number;
  name: string;
  role: string | null;
  site: string | null;
  url: string;
  ports?: PortPair;
  ingress?: PortPair;
  egress?: PortPair;
  splice?: SpliceInfo;
}

/** A cable hop. */
export interface CableHop {
  type: 'cable';
  id: number;
  label: string;
  fiber_type?: string | null;
  strand_count?: number | null;
  strand_position?: number | null;
  strand_color?: string | null;
  tube_name?: string | null;
  tube_color?: string | null;
  fiber_cable_id?: number | null;
  fiber_cable_url?: string | null;
}

/** Union of all hop types. */
export type Hop = DeviceHop | CableHop;

/** Response from the trace API endpoint. */
export interface TraceResponse {
  circuit_id: number;
  circuit_name: string;
  circuit_url: string;
  path_position: number;
  is_complete: boolean;
  total_calculated_loss_db: string | null;
  total_actual_loss_db: string | null;
  wavelength_nm: number | null;
  hops: Hop[];
}
```

- [ ] **Step 2: Create trace-view.ts entry point**

```typescript
import type { TraceConfig, TraceResponse } from './trace-types';
import { TraceRenderer } from './trace-renderer';

declare const d3: typeof import('d3');
declare const htmx: any;

const config = (window as unknown as { TRACE_VIEW_CONFIG?: TraceConfig }).TRACE_VIEW_CONFIG;
if (config) {
  initTraceView(config);
}

let activeRenderer: any = null;

async function initTraceView(config: TraceConfig): Promise<void> {
  const container = document.getElementById('trace-canvas-container');
  if (!container) return;

  // Wait for tab activation before initializing
  const tabBtn = document.getElementById('trace-tab-btn');
  if (tabBtn) {
    tabBtn.addEventListener('shown.bs.tab', () => loadAndRender(), { once: true });
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

      // Clear loading spinner
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

      // Initialize D3 renderer (Task 9)
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
  // Dispatch custom event for renderer to handle deselection
  document.dispatchEvent(new CustomEvent('trace:deselect'));
}
```

- [ ] **Step 3: Build to verify TypeScript compiles**

Run: `cd /opt/netbox-fms/netbox_fms/static/netbox_fms && node bundle.cjs 2>&1 || true`

Expected: `splice-editor.min.js` builds. `trace-view.min.js` may warn about missing `trace-renderer` module — that is expected and will be resolved in Task 9.

- [ ] **Step 4: Commit**

```bash
git add netbox_fms/static/netbox_fms/src/trace-types.ts netbox_fms/static/netbox_fms/src/trace-view.ts
git commit -m "feat: add TypeScript interfaces and entry point for trace view"
```

---

## Task 9: D3 Trace Renderer

**Files:**
- Create: `netbox_fms/static/netbox_fms/src/trace-renderer.ts`

This is the largest task. The renderer handles overview mode, node selection, zoom-in expansion with transitions, and HTMX sidebar wiring. See the spec for full UX details.

- [ ] **Step 1: Create trace-renderer.ts**

Create `netbox_fms/static/netbox_fms/src/trace-renderer.ts` with the full D3 rendering implementation. Key responsibilities:

- `computeLayout()` — position device nodes and cable edges vertically, with expanded heights for selected nodes
- `drawSvg()` — clear and redraw all SVG elements
- `drawDeviceNode()` — rounded rect with name, role, site; expanded view shows ports and splice info
- `drawCableEdge()` — vertical line with label badge; expanded view shows strand detail
- `selectNode(index)` — expand node, fade siblings, update breadcrumb, trigger HTMX detail load
- `deselect()` — restore overview, clear breadcrumb suffix, listen for `trace:deselect` custom event and Esc key

Layout constants: `NODE_WIDTH=220`, `NODE_HEIGHT=56`, `NODE_RX=8`, `EDGE_HEIGHT=80`, `TOP_PAD=30`. Expanded heights: endpoint=100, closure=160, cable=120.

All text rendering uses D3 `.text()` (auto-escaped, safe from XSS). Theme detection uses `document.body.getAttribute('data-bs-theme')`. HTMX interaction uses `htmx.ajax('GET', url, {target: '#trace-detail-panel'})`.

The full implementation follows the patterns established in the existing `renderer.ts` (splice editor) — D3 selections, theme-aware colors, cursor/hover states, click handlers with `event.stopPropagation()`.

- [ ] **Step 2: Build both bundles**

Run: `cd /opt/netbox-fms/netbox_fms/static/netbox_fms && node bundle.cjs`

Expected: Both `splice-editor.min.js` and `trace-view.min.js` produced in `dist/`.

- [ ] **Step 3: Commit**

```bash
git add netbox_fms/static/netbox_fms/src/trace-renderer.ts netbox_fms/static/netbox_fms/dist/trace-view.min.js netbox_fms/static/netbox_fms/dist/trace-view.min.js.map
git commit -m "feat: add D3 trace renderer with overview mode, zoom transitions, and node selection"
```

---

## Task 10: Final Integration & Lint

**Files:**
- All modified files

- [ ] **Step 1: Run all Python tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v`

Expected: All tests pass.

- [ ] **Step 2: Run linter**

Run: `ruff check --fix netbox_fms/ && ruff format netbox_fms/`

Expected: No errors (or auto-fixed).

- [ ] **Step 3: Verify all imports**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.models import *; from netbox_fms.forms import *; from netbox_fms.filters import *; from netbox_fms.views import *; from netbox_fms.trace_hops import build_hops; print('All imports OK')"`

Expected: `All imports OK`

- [ ] **Step 4: Rebuild TypeScript**

Run: `cd /opt/netbox-fms/netbox_fms/static/netbox_fms && node bundle.cjs`

Expected: Both bundles build cleanly.

- [ ] **Step 5: Commit any lint fixes**

```bash
git add -u
git commit -m "chore: lint fixes for trace view feature"
```
