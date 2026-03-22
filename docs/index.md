# NetBox FMS — Fiber Management System

Fiber cable management, splice planning, and circuit provisioning for NetBox.

**Version:** 0.1.0 | **Requires:** NetBox 4.5+ | **Python:** 3.12+

---

## Feature Highlights

- **Cable type blueprints with auto-instantiation** — Define fiber cable construction once as a FiberCableType, then create instances that automatically populate components, following NetBox's Device/DeviceType pattern.
- **Four construction cases** — Model loose tube, ribbon-in-tube, central-core ribbon, and tight buffer cable designs with full template-driven instantiation.
- **Splice planning with diff computation and draw.io export** — Build splice plans that map strand-to-strand connections, compute diffs against existing plans, and export diagrams for field crews.
- **Fiber circuit provisioning with DAG-based pathfinding** — Provision end-to-end fiber circuits across your infrastructure using directed acyclic graph traversal for optimal path selection.
- **Device fiber overview with closure management** — View all fiber connections on a device at a glance and manage splice closures with tray and group organization.
- **WDM wavelength modeling** — Model terminal muxes, OADMs, ROADMs, and amplifiers with ITU grid channel plans. Provision wavelength services across WDM nodes and manage channel assignments with the interactive ROADM editor.

---

## Documentation

<div class="grid cards" markdown>

-   **Getting Started**

    Install and configure the plugin in your NetBox environment.

    [:octicons-arrow-right-24: Getting Started](getting-started/installation.md)

-   **User Guide**

    Learn how to use each feature, from cable types to splice planning.

    [:octicons-arrow-right-24: User Guide](user-guide/concepts.md)

-   **WDM**

    Model WDM nodes, provision wavelength services, and manage ROADM channel assignments.

    [:octicons-arrow-right-24: WDM Nodes](user-guide/wdm-nodes.md)

-   **Developer**

    Architecture overview, REST API reference, and contributing guidelines.

    [:octicons-arrow-right-24: Developer](developer/architecture.md)

-   **Reference**

    Choice values, cable profiles, and configuration options.

    [:octicons-arrow-right-24: Reference](reference/choices.md)

</div>
