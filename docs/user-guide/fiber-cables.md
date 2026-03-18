# Fiber Cables

A **FiberCable** is an instance of a [FiberCableType](fiber-cable-types.md),
linked one-to-one with a NetBox `dcim.Cable`. When you create a FiberCable, the
plugin automatically instantiates all internal components -- BufferTubes,
Ribbons, FiberStrands, and CableElements -- based on the type's templates. You
never need to create strands or tubes by hand.

---

## Creating a Fiber Cable

1. **Ensure a `dcim.Cable` exists.** The cable must already be created in
   NetBox between two devices (or between a device and a patch panel, splice
   closure, etc.). FiberCable does not create the underlying cable record -- it
   wraps one.

2. **Navigate to FMS > Fiber Cables > Add.**

3. **Select the FiberCableType.** Choose the cable type that matches the
   physical cable being installed. The type determines how many tubes, ribbons,
   and strands will be created.

4. **Link to the existing `dcim.Cable`.** Select the cable record from the
   dropdown. Each `dcim.Cable` can be associated with at most one FiberCable.

5. **Save.** On save, the plugin runs auto-instantiation and creates the full
   internal component hierarchy. No further action is needed to populate
   strands.

---

## Auto-Instantiation

When a FiberCable is saved for the first time, the `_instantiate_components()`
method reads the associated FiberCableType's templates and creates instance-level
components. The exact components depend on the
[construction case](concepts.md#four-construction-cases):

### BufferTubes

One **BufferTube** is created for each **BufferTubeTemplate** on the type. Each
tube receives a position number and an EIA-598 color matching its position within
the cable.

### Ribbons

**Ribbons** are created in two scenarios:

- **Ribbon-in-tube** -- when a BufferTubeTemplate has RibbonTemplate children,
  a Ribbon is created inside each BufferTube for each RibbonTemplate.
- **Central-core ribbon** -- when RibbonTemplates are attached directly to the
  FiberCableType (with no tubes), Ribbons are created at the cable level.

### FiberStrands

**FiberStrands** are the individual optical fibers. They are created inside
their parent container (tube, ribbon, or cable) and automatically assigned
[EIA-598 colors](concepts.md#eia-598-color-code) based on their position within
that container. The color sequence cycles every 12 fibers.

Each strand receives a globally unique `position` number across the entire
cable, ensuring unambiguous identification regardless of the construction style.

### CableElements

**CableElements** represent non-fiber components such as strength members,
ripcords, or armor. One CableElement is created for each CableElementTemplate
on the type.

---

## Viewing Internal Structure

The FiberCable detail page displays the full component hierarchy. For a
loose-tube cable, this shows:

```
FiberCable
 +-- BufferTube 1 (Blue)
 |    +-- FiberStrand 1 (Blue)
 |    +-- FiberStrand 2 (Orange)
 |    +-- ...
 +-- BufferTube 2 (Orange)
 |    +-- FiberStrand 13 (Blue)
 |    +-- ...
 +-- CableElement: Strength Member
```

For ribbon-in-tube cables, Ribbons appear as an intermediate level between
tubes and strands. For central-core ribbon cables, Ribbons appear directly
under the FiberCable. For tight-buffer cables, FiberStrands attach directly to
the cable with no intermediate containers.

---

## EIA-598 Color Assignment

All FiberStrands and BufferTubes receive colors automatically using the TIA/EIA-598
standard. Colors are determined by position within the parent container, not by
the strand's global position. This means fiber 1 in every tube is always Blue,
fiber 2 is always Orange, and so on.

For a full color table and details on the cycling behavior, see
[Core Concepts: EIA-598 Color Code](concepts.md#eia-598-color-code).

---

## Linking Cable Topology

The `link_cable_topology()` service automates the creation of a FiberCable and
its associated port infrastructure on termination devices. It is designed for
scenarios where you want to go from a bare `dcim.Cable` to a fully modeled
fiber plant in a single operation.

### What It Does

1. **Creates the FiberCable** from the specified `dcim.Cable` and
   FiberCableType, triggering auto-instantiation of all internal components.

2. **Adopts or creates FrontPorts** on the termination device. If the device
   already has RearPorts terminated by the cable, the service detects them and
   maps existing FrontPorts to strands. If no ports exist, it creates new
   RearPorts and FrontPorts.

3. **Creates PortMappings** connecting each FrontPort to its parent RearPort,
   establishing the internal wiring that NetBox's cable trace algorithm uses to
   follow a signal through the device.

4. **Sets the cable profile** on the `dcim.Cable` automatically. The profile is
   determined by the FiberCableType's strand count and registered in the custom
   cable profile system.

### Adopt vs. Greenfield

The service handles two paths:

- **Greenfield** -- no existing ports on the device for this cable. The service
  creates one RearPort per tube (or a single RearPort if the cable has no
  tubes), then creates a FrontPort and PortMapping for every strand.

- **Adopt** -- the device already has RearPorts terminated by this cable. The
  service proposes a mapping between existing FrontPorts and strand positions.
  If the mapping has not been confirmed, it raises a `NeedsMappingConfirmation`
  exception with the proposed mapping so the caller can review and approve it.

---

## Cable Profiles

NetBox's built-in cable profiles cap at 16 positions (`Single1C16P`). Fiber
cables commonly exceed this limit. NetBox FMS registers custom cable profiles
for standard fiber strand counts:

| Profile Key | Positions | Typical Use |
|-------------|-----------|-------------|
| `single-1c24p` | 24 | 2 tubes x 12F |
| `single-1c48p` | 48 | 4 tubes x 12F |
| `single-1c72p` | 72 | 6 tubes x 12F |
| `single-1c96p` | 96 | 8 tubes x 12F |
| `single-1c144p` | 144 | 12 tubes x 12F |
| `single-1c216p` | 216 | 18 tubes x 12F |
| `single-1c288p` | 288 | 24 tubes x 12F |
| `single-1c432p` | 432 | 18 tubes x 24F |

Trunk cable profiles (multi-connector) are also registered for common
configurations such as 2C12P, 4C12P, 6C12P, and others.

These profiles are registered at plugin startup and integrate with NetBox's
cable trace algorithm, allowing it to route signals at the individual strand
level through high-density fiber cables.

For the complete profile registry, see
[Cable Profiles](../reference/cable-profiles.md).
