# Fiber Cable Types

A **FiberCableType** is the blueprint that defines a cable product's physical
construction, fiber specification, and internal component layout. It is the
"type" side of the [Type/Instance pattern](concepts.md#the-typeinstance-pattern)
-- you define a FiberCableType once for each distinct cable product, then create
any number of [FiberCable](fiber-cables.md) instances from it.

---

## Fields Reference

| Field | Required | Description |
|-------|----------|-------------|
| **Manufacturer** | Yes | The cable manufacturer (references `dcim.Manufacturer`). |
| **Model** | Yes | Model name or designation. Must be unique per manufacturer. |
| **Part number** | No | Manufacturer's part number or SKU. |
| **Construction** | Yes | Cable construction style: Loose Tube, Tight Buffer, Ribbon, Ribbon-in-Tube, Micro Cable, or Blown Fiber. See [Construction Choices](../reference/choices.md) for details. |
| **Fiber type** | Yes | Optical fiber specification. Single-mode: SMF OS1, SMF OS2. Multi-mode: MMF OM1, MMF OM2, MMF OM3, MMF OM4, MMF OM5. |
| **Strand count** | Yes | Total number of fiber strands in the cable. Must match the sum computed from component templates if any are defined. |
| **Sheath material** | No | Outer jacket material: LSZH, PE, MDPE, HDPE, PVC, or PVDF. |
| **Jacket color** | No | Color of the cable's outer jacket. |
| **Armored** | No | Whether the cable has armor. Defaults to false. |
| **Armor type** | Conditional | Required when **Armored** is checked. Options: Steel Tape, Steel Wire, Corrugated Steel, Aluminum, Dielectric. |
| **Deployment** | No | Intended deployment environment. Groups: Indoor, Outdoor (Outdoor, Direct Buried, Duct, Microduct, Submarine), Aerial (ADSS, Figure-8, Lashed), Universal (Indoor/Outdoor). |
| **Fire rating** | No | Fire safety classification. NEC (North America): OFNP, OFNR, OFNG, OFN. CPR (Europe): Aca through Eca. Other: LSZH, None. |
| **Notes** | No | Free-text notes. |

---

## Creating a Fiber Cable Type

Follow these steps to define a new cable type through the NetBox UI.

1. **Navigate to the form.** Open **FMS > Fiber Cable Types** in the navigation
   menu, then click **Add**.

2. **Select a manufacturer.** Choose the cable manufacturer from the dropdown.
   If the manufacturer does not exist yet, create it first under **Devices >
   Manufacturers** in core NetBox.

3. **Enter the model name.** Type the manufacturer's model or product
   designation. The combination of manufacturer and model must be unique.

4. **Choose the construction type.** Select the construction that matches the
   cable's physical design:
   - **Loose Tube** -- tubes containing individual loose fibers.
   - **Tight Buffer** -- fibers individually coated, no tubes.
   - **Ribbon** -- central-core ribbon with no tube structure.
   - **Ribbon-in-Tube** -- ribbons housed inside buffer tubes.
   - **Micro Cable** -- small-diameter designs for microduct.
   - **Blown Fiber** -- fiber units designed for air-blown installation.

   For a detailed explanation of how each construction case affects component
   instantiation, see [Four Construction Cases](concepts.md#four-construction-cases).

5. **Set fiber type and strand count.** Select the fiber specification (e.g.,
   SMF OS2 for standard single-mode outdoor plant) and enter the total number of
   fiber strands in the cable.

6. **Fill in optional fields.** Set sheath material, jacket color, armor,
   deployment type, and fire rating as needed for your cable product.

7. **Save.** Click **Create** to save the FiberCableType. You can now add
   component templates to define the cable's internal structure.

---

## Adding Buffer Tube Templates

Buffer tube templates define the tubes inside a loose-tube or ribbon-in-tube
cable. Each template specifies one tube; create as many as the cable contains.

To add a buffer tube template, open a FiberCableType's detail page and use the
**Buffer Tube Templates** panel.

| Field | Required | Description |
|-------|----------|-------------|
| **Name** | Yes | Tube identifier (e.g., "Tube 1"). Must be unique within the cable type. |
| **Position** | Yes | Numeric position of the tube within the cable, starting at 1. |
| **Color** | No | Tube color. If left blank, the plugin assigns the standard EIA/TIA-598 color based on position (position 1 = Blue, position 2 = Orange, etc.). |
| **Stripe color** | No | Secondary stripe or dash color used for identification beyond 12 tubes per the EIA/TIA-598 standard. |
| **Fiber count** | Conditional | Number of loose fibers in this tube. Set this for loose-tube construction. Leave blank if the tube contains ribbons instead. |
| **Description** | No | Optional description. |

A tube template cannot have both a `fiber_count` and child ribbon templates.
Choose one or the other depending on the construction style.

---

## Adding Ribbon Templates

Ribbon templates define fiber ribbons. A ribbon template can be attached in two
ways, corresponding to the two ribbon construction cases:

- **Ribbon-in-Tube:** Attach the ribbon template to a **BufferTubeTemplate**.
  The tube's `fiber_count` must be blank. Each ribbon defines a group of fibers
  housed inside that tube.

- **Central-Core Ribbon:** Attach the ribbon template directly to the
  **FiberCableType** (leave the buffer tube template field blank). This models
  cables where ribbons are stacked in the cable core with no tube structure.

| Field | Required | Description |
|-------|----------|-------------|
| **Name** | Yes | Ribbon identifier (e.g., "Ribbon 1"). Must be unique within its parent scope. |
| **Position** | Yes | Numeric position of the ribbon within its parent (tube or cable type). |
| **Color** | No | Ribbon marking color. |
| **Stripe color** | No | Secondary stripe color for identification beyond 12 ribbons. |
| **Fiber count** | Yes | Number of fibers in this ribbon (commonly 12 or 24). |
| **Buffer tube template** | No | Parent tube for ribbon-in-tube construction. Leave blank for central-core ribbon. |
| **Description** | No | Optional description. |

---

## Adding Cable Element Templates

Cable element templates define non-fiber components inside the cable. These are
informational -- they do not affect fiber strand instantiation but help document
the complete cable construction.

| Field | Required | Description |
|-------|----------|-------------|
| **Name** | Yes | Element identifier (e.g., "Central Strength Member"). Must be unique within the cable type. |
| **Element type** | Yes | The type of non-fiber element. Options: Strength Member, Central Strength Member, DC Power Conductor, Tracer Wire, Messenger Wire, Ripcord, Water Blocking. |
| **Description** | No | Optional description. |

---

## Bulk Import

Fiber cable types can be imported in bulk via CSV from the list view. Navigate
to **FMS > Fiber Cable Types**, then click the **Import** button in the toolbar.
The CSV must include all required fields (manufacturer, model, construction,
fiber_type, strand_count) and may include any optional fields.

Component templates (buffer tubes, ribbons, cable elements) must be added after
the cable type records are imported, either through the UI or via the REST API.

---

## Related Topics

- [Core Concepts](concepts.md) -- Type/Instance pattern and the four
  construction cases explained in detail.
- [Choices Reference](../reference/choices.md) -- Complete list of all valid
  values for construction, fiber type, sheath material, armor type, deployment,
  and fire rating fields.
- [Fiber Cables](fiber-cables.md) -- Creating cable instances from a
  FiberCableType.
