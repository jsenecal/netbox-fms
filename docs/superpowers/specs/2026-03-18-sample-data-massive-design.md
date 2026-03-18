# Massive Sample Data Network — Design Spec

## Overview

Replace the existing `create_sample_data` management command with a massive ISP-scale metro fiber network. The new dataset exercises every plugin feature: multiple cable types, diverse backbone paths, metro rings, business ring-fed spurs, residential single-homed spurs, slack loops, express splices, closure cable entries, and a handful of provisioned fiber circuits (with most paths left open for testing).

---

## Network Topology

```
                    CO-Downtown
                   / A    B \
            10cl/288F    8cl/144F
               /              \
         CO-North ══════════ CO-South
              A=10cl/288F    A=10cl/288F
              B=8cl/144F     B=8cl/144F

Each CO has a metro ring:
  CO ── Hub-1 ── Hub-2 ── Hub-3 ── Hub-4 ── CO
       (96F, ~5 closures between each pair)

Each Hub has 2-3 spur routes:
  - 1 business spur (ring-fed, loops to adjacent hub, ~8 closures, 48F)
  - 2 residential spurs (single-homed, 5-10 closures, 48F, slack loops every 3rd)

Some spur closures have 12F/24F drop cables to buildings.
```

## Scale Targets

| Layer | Closures | Cables | Cable Type |
|-------|----------|--------|------------|
| Backbone (6 diverse routes, 3 CO pairs × 2 paths) | ~54 | ~60 | 288F / 144F |
| Metro rings (3 COs × 4 hubs, ~5 closures per segment) | ~60 | ~72 | 96F |
| Business spurs (12 hub × 1 ring spur, ~8 closures) | ~96 | ~108 | 48F |
| Residential spurs (12 hubs × 2 spurs, ~7 closures avg) | ~168 | ~168 | 48F |
| Building drops | — | ~50 | 12F / 24F |
| Patch cables (router/switch ↔ ODF) | — | ~170 | smf-os2 (1m) |
| **Total** | **~378 closures + ~65 routers/switches** | **~628** | |

## Cable Types (6)

| Model Name | Construction | Strands | Tubes | Fiber Type |
|-----------|-------------|---------|-------|------------|
| 288F Backbone | loose_tube | 288 | 24×12 | SMF OS2 |
| 144F Ribbon | ribbon_in_tube | 144 | 12 tubes × 1 ribbon × 12F | SMF OS2 |
| 96F Distribution | loose_tube | 96 | 8×12 | SMF OS2 |
| 48F Branch (existing) | loose_tube | 48 | 4×12 | SMF OS2 |
| 24F Building | tight_buffer | 24 | — | SMF OS2 |
| 12F Drop | tight_buffer | 12 | — | SMF OS2 |

## Sites (~35)

- 3 CO sites: Downtown, Northside, Southside
- 12 hub sites: 4 per CO (e.g., Downtown-Hub-NE, Downtown-Hub-SE, ...)
- ~20 neighborhood sites: grouped by spur area (e.g., Northside-Elm-St, Southside-Industrial)

## Devices

### Network Infrastructure (fiber plant)
- **3 COs**: DeviceType "ODF-288", role "Central Office"
- **12 Hubs**: DeviceType "ODF-96", role "Distribution Hub"
- **~378 Closures**: DeviceType "FOSC-450D" (backbone/metro) or "FOSC-200B" (spur), role "Splice Closure"
- **~50 Building Panels**: DeviceType "Wall-Box-24", role "Patch Panel" (drop termination endpoints)

### Routers and Switches (enables native NetBox cable tracing)
These devices sit at the "edges" of the fiber plant — their Interfaces connect to the ODF/panel FrontPorts via short patch cables, giving NetBox's built-in cable trace a starting point.

- **3 CO Core Routers**: DeviceType "Generic Router", role "Router", 48 LC interfaces each. Placed at each CO site, patched into the ODF.
- **12 Hub Aggregation Switches**: DeviceType "Generic Switch", role "Switch", 24 LC interfaces each. Placed at each hub, patched into the ODF.
- **~50 CPE Routers**: DeviceType "CPE Router", role "CPE", 2 LC interfaces each. Placed at building drop sites, patched into the wall box.

### Patch Cables
Short patch cables (type `smf-os2`, length 1m) connect router/switch Interfaces to ODF/panel FrontPorts. This completes the end-to-end path so NetBox's native cable trace can walk: `Interface → patch cable → FrontPort → (PortMapping) → RearPort → plant cable → ... → RearPort → (PortMapping) → FrontPort → patch cable → Interface`.

- CO routers: ~12 patch cables each (one per metro direction × tubes in use)
- Hub switches: ~8 patch cables each (subset of available ports)
- CPE routers: 1-2 patch cables each

## Features Exercised

### Splice Plans
Every closure gets a SplicePlan with tube-for-tube splicing between incoming cables.

### Express Splices
Backbone pass-through closures (where cable continues without branching) get `is_express=True` on all splice entries for the express tubes. Typically 2 of 24 tubes are cut for local drop, rest are express.

### Slack Loops (~86)
- Backbone: every 3rd closure (~18 loops), storage: coil/in-vault, meter marks 500-2000m range
- Business spur ring junctions (~12 loops), storage: figure-8/on-pole
- Residential spurs: every 3rd closure (~56 loops), storage: mixed, meter marks 50-500m range

### ClosureCableEntries
All closures document which cables enter through which gland/port.

### FiberCircuits (~5, most paths left unprovisioned)
1. **Backbone circuit**: CO-Downtown → CO-North via Path A (full end-to-end)
2. **Metro circuit**: CO-Downtown → Hub-Downtown-NE → Hub-Downtown-SE (metro ring segment)
3. **Spur-to-CO circuit**: CO-North → Hub-North-NW → business spur closure
4. **Drop circuit**: CO-South → Hub → spur closure → building panel (full last-mile)
5. **Cross-CO circuit**: CO-North → CO-South via backbone (tests diverse path)

All remaining paths are left unprovisioned for user testing.

## Implementation Details

### Performance
- Use `bulk_create` for all batch operations (FrontPorts, RearPorts, PortMappings, FiberStrands, SplicePlanEntries, SlackLoops)
- Expect ~5-10 minutes generation time
- Wrap in `transaction.atomic()` for all-or-nothing

### Idempotency
- Check if data already exists (by site/device name) before creating
- Safe to re-run: skips existing objects

### Command Interface
```bash
cd /opt/netbox/netbox && python manage.py create_sample_data
```

No flags needed — always creates the massive dataset.

---

## Testing Guide

After running `create_sample_data`, these scenarios can be tested:

### Splice Plan Editing
1. Navigate to FMS → Splice Planning → Splice Plans
2. Pick any backbone closure (e.g., "BB-DT-N-A-05") — it will have express and non-express entries
3. Open the splice editor to visualize the through-splices

### Slack Loop Inspection
1. Navigate to FMS → Slack Loops → Slack Loops
2. Filter by site to see loops at a specific location
3. Pick a residential spur slack loop and verify start/end marks and storage method

### Insert Slack Loop into Closure
1. Find a slack loop on a residential spur (filter by storage_method="coil")
2. Create a new closure Device at that site with appropriate RearPorts and FrontPort/PortMapping setup
3. Use the "Insert into Splice Closure" button on the slack loop detail page
4. Verify: original cable split, two new cables, splice plan entries created

### Fiber Circuit Provisioning
1. Navigate to FMS → Circuits → Fiber Circuits
2. View the 5 pre-provisioned circuits to understand the pattern
3. Create a new circuit: pick a FrontPort at CO-Downtown, trace through the backbone to CO-South
4. The trace engine should follow cables → splices → cables through each closure

### Express Fiber Verification
1. Open a backbone closure's splice plan
2. Verify that through-traffic tubes are marked "Express" (is_express=True)
3. Only the locally-dropped tubes should be physical splices

### Cable Type Diversity
1. Navigate to FMS → Cable Types → Fiber Cable Types
2. Verify all 6 types exist with correct strand counts and constructions
3. Filter Fiber Cables by type to see distribution across the network

### Native NetBox Cable Trace
1. Navigate to a CO core router (e.g., "CO-Downtown-Router") → Interfaces tab
2. Pick an interface that has a cable connected (e.g., "xe-0/0/0")
3. Click "Trace" — NetBox will follow: Interface → patch cable → ODF FrontPort → RearPort → plant cable → closure → ... → building panel → patch cable → CPE Interface
4. Verify the trace traverses multiple closures and cable segments end-to-end

### Loss Budget Path (future)
1. Pick a fiber circuit and note the number of splices and cable lengths
2. When loss budgeting is implemented, this data provides realistic multi-hop paths

---

## Design Decisions

1. **Replace, don't extend** — the old 13-segment ring is too small to exercise real-world patterns.
2. **Dual diverse backbone** — uses both 288F loose tube and 144F ribbon-in-tube for cable type variety.
3. **Business vs residential spurs** — ring-fed vs single-homed exercises different splice patterns.
4. **Sparse circuit provisioning** — 5 circuits demonstrate the feature without removing testing opportunities.
5. **Slack loops on residential spurs** — realistic placement where future splice points are most common.
6. **Express splices on backbone** — demonstrates the is_express field in a realistic pass-through scenario.
