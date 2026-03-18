# Fiber Circuit Path Trace View

**Date:** 2026-03-18
**Status:** Draft

## Summary

Interactive D3.js trace visualization for `FiberCircuitPath`, showing the end-to-end fiber route from origin to destination. Lives as a "Trace" tab on the FiberCircuitPath detail page. Uses a zoom-in/zoom-out interaction model: the overview shows the full device-level chain, clicking a node zooms in to reveal internal detail (ports, strands, splices) with smooth D3 transitions. A 340px HTMX-powered sidebar (modeled on netbox-pathways' map sidebar) displays contextual detail for the selected node.

The FiberCircuit detail page does **not** get its own trace diagram — its existing paths table already serves as the overview, with "Trace" links per path row.

## Prerequisites

The FiberCircuitPath model exists but has **no detail page yet** — no views, URLs, or templates. Before the trace tab can be added, the standard CRUD infrastructure must be created:

- `FiberCircuitPathView` (detail), `FiberCircuitPathListView`, `FiberCircuitPathEditView`, `FiberCircuitPathDeleteView` in `views.py`
- URL patterns in `urls.py` following the `plugins:netbox_fms:fibercircuitpath` convention
- `fibercircuitpath.html` base detail template
- `FiberCircuitPathFilterSet` in `filters.py` (also needed for the API viewset)

These are implementation prerequisites, not part of the trace feature itself, but must be built first.

## Architecture

### Two-State D3 Canvas

**Overview state (default):**
- Vertical top-to-bottom chain of device/closure nodes connected by cable edges
- Nodes are compact rounded rectangles showing device name, role (`device.role.name`), site
- Cable edges show cable label, strand count badge, fiber type
- Origin at top, destination at bottom
- Incomplete paths end with a dashed "incomplete" indicator
- Error state: if trace API returns an error, show centered error message in canvas
- Empty state: if path has no hops, show "No trace data available"
- Loading state: spinner while API call is in flight

**Zoomed-in state (on node click):**
- Clicked node expands in-place with `transition().duration(300)`
- Surrounding nodes scale down + reduce opacity, push apart to make room
- Expanded node reveals internal detail with staggered fade-in:
  - **Closure:** Ingress RearPort → FrontPort → splice entry → FrontPort → egress RearPort, with strand EIA-598 color dots
  - **End device:** Port assignment, connected strand detail
  - **Cable segment:** Strand position, EIA-598 color, fiber type
- Click background or "back" → reverse transition, node contracts, siblings restore
- Breadcrumb above canvas: `Circuit Name > Path #N > [Node Name]` — circuit name and path position come from the API response, last segment appears when zoomed

### Zoom Transition UX

- Hover: subtle glow/lift on nodes to signal clickability
- Selection: highlight ring on expanded node (consistent with pathways selection pattern)
- D3 transition and HTMX sidebar swap happen in parallel
- Stagger timing: node expansion (0-300ms), internal elements fade in (150-450ms)

### HTMX Detail Sidebar

**Layout:** Flex container inside a `.card`, D3 canvas `flex: 1`, sidebar 340px fixed width with left border.

**Sidebar CSS conventions (matching netbox-pathways):**
- `.trace-sidebar` — 340px width, `border-left: 1px solid var(--bs-border-color)`, `display: flex`, `flex-direction: column`
- `.trace-detail-body` — `flex: 1`, `overflow-y: auto`, scrollable content area
- `.trace-detail-table` — key-value pairs, same styling as pathways `.pw-detail-table`
- Back button at top with Esc key support to return to empty state

**Empty state:** "Click a node to view details" centered text.

**Detail state (swapped via HTMX on D3 click):**

D3 click handler calls `htmx.ajax('GET', url, {target: '#trace-detail-panel'})`. Each D3 node stores its detail URL in data.

Content varies by node type:

**Device (node_type=`device`):**
- Name, role, site, location
- Device type
- Cable count
- Links: "View Device"
- Additional for closures: "Splice Editor" link (shown if device has any SplicePlan)

**Cable Segment (node_type=`cable`):**
- Cable label, status
- Fiber cable type name, fiber type, strand count
- A-side / B-side device names
- Length (if recorded)
- Strand in use: position, EIA-598 color swatch, tube name
- Links: "View Cable", "View Fiber Cable"

**Port Pair (node_type=`port`):**
- Port name, device
- Strand position, EIA-598 color swatch
- Tube name/color (if applicable)
- Link: "View Port"

**Splice Entry (node_type=`splice`):**
- Splice plan name, status
- Tray (module) name
- Fiber A → Fiber B names
- Express vs fusion indicator
- Link: "View Splice Plan"

**Path Loss Summary (always visible at sidebar bottom when any node is selected):**
- Total path loss: `calculated_loss_db` / `actual_loss_db` (from FiberCircuitPath model)
- Wavelength (nm)
- Path status (complete / incomplete)

Note: per-segment loss is **out of scope** for this feature. The model stores only total path loss. Per-hop loss breakdown would require a loss calculation engine (future work).

### HTMX Detail Endpoint

**URL:** `GET /fiber-circuit-paths/{path_id}/trace-detail/{node_type}/{object_id}/`

**node_type values:** `device`, `cable`, `port`, `splice`

There is no separate "closure" node_type. The `device` template checks whether the device has any SplicePlan objects and conditionally shows the "Splice Editor" link. This keeps the URL scheme simple and avoids encoding domain knowledge into the URL.

**Permissions:** View requires `netbox_fms.view_fibercircuitpath`. The view inherits from `ObjectPermissionRequiredMixin` following existing patterns.

### Data Flow

**API endpoint:** `FiberCircuitPathViewSet.@action("trace")` — single call returns enriched trace JSON.

Input: the path's stored `path` JSONField (flat list from `trace.py`).

#### Trace-to-Hops Transformation Algorithm

The flat path from `trace.py` follows this repeating pattern:
```
front_port → rear_port → cable → rear_port → front_port [→ splice_entry → front_port → ...]
```

The `@action("trace")` view transforms this into semantic hops:

```python
def build_hops(path_entries):
    hops = []
    i = 0
    entries = path_entries  # list of {"type": str, "id": int}

    while i < len(entries):
        entry = entries[i]

        if entry["type"] == "front_port":
            fp = FrontPort.objects.select_related("device__role", "device__site").get(pk=entry["id"])
            device = fp.device

            # Look ahead: is there a rear_port next? (device with outgoing cable)
            # Or is this the final front_port? (destination)
            if i + 1 < len(entries) and entries[i + 1]["type"] == "rear_port":
                rp = RearPort.objects.get(pk=entries[i + 1]["id"])

                # Check if this device already appeared as the previous hop's device
                # If so, this is a closure (mid-path device with ingress + egress)
                if hops and hops[-1].get("_pending_device_id") == device.pk:
                    # Complete the closure hop: add egress ports
                    closure_hop = hops[-1]
                    closure_hop["egress"] = {
                        "front_port": {"id": fp.pk, "name": fp.name},
                        "rear_port": {"id": rp.pk, "name": rp.name},
                    }
                    del closure_hop["_pending_device_id"]
                    i += 2  # skip front_port + rear_port
                    continue

                # New device hop — could become a closure if we see it again
                hop = {
                    "type": "device",
                    "id": device.pk,
                    "name": device.name,
                    "role": device.role.name if device.role else None,
                    "site": device.site.name if device.site else None,
                    "url": device.get_absolute_url(),
                    "ports": {
                        "front_port": {"id": fp.pk, "name": fp.name},
                        "rear_port": {"id": rp.pk, "name": rp.name},
                    },
                    "_pending_device_id": device.pk,
                }
                hops.append(hop)
                i += 2  # skip front_port + rear_port
            else:
                # Final front_port — destination device
                hop = {
                    "type": "device",
                    "id": device.pk,
                    "name": device.name,
                    "role": device.role.name if device.role else None,
                    "site": device.site.name if device.site else None,
                    "url": device.get_absolute_url(),
                    "ports": {
                        "front_port": {"id": fp.pk, "name": fp.name},
                    },
                }
                hops.append(hop)
                i += 1

        elif entry["type"] == "cable":
            cable = Cable.objects.get(pk=entry["id"])
            # Resolve strand: find FiberStrand whose front_port_a or front_port_b
            # matches the previous hop's FrontPort
            prev_fp_id = _get_last_front_port_id(hops)
            strand = FiberStrand.objects.filter(
                Q(front_port_a_id=prev_fp_id) | Q(front_port_b_id=prev_fp_id)
            ).first()

            hop = {
                "type": "cable",
                "id": cable.pk,
                "label": cable.label or f"Cable #{cable.pk}",
                "fiber_type": strand.fiber_cable.fiber_cable_type.fiber_type if strand else None,
                "strand_count": strand.fiber_cable.fiber_cable_type.strand_count if strand else None,
                "strand_position": strand.position if strand else None,
                "strand_color": strand.color if strand else None,
                "tube_name": _get_tube_name(strand) if strand else None,
                "tube_color": _get_tube_color(strand) if strand else None,
                "fiber_cable_id": strand.fiber_cable_id if strand else None,
                "fiber_cable_url": strand.fiber_cable.get_absolute_url() if strand else None,
            }
            hops.append(hop)
            i += 1

        elif entry["type"] == "rear_port":
            # Rear port after cable = ingress into next device
            rp = RearPort.objects.select_related("device").get(pk=entry["id"])
            device = rp.device

            # Next entry should be front_port on same device
            if i + 1 < len(entries) and entries[i + 1]["type"] == "front_port":
                fp = FrontPort.objects.get(pk=entries[i + 1]["id"])

                hop = {
                    "type": "device",
                    "id": device.pk,
                    "name": device.name,
                    "role": device.role.name if device.role else None,
                    "site": device.site.name if device.site else None,
                    "url": device.get_absolute_url(),
                    "ingress": {
                        "rear_port": {"id": rp.pk, "name": rp.name},
                        "front_port": {"id": fp.pk, "name": fp.name},
                    },
                    "_pending_device_id": device.pk,
                }
                hops.append(hop)
                i += 2
            else:
                i += 1

        elif entry["type"] == "splice_entry":
            se = SplicePlanEntry.objects.select_related("plan", "tray").get(pk=entry["id"])
            # Attach splice to the most recent device hop (the closure)
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
            i += 1  # skip unknown entries

    # Clean up internal markers
    for h in hops:
        h.pop("_pending_device_id", None)

    return hops
```

**Key rules:**
- A device appearing mid-path (with both ingress and egress ports) is a closure. The algorithm detects this by checking if the device was already seen as the previous device hop via `_pending_device_id`. Note: origin/destination hops also get `_pending_device_id` set but it is a benign no-op — these devices are never revisited.
- Strand info is resolved by looking up `FiberStrand` via the FrontPort FK from the previous hop.
- Splice entries are attached to their parent closure hop, not emitted as standalone hops.

**Performance note:** The pseudocode above shows per-entry DB queries for clarity. The actual implementation should bulk-prefetch all referenced objects before the loop: collect all FrontPort, RearPort, Cable, and SplicePlanEntry PKs from the path list, then batch-fetch with `in_bulk()` or `filter(pk__in=...)` with `select_related()`. This avoids N+1 query issues on longer paths.

**Output shape:**
```json
{
  "circuit_id": 1,
  "circuit_name": "Circuit A",
  "circuit_url": "/plugins/netbox-fms/fiber-circuits/1/",
  "path_position": 1,
  "is_complete": true,
  "total_calculated_loss_db": 3.2,
  "total_actual_loss_db": null,
  "wavelength_nm": 1310,
  "hops": [
    {
      "type": "device",
      "id": 42,
      "name": "OLT-01",
      "role": "OLT",
      "site": "Site A",
      "url": "/dcim/devices/42/",
      "ports": {
        "front_port": {"id": 1, "name": "Port 1/1"},
        "rear_port": {"id": 2, "name": "Rear 1/1"}
      }
    },
    {
      "type": "cable",
      "id": 10,
      "label": "Cable-001",
      "fiber_type": "SM OS2",
      "strand_count": 48,
      "strand_position": 12,
      "strand_color": "ff0000",
      "tube_name": "Tube 1",
      "tube_color": "0000ff",
      "fiber_cable_id": 5,
      "fiber_cable_url": "/plugins/netbox-fms/fiber-cables/5/"
    },
    {
      "type": "device",
      "id": 55,
      "name": "Closure-01",
      "role": "Splice Closure",
      "site": "Manhole 7",
      "url": "/dcim/devices/55/",
      "ingress": {
        "rear_port": {"id": 3, "name": "Rear 2/12"},
        "front_port": {"id": 4, "name": "Port 2/12"}
      },
      "splice": {
        "id": 99,
        "plan_name": "Plan A",
        "tray": "Tray 1",
        "is_express": false
      },
      "egress": {
        "front_port": {"id": 5, "name": "Port 3/7"},
        "rear_port": {"id": 6, "name": "Rear 3/7"}
      }
    },
    {
      "type": "cable",
      "id": 11,
      "label": "Cable-002",
      "...": "..."
    },
    {
      "type": "device",
      "id": 70,
      "name": "ONT-01",
      "role": "ONT",
      "site": "Site B",
      "url": "/dcim/devices/70/",
      "ports": {
        "front_port": {"id": 8, "name": "Port 1/1"}
      }
    }
  ]
}
```

**Closure detection summary:** A device hop that has `ingress`, `splice` (optional), and `egress` keys is a closure. A device hop with only `ports` is an endpoint. The D3 renderer uses this shape to determine rendering style.

## Build Pipeline

The current `bundle.cjs` uses a single IIFE entry point. To support two independent entry points, switch to multiple build configs:

```javascript
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

// Shared options applied to each entry
const shared = {
  bundle: true,
  minify: !isWatch,
  sourcemap: 'linked',
  target: 'es2016',
  external: ['d3'],
  format: 'iife',
  logLevel: 'info',
};
```

Each entry gets its own `globalName` and `outfile`. The `outdir` + `outExtension` pattern is replaced with explicit `outfile` per entry since IIFE format requires a single output file per global.

## New Files

| File | Purpose |
|------|---------|
| `templates/netbox_fms/fibercircuitpath.html` | Base detail template (prerequisite) |
| `static/netbox_fms/src/trace-view.ts` | Entry point: init D3 canvas, wire sidebar HTMX calls |
| `static/netbox_fms/src/trace-renderer.ts` | D3 rendering: nodes, edges, zoom transitions |
| `static/netbox_fms/src/trace-types.ts` | TypeScript interfaces for trace API data |
| `static/netbox_fms/dist/trace-view.min.js` | esbuild bundled output |
| `templates/netbox_fms/fibercircuitpath_trace_tab.html` | Tab content: flex container with canvas + sidebar |
| `templates/netbox_fms/htmx/trace_device_detail.html` | Device/closure sidebar partial |
| `templates/netbox_fms/htmx/trace_cable_detail.html` | Cable segment sidebar partial |
| `templates/netbox_fms/htmx/trace_port_detail.html` | Port pair sidebar partial |
| `templates/netbox_fms/htmx/trace_splice_detail.html` | Splice entry sidebar partial |

## Modified Files

| File | Change |
|------|--------|
| `views.py` | Add FiberCircuitPath CRUD views (prerequisite) + TraceDetailView |
| `urls.py` | Add FiberCircuitPath CRUD routes (prerequisite) + HTMX trace-detail route |
| `filters.py` | Add `FiberCircuitPathFilterSet` (prerequisite) |
| `api/views.py` | Add `@action("trace")` to `FiberCircuitPathViewSet`, add filterset_class |
| `static/netbox_fms/bundle.cjs` | Switch to multi-entry build config |

## Out of Scope

- FiberCircuit-level trace diagram (paths table + per-row trace links suffice)
- Network topology map
- Per-segment loss calculation (requires a loss calculation engine; only total path loss is shown)
- Real-time loss measurement integration
- Editable trace (trace is read-only, editing happens in splice editor)
- Per-hop cumulative loss (future: would need loss model per cable segment)
