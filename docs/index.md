# NetBox FMS - Fiber Management System

Fiber cable management, splice planning, and circuit provisioning for NetBox.

**Version:** 0.1.0  |  **Requires:** NetBox 4.5+  |  **Python:** 3.12+

---

## What it does

NetBox FMS extends NetBox with the data model and tooling needed to track real
fiber plant: outside-plant trunks, splice closures, fiber circuits, and the
day-to-day work of moving glass around. It plugs into NetBox's existing
`dcim.Cable` / `FrontPort` / `RearPort` graph rather than replacing it, so the
trace algorithm, REST API, GraphQL schema, change log, and permission system
all work the same way they do for the rest of NetBox.

The plugin focuses on four problems:

- **Cable construction modeling.** Define a fiber cable product once as a
  blueprint (`FiberCableType`), then auto-instantiate buffer tubes, ribbons,
  strands, and non-fiber elements every time you install that cable.
- **Splice planning with review.** Plan splice work in `draft`, route it
  through a review gate (`pending_approval` -> `approved`), and apply
  approved plans atomically per closure.
- **Fiber circuit provisioning.** Discover candidate paths between two devices
  via DAG-based pathfinding and create end-to-end circuits with traceable hops.
- **Operational metadata.** Slack loops, gland labels, tube-to-tray
  assignments, and a per-device fiber overview tab.

## Feature highlights

- **Type/Instance pattern.** `FiberCableType` is a blueprint;
  `FiberCable` is an instance. On creation, the instance auto-instantiates
  components from the type's templates following the same shape NetBox uses
  for `DeviceType` / `Device`.
- **Four construction cases.** Loose tube, ribbon-in-tube, central-core
  ribbon, and tight buffer. The case is determined entirely by which
  templates are attached to the type; no flag is needed.
- **EIA-598 colors.** Strands and tubes are colored automatically by position,
  cycling every 12. No manual color entry.
- **Splice plan FSM.** `draft` -> `pending_approval` -> `approved` ->
  `archived`. Multiple plans can target the same closure in parallel; fiber
  exclusivity prevents collisions. Approval requires the
  `approve_spliceplan` permission.
- **Splice editor.** TypeScript/D3 visual editor at the device level. Drag to
  splice, click to remove, ghost lines for fibers claimed by other plans,
  read-only mode for non-draft plans, undo/redo, optimistic locking.
- **Draw.io export.** One page per tray, EIA-598 colors, diff annotations.
- **Custom cable profiles.** 24, 48, 72, 96, 144, 216, 288, and 432 strand
  profiles plus trunk profiles, registered via a startup monkey-patch
  (NetBox's built-in profiles cap at 16 positions).
- **REST API and GraphQL.** Every model is exposed; the splice plan viewset
  has dedicated `bulk-update`, `apply`, `import-from-device`, and `diff`
  actions.
- **Search integration.** `FiberCableType`, `FiberCable`, `SplicePlan`,
  `SpliceProject`, `FiberCircuit`, `SlackLoop`, and `TrayProfile` are
  registered with NetBox's global search.
- **Sample data.** A `create_sample_data` management command builds a full
  ISP-scale topology (380+ closures, 460+ plant cables, 5 fiber circuits) for
  demo, screenshots, and benchmarking.

## Quick install

```bash
pip install netbox-fms
```

```python
# configuration.py
PLUGINS = ["netbox_fms"]
```

```bash
cd /opt/netbox/netbox
python manage.py migrate
sudo systemctl restart netbox netbox-rq
```

See [Installation](getting-started/installation.md) for the full procedure.

---

## Documentation

<div class="grid cards" markdown>

-   **Getting Started**

    Install, configure, and walk through your first cable, splice plan, and
    circuit.

    [:octicons-arrow-right-24: Getting Started](getting-started/installation.md)

-   **User Guide**

    Cable types, cables, splice planning, fiber circuits, the splice editor,
    closures, and slack loops.

    [:octicons-arrow-right-24: User Guide](user-guide/concepts.md)

-   **Developer**

    Architecture, REST API, GraphQL, signals, services, and contributing.

    [:octicons-arrow-right-24: Developer](developer/architecture.md)

-   **Reference**

    Choice values, cable profiles, permissions, and management commands.

    [:octicons-arrow-right-24: Reference](reference/choices.md)

</div>
