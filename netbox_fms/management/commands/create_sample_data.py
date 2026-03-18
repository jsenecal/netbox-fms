"""Create massive ISP-scale sample data for the netbox-fms plugin.

Topology: 3 Central Offices connected by dual diverse backbone routes,
each CO feeds a metro ring of 4 distribution hubs, each hub has
business ring-fed spurs and residential single-homed spurs.

Scale: ~380 closures, ~460 plant cables, ~170 patch cables, ~65 routers/switches,
~86 slack loops, 5 fiber circuits.
"""

from dcim.choices import CableTypeChoices
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

from netbox_fms.models import (
    BufferTubeTemplate,
    CableElementTemplate,
    FiberCable,
    FiberCableType,
    FiberCircuit,
    FiberStrand,
    RibbonTemplate,
    SlackLoop,
)

# EIA/TIA-598 colors (12 standard)
EIA_COLORS = {
    1: "0000ff",
    2: "ff8000",
    3: "00ff00",
    4: "8b4513",
    5: "708090",
    6: "ffffff",
    7: "ff0000",
    8: "000000",
    9: "ffff00",
    10: "ee82ee",
    11: "ff69b4",
    12: "00ffff",
}

# CO definitions: name, slug, hub directions
CO_DEFS = [
    ("CO-Downtown", "co-downtown", ["NE", "SE", "SW", "NW"]),
    ("CO-North", "co-north", ["NE", "SE", "SW", "NW"]),
    ("CO-South", "co-south", ["NE", "SE", "SW", "NW"]),
]

# Backbone pairs: (co_a, co_b)
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
        self.mfr = None
        self.mfr_generic = None
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

        self.stdout.write(
            self.style.SUCCESS(
                f"Sample data created: {Device.objects.count()} devices, "
                f"{Cable.objects.count()} cables, "
                f"{SlackLoop.objects.count()} slack loops, "
                f"{FiberCircuit.objects.count()} fiber circuits"
            )
        )

    # ------------------------------------------------------------------
    # Setup: users, manufacturers, types
    # ------------------------------------------------------------------

    def _ensure_admin_user(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()  # noqa: N806
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "admin")
            self.stdout.write("  Created admin user")

    def _create_manufacturer(self):
        self.mfr, _ = Manufacturer.objects.get_or_create(name="Corning", defaults={"slug": "corning"})
        self.mfr_generic, _ = Manufacturer.objects.get_or_create(name="Generic", defaults={"slug": "generic"})

    def _create_cable_types(self):
        self.stdout.write("Creating cable types...")

        # 1. 288F Backbone: loose_tube, 24 tubes x 12F
        fct, created = FiberCableType.objects.get_or_create(
            manufacturer=self.mfr,
            model="ALTOS 288TCF-14180D20",
            defaults={
                "part_number": "288TCF-14180D20",
                "construction": "loose_tube",
                "fiber_type": "smf_os2",
                "strand_count": 288,
                "sheath_material": "pe",
                "jacket_color": "000000",
                "deployment": "duct",
            },
        )
        if created:
            for t in range(1, 25):
                color_idx = ((t - 1) % 12) + 1
                BufferTubeTemplate.objects.create(
                    fiber_cable_type=fct,
                    name=f"T{t}",
                    position=t,
                    color=EIA_COLORS[color_idx],
                    fiber_count=12,
                )
            CableElementTemplate.objects.create(
                fiber_cable_type=fct, name="Central Strength Member", element_type="central_member"
            )
        self.cable_types["288f"] = fct

        # 2. 144F Ribbon: ribbon_in_tube, 12 tubes x 1 ribbon x 12F
        fct, created = FiberCableType.objects.get_or_create(
            manufacturer=self.mfr,
            model="ALTOS 144RCF-14180D20",
            defaults={
                "part_number": "144RCF-14180D20",
                "construction": "ribbon_in_tube",
                "fiber_type": "smf_os2",
                "strand_count": 144,
                "sheath_material": "pe",
                "jacket_color": "000000",
                "deployment": "duct",
            },
        )
        if created:
            for t in range(1, 13):
                btt = BufferTubeTemplate.objects.create(
                    fiber_cable_type=fct,
                    name=f"T{t}",
                    position=t,
                    color=EIA_COLORS[t],
                    fiber_count=None,
                )
                RibbonTemplate.objects.create(
                    fiber_cable_type=fct,
                    buffer_tube_template=btt,
                    name=f"T{t}-R1",
                    position=1,
                    color=EIA_COLORS[t],
                    fiber_count=12,
                )
            CableElementTemplate.objects.create(
                fiber_cable_type=fct, name="Central Strength Member", element_type="central_member"
            )
        self.cable_types["144f"] = fct

        # 3. 96F Distribution: loose_tube, 8 tubes x 12F
        fct, created = FiberCableType.objects.get_or_create(
            manufacturer=self.mfr,
            model="ALTOS 096TCF-14180D20",
            defaults={
                "part_number": "096TCF-14180D20",
                "construction": "loose_tube",
                "fiber_type": "smf_os2",
                "strand_count": 96,
                "sheath_material": "pe",
                "jacket_color": "000000",
                "deployment": "duct",
            },
        )
        if created:
            for t in range(1, 9):
                BufferTubeTemplate.objects.create(
                    fiber_cable_type=fct,
                    name=f"T{t}",
                    position=t,
                    color=EIA_COLORS[t],
                    fiber_count=12,
                )
            CableElementTemplate.objects.create(
                fiber_cable_type=fct, name="Central Strength Member", element_type="central_member"
            )
        self.cable_types["96f"] = fct

        # 4. 48F Branch: loose_tube, 4 tubes x 12F
        fct, created = FiberCableType.objects.get_or_create(
            manufacturer=self.mfr,
            model="ALTOS 048TCF-14180D20",
            defaults={
                "part_number": "048TCF-14180D20",
                "construction": "loose_tube",
                "fiber_type": "smf_os2",
                "strand_count": 48,
                "sheath_material": "pe",
                "jacket_color": "000000",
                "deployment": "duct",
            },
        )
        if created:
            for t in range(1, 5):
                BufferTubeTemplate.objects.create(
                    fiber_cable_type=fct,
                    name=f"T{t}",
                    position=t,
                    color=EIA_COLORS[t],
                    fiber_count=12,
                )
            CableElementTemplate.objects.create(
                fiber_cable_type=fct, name="Central Strength Member", element_type="central_member"
            )
        self.cable_types["48f"] = fct

        # 5. 24F Building: tight_buffer, 24 strands (no tubes)
        fct, created = FiberCableType.objects.get_or_create(
            manufacturer=self.mfr,
            model="MIC 024TCF-14190D20",
            defaults={
                "part_number": "024TCF-14190D20",
                "construction": "tight_buffer",
                "fiber_type": "smf_os2",
                "strand_count": 24,
                "sheath_material": "lszh",
                "jacket_color": "ffff00",
                "deployment": "indoor",
            },
        )
        if created:
            CableElementTemplate.objects.create(fiber_cable_type=fct, name="Ripcord", element_type="ripcord")
        self.cable_types["24f"] = fct

        # 6. 12F Drop: tight_buffer, 12 strands (no tubes)
        fct, created = FiberCableType.objects.get_or_create(
            manufacturer=self.mfr,
            model="MIC 012TCF-14190D20",
            defaults={
                "part_number": "012TCF-14190D20",
                "construction": "tight_buffer",
                "fiber_type": "smf_os2",
                "strand_count": 12,
                "sheath_material": "lszh",
                "jacket_color": "ffff00",
                "deployment": "indoor",
            },
        )
        if created:
            CableElementTemplate.objects.create(fiber_cable_type=fct, name="Ripcord", element_type="ripcord")
        self.cable_types["12f"] = fct

        self.stdout.write(f"  Created {len(self.cable_types)} cable types")

    def _create_device_types_and_roles(self):
        self.stdout.write("Creating device types and roles...")
        # Fiber plant device types
        self.device_types["odf_288"], _ = DeviceType.objects.get_or_create(
            manufacturer=self.mfr, model="ODF-288", defaults={"slug": "odf-288"}
        )
        self.device_types["odf_96"], _ = DeviceType.objects.get_or_create(
            manufacturer=self.mfr, model="ODF-96", defaults={"slug": "odf-96"}
        )
        self.device_types["fosc_450d"], _ = DeviceType.objects.get_or_create(
            manufacturer=self.mfr, model="FOSC-450D", defaults={"slug": "fosc-450d"}
        )
        self.device_types["fosc_200b"], _ = DeviceType.objects.get_or_create(
            manufacturer=self.mfr, model="FOSC-200B", defaults={"slug": "fosc-200b"}
        )
        self.device_types["wall_box"], _ = DeviceType.objects.get_or_create(
            manufacturer=self.mfr, model="Wall-Box-24", defaults={"slug": "wall-box-24"}
        )
        # Edge device types
        self.device_types["router"], _ = DeviceType.objects.get_or_create(
            manufacturer=self.mfr_generic, model="Generic Router", defaults={"slug": "generic-router"}
        )
        self.device_types["switch"], _ = DeviceType.objects.get_or_create(
            manufacturer=self.mfr_generic, model="Generic Switch", defaults={"slug": "generic-switch"}
        )
        self.device_types["cpe"], _ = DeviceType.objects.get_or_create(
            manufacturer=self.mfr_generic, model="CPE Router", defaults={"slug": "cpe-router"}
        )

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
            manufacturer=self.mfr, model="24F Splice Tray", defaults={}
        )

    def _create_sites(self):
        self.stdout.write("Creating sites...")
        # CO sites
        for co_name, co_slug, _ in CO_DEFS:
            self.sites[co_slug], _ = Site.objects.get_or_create(
                name=co_name.replace("CO-", ""), defaults={"slug": co_slug}
            )

        # Hub sites: 4 per CO
        for co_name, co_slug, directions in CO_DEFS:
            co_short = co_slug.replace("co-", "")
            for d in directions:
                slug = f"{co_short}-hub-{d.lower()}"
                name = f"{co_name.replace('CO-', '')} Hub {d}"
                self.sites[slug], _ = Site.objects.get_or_create(name=name, defaults={"slug": slug})

        # Neighborhood sites for spurs
        neighborhoods = [
            "elm-st",
            "oak-ave",
            "maple-dr",
            "pine-rd",
            "cedar-ln",
            "birch-ct",
            "walnut-st",
            "spruce-ave",
            "ash-blvd",
            "cherry-way",
            "willow-ln",
            "poplar-dr",
            "hickory-rd",
            "beech-st",
            "cypress-ct",
            "magnolia-ave",
            "dogwood-ln",
            "sycamore-rd",
            "juniper-st",
            "hemlock-dr",
        ]
        for co_name, co_slug, _ in CO_DEFS:
            co_short = co_slug.replace("co-", "")
            for hood in neighborhoods[:7]:  # ~7 neighborhoods per CO
                slug = f"{co_short}-{hood}"
                name = f"{co_name.replace('CO-', '')} {hood.replace('-', ' ').title()}"
                self.sites[slug], _ = Site.objects.get_or_create(name=name, defaults={"slug": slug})

        self.stdout.write(f"  Created {len(self.sites)} sites")

    # ------------------------------------------------------------------
    # Helper methods for device/cable creation
    # ------------------------------------------------------------------

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
                device=device, name=f"Tray Slot {i}", defaults={"position": str(i)}
            )
            mod, _ = Module.objects.get_or_create(
                device=device, module_bay=bay, defaults={"module_type": self.tray_module_type, "status": "active"}
            )
            trays.append(mod)
        return trays

    def _create_cable_segment(self, label, a_device, b_device, cable_type_key, length_m):
        """Create a cable with FiberCable between two devices.

        Does NOT create terminations (ports) -- that happens in the port-building step.
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
        Link FiberStrands to their FrontPorts. Uses bulk_create for performance."""
        cable = cable_info["cable"]
        fc = cable_info["fiber_cable"]
        if not fc:
            return

        for device, cable_end, fk_field in [
            (cable_info["a_device"], "A", "front_port_a"),
            (cable_info["b_device"], "B", "front_port_b"),
        ]:
            # Skip if terminations already exist
            existing = CableTermination.objects.filter(cable=cable, cable_end=cable_end, termination_type=self.rp_ct)
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
                        device=device,
                        module=tray,
                        name=f"#{cable.pk}:T{tube.position}",
                        type="splice",
                        positions=len(tube_strands),
                    )
                    CableTermination.objects.create(
                        cable=cable,
                        cable_end=cable_end,
                        termination_type=self.rp_ct,
                        termination_id=rp.pk,
                    )

                    fps_to_create = []
                    for pos_in_tube, strand in enumerate(tube_strands, 1):
                        fp = FrontPort(
                            device=device,
                            module=tray,
                            name=f"#{cable.pk}:T{tube.position}:F{strand.position}",
                            type="splice",
                            color=EIA_COLORS.get(pos_in_tube, "cccccc"),
                        )
                        fps_to_create.append((fp, rp, pos_in_tube, strand))

                    # Bulk create FrontPorts
                    fp_objects = FrontPort.objects.bulk_create([f[0] for f in fps_to_create])
                    pms_to_create = []
                    for fp_obj, (_, rp_ref, pos, strand) in zip(fp_objects, fps_to_create, strict=False):
                        pms_to_create.append(
                            PortMapping(
                                device=device,
                                front_port=fp_obj,
                                rear_port=rp_ref,
                                front_port_position=1,
                                rear_port_position=pos,
                            )
                        )
                        setattr(strand, fk_field, fp_obj)

                    PortMapping.objects.bulk_create(pms_to_create)
                    FiberStrand.objects.bulk_update(tube_strands, [fk_field])
            else:
                # Tight buffer (no tubes)
                tray = trays[0] if trays else None
                rp = RearPort.objects.create(
                    device=device,
                    module=tray,
                    name=f"#{cable.pk}",
                    type="splice",
                    positions=len(strands),
                )
                CableTermination.objects.create(
                    cable=cable,
                    cable_end=cable_end,
                    termination_type=self.rp_ct,
                    termination_id=rp.pk,
                )

                fps_to_create = []
                for strand in strands:
                    fp = FrontPort(
                        device=device,
                        module=tray,
                        name=f"#{cable.pk}:F{strand.position}",
                        type="splice",
                        color=EIA_COLORS.get(strand.position, "cccccc"),
                    )
                    fps_to_create.append((fp, rp, strand.position, strand))

                fp_objects = FrontPort.objects.bulk_create([f[0] for f in fps_to_create])
                pms_to_create = []
                for fp_obj, (_, rp_ref, pos, strand) in zip(fp_objects, fps_to_create, strict=False):
                    pms_to_create.append(
                        PortMapping(
                            device=device,
                            front_port=fp_obj,
                            rear_port=rp_ref,
                            front_port_position=1,
                            rear_port_position=pos,
                        )
                    )
                    setattr(strand, fk_field, fp_obj)

                PortMapping.objects.bulk_create(pms_to_create)
                FiberStrand.objects.bulk_update(strands, [fk_field])

    # ------------------------------------------------------------------
    # Backbone
    # ------------------------------------------------------------------

    def _build_backbone(self):
        self.stdout.write("Building backbone...")
        # Create CO ODF devices
        for co_name, co_slug, _ in CO_DEFS:
            self._get_or_create_device(co_name, co_slug, "co", "odf_288")

        # Build 6 backbone routes (3 pairs x 2 paths)
        for co_a_name, co_b_name in BACKBONE_PAIRS:
            co_a_slug = co_a_name.lower()
            co_b_slug = co_b_name.lower()

            # Derive short names for labels
            a_short = co_a_name.replace("CO-", "")[:2].upper()  # DT, NO, SO
            b_short = co_b_name.replace("CO-", "")[:2].upper()

            # Path A: 288F, 10 closures
            self._build_backbone_path(
                co_a_name,
                co_b_name,
                co_a_slug,
                co_b_slug,
                path_label="A",
                cable_type_key="288f",
                num_closures=10,
                a_short=a_short,
                b_short=b_short,
            )
            # Path B: 144F, 8 closures
            self._build_backbone_path(
                co_a_name,
                co_b_name,
                co_a_slug,
                co_b_slug,
                path_label="B",
                cable_type_key="144f",
                num_closures=8,
                a_short=a_short,
                b_short=b_short,
            )

    def _build_backbone_path(
        self, co_a_name, co_b_name, co_a_slug, co_b_slug, path_label, cable_type_key, num_closures, a_short, b_short
    ):
        """Build one backbone path between two COs with intermediate closures."""
        # Use the site of co_a for all intermediate closures (simplification)
        closures = []
        for i in range(1, num_closures + 1):
            name = f"BB-{a_short}-{b_short}-{path_label}-{i:02d}"
            device = self._get_or_create_device(name, co_a_slug, "closure", "fosc_450d")
            num_trays = 24 if cable_type_key == "288f" else 12
            self._create_tray_modules(device, min(num_trays, 8))  # Cap at 8 trays
            closures.append(device)

        # Build chain: CO-A -> closure-1 -> ... -> closure-N -> CO-B
        chain = [self.devices[co_a_name], *closures, self.devices[co_b_name]]
        for i in range(len(chain) - 1):
            dev_a, dev_b = chain[i], chain[i + 1]
            seg_label = f"{dev_a.name} \u2192 {dev_b.name}"
            length = 800 + (hash(seg_label) % 3000)  # 800-3800m
            info = self._create_cable_segment(seg_label, dev_a, dev_b, cable_type_key, length)
            self._create_ports_and_link_strands(info)

        self.stdout.write(
            f"  Backbone {a_short}\u2192{b_short} Path {path_label}: {num_closures} closures, {num_closures + 1} cables"
        )

    # ------------------------------------------------------------------
    # Stubs for future tasks
    # ------------------------------------------------------------------

    def _build_metro_rings(self):
        self.stdout.write("Building metro rings... (not yet implemented)")

    def _build_spurs(self):
        self.stdout.write("Building spurs... (not yet implemented)")

    def _build_edge_devices(self):
        self.stdout.write("Building edge devices... (not yet implemented)")

    def _create_slack_loops(self):
        self.stdout.write("Creating slack loops... (not yet implemented)")

    def _create_splice_plans(self):
        self.stdout.write("Creating splice plans... (not yet implemented)")

    def _create_closure_cable_entries(self):
        self.stdout.write("Creating closure cable entries... (not yet implemented)")

    def _create_fiber_circuits(self):
        self.stdout.write("Creating fiber circuits... (not yet implemented)")
