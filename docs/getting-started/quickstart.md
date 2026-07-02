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

## 3. Create a Splice Closure Device

A splice closure is a regular NetBox device. If you do not already have one:

1. Navigate to **Devices > Device Types** and create a device type for the
   closure model (e.g., "FOSC 450"), with a matching device role (e.g.,
   "Splice Closure").
2. Navigate to **Devices > Devices** and create the closure device at its site
   (e.g., "Closure-A"). Repeat for the far end of the cable (another closure
   or any fiber-terminating device).

You do not need to pre-define front ports on the closure -- the plugin creates
the per-strand ports when you link the cable topology (step 6).

## 4. Model the Closure's Splice Trays

Splice trays are NetBox **Modules** installed in the closure, and the plugin
needs to know which module types are trays:

1. Navigate to **Devices > Module Types** and create a module type for each
   tray product (e.g., "24F Splice Tray").
2. Navigate to **FMS > Tray Profiles** and click **Add**. Select the module
   type, set the **tray role** to **Splice Tray**, and set **max fibers** to
   the tray's splice capacity. Use the **Express Basket** role for
   pass-through storage baskets -- tubes can only be assigned to splice trays.
3. On the closure device, create **Module Bays** (e.g., "Bay 1", "Bay 2") and
   install a **Module** of the tray module type in each bay.

## 5. Create a Cable

1. Navigate to **Devices** and select one of the closure devices.
2. Create a `dcim.Cable` between the two devices with a fiber cable type
   (e.g., **SMF OS2**).
3. Save the cable.

## 6. Create a Fiber Cable

This is where the plugin takes over.

1. Navigate to **FMS > Fiber Cables** and click **Add**.
2. Select the **dcim.Cable** created in the previous step.
3. Select the **FiberCableType** defined earlier.
4. Save.

On save, the plugin automatically instantiates the internal cable structure based on the type's templates:

- **BufferTubes** are created matching each BufferTubeTemplate.
- **FiberStrands** are created inside each tube, automatically assigned EIA-598 standard colors.

Navigate to the new FiberCable's detail page to inspect the generated tubes and strands.

Alternatively, use the **Link Topology** action on the closure's **Fiber
Overview** tab. It performs the same FiberCable creation and additionally
provisions the per-strand FrontPorts, per-tube RearPorts, and PortMappings on
the closure, and sets the cable profile used by NetBox's trace engine. See
[Fiber Cables](../user-guide/fiber-cables.md#linking-cable-topology).

## 7. Register the Cable at the Closure

Each cable entering a closure is recorded with a **ClosureCableEntry**:

1. Navigate to **FMS > Closure Cable Entries** and click **Add** (or use the
   inline gland editor on the closure's **Fiber Overview** tab).
2. Select the closure device and the FiberCable, and give the entrance a label
   (e.g., "Gland A").
3. Save. A fiber cable can be registered once per closure.

This step is required before tubes from that cable can be assigned to trays.

## 8. Assign Buffer Tubes to Trays

Tube assignments record which tray each buffer tube is routed to inside the
closure:

1. On the closure's **Fiber Overview** tab, use **Assign** next to an
   unassigned tube (or **Auto-assign**, which pairs same-position tubes from
   different cables onto the same tray while capacity allows). Assignments can
   also be managed under **FMS > Tube Assignments**.
2. Only modules whose type has a **Splice Tray** profile are offered; express
   baskets and plain modules are rejected.

## 9. Create a Splice Plan

Splice plans capture the desired splice state of a single closure:

1. Navigate to **FMS > Splice Plans** and click **Add**.
2. Give the plan a name and select the **closure** device.
3. Optionally associate it with a **SpliceProject** (create one under
   **FMS > Splice Projects**) to group related plans for a route or job.
4. Save. The plan starts in **draft** status.

## 10. Add Splice Plan Entries

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
