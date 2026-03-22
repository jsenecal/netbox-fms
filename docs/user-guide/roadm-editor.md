# ROADM Editor

## Overview

The ROADM Editor is an interactive interface for managing channel-to-port assignments on ROADM [WDM Nodes](wdm-nodes.md). Instead of editing individual WavelengthChannel records one at a time, the editor presents all channels in a single table with inline dropdown selects, undo/redo support, and atomic save with concurrent edit detection.

The editor is designed for the operational workflow of provisioning and regrooming wavelengths on reconfigurable nodes, where an operator needs to see the full channel plan at a glance and make multiple assignment changes in a single session.

---

## Accessing the Editor

1. Navigate to the detail page of a **WDM Node** (FMS > WDM Nodes > select a node).
2. Click the **Wavelength Editor** tab.

The tab is available on all WDM node types, but it is most useful for ROADM nodes where channel-to-port assignments change over time. For Terminal MUX and OADM nodes, the initial assignments are typically set once during commissioning and rarely modified.

---

## Editor Layout

The editor displays a table with one row per wavelength channel, sorted by grid position:

| Column | Description |
|--------|-------------|
| **Grid Pos** | The channel's ordinal position in the ITU grid. |
| **Label** | ITU channel label (e.g., "C32", "C32.5"). |
| **Wavelength (nm)** | Center wavelength. |
| **Port Assignment** | Dropdown select for choosing which FrontPort this channel maps to. |
| **Status** | Current channel status: Available, Reserved, or Lit. |

Above the table, a toolbar provides Undo, Redo, and Save buttons, along with an "Unsaved changes" badge that appears when the current mapping differs from the saved state.

---

## Assigning Channels to Ports

For channels with **Available** status, the Port Assignment column contains a dropdown listing all FrontPorts on the device that are not already assigned to another channel. To assign a channel:

1. Select a FrontPort from the dropdown. The available options include all unassigned FrontPorts on the device, plus any ports currently assigned to other available channels (since those could be reassigned).
2. To unassign a channel, select "-- Unassigned --" from the dropdown.

Changes are tracked locally in the browser until you save. You can make multiple changes before saving.

---

## Protected Channels

Channels with **Reserved** or **Lit** status cannot be reassigned through the editor. These channels display a lock icon instead of a dropdown select. If the channel is associated with a [Wavelength Service](wavelength-services.md), the service name appears as a tooltip on the lock icon.

To modify a protected channel, you must first change the underlying condition:

- **Reserved** channels must be unreserved by editing the channel record directly.
- **Lit** channels are protected by an active wavelength service. The service must be decommissioned before the channel can be reassigned.

---

## Undo and Redo

The editor maintains an undo/redo stack for all port assignment changes made in the current session:

- **Undo** (toolbar button or Ctrl+Z / Cmd+Z) -- reverts the most recent assignment change.
- **Redo** (toolbar button or Ctrl+Shift+Z / Cmd+Shift+Z) -- reapplies a previously undone change.

The undo/redo stack is cleared after a successful save, since the saved state becomes the new baseline.

---

## Save

Clicking **Save** submits all pending changes to the server in a single atomic transaction. The save operation:

1. **Validates** the proposed mapping. The server checks that no protected channels are being remapped and that no two channels map to the same FrontPort.
2. **Updates WavelengthChannel records** -- sets the `front_port` FK on each changed channel.
3. **Updates PortMappings** -- deletes old `PortMapping` records for removed assignments and creates new ones linking the assigned FrontPort to each trunk port's RearPort. This ensures that NetBox's standard cable trace follows the optical path correctly through the node.
4. **Retraces affected paths** -- any `FiberCircuitPath` records that traverse cables connected to the node's trunk ports are retraced to reflect the new mapping.

After a successful save, the editor displays a summary (e.g., "Saved: 2 added, 1 removed, 0 changed") and resets the undo/redo stack.

If validation fails, the server returns specific error messages (e.g., "Channel C32 is Lit and cannot be remapped" or "Port conflict: channels C32 and C33 both map to FrontPort pk=42"). The editor displays these errors and does not clear the pending changes, so you can correct the issue and save again.

---

## Concurrent Edit Detection

The editor tracks the node's `last_updated` timestamp from when the page was loaded. When you save, the server compares this timestamp against the current value in the database. If another user (or API call) has modified the node since you loaded the editor, the server returns a **409 Conflict** response.

The editor displays a warning message: "This node was modified by another user." with a **Reload** button. Clicking Reload refreshes the page to pick up the latest channel state. Your unsaved changes will be lost, so it is best to coordinate with other operators when making changes to the same node.

---

## Browser Navigation Warning

If you have unsaved changes and attempt to navigate away from the page or close the browser tab, a confirmation dialog will appear warning you about unsaved changes. This prevents accidental loss of work during a multi-change editing session.
