# Device Fiber Overview

NetBox FMS injects a **Fiber Overview** tab on device detail pages (via `template_content.py`), giving operators a unified view of all fiber infrastructure connected to a device. This eliminates the need to navigate between multiple pages to assess a device's fiber connectivity, splice status, and closure configuration.

## What the Tab Shows

The Fiber Overview tab consolidates the following information for the selected device:

- **Connected fiber cables** -- all FiberCable instances associated with the device, including cable type, strand count, and termination details.
- **Fiber strand status** -- a per-strand breakdown showing whether each strand is available, in use, or spliced.
- **Associated splice plans** -- any SplicePlan entries that reference strands terminating at the device.
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
