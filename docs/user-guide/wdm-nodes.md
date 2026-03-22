# WDM Nodes

## Overview

A **WDM Node** is an overlay on a `dcim.Device` that marks the device as participating in wavelength-division multiplexing. This follows the same pattern used elsewhere in NetBox FMS -- just as a [FiberCable](fiber-cables.md) adds fiber structure to a `dcim.Cable`, a WDM Node adds optical multiplexing semantics to a Device.

WDM nodes model the equipment that combines and separates wavelengths on shared fiber strands: terminal multiplexers, add/drop nodes, reconfigurable nodes, and amplifiers. Each node carries a channel plan derived from an ITU grid and maps those channels to the device's physical front ports.

---

## Node Types

| Node Type | Description |
|-----------|-------------|
| **Terminal MUX** | Multiplexes/demultiplexes all channels at the edge of a WDM network. Typically deployed at headend or customer-facing sites. |
| **OADM** | Optical Add/Drop Multiplexer. Adds or drops a fixed subset of channels at intermediate sites while passing the remaining channels through. |
| **ROADM** | Reconfigurable Optical Add/Drop Multiplexer. Like an OADM, but channel-to-port assignments can be changed without physical intervention. Use the [ROADM Editor](roadm-editor.md) to manage assignments. |
| **Amplifier** | Amplifies the optical signal without demultiplexing individual channels. Amplifier nodes have no channel plan -- they pass all wavelengths through as a single composite signal. |

---

## WDM Device Type Profiles

A **WDM Device Type Profile** is a blueprint attached to a `dcim.DeviceType`. It defines the WDM capabilities that any device of that type will have. This follows the same Type/Instance pattern described in [Core Concepts](concepts.md#the-typeinstance-pattern) -- the profile is the type-level definition, and the WDM Node is the instance.

### Creating a Profile

1. Navigate to **FMS > WDM Device Type Profiles** and click **Add**.
2. Select the **Device Type** this profile applies to. Each DeviceType can have at most one WDM profile.
3. Set the **Node Type** (Terminal MUX, OADM, ROADM, or Amplifier).
4. Select the **Grid**:
   - **DWDM 100 GHz** -- 44 channels (C21 through C64) on the ITU-T G.694.1 100 GHz grid.
   - **DWDM 50 GHz** -- 88 channels (C21 through C64.5, including half-channels) on the 50 GHz grid.
   - **CWDM** -- 18 channels (1270 nm through 1610 nm, 20 nm spacing) on the ITU-T G.694.2 grid.
5. Save the profile.

### Adding Channel Templates

After saving the profile, add **WDM Channel Templates** to define which channels this device type supports:

1. On the profile detail page, click **Add Channel Template**.
2. Select the channels from the ITU grid defined by the profile's grid setting. Each channel template specifies:
   - **Grid position** -- ordinal position in the grid (auto-populated from the ITU channel table).
   - **Label** -- ITU channel label (e.g., "C32" for DWDM, "CWDM-1550" for CWDM).
   - **Wavelength (nm)** -- center wavelength computed from the ITU frequency grid.
   - **Front port template** -- optionally map this channel to a specific `dcim.FrontPortTemplate` on the DeviceType. This pre-wires the channel-to-port assignment so that instances inherit it automatically.

Not every device type supports all channels on a grid. A 16-channel DWDM mux, for example, would have 16 channel templates selected from the 44 available on the 100 GHz grid.

---

## Creating a WDM Node

### From a Device with a Profile

When you create a WDM Node for a Device whose DeviceType has a WDM Device Type Profile:

1. Navigate to **FMS > WDM Nodes** and click **Add**.
2. Select the **Device**.
3. The **Node Type** and **Grid** fields default to the values from the profile.
4. Save.

On save, the plugin automatically populates the node's **Wavelength Channels** from the profile's channel templates. If the channel templates have front port template mappings, the corresponding `dcim.FrontPort` instances on the device are linked to the channels automatically.

### Manual Setup (No Profile)

If the DeviceType does not have a WDM profile, you can still create a WDM Node:

1. Select the **Device**, **Node Type**, and **Grid** manually.
2. Save the node.
3. Add **Wavelength Channels** individually from the node's channels tab, specifying the grid position, label, wavelength, and optional front port assignment for each channel.

This approach is useful for one-off equipment or devices that do not conform to a standard type profile.

### Amplifier Nodes

Amplifier nodes are a special case. Because amplifiers do not demultiplex individual channels, no wavelength channels are created on save -- even if the DeviceType has a profile with channel templates. An amplifier node simply represents a pass-through amplification point in the WDM path.

---

## Trunk Ports

**WDM Trunk Ports** map a device's `dcim.RearPort` instances to directional trunks on the WDM node. These represent the aggregate fiber connections carrying the multiplexed signal.

| Field | Description |
|-------|-------------|
| **Rear port** | The physical `dcim.RearPort` on the device that carries the trunk signal. |
| **Direction** | A label identifying the trunk direction -- typically "east", "west", or "common". |
| **Position** | Ordering position for display and path tracing. |

Common configurations:

- **Terminal MUX** -- one trunk port labeled "common" (the single multiplexed output).
- **OADM / ROADM** -- two trunk ports labeled "east" and "west" for the pass-through fiber directions.
- **Amplifier** -- two trunk ports for the input and output directions.

Trunk ports are used by the channel mapping system. When a channel is assigned to a front port, the plugin creates `PortMapping` records linking that front port to each trunk port's rear port. This enables NetBox's standard cable trace to follow the optical path through the WDM node.

---

## Wavelength Channels

Each non-amplifier WDM node has a set of **Wavelength Channels** representing the individual lambdas it can handle. A channel carries:

| Field | Description |
|-------|-------------|
| **Grid position** | Ordinal position in the ITU grid. |
| **Label** | ITU channel label (e.g., "C32"). |
| **Wavelength (nm)** | Center wavelength. |
| **Front port** | The `dcim.FrontPort` this channel is mapped to (may be null if unassigned). |
| **Status** | Available, Reserved, or Lit. |

Channel status governs what operations are permitted:

- **Available** -- the channel can be freely assigned or reassigned to ports.
- **Reserved** -- the channel is held for a planned service and cannot be remapped.
- **Lit** -- the channel is in active use by a [Wavelength Service](wavelength-services.md) and is protected from changes.

For ROADM nodes, channel-to-port assignments are managed interactively through the [ROADM Editor](roadm-editor.md) rather than by editing individual channel records.
