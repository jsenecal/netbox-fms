# Configuration

NetBox FMS works out of the box with no required configuration. This page
covers the optional settings, the permission model, optional integration
points, and the runtime side effects of installing the plugin.

## Plugin settings

The current release ships with no required entries in `PLUGINS_CONFIG`:

```python
PLUGINS_CONFIG = {
    "netbox_fms": {},
}
```

`PluginConfig.default_settings` is intentionally empty. Future releases that
introduce configurable behavior will document any new keys here.

## What `ready()` does at startup

When NetBox loads the plugin, `NetBoxFMSConfig.ready()` performs four actions:

1. **Patches the cable-profile registry** to register custom 24, 48, 72, 96,
   144, 216, 288, and 432 strand profiles plus trunk profiles. NetBox does
   not yet expose a public API for plugin-defined cable profiles
   (see [netbox#21663](https://github.com/netbox-community/netbox/issues/21663)),
   so the registration uses a monkey-patch in `monkey_patches.py`.
2. **Connects signal handlers** that keep splice plan diffs fresh and block
   out-of-band edits to FMS-managed `PortMapping` rows. See
   [signals](../developer/architecture.md#signal-handlers).
3. **Connects the counter cache** for `FiberCableType` so list views can
   display the instance count without an extra query.
4. **Registers map layers** with `netbox-pathways`, if it is installed:
   `fms_splice_closures` and `fms_slack_loops`. The integration is best-effort
   and silently skipped when `netbox-pathways` is not present.

None of these are configurable, but they are useful to know if you are
debugging plugin startup.

## Permissions

NetBox FMS uses Django's standard permission system. Every model exposes the
four CRUD permissions (`view`, `add`, `change`, `delete`); `SplicePlan` adds
one custom permission, `approve_spliceplan`, that gates the approval workflow.

### Cable types and instances

| Permission                                  | Description                                |
| ------------------------------------------- | ------------------------------------------ |
| `netbox_fms.{view,add,change,delete}_fibercabletype`         | Manage cable type blueprints               |
| `netbox_fms.{view,add,change,delete}_buffertubetemplate`     | Manage buffer tube templates               |
| `netbox_fms.{view,add,change,delete}_ribbontemplate`         | Manage ribbon templates                    |
| `netbox_fms.{view,add,change,delete}_cableelementtemplate`   | Manage non-fiber element templates         |
| `netbox_fms.{view,add,change,delete}_fibercable`             | Manage cable instances                     |
| `netbox_fms.{view,add,change,delete}_buffertube`             | Manage buffer tube instances (rare)        |
| `netbox_fms.{view,add,change,delete}_ribbon`                 | Manage ribbon instances (rare)             |
| `netbox_fms.{view,add,change,delete}_fiberstrand`            | Manage fiber strand instances (rare)      |
| `netbox_fms.{view,add,change,delete}_cableelement`           | Manage cable element instances (rare)      |

Most users do not need write access to the instance-level component models
(buffer tubes, ribbons, strands, cable elements). The plugin creates and
maintains them automatically when a `FiberCable` is saved.

### Splice planning

| Permission                                                 | Description                                                            |
| ---------------------------------------------------------- | ---------------------------------------------------------------------- |
| `netbox_fms.{view,add,change,delete}_spliceproject`        | Manage splice projects                                                 |
| `netbox_fms.{view,add,change,delete}_spliceplan`           | Manage splice plans                                                    |
| `netbox_fms.approve_spliceplan`                            | Approve, reject, reopen, or archive a non-draft plan                   |
| `netbox_fms.{view,add,change,delete}_spliceplanentry`      | Manage individual splice plan entries                                  |
| `netbox_fms.{view,add,change,delete}_closurecableentry`    | Manage gland labels for cables entering a closure                      |
| `netbox_fms.{view,add,change,delete}_trayprofile`          | Mark a `dcim.ModuleType` as a splice tray or express basket            |
| `netbox_fms.{view,add,change,delete}_tubeassignment`       | Assign buffer tubes to splice trays inside a closure                   |

The `change_spliceplan` permission lets a user submit a draft plan and make
edits, but it does not let them approve the plan once it is in
`pending_approval`. Reserve `approve_spliceplan` for leads, network engineers,
or anyone responsible for validating splice designs before they are applied.

### Fiber circuits

| Permission                                                | Description                              |
| --------------------------------------------------------- | ---------------------------------------- |
| `netbox_fms.{view,add,change,delete}_fibercircuit`        | Manage fiber circuits                    |
| `netbox_fms.{view,add,change,delete}_fibercircuitpath`    | Manage individual fiber circuit paths    |

`FiberCircuitNode` is a relational index used internally by the trace engine
and circuit-protection checks. It does not have its own UI, but the standard
Django auto-generated permissions exist if needed.

### Operational metadata

| Permission                                              | Description                                  |
| ------------------------------------------------------- | -------------------------------------------- |
| `netbox_fms.{view,add,change,delete}_slackloop`         | Manage slack loop records                    |

### Assigning permissions

Permissions are assigned through standard NetBox flows. The most common
patterns are:

- **Admin > Users > Permissions** in the UI.
- **`/api/users/permissions/`** in the REST API.
- A constraint-based permission with an object filter (for example, restrict
  approval to plans owned by a specific tenant or located on closures inside a
  specific site group).

`approve_spliceplan` is enforced both by API view permissions and by model
`clean()` validation, so granting it via a constrained permission also
constrains the action.

## Optional integrations

### netbox-pathways (map layers)

If `netbox-pathways` is installed, FMS automatically registers two map layers
during startup:

| Layer name              | Geometry | Source data                                              |
| ----------------------- | -------- | -------------------------------------------------------- |
| `fms_splice_closures`   | Point    | `dcim.Device` instances that have at least one `SplicePlan` |
| `fms_slack_loops`       | Point    | `SlackLoop` instances                                    |

Both layers are placed in the `Fiber Management` group on the layer toolbar.
No configuration is needed; the registration is silently skipped if the
import of `netbox_pathways.registry` fails.

### Cable profiles (NetBox core)

The plugin's cable profile registrations make NetBox's strand-level cable
trace work for high-count fiber. See
[Cable Profiles](../reference/cable-profiles.md) for the full list and the
upstream issue tracking the migration to a public API.

## Disabling features

There is currently no flag for disabling any of the runtime side effects.
If you need to skip the cable-profile patching (for example, while testing
upstream NetBox changes), the cleanest path is to remove `netbox_fms` from
`PLUGINS` for that environment.
