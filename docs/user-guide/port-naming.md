# Port Naming

NetBox FMS names every FrontPort and RearPort it provisions with a fixed,
machine-facing identifier built from the linked `dcim.Cable`'s primary key
and the strand's absolute cable-wide fiber number. Names are the identity
layer; the human-readable identity lives in the port **label** (see
[Port Label Templates](port-label-templates.md)).

## The grammar

| Port | Name | Example |
|------|------|---------|
| FrontPort (one per strand) | `{cable.id}:F{position}` | `1043:F25` |
| RearPort for a buffer tube (loose tube) | `{cable.id}:T{n}` | `1043:T3` |
| RearPort for a ribbon | `{cable.id}:R{n}` | `1043:R2` |
| RearPort of a containerless cable (tight buffer) | `{cable.id}` | `1043` |

- `{cable.id}` is the `dcim.Cable` **primary key**, never the display
  label. The pk is immutable, so generated names are **write-once**:
  relabeling a cable re-renders port labels but never renames ports, and
  the whole class of name-drift bugs (and the 64-character truncation
  concern) disappears.
- `F{position}` is `FiberStrand.position`, the **absolute cable-wide
  fiber number** -- fiber 25 of a 12F-per-tube cable is `F25`, not "fiber
  1 of tube 3". This follows OSP record-keeping convention (ArcFM Fiber
  Manager's `FiberNumber`): a strand's identity is the cable plus its
  absolute number; tube and fiber colors are the derived human locator,
  which the label carries.
- `T{n}` is the buffer tube's position; `R{n}` numbers the ribbons across
  the whole cable in fiber order (ribbon positions restart per tube, so
  they cannot name a ribbon cable-wide).

## Rear ports mirror the physical hierarchy

Provisioning creates one RearPort per physical container:

| Construction | Rear ports |
|--------------|-----------|
| Loose tube | One per buffer tube (`{cable.id}:T{n}`), positions = fibers in the tube |
| Ribbon-in-tube | One **per ribbon** (`{cable.id}:R{n}`), positions = fibers in the ribbon |
| Central-core ribbon | One **per ribbon** (`{cable.id}:R{n}`) |
| Tight buffer | A single rear port (`{cable.id}`) covering every strand |

The ribbon is the unit a mass-fusion splicer handles, so ribbons get their
own rear ports instead of being flattened into their tube (ribbon-in-tube)
or into a single cable-wide port (central-core). The derived cable profile
and the CableTermination `connector`/`positions` values follow the same
grouping, so profile-based tracing keeps working at strand granularity.

## Converting existing data

Names are write-once, so ports provisioned under the old label-derived
scheme do not self-convert. The `convert_port_names` management command
rewrites them:

```
python manage.py convert_port_names [--cable-type <pk-or-model>] [--dry-run] [--limit N]
```

- The walk covers every FMS-provisioned port (FiberCable -> strand ->
  FrontPort -> PortMapping); `--dry-run` reports each rename without
  writing.
- Port names are unique per device. The command detects collisions before
  writing and **skips the whole cable** with a message rather than leaving
  it half-renamed.
- **Rear-port structure is not migrated.** Renames happen within the
  existing rear-port layout: a ribbon cable provisioned before the
  per-ribbon grouping keeps its tube-grouped (or single) rear ports and
  gets `{cable.id}:T{n}` (or bare `{cable.id}`) names. The per-ribbon
  structure applies to newly provisioned cables only.

After converting names, run `rerender_port_labels` if the affected ports
predate the label engine, so their labels carry the readable identity.

## Which ports FMS renames

FMS records that it touched a port (the strand's FrontPort reference) but
not whether it created it, so an adopted patch-panel port and a provisioned
splice port look alike. The conversion command tells them apart by where
the port sits:

| Front port location | Treatment |
|---------------------|-----------|
| On a module whose tray profile role is splice tray | FMS-owned: converted. Tube assignment parks ports on splice trays only. |
| At device level (no module) | FMS-owned unless its name matches one of the DeviceType's front port templates. FMS creates ports at device level and leaves them there until a tray assignment moves them. |
| On any other module (cassette, panel module, express basket) | Left alone. FMS never places ports there, so the port came from the ModuleType's templates or was moved by hand. |

A rear port follows its mapped front ports: it is converted only when every
one of them is FMS-owned, so a cassette's MPO rear port stays untouched even
though the trunk cable terminates on it.

Adoption through Link Topology never renames: the adopted ports keep the
names they were created with.
