# NetBox FMS -- Fiber Management System

A [NetBox](https://github.com/netbox-community/netbox) plugin for fiber cable management, splice planning, and circuit provisioning.

Define fiber cable construction as reusable blueprints, auto-instantiate components on cable creation, plan splices with diff computation and draw.io export, and provision end-to-end fiber circuits with DAG-based pathfinding -- all within NetBox's native UI and API.

## Features

- **Cable type blueprints with auto-instantiation** -- Define fiber cable construction once as a FiberCableType, then create instances that automatically populate buffer tubes, ribbons, strands, and cable elements following NetBox's Device/DeviceType pattern.
- **Four construction cases** -- Loose tube, ribbon-in-tube, central-core ribbon, and tight buffer cable designs with full template-driven instantiation.
- **Splice planning** -- Map strand-to-strand connections in splice closures, compute diffs against live state, and export diagrams to draw.io for field crews.
- **Fiber circuit provisioning** -- End-to-end fiber circuit provisioning with DAG-based pathfinding and multi-hop tracing.
- **Device fiber overview** -- Per-device fiber connection view, splice closure management with tray and group organization.
- **Slack loop tracking** -- Record slack loop locations and storage methods at splice closures, with insert-into-closure workflows.
- **Full REST API and GraphQL** -- All models exposed via NetBox's standard API framework.

## Compatibility

| NetBox FMS | NetBox  | Python |
|------------|---------|--------|
| 0.1.x      | 4.5+    | 3.12+  |

## Python Dependencies

None beyond NetBox itself.

## Installation

Install the plugin into your NetBox Python environment:

```bash
pip install netbox-fms
```

Add it to `PLUGINS` in your NetBox `configuration.py`:

```python
PLUGINS = [
    'netbox_fms',
]
```

Run database migrations and restart NetBox:

```bash
cd /opt/netbox/netbox
python manage.py migrate
sudo systemctl restart netbox netbox-rq
```

## Documentation

Full documentation is available at [jsenecal.github.io/netbox-fms](https://jsenecal.github.io/netbox-fms/).

- [Getting Started](https://jsenecal.github.io/netbox-fms/getting-started/installation/)
- [User Guide](https://jsenecal.github.io/netbox-fms/user-guide/concepts/)
- [Developer / Architecture](https://jsenecal.github.io/netbox-fms/developer/architecture/)
- [API Examples](https://jsenecal.github.io/netbox-fms/developer/api-examples/)
- [Contributing](https://jsenecal.github.io/netbox-fms/developer/contributing/)

## Bugs & Feature Requests

Please open an issue on the [GitHub issue tracker](https://github.com/jsenecal/netbox-fms/issues).

For questions and discussion, join the **#netbox** channel on the [NetDev Community Slack](https://netdev.chat/).

## License

This project is licensed under the [GNU Affero General Public License v3.0](LICENSE).
