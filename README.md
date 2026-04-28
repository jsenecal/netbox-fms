# NetBox FMS -- Fiber Management System

> A [NetBox](https://github.com/netbox-community/netbox) plugin for fiber cable management, splice planning, and circuit provisioning.

[![PyPI](https://img.shields.io/pypi/v/netbox-fms.svg)](https://pypi.org/project/netbox-fms/)
[![Python](https://img.shields.io/pypi/pyversions/netbox-fms.svg)](https://pypi.org/project/netbox-fms/)
[![NetBox](https://img.shields.io/badge/NetBox-4.5%2B-success.svg)](https://github.com/netbox-community/netbox)
[![CI](https://github.com/jsenecal/netbox-fms/actions/workflows/ci.yml/badge.svg)](https://github.com/jsenecal/netbox-fms/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jsenecal/netbox-fms/branch/main/graph/badge.svg)](https://codecov.io/gh/jsenecal/netbox-fms)
[![Documentation](https://img.shields.io/badge/docs-jsenecal.github.io-blue)](https://jsenecal.github.io/netbox-fms/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-blue.svg)](LICENSE)

Define fiber cable construction as reusable blueprints, auto-instantiate components on cable creation, plan splices with diff computation and draw.io export, and provision end-to-end fiber circuits with DAG-based pathfinding -- all within NetBox's native UI and API.

## Features

- **Cable type blueprints with auto-instantiation** -- Define fiber cable construction once as a FiberCableType, then create instances that automatically populate buffer tubes, ribbons, strands, and cable elements following NetBox's Device/DeviceType pattern.
- **Four construction cases** -- Loose tube, ribbon-in-tube, central-core ribbon, and tight buffer cable designs with full template-driven instantiation.
- **Splice planning** -- Map strand-to-strand connections in splice closures, compute diffs against live state, and export diagrams to draw.io for field crews.
- **Fiber circuit provisioning** -- End-to-end provisioning with DAG-based pathfinding and multi-hop tracing.
- **Device fiber overview** -- Per-device fiber connection view, splice closure management with tray and group organization.
- **Slack loop tracking** -- Record slack loop locations and storage methods at splice closures, with insert-into-closure workflows.
- **Full REST API and GraphQL** -- All models exposed via NetBox's standard API framework.

## Compatibility

| Plugin version | NetBox version | Python    |
|----------------|----------------|-----------|
| 0.1.x          | 4.5            | 3.12-3.14 |

## Installation

```bash
pip install netbox-fms
```

In your NetBox `configuration.py`:

```python
PLUGINS = [
    "netbox_fms",
]
```

Run migrations and restart NetBox:

```bash
cd /opt/netbox/netbox
python manage.py migrate
sudo systemctl restart netbox netbox-rq
```

## Configuration

`netbox-fms` has no required `PLUGINS_CONFIG` entries. See [Configuration](https://jsenecal.github.io/netbox-fms/getting-started/configuration/) for optional settings.

## Documentation

Full documentation: **[jsenecal.github.io/netbox-fms](https://jsenecal.github.io/netbox-fms/)**

- [Getting Started](https://jsenecal.github.io/netbox-fms/getting-started/installation/)
- [User Guide](https://jsenecal.github.io/netbox-fms/user-guide/concepts/)
- [Developer / Architecture](https://jsenecal.github.io/netbox-fms/developer/architecture/)
- [API Examples](https://jsenecal.github.io/netbox-fms/developer/api-examples/)
- [Contributing](https://jsenecal.github.io/netbox-fms/developer/contributing/)

## Contributing

PRs welcome. Use conventional-commits PR titles (`feat:`, `fix:`, `chore:`, `docs:`, ...) -- release-drafter assembles release notes from them. Run `make setup` after cloning to install dev dependencies and the pre-commit hooks (including the AI-attribution-rejecting `commit-msg` hook).

For questions and discussion, join the **#netbox** channel on the [NetDev Community Slack](https://netdev.chat/).

## License

[GNU Affero General Public License v3.0](LICENSE).
