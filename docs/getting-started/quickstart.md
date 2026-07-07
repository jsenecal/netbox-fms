# Quickstart

This walkthrough takes you from an empty plugin to a fully modeled fiber cable
entering a splice closure, with tubes assigned to trays and a splice plan ready
for entries. It assumes NetBox FMS is already installed (see
[Installation](installation.md)).

The plugin is closure-centric: splice plans, cable entries, and tray
assignments all hang off a `dcim.Device` acting as a splice closure. Patch
panels are not modeled by the plugin at this time.

## 1. Create a Manufacturer

If your NetBox instance does not yet have a cable manufacturer defined, create one first:

1. Navigate to **Devices > Manufacturers**.
2. Click **Add** and enter the manufacturer name (e.g., "Corning").
3. Save.

## 2. Define a Fiber Cable Type

A FiberCableType is the blueprint that describes how a cable is constructed.

1. Navigate to **FMS > Fiber Cable Types** and click **Add**.
2. Select the manufacturer created above.
3. Enter a model name (e.g., "ALTOS 48F Loose Tube").
4. Set the fiber type (e.g., **SMF OS2**) and total strand count (e.g., **48**).
5. Choose the construction style. For a loose tube cable, add **BufferTubeTemplates** -- for example, 4 tubes with 12 fibers each.
6. Save the cable type.

## 3. One-Time Catalog Setup for Closures

Before creating closure devices, the catalog needs one entry per hardware
model (this is done once, then reused for every closure):

1. Navigate to **Devices > Device Types** and create a device type for the
   closure model (e.g., "FOSC 450"), with a matching device role (e.g.,
   "Splice Closure").
2. Navigate to **Devices > Module Types** and create a module type for each
   tray product (e.g., "24F Splice Tray").
3. Navigate to **FMS > Tray Profiles** and click **Add**. Select the module
   type, set the **tray role** to **Splice Tray**, and set **max fibers** to
   the tray's splice capacity. Use the **Express Basket** role for
   pass-through storage baskets -- tubes can only be assigned to splice trays.

You do not need to define front ports anywhere -- the plugin creates the
per-strand ports when you add the cable (step 5).

## 4. Create the Splice Closure

Navigate to **FMS > Add Splice Closure**. The wizard creates the device and
its trays in one atomic action:

1. Enter the device name (e.g., "Closure-A"), site, device type, and role.
2. Pick the splice tray type and how many trays the closure holds; the
   wizard creates a "Tray 1..N" module bay with an installed tray module for
   each.
3. Optionally pick an express basket type and count ("Basket 1..N").
4. Save. Repeat for the far end of the cable (another closure or any
   fiber-terminating device).

The closure can also be assembled manually (device, module bays, modules) --
the wizard is a convenience, not a requirement.

## 5. Add the Cable from the Closure

Open either closure's device page and switch to the **Fiber Overview** tab,
then click **Add Cable**. The wizard creates the `dcim.Cable`, the
FiberCable with its internal structure, and all ports in one atomic action:

1. **Scope** -- pick the far-end device (the other closure), the
   FiberCableType defined earlier, and the port type (defaults to Splice).
2. **Cable details** -- set the native cable attributes: fiber type (e.g.,
   **SMF OS2**), status, label (pre-suggested from the device names),
   color, length (with unit), tenant, and an optional description.
3. **Review** -- check the per-device summary (rear ports per tube, front
   ports per strand) and click **Create Cable**.

On create, the plugin instantiates **BufferTubes** and **FiberStrands**
(with EIA-598 standard colors) from the type's templates, creates the
per-tube RearPorts and per-strand FrontPorts on both devices, terminates
the cable on the rear ports, sets the cable profile used by NetBox's trace
engine, and registers the cable at both closures with a blank gland entry.

If the cable already terminates on existing rear ports at the closure
(defined on its device type or created manually), use **Link Topology** on
the Fiber Overview tab instead -- it detects the existing ports and offers
to adopt them. See
[Fiber Cables](../user-guide/fiber-cables.md#linking-cable-topology).

## 6. Label the Cable Entrance

Each cable entering a closure is recorded with a **ClosureCableEntry**. The
wizard already created a blank entry at each closure -- this step is just
giving the entrance a label:

1. Open the blank entry via the inline gland editor on the closure's
   **Fiber Overview** tab (or under **FMS > Closure Cable Entries**).
2. Give the entrance a label (e.g., "Gland A") and save.

For cables registered without the wizard, navigate to **FMS > Closure Cable
Entries**, click **Add**, and select the closure device and the FiberCable
first. A fiber cable can be registered once per closure, and registration is
required before tubes from that cable can be assigned to trays.

## 7. Assign Buffer Tubes to Trays

Tube assignments record which tray each buffer tube is routed to inside the
closure:

1. On the closure's **Fiber Overview** tab, use **Assign** next to an
   unassigned tube (or **Auto-assign**, which pairs same-position tubes from
   different cables onto the same tray while capacity allows). Assignments can
   also be managed under **FMS > Tube Assignments**.
2. Only modules whose type has a **Splice Tray** profile are offered; express
   baskets and plain modules are rejected.

## 8. Create a Splice Plan

Splice plans capture the desired splice state of a single closure:

1. Navigate to **FMS > Splice Plans** and click **Add**.
2. Give the plan a name and select the **closure** device.
3. Optionally associate it with a **SpliceProject** (create one under
   **FMS > Splice Projects**) to group related plans for a route or job.
4. Save. The plan starts in **draft** status.

## 9. Add Splice Plan Entries

Splice plan entries define the fiber-to-fiber mappings inside the closure:

1. Open the plan's **Visual Editor** tab and drag fiber endpoints together, or
   add **SplicePlanEntries** manually.
2. Each entry pairs two FrontPorts on the closure (**fiber A** and
   **fiber B**) on a tray. Both ports must belong to the closure, and each
   fiber's FrontPort must be assigned to a tray module before it can be used
   in an entry.
3. Entries can only be edited while the plan is in **draft** status.

Once complete, submit the plan for approval and apply it from the closure's
**Pending Work** tab. See [Splice Planning](../user-guide/splice-planning.md)
for the full lifecycle.

## Next Steps

For a deeper explanation of the type/instance pattern, cable construction models, and splice planning concepts, see the [Concepts](../user-guide/concepts.md) guide.
