# Massive Sample Data Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `create_sample_data` management command with a massive ISP-scale metro fiber network (~380 closures, ~630 cables, 6 cable types, routers/switches, slack loops, express splices, and 5 fiber circuits).

**Architecture:** Single management command file rewrite. The script builds the network bottom-up: infrastructure types → sites → backbone → metro rings → spurs → edge devices → slack loops → splice plans → fiber circuits. All operations use `bulk_create` where possible and wrap in `transaction.atomic()`.

**Tech Stack:** Django management command, NetBox 4.5+ models, PostgreSQL

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `netbox_fms/management/commands/create_sample_data.py` | Rewrite | Complete replacement of sample data generation |

---

## Task 1: Scaffold command, cable types, sites, device types, roles

Replace the entire file with the new command structure. This task creates all the "type" objects (FiberCableTypes with templates, DeviceTypes, DeviceRoles, Sites) but no instances yet.

**Files:**
- Rewrite: `netbox_fms/management/commands/create_sample_data.py`

- [ ] **Step 1: Write the new command scaffold**

Replace the file entirely. Read the existing file first to understand the structure, then write the new version.

The command class should have this structure:

```python
"""Create massive ISP-scale sample data for the netbox-fms plugin.

Topology: 3 Central Offices connected by dual diverse backbone routes,
each CO feeds a metro ring of 4 distribution hubs, each hub has
business ring-fed spurs and residential single-homed spurs.

Scale: ~380 closures, ~460 plant cables, ~170 patch cables, ~65 routers/switches,
~86 slack loops, 5 fiber circuits.
"""

from dcim.choices import CableTypeChoices, InterfaceTypeChoices
from dcim.models import (
    Cable,
    CableTermination,
    Device,
    DeviceRole,
    DeviceType,
    FrontPort,
    Interface,
    Manufacturer,
    Module,
    ModuleBay,
    ModuleType,
    PortMapping,
    RearPort,
    Site,
)
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction

from netbox_fms.choices import StorageMethodChoices
from netbox_fms.models import (
    BufferTubeTemplate,
    CableElementTemplate,
    ClosureCableEntry,
    FiberCable,
    FiberCableType,
    FiberCircuit,
    FiberCircuitPath,
    RibbonTemplate,
    SlackLoop,
    SplicePlan,
    SplicePlanEntry,
)

# EIA/TIA-598 colors (12 standard)
EIA_COLORS = {
    1: "0000ff", 2: "ff8000", 3: "00ff00", 4: "8b4513",
    5: "708090", 6: "ffffff", 7: "ff0000", 8: "000000",
    9: "ffff00", 10: "ee82ee", 11: "ff69b4", 12: "00ffff",
}

# CO definitions: name, slug, hub directions
CO_DEFS = [
    ("CO-Downtown", "co-downtown", ["NE", "SE", "SW", "NW"]),
    ("CO-North", "co-north", ["NE", "SE", "SW", "NW"]),
    ("CO-South", "co-south", ["NE", "SE", "SW", "NW"]),
]

# Backbone pairs: (co_a, co_b, path_label)
BACKBONE_PAIRS = [
    ("CO-Downtown", "CO-North"),
    ("CO-North", "CO-South"),
    ("CO-South", "CO-Downtown"),
]


class Command(BaseCommand):
    help = "Create massive ISP-scale sample data"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rp_ct = None
        self.fp_ct = None
        self.intf_ct = None
        # Caches
        self.sites = {}
        self.devices = {}
        self.cable_types = {}
        self.device_types = {}
        self.roles = {}
        self.tray_module_type = None
        self.cables_by_segment = {}  # label -> {cable, fiber_cable, a_device, b_device}

    @transaction.atomic
    def handle(self, *args, **options):
        self.rp_ct = ContentType.objects.get_for_model(RearPort)
        self.fp_ct = ContentType.objects.get_for_model(FrontPort)
        self.intf_ct = ContentType.objects.get_for_model(Interface)

        self._ensure_admin_user()
        self._create_manufacturer()
        self._create_cable_types()
        self._create_device_types_and_roles()
        self._create_sites()

        self._build_backbone()
        self._build_metro_rings()
        self._build_spurs()

        self._build_edge_devices()

        self._create_slack_loops()
        self._create_splice_plans()
        self._create_closure_cable_entries()
        self._create_fiber_circuits()

        self.stdout.write(self.style.SUCCESS(
            f"Sample data created: {Device.objects.count()} devices, "
            f"{Cable.objects.count()} cables, "
            f"{SlackLoop.objects.count()} slack loops, "
            f"{FiberCircuit.objects.count()} fiber circuits"
        ))
```

- [ ] **Step 2: Implement `_ensure_admin_user` and `_create_manufacturer`**

```python
    def _ensure_admin_user(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()  # noqa: N806
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "admin")
            self.stdout.write("  Created admin user")

    def _create_manufacturer(self):
        self.mfr, _ = Manufacturer.objects.get_or_create(name="Corning", defaults={"slug": "corning"})
        self.mfr_generic, _ = Manufacturer.objects.get_or_create(name="Generic", defaults={"slug": "generic"})
```

- [ ] **Step 3: Implement `_create_cable_types` — all 6 types with templates**

Create all 6 FiberCableTypes with their BufferTubeTemplates, RibbonTemplates, and CableElementTemplates.

Cable types to create:
1. **288F Backbone**: loose_tube, 24 tubes × 12F, central strength member
2. **144F Ribbon**: ribbon_in_tube, 12 tubes × 1 ribbon × 12F, central strength member
3. **96F Distribution**: loose_tube, 8 tubes × 12F, central strength member
4. **48F Branch**: loose_tube, 4 tubes × 12F, central strength member (matches existing)
5. **24F Building**: tight_buffer, 24 strands (no tubes), ripcord
6. **12F Drop**: tight_buffer, 12 strands (no tubes), ripcord

For each type, use `get_or_create` on `(manufacturer, model)`. Only create templates if the type was just created. Store in `self.cable_types` dict keyed by strand count string (e.g., `"288f"`, `"144f"`).

For the ribbon type: create BufferTubeTemplates with `fiber_count=None`, then attach a RibbonTemplate to each tube with `fiber_count=12`.

- [ ] **Step 4: Implement `_create_device_types_and_roles`**

```python
    def _create_device_types_and_roles(self):
        self.stdout.write("Creating device types and roles...")
        # Fiber plant device types
        self.device_types["odf_288"], _ = DeviceType.objects.get_or_create(
            manufacturer=self.mfr, model="ODF-288", defaults={"slug": "odf-288"})
        self.device_types["odf_96"], _ = DeviceType.objects.get_or_create(
            manufacturer=self.mfr, model="ODF-96", defaults={"slug": "odf-96"})
        self.device_types["fosc_450d"], _ = DeviceType.objects.get_or_create(
            manufacturer=self.mfr, model="FOSC-450D", defaults={"slug": "fosc-450d"})
        self.device_types["fosc_200b"], _ = DeviceType.objects.get_or_create(
            manufacturer=self.mfr, model="FOSC-200B", defaults={"slug": "fosc-200b"})
        self.device_types["wall_box"], _ = DeviceType.objects.get_or_create(
            manufacturer=self.mfr, model="Wall-Box-24", defaults={"slug": "wall-box-24"})
        # Edge device types
        self.device_types["router"], _ = DeviceType.objects.get_or_create(
            manufacturer=self.mfr_generic, model="Generic Router", defaults={"slug": "generic-router"})
        self.device_types["switch"], _ = DeviceType.objects.get_or_create(
            manufacturer=self.mfr_generic, model="Generic Switch", defaults={"slug": "generic-switch"})
        self.device_types["cpe"], _ = DeviceType.objects.get_or_create(
            manufacturer=self.mfr_generic, model="CPE Router", defaults={"slug": "cpe-router"})

        # Roles
        for key, name, slug in [
            ("co", "Central Office", "central-office"),
            ("hub", "Distribution Hub", "distribution-hub"),
            ("closure", "Splice Closure", "splice-closure"),
            ("panel", "Patch Panel", "patch-panel"),
            ("router", "Router", "router"),
            ("switch", "Switch", "switch"),
            ("cpe", "CPE", "cpe"),
        ]:
            self.roles[key], _ = DeviceRole.objects.get_or_create(name=name, defaults={"slug": slug})

        # Tray module type
        self.tray_module_type, _ = ModuleType.objects.get_or_create(
            manufacturer=self.mfr, model="24F Splice Tray", defaults={})
```

- [ ] **Step 5: Implement `_create_sites`**

Create sites for all 3 COs, 12 hubs, and ~20 neighborhoods.

```python
    def _create_sites(self):
        self.stdout.write("Creating sites...")
        # CO sites
        for co_name, co_slug, _ in CO_DEFS:
            self.sites[co_slug], _ = Site.objects.get_or_create(
                name=co_name.replace("CO-", ""), defaults={"slug": co_slug})

        # Hub sites: 4 per CO
        for co_name, co_slug, directions in CO_DEFS:
            co_short = co_slug.replace("co-", "")
            for d in directions:
                slug = f"{co_short}-hub-{d.lower()}"
                name = f"{co_name.replace('CO-', '')} Hub {d}"
                self.sites[slug], _ = Site.objects.get_or_create(name=name, defaults={"slug": slug})

        # Neighborhood sites for spurs
        neighborhoods = [
            "elm-st", "oak-ave", "maple-dr", "pine-rd", "cedar-ln",
            "birch-ct", "walnut-st", "spruce-ave", "ash-blvd", "cherry-way",
            "willow-ln", "poplar-dr", "hickory-rd", "beech-st", "cypress-ct",
            "magnolia-ave", "dogwood-ln", "sycamore-rd", "juniper-st", "hemlock-dr",
        ]
        for co_name, co_slug, _ in CO_DEFS:
            co_short = co_slug.replace("co-", "")
            for i, hood in enumerate(neighborhoods[:7]):  # ~7 neighborhoods per CO
                slug = f"{co_short}-{hood}"
                name = f"{co_name.replace('CO-', '')} {hood.replace('-', ' ').title()}"
                self.sites[slug], _ = Site.objects.get_or_create(name=name, defaults={"slug": slug})

        self.stdout.write(f"  Created {len(self.sites)} sites")
```

- [ ] **Step 6: Run the command to verify scaffold works**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py create_sample_data
```

Expected: Creates admin user, manufacturer, 6 cable types (with templates), device types, roles, and sites. No cables or devices yet.

- [ ] **Step 7: Verify cable types have correct template counts**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "
import django; django.setup()
from netbox_fms.models import FiberCableType
for fct in FiberCableType.objects.all():
    tubes = fct.buffer_tube_templates.count()
    ribbons = fct.ribbon_templates.count()
    print(f'{fct}: {fct.strand_count}F, {tubes} tubes, {ribbons} ribbons')
"
```

Expected output showing all 6 types with correct strand counts and template counts.

- [ ] **Step 8: Commit**

```bash
git add netbox_fms/management/commands/create_sample_data.py
git commit -m "feat: scaffold massive sample data command with cable types and sites"
```

---

## Task 2: Build backbone layer

Add methods to create the 3 CO devices, 6 backbone routes (2 per CO pair), and ~54 closures with ports and strand linking.

**Files:**
- Modify: `netbox_fms/management/commands/create_sample_data.py`

- [ ] **Step 1: Implement helper methods for device/cable creation**

These are reusable helpers used by backbone, metro, and spur builders:

```python
    def _get_or_create_device(self, name, site_slug, role_key, dtype_key):
        """Get or create a device, caching in self.devices."""
        if name in self.devices:
            return self.devices[name]
        device, _ = Device.objects.get_or_create(
            name=name,
            defaults={
                "site": self.sites[site_slug],
                "role": self.roles[role_key],
                "device_type": self.device_types[dtype_key],
            },
        )
        self.devices[name] = device
        return device

    def _create_tray_modules(self, device, num_trays):
        """Create splice tray modules on a device (if they don't exist)."""
        if device.modules.exists():
            return list(Module.objects.filter(device=device).order_by("module_bay__position"))
        trays = []
        for i in range(1, num_trays + 1):
            bay, _ = ModuleBay.objects.get_or_create(
                device=device, name=f"Tray Slot {i}", defaults={"position": str(i)})
            mod, _ = Module.objects.get_or_create(
                device=device, module_bay=bay, defaults={"module_type": self.tray_module_type, "status": "active"})
            trays.append(mod)
        return trays

    def _create_cable_segment(self, label, a_device, b_device, cable_type_key, length_m):
        """Create a cable with FiberCable between two devices.

        Does NOT create terminations (ports) — that happens in the port-building step.
        Returns dict with cable info and stores in self.cables_by_segment.
        """
        if label in self.cables_by_segment:
            return self.cables_by_segment[label]

        existing = Cable.objects.filter(label=label).first()
        if existing:
            info = {
                "cable": existing,
                "fiber_cable": FiberCable.objects.filter(cable=existing).first(),
                "a_device": a_device,
                "b_device": b_device,
                "cable_type_key": cable_type_key,
            }
            self.cables_by_segment[label] = info
            return info

        cable = Cable(
            type=CableTypeChoices.TYPE_SMF_OS2,
            label=label,
            length=length_m,
            length_unit="m",
            color="ffeb3b",
        )
        cable.save()

        fc = FiberCable.objects.create(
            cable=cable,
            fiber_cable_type=self.cable_types[cable_type_key],
            serial_number=f"SN-{label.replace(' ', '-')}",
        )

        info = {
            "cable": cable,
            "fiber_cable": fc,
            "a_device": a_device,
            "b_device": b_device,
            "cable_type_key": cable_type_key,
        }
        self.cables_by_segment[label] = info
        return info

    def _create_ports_and_link_strands(self, cable_info):
        """Create RearPorts, FrontPorts, PortMappings on both sides of a cable.
        Link FiberStrands to FrontPorts. Uses bulk_create for performance."""
        cable = cable_info["cable"]
        fc = cable_info["fiber_cable"]
        if not fc:
            return

        for device, cable_end, fk_field in [
            (cable_info["a_device"], "A", "front_port_a"),
            (cable_info["b_device"], "B", "front_port_b"),
        ]:
            # Skip if terminations already exist
            existing = CableTermination.objects.filter(
                cable=cable, cable_end=cable_end, termination_type=self.rp_ct)
            if existing.exists():
                continue

            tubes = list(fc.buffer_tubes.all().order_by("position"))
            strands = list(fc.fiber_strands.all().order_by("position"))
            trays = list(Module.objects.filter(device=device).order_by("module_bay__position"))

            if tubes:
                for tube_idx, tube in enumerate(tubes):
                    tray = trays[tube_idx % len(trays)] if trays else None
                    tube_strands = [s for s in strands if s.buffer_tube_id == tube.pk]

                    rp = RearPort.objects.create(
                        device=device, module=tray,
                        name=f"#{cable.pk}:T{tube.position}",
                        type="splice", positions=len(tube_strands),
                    )
                    CableTermination.objects.create(
                        cable=cable, cable_end=cable_end,
                        termination_type=self.rp_ct, termination_id=rp.pk,
                    )

                    fps_to_create = []
                    pms_to_create = []
                    for pos_in_tube, strand in enumerate(tube_strands, 1):
                        fp = FrontPort(
                            device=device, module=tray,
                            name=f"#{cable.pk}:T{tube.position}:F{strand.position}",
                            type="splice",
                            color=EIA_COLORS.get(pos_in_tube, "cccccc"),
                        )
                        fps_to_create.append((fp, rp, pos_in_tube, strand))

                    # Bulk create FrontPorts
                    fp_objects = FrontPort.objects.bulk_create([f[0] for f in fps_to_create])
                    for fp_obj, (_, rp_ref, pos, strand) in zip(fp_objects, fps_to_create, strict=False):
                        pms_to_create.append(PortMapping(
                            device=device, front_port=fp_obj, rear_port=rp_ref,
                            front_port_position=1, rear_port_position=pos,
                        ))
                        setattr(strand, fk_field, fp_obj)

                    PortMapping.objects.bulk_create(pms_to_create)
                    # Bulk update strands
                    from netbox_fms.models import FiberStrand
                    FiberStrand.objects.bulk_update(tube_strands, [fk_field])
            else:
                # Tight buffer (no tubes)
                tray = trays[0] if trays else None
                rp = RearPort.objects.create(
                    device=device, module=tray,
                    name=f"#{cable.pk}",
                    type="splice", positions=len(strands),
                )
                CableTermination.objects.create(
                    cable=cable, cable_end=cable_end,
                    termination_type=self.rp_ct, termination_id=rp.pk,
                )

                fps_to_create = []
                pms_to_create = []
                for strand in strands:
                    fp = FrontPort(
                        device=device, module=tray,
                        name=f"#{cable.pk}:F{strand.position}",
                        type="splice",
                        color=EIA_COLORS.get(strand.position, "cccccc"),
                    )
                    fps_to_create.append((fp, rp, strand.position, strand))

                fp_objects = FrontPort.objects.bulk_create([f[0] for f in fps_to_create])
                for fp_obj, (_, rp_ref, pos, strand) in zip(fp_objects, fps_to_create, strict=False):
                    pms_to_create.append(PortMapping(
                        device=device, front_port=fp_obj, rear_port=rp_ref,
                        front_port_position=1, rear_port_position=pos,
                    ))
                    setattr(strand, fk_field, fp_obj)

                PortMapping.objects.bulk_create(pms_to_create)
                from netbox_fms.models import FiberStrand
                FiberStrand.objects.bulk_update(strands, [fk_field])
```

- [ ] **Step 2: Implement `_build_backbone`**

Creates 3 CO ODF devices, then for each CO pair, builds 2 diverse routes (Path A with 288F, Path B with 144F) with intermediate closures.

```python
    def _build_backbone(self):
        self.stdout.write("Building backbone...")
        # Create CO ODF devices
        for co_name, co_slug, _ in CO_DEFS:
            self._get_or_create_device(co_name, co_slug, "co", "odf_288")

        # Build 6 backbone routes (3 pairs × 2 paths)
        for co_a_name, co_b_name in BACKBONE_PAIRS:
            co_a_slug = co_a_name.lower().replace("-", "-", 1).replace("co-", "co-")
            co_b_slug = co_b_name.lower().replace("-", "-", 1).replace("co-", "co-")

            # Derive short names for labels
            a_short = co_a_name.replace("CO-", "")[:2].upper()  # DT, NO, SO
            b_short = co_b_name.replace("CO-", "")[:2].upper()

            # Path A: 288F, 10 closures
            self._build_backbone_path(
                co_a_name, co_b_name, co_a_slug, co_b_slug,
                path_label="A", cable_type_key="288f",
                num_closures=10, a_short=a_short, b_short=b_short,
            )
            # Path B: 144F, 8 closures
            self._build_backbone_path(
                co_a_name, co_b_name, co_a_slug, co_b_slug,
                path_label="B", cable_type_key="144f",
                num_closures=8, a_short=a_short, b_short=b_short,
            )

    def _build_backbone_path(self, co_a_name, co_b_name, co_a_slug, co_b_slug,
                              path_label, cable_type_key, num_closures, a_short, b_short):
        """Build one backbone path between two COs with intermediate closures."""
        # Use the site of co_a for all intermediate closures (simplification)
        closures = []
        for i in range(1, num_closures + 1):
            name = f"BB-{a_short}-{b_short}-{path_label}-{i:02d}"
            device = self._get_or_create_device(name, co_a_slug, "closure", "fosc_450d")
            num_trays = 24 if cable_type_key == "288f" else 12
            self._create_tray_modules(device, min(num_trays, 8))  # Cap at 8 trays
            closures.append(device)

        # Build chain: CO-A → closure-1 → ... → closure-N → CO-B
        chain = [self.devices[co_a_name]] + closures + [self.devices[co_b_name]]
        for i in range(len(chain) - 1):
            dev_a, dev_b = chain[i], chain[i + 1]
            seg_label = f"{dev_a.name} → {dev_b.name}"
            length = 800 + (hash(seg_label) % 3000)  # 800-3800m
            info = self._create_cable_segment(seg_label, dev_a, dev_b, cable_type_key, length)
            self._create_ports_and_link_strands(info)

        self.stdout.write(f"  Backbone {a_short}→{b_short} Path {path_label}: {num_closures} closures, {num_closures + 1} cables")
```

- [ ] **Step 3: Run command to verify backbone builds**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py create_sample_data
```

Expected: Creates 3 COs + ~54 backbone closures + ~60 backbone cables. Check output counts.

- [ ] **Step 4: Commit**

```bash
git add netbox_fms/management/commands/create_sample_data.py
git commit -m "feat: sample data backbone layer with dual diverse routes"
```

---

## Task 3: Build metro rings and spur routes

Add methods for metro ring (COs → hubs → closures → COs) and spur routes (business ring-fed + residential single-homed).

**Files:**
- Modify: `netbox_fms/management/commands/create_sample_data.py`

- [ ] **Step 1: Implement `_build_metro_rings`**

For each CO, create 4 hubs and connect them in a ring with 96F cables and ~5 closures between each pair.

```python
    def _build_metro_rings(self):
        self.stdout.write("Building metro rings...")
        for co_name, co_slug, directions in CO_DEFS:
            co_short = co_slug.replace("co-", "")
            hub_names = []
            for d in directions:
                hub_name = f"Hub-{co_short.title()}-{d}"
                hub_slug = f"{co_short}-hub-{d.lower()}"
                self._get_or_create_device(hub_name, hub_slug, "hub", "odf_96")
                self._create_tray_modules(self.devices[hub_name], 8)
                hub_names.append(hub_name)

            # Ring: CO → Hub1 → Hub2 → Hub3 → Hub4 → CO
            ring = [co_name] + hub_names + [co_name]
            for i in range(len(ring) - 1):
                dev_a_name, dev_b_name = ring[i], ring[i + 1]
                # Don't duplicate the return-to-CO segment label
                seg_prefix = f"MR-{co_short.title()}"
                self._build_metro_segment(
                    dev_a_name, dev_b_name, seg_prefix,
                    num_closures=5, co_slug=co_slug,
                )

    def _build_metro_segment(self, dev_a_name, dev_b_name, seg_prefix, num_closures, co_slug):
        """Build a metro ring segment with intermediate closures."""
        closures = []
        for i in range(1, num_closures + 1):
            name = f"{seg_prefix}-{dev_a_name[-2:]}-{dev_b_name[-2:]}-{i:02d}"
            device = self._get_or_create_device(name, co_slug, "closure", "fosc_450d")
            self._create_tray_modules(device, 4)
            closures.append(device)

        chain = [self.devices[dev_a_name]] + closures + [self.devices[dev_b_name]]
        for i in range(len(chain) - 1):
            seg_label = f"{chain[i].name} → {chain[i + 1].name}"
            length = 200 + (hash(seg_label) % 1500)
            info = self._create_cable_segment(seg_label, chain[i], chain[i + 1], "96f", length)
            self._create_ports_and_link_strands(info)
```

- [ ] **Step 2: Implement `_build_spurs`**

For each hub, create 1 business ring-fed spur and 2 residential single-homed spurs.

```python
    def _build_spurs(self):
        self.stdout.write("Building spur routes...")
        hub_devices = {n: d for n, d in self.devices.items() if n.startswith("Hub-")}

        for hub_name, hub_device in hub_devices.items():
            co_short = hub_name.split("-")[1].lower()
            hub_dir = hub_name.split("-")[-1]

            # Business spur: ring-fed back to an adjacent hub
            self._build_business_spur(hub_name, co_short, hub_dir)

            # 2 residential spurs
            for spur_idx in range(1, 3):
                self._build_residential_spur(hub_name, co_short, hub_dir, spur_idx)

    def _build_business_spur(self, hub_name, co_short, hub_dir):
        """Build a ring-fed business spur (~8 closures, loops back to a different hub)."""
        # Find an adjacent hub to loop back to
        all_hubs = [n for n in self.devices if n.startswith(f"Hub-{co_short.title()}-")]
        adj_hub = None
        for h in all_hubs:
            if h != hub_name:
                adj_hub = h
                break
        if not adj_hub:
            return

        site_slug = f"{co_short}-hub-{hub_dir.lower()}"
        num_closures = 8
        closures = []
        for i in range(1, num_closures + 1):
            name = f"BS-{co_short[:2].upper()}-{hub_dir}-{i:02d}"
            device = self._get_or_create_device(name, site_slug, "closure", "fosc_200b")
            self._create_tray_modules(device, 4)
            closures.append(device)

        # Ring: hub → closures → adj_hub
        chain = [self.devices[hub_name]] + closures + [self.devices[adj_hub]]
        for i in range(len(chain) - 1):
            seg_label = f"{chain[i].name} → {chain[i + 1].name}"
            length = 100 + (hash(seg_label) % 800)
            info = self._create_cable_segment(seg_label, chain[i], chain[i + 1], "48f", length)
            self._create_ports_and_link_strands(info)

    def _build_residential_spur(self, hub_name, co_short, hub_dir, spur_idx):
        """Build a single-homed residential spur (5-10 closures from hub)."""
        site_slug = f"{co_short}-hub-{hub_dir.lower()}"
        num_closures = 5 + (hash(f"{hub_name}-{spur_idx}") % 6)  # 5-10
        closures = []
        for i in range(1, num_closures + 1):
            name = f"RS-{co_short[:2].upper()}-{hub_dir}-S{spur_idx}-{i:02d}"
            device = self._get_or_create_device(name, site_slug, "closure", "fosc_200b")
            self._create_tray_modules(device, 4)
            closures.append(device)

        # Linear: hub → closures (no loop back)
        chain = [self.devices[hub_name]] + closures
        for i in range(len(chain) - 1):
            seg_label = f"{chain[i].name} → {chain[i + 1].name}"
            length = 50 + (hash(seg_label) % 500)
            info = self._create_cable_segment(seg_label, chain[i], chain[i + 1], "48f", length)
            self._create_ports_and_link_strands(info)

        # Add drop cables from some spur closures to buildings
        for i, closure in enumerate(closures):
            if i % 3 == 0:  # Every 3rd closure gets a drop
                bldg_name = f"Bldg-{closure.name}"
                bldg = self._get_or_create_device(bldg_name, site_slug, "panel", "wall_box")
                seg_label = f"{closure.name} → {bldg_name}"
                drop_type = "12f" if spur_idx == 1 else "24f"
                info = self._create_cable_segment(seg_label, closure, bldg, drop_type, 30 + (hash(seg_label) % 100))
                self._create_ports_and_link_strands(info)
```

- [ ] **Step 3: Run and verify**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py create_sample_data
```

Expected: Creates hubs, spur closures, building panels, and all cables. Total devices should be ~380+.

- [ ] **Step 4: Commit**

```bash
git add netbox_fms/management/commands/create_sample_data.py
git commit -m "feat: sample data metro rings and spur routes"
```

---

## Task 4: Build edge devices, slack loops, splice plans, closure entries, fiber circuits

Add routers/switches/CPE with patch cables, slack loops, splice plans with express entries, closure cable entries, and 5 fiber circuits.

**Files:**
- Modify: `netbox_fms/management/commands/create_sample_data.py`

- [ ] **Step 1: Implement `_build_edge_devices`**

Create routers at COs, switches at hubs, CPE at buildings. Create LC interfaces and patch cables.

```python
    def _build_edge_devices(self):
        self.stdout.write("Building edge devices and patch cables...")

        # CO core routers: 48 LC interfaces, patch ~12 to ODF FrontPorts
        for co_name, co_slug, _ in CO_DEFS:
            router_name = f"{co_name}-Router"
            router = self._get_or_create_device(router_name, co_slug, "router", "router")
            intfs = self._create_interfaces(router, 48, "xe-0/0/")
            self._patch_interfaces_to_odf(router, self.devices[co_name], intfs[:12])

        # Hub aggregation switches: 24 LC interfaces, patch ~8
        for name, device in list(self.devices.items()):
            if not name.startswith("Hub-"):
                continue
            sw_name = f"{name}-Switch"
            site_slug = next(
                (s for s in self.sites if self.sites[s] == device.site), None
            )
            if not site_slug:
                continue
            sw = self._get_or_create_device(sw_name, site_slug, "switch", "switch")
            intfs = self._create_interfaces(sw, 24, "ge-0/0/")
            self._patch_interfaces_to_odf(sw, device, intfs[:8])

        # CPE routers at buildings: 2 LC interfaces, patch 1
        for name, device in list(self.devices.items()):
            if not name.startswith("Bldg-"):
                continue
            cpe_name = f"CPE-{name.replace('Bldg-', '')}"
            site_slug = next(
                (s for s in self.sites if self.sites[s] == device.site), None
            )
            if not site_slug:
                continue
            cpe = self._get_or_create_device(cpe_name, site_slug, "cpe", "cpe")
            intfs = self._create_interfaces(cpe, 2, "eth")
            self._patch_interfaces_to_odf(cpe, device, intfs[:1])

    def _create_interfaces(self, device, count, prefix):
        """Create LC interfaces on a device if they don't exist."""
        if Interface.objects.filter(device=device).exists():
            return list(Interface.objects.filter(device=device).order_by("name"))
        intfs = []
        for i in range(count):
            intfs.append(Interface(
                device=device, name=f"{prefix}{i}",
                type=InterfaceTypeChoices.TYPE_10GE_SFP_PLUS,
            ))
        return Interface.objects.bulk_create(intfs)

    def _patch_interfaces_to_odf(self, edge_device, odf_device, interfaces):
        """Create patch cables from interfaces to available FrontPorts on ODF."""
        available_fps = list(
            FrontPort.objects.filter(device=odf_device)
            .exclude(cable_terminations__isnull=False)
            .order_by("name")[:len(interfaces)]
        )
        for intf, fp in zip(interfaces, available_fps, strict=False):
            # Check if interface already has a cable
            if CableTermination.objects.filter(
                termination_type=self.intf_ct, termination_id=intf.pk
            ).exists():
                continue
            cable = Cable(
                a_terminations=[intf],
                b_terminations=[fp],
                type=CableTypeChoices.TYPE_SMF_OS2,
                length=1,
                length_unit="m",
                label=f"Patch: {intf.device.name}:{intf.name}",
                color="2196f3",
            )
            cable.save()
```

- [ ] **Step 2: Implement `_create_slack_loops`**

```python
    def _create_slack_loops(self):
        self.stdout.write("Creating slack loops...")
        from dcim.choices import CableLengthUnitChoices
        from decimal import Decimal

        loops = []
        storage_cycle = [
            StorageMethodChoices.COIL, StorageMethodChoices.IN_VAULT,
            StorageMethodChoices.FIGURE_8, StorageMethodChoices.ON_POLE,
            StorageMethodChoices.IN_TRAY,
        ]

        for label, info in self.cables_by_segment.items():
            fc = info["fiber_cable"]
            if not fc:
                continue
            a_device = info["a_device"]

            # Backbone: every 3rd closure
            is_backbone = label.startswith("BB-") or a_device.name.startswith("BB-")
            is_residential = a_device.name.startswith("RS-")
            is_business = a_device.name.startswith("BS-")

            should_add = False
            if is_backbone and hash(label) % 3 == 0:
                should_add = True
                start = Decimal(str(500 + hash(label) % 1500))
                end = start + Decimal(str(10 + hash(label) % 30))
            elif is_residential and hash(label) % 3 == 0:
                should_add = True
                start = Decimal(str(50 + hash(label) % 400))
                end = start + Decimal(str(5 + hash(label) % 20))
            elif is_business and hash(label) % 4 == 0:
                should_add = True
                start = Decimal(str(100 + hash(label) % 600))
                end = start + Decimal(str(8 + hash(label) % 25))

            if should_add:
                loops.append(SlackLoop(
                    fiber_cable=fc,
                    site=a_device.site,
                    start_mark=start,
                    end_mark=end,
                    length_unit=CableLengthUnitChoices.UNIT_METER,
                    storage_method=storage_cycle[len(loops) % len(storage_cycle)],
                ))

        SlackLoop.objects.bulk_create(loops, ignore_conflicts=True)
        self.stdout.write(f"  Created {len(loops)} slack loops")
```

- [ ] **Step 3: Implement `_create_splice_plans`**

Same pattern as the old script but with `is_express` support for backbone pass-through closures.

```python
    def _create_splice_plans(self):
        self.stdout.write("Creating splice plans...")
        closures = {n: d for n, d in self.devices.items()
                    if n.startswith(("BB-", "MR-", "BS-", "RS-"))}
        plans_created = 0

        for name, closure in closures.items():
            if SplicePlan.objects.filter(closure=closure).exists():
                continue

            plan = SplicePlan.objects.create(
                closure=closure, name=f"{name} Plan",
                description=f"Splice plan for {name}", status="draft",
            )

            # Group FrontPorts by cable
            fps_by_cable = {}
            for fp in FrontPort.objects.filter(device=closure, module__isnull=False).order_by("name"):
                if fp.name.startswith("#"):
                    try:
                        cable_pk = int(fp.name.split(":")[0][1:])
                        fps_by_cable.setdefault(cable_pk, []).append(fp)
                    except (ValueError, IndexError):
                        pass

            cable_pks = sorted(fps_by_cable.keys())
            if len(cable_pks) < 2:
                continue

            # Determine if this is a backbone pass-through
            is_backbone_passthrough = name.startswith("BB-")

            entries = []
            cable_a_fps = fps_by_cable[cable_pks[0]]
            cable_b_fps = fps_by_cable[cable_pks[1]]

            # Splice tube-for-tube (12 strands at a time)
            for fp_a, fp_b in zip(cable_a_fps[:48], cable_b_fps[:48], strict=False):
                tray = fp_a.module
                if tray:
                    # Backbone: first 24 strands are express (2 tubes cut, rest through)
                    is_express = is_backbone_passthrough and fp_a.name.split(":")[1] > "T02"
                    entries.append(SplicePlanEntry(
                        plan=plan, tray=tray, fiber_a=fp_a, fiber_b=fp_b,
                        is_express=is_express,
                    ))

            # Third cable if present
            if len(cable_pks) >= 3:
                cable_c_fps = fps_by_cable[cable_pks[2]]
                remaining_b = cable_b_fps[48:] if len(cable_b_fps) > 48 else cable_b_fps[12:]
                for fp_c, fp_b in zip(cable_c_fps[:12], remaining_b[:12], strict=False):
                    tray = fp_c.module
                    if tray:
                        entries.append(SplicePlanEntry(
                            plan=plan, tray=tray, fiber_a=fp_c, fiber_b=fp_b,
                        ))

            SplicePlanEntry.objects.bulk_create(entries, ignore_conflicts=True)
            plans_created += 1

        self.stdout.write(f"  Created {plans_created} splice plans")
```

- [ ] **Step 4: Implement `_create_closure_cable_entries`**

```python
    def _create_closure_cable_entries(self):
        self.stdout.write("Creating closure cable entries...")
        entries = []
        for label, info in self.cables_by_segment.items():
            fc = info["fiber_cable"]
            if not fc:
                continue
            for device in [info["a_device"], info["b_device"]]:
                if device.name.startswith(("BB-", "MR-", "BS-", "RS-", "SC-")):
                    if not ClosureCableEntry.objects.filter(closure=device, fiber_cable=fc).exists():
                        entries.append(ClosureCableEntry(
                            closure=device, fiber_cable=fc,
                            entrance_label=f"Port {len(entries) % 8 + 1}",
                        ))
        ClosureCableEntry.objects.bulk_create(entries, ignore_conflicts=True)
        self.stdout.write(f"  Created {len(entries)} closure cable entries")
```

- [ ] **Step 5: Implement `_create_fiber_circuits`**

Create 5 sample circuits. These are just the FiberCircuit + FiberCircuitPath records — the actual tracing uses `FiberCircuitPath.from_origin()`.

```python
    def _create_fiber_circuits(self):
        self.stdout.write("Creating fiber circuits...")
        if FiberCircuit.objects.exists():
            self.stdout.write("  Skipping — circuits already exist")
            return

        circuits_to_create = [
            ("Backbone DT→NO Path A", "BB-DT-NO-001", 1),
            ("Metro Downtown Ring", "MR-DT-001", 1),
            ("Spur North Business", "BS-NO-001", 1),
            ("Cross-CO NO→SO", "BB-NO-SO-001", 1),
            ("Last-Mile Drop", "DROP-001", 1),
        ]

        for name, cid, strand_count in circuits_to_create:
            circuit = FiberCircuit.objects.create(
                name=name, cid=cid, strand_count=strand_count,
                status="active",
                description=f"Sample circuit: {name}",
            )
            self.stdout.write(f"  Created circuit: {name}")
```

- [ ] **Step 6: Run and verify full generation**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py create_sample_data
```

Expected: Full output showing all layers created. Verify counts match spec targets (~380 closures, ~460 plant cables, ~170 patch cables, ~86 slack loops, 5 circuits).

- [ ] **Step 7: Verify specific features**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "
import django; django.setup()
from netbox_fms.models import *
from dcim.models import Device, Cable, Interface

print(f'Devices: {Device.objects.count()}')
print(f'Cables: {Cable.objects.count()}')
print(f'FiberCables: {FiberCable.objects.count()}')
print(f'SlackLoops: {SlackLoop.objects.count()}')
print(f'SplicePlans: {SplicePlan.objects.count()}')
print(f'Express entries: {SplicePlanEntry.objects.filter(is_express=True).count()}')
print(f'ClosureCableEntries: {ClosureCableEntry.objects.count()}')
print(f'FiberCircuits: {FiberCircuit.objects.count()}')
print(f'Interfaces: {Interface.objects.count()}')
print(f'Routers: {Device.objects.filter(role__slug=\"router\").count()}')
print(f'Switches: {Device.objects.filter(role__slug=\"switch\").count()}')
print(f'CPEs: {Device.objects.filter(role__slug=\"cpe\").count()}')
"
```

- [ ] **Step 8: Run existing tests to verify no regressions**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v
```

Expected: All tests pass.

- [ ] **Step 9: Lint and format**

```bash
ruff check --fix netbox_fms/management/commands/create_sample_data.py
ruff format netbox_fms/management/commands/create_sample_data.py
```

- [ ] **Step 10: Commit**

```bash
git add netbox_fms/management/commands/create_sample_data.py
git commit -m "feat: complete massive sample data with edge devices, slack loops, express splices, and circuits"
```
