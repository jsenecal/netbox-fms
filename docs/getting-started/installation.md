# Installation

## Prerequisites

- NetBox 4.5 or later, fully installed and operational
- Python 3.12 or later

## Install the Plugin

Install `netbox-fms` using pip within the same Python environment that NetBox uses:

```bash
pip install netbox-fms
```

## Enable the Plugin

Add `netbox_fms` to the `PLUGINS` list in your NetBox `configuration.py`:

```python
PLUGINS = [
    'netbox_fms',
]
```

## Run Database Migrations

Apply the plugin's database migrations:

```bash
cd /opt/netbox/netbox
python manage.py migrate
```

## Restart NetBox Services

Restart both the NetBox WSGI service and the background worker. The exact command depends on your process manager:

```bash
# If using systemd
sudo systemctl restart netbox netbox-rq

# If using supervisord
sudo supervisorctl restart netbox netbox-rq
```

## Verify the Installation

Log in to NetBox and confirm that the **FMS** menu appears in the sidebar navigation. If the menu is not visible, check that:

1. The plugin is listed in `PLUGINS` within `configuration.py`.
2. Migrations have been applied without errors.
3. The NetBox services have been fully restarted.
