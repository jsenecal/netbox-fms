# Device Fiber Overview

NetBox FMS injects a **Fiber Overview** tab on device detail pages (via `template_content.py`), giving operators a unified view of all fiber infrastructure connected to a device. This eliminates the need to navigate between multiple pages to assess a device's fiber connectivity, splice status, and closure configuration.

## What the Tab Shows

The Fiber Overview tab consolidates the following information for the selected device:

- **Connected fiber cables** -- all FiberCable instances associated with the device, including cable type, strand count, and termination details.
- **Fiber strand status** -- a per-strand breakdown showing whether each strand is available, in use, or spliced.
- **Associated splice plans** -- one or more SplicePlan entries that reference strands terminating at the device. A single closure may have multiple active plans from different teams or projects.
- **Closure cable entry (gland) assignments** -- for closure-type devices, the mapping of cables to physical entry points on the enclosure.

## ClosureCableEntry Management

Each `ClosureCableEntry` links a FiberCable to a specific entrance or gland label on a closure device. This tracks which cables enter through which physical openings on the closure, an essential detail for field technicians performing maintenance or troubleshooting.

Key capabilities:

- **Gland label assignment** -- assign a descriptive label (e.g., "Port A", "Entry 3") to each cable entry point.
- **Inline editing** -- gland assignments can be edited inline via HTMX-powered modals, allowing changes without leaving the device view.
- **Cable-to-entry mapping** -- provides a clear record of cable routing into the closure for documentation and audit purposes.

## Link Topology Modal

From the Fiber Overview tab, operators can link cable topology for cables connected to the device. This triggers the `link_cable_topology()` workflow, which:

1. Creates a FiberCable from an existing `dcim.Cable`.
2. Proposes FrontPort adoption or creation based on the cable type's strand configuration.
3. Confirms port mappings before committing changes.

This workflow bridges the gap between NetBox's native cable plant and the FMS fiber layer. See [Fiber Cables](fiber-cables.md) for a detailed description of the topology linking process.

## Splice Editor Widget

An embedded splice editor is available directly from the device view, enabling quick creation and editing of splice plan entries without navigating away. This is particularly useful when:

- Performing initial splice documentation for a newly installed closure.
- Updating splice records during field maintenance.
- Reviewing and correcting splice assignments reported by technicians.

The widget provides the same functionality as the full splice plan interface in a compact, context-aware form. See [Splice Planning](splice-planning.md) for the full workflow and splice plan management details.

## Pending Work Tab

Closure devices with approved splice plans display a **Pending Work** tab on their detail page. This tab provides a combined view of all approved plans targeting the closure, enabling batch application of changes.

### What the Tab Shows

- **Per-plan summary** -- Each approved plan is listed with its name, project, and a summary of the changes it introduces (additions, removals, unchanged splices).
- **Combined diff** -- The aggregate diff across all approved plans, organized by tray. Each tray section shows which splices will be added, removed, or kept.
- **Apply All action** -- A single button applies all approved plans' changes atomically. This creates and removes splice cables as needed, then archives the applied plans.

### Batch Apply Workflow

Instead of applying plans individually, the Pending Work tab merges all approved plans into a single operation:

1. Multiple teams create splice plans for the same closure (each plan is independent).
2. Plans go through the approval workflow (draft → pending_approval → approved).
3. A field technician opens the closure's Pending Work tab and reviews the combined diff.
4. The "Apply All" action commits all changes in a single atomic transaction.
5. Applied plans are automatically archived.

This approach ensures that a closure is only opened once for all pending changes, reducing field visits and minimizing the risk of partial updates.
