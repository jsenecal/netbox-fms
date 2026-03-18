# Quickstart

This walkthrough takes you from an empty plugin to a fully modeled fiber cable with splice mappings. It assumes NetBox FMS is already installed (see [Installation](installation.md)).

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

## 3. Create Two Devices

Fiber cables connect between devices. If you do not already have devices in NetBox:

1. Navigate to **Devices > Devices** and create two devices (e.g., "Panel-A" and "Panel-B").
2. Ensure each device has a device type with front ports defined, so that fiber strands can terminate to them.

## 4. Create a Cable

1. Navigate to **Devices** and select one of the devices.
2. Under the device's interface or front port listing, click **Connect** to create a `dcim.Cable` between the two devices.
3. Save the cable.

## 5. Create a Fiber Cable

This is where the plugin takes over.

1. Navigate to **FMS > Fiber Cables** and click **Add**.
2. Select the **dcim.Cable** created in the previous step.
3. Select the **FiberCableType** defined earlier.
4. Save.

On save, the plugin automatically instantiates the internal cable structure based on the type's templates:

- **BufferTubes** are created matching each BufferTubeTemplate.
- **FiberStrands** are created inside each tube, automatically assigned EIA-598 standard colors.

Navigate to the new FiberCable's detail page to inspect the generated tubes and strands.

## 6. Create a Splice Project and Plan

Splice projects organize the splicing work at a specific location (typically a fiber closure).

1. Navigate to **FMS > Splice Projects** and click **Add**.
2. Give the project a name and associate it with a closure device.
3. Save, then navigate to **FMS > Splice Plans** and click **Add**.
4. Associate the plan with the splice project created above.
5. Save.

## 7. Add Splice Plan Entries

Splice plan entries define the fiber-to-fiber mappings inside a closure.

1. Open the splice plan and add **SplicePlanEntries**.
2. Each entry maps a fiber strand from one cable to a fiber strand on another cable.
3. Repeat for each fiber pair that will be spliced at this location.

Once complete, the splice plan provides a full record of which fibers are connected through the closure.

## Next Steps

For a deeper explanation of the type/instance pattern, cable construction models, and splice planning concepts, see the [Concepts](../user-guide/concepts.md) guide.
