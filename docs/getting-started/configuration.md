# Configuration

## Plugin Settings

The current release (v0.1.0) ships with no custom plugin settings. The default configuration is empty:

```python
PLUGINS_CONFIG = {
    'netbox_fms': {},
}
```

No additional entries in `PLUGINS_CONFIG` are required. Future releases may introduce configurable options here.

## Permissions

NetBox FMS follows Django's standard permission system. Each model exposes four permissions: **view**, **add**, **change**, and **delete**. Assign these permissions to users or groups to control access.

### Key Permission Names

**Fiber Cable Types and Cables**

| Permission | Description |
|---|---|
| `netbox_fms.view_fibercabletype` | View fiber cable type definitions |
| `netbox_fms.add_fibercabletype` | Create new fiber cable types |
| `netbox_fms.change_fibercabletype` | Modify existing fiber cable types |
| `netbox_fms.delete_fibercabletype` | Delete fiber cable types |
| `netbox_fms.view_fibercable` | View fiber cable instances |
| `netbox_fms.add_fibercable` | Create new fiber cables |
| `netbox_fms.change_fibercable` | Modify existing fiber cables |
| `netbox_fms.delete_fibercable` | Delete fiber cables |

**Splice Planning**

| Permission | Description |
|---|---|
| `netbox_fms.view_spliceproject` | View splice projects |
| `netbox_fms.add_spliceproject` | Create splice projects |
| `netbox_fms.view_spliceplan` | View splice plans |
| `netbox_fms.add_spliceplan` | Create splice plans |

**Fiber Circuits**

| Permission | Description |
|---|---|
| `netbox_fms.view_fibercircuit` | View fiber circuits |
| `netbox_fms.add_fibercircuit` | Create fiber circuits |
| `netbox_fms.change_fibercircuit` | Modify fiber circuits |
| `netbox_fms.delete_fibercircuit` | Delete fiber circuits |

### Assigning Permissions

Permissions can be assigned through the NetBox admin interface under **Admin > Permissions**, or programmatically via the NetBox REST API. Create a permission object, associate it with the relevant actions and object types, and assign it to the appropriate users or groups.
