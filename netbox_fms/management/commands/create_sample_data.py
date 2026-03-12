"""Create sample data for the netbox-fms plugin."""

from dcim.choices import CableProfileChoices, CableTypeChoices
from dcim.models import (
    Cable,
    CablePath,
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
from django.core.management.base import BaseCommand
from django.db import transaction

from netbox_fms.models import (
    BufferTubeTemplate,
    CableElementTemplate,
    FiberCable,
    FiberCableType,
    RibbonTemplate,
    SplicePlan,
    SplicePlanEntry,
)

# EIA/TIA-598 fiber strand color code (12 standard colors)
EIA_STRAND_COLORS = {
    1: ("0000ff", "Blue"),
    2: ("ff8000", "Orange"),
    3: ("00ff00", "Green"),
    4: ("8b4513", "Brown"),
    5: ("708090", "Slate"),
    6: ("ffffff", "White"),
    7: ("ff0000", "Red"),
    8: ("000000", "Black"),
    9: ("ffff00", "Yellow"),
    10: ("ee82ee", "Violet"),
    11: ("ff69b4", "Rose"),
    12: ("00ffff", "Aqua"),
}

STRAND_COUNT = 12


class Command(BaseCommand):
    help = "Create sample data for the Fiber Management System plugin"

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete all existing FMS data before creating sample data",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["flush"]:
            self._flush()

        manufacturers = self._create_manufacturers()
        cable_types = self._create_cable_types(manufacturers)
        self._create_templates(cable_types)
        topology = self._create_network_topology(manufacturers)
        self._create_fiber_cables(cable_types, topology)
        self._create_splice_plans(manufacturers, topology)
        self._rebuild_cable_paths()

        self.stdout.write(self.style.SUCCESS("Sample data created successfully."))

    def _flush(self):
        self.stdout.write("Flushing existing FMS data...")
        SplicePlan.objects.all().delete()
        FiberCable.objects.all().delete()
        FiberCableType.objects.all().delete()
        Cable.objects.filter(label__startswith="Splice:").delete()
        Cable.objects.filter(label__startswith="Trunk ").delete()
        Cable.objects.filter(label__contains="\u2192").delete()
        CablePath.objects.all().delete()
        PortMapping.objects.all().delete()
        FrontPort.objects.all().delete()
        RearPort.objects.all().delete()
        Interface.objects.filter(device__name__startswith="SW-").delete()
        Device.objects.filter(name__startswith="SC-").delete()
        Device.objects.filter(name__startswith="PP-").delete()
        Device.objects.filter(name__startswith="SW-").delete()
        Site.objects.filter(slug__startswith="site-").delete()

    def _create_manufacturers(self):
        self.stdout.write("Creating manufacturers...")
        names = ["Corning", "CommScope", "Prysmian", "AFL", "OFS Fitel"]
        mfrs = {}
        for name in names:
            slug = name.lower().replace(" ", "-")
            mfrs[name], _ = Manufacturer.objects.get_or_create(name=name, defaults={"slug": slug})
        return mfrs

    def _create_cable_types(self, mfrs):
        self.stdout.write("Creating fiber cable types...")
        types = {}

        types["tight12"], _ = FiberCableType.objects.get_or_create(
            manufacturer=mfrs["CommScope"],
            model="TeraSPEED 012",
            defaults={
                "part_number": "760004812",
                "construction": "tight_buffer",
                "fiber_type": "smf_os2",
                "strand_count": 12,
                "sheath_material": "lszh",
                "jacket_color": "ffff00",
                "is_armored": False,
                "deployment": "indoor",
                "fire_rating": "ofnp",
            },
        )

        types["loose48"], _ = FiberCableType.objects.get_or_create(
            manufacturer=mfrs["Corning"],
            model="ALTOS 048TCF",
            defaults={
                "part_number": "048TCF-14180D20",
                "construction": "loose_tube",
                "fiber_type": "smf_os2",
                "strand_count": 48,
                "sheath_material": "pe",
                "jacket_color": "000000",
                "is_armored": False,
                "deployment": "duct",
                "fire_rating": "",
            },
        )

        types["ribbon144"], _ = FiberCableType.objects.get_or_create(
            manufacturer=mfrs["Prysmian"],
            model="FlexRibbon 144",
            defaults={
                "part_number": "FR-144-OS2",
                "construction": "ribbon",
                "fiber_type": "smf_os2",
                "strand_count": 144,
                "sheath_material": "hdpe",
                "jacket_color": "000000",
                "is_armored": True,
                "armor_type": "corrugated_steel",
                "deployment": "direct_buried",
                "fire_rating": "",
            },
        )

        return types

    def _create_templates(self, types):
        self.stdout.write("Creating component templates...")

        # --- Tight buffer 12F: 12 individual fibers ---
        ct = types["tight12"]
        if not ct.cable_element_templates.exists():
            CableElementTemplate.objects.create(
                fiber_cable_type=ct,
                name="Central Strength Member",
                element_type="central_member",
            )

        # --- Loose tube 48F: 4 tubes x 12 fibers ---
        ct = types["loose48"]
        if not ct.buffer_tube_templates.exists():
            tube_colors = [
                ("0000ff", "Blue"),
                ("ff8000", "Orange"),
                ("00ff00", "Green"),
                ("8b4513", "Brown"),
            ]
            for i, (color, name) in enumerate(tube_colors, 1):
                BufferTubeTemplate.objects.create(
                    fiber_cable_type=ct,
                    name=f"Tube {name}",
                    position=i,
                    color=color,
                    fiber_count=12,
                )
            CableElementTemplate.objects.create(
                fiber_cable_type=ct,
                name="Central Strength Member",
                element_type="central_member",
            )
            CableElementTemplate.objects.create(
                fiber_cable_type=ct,
                name="Ripcord",
                element_type="ripcord",
            )

        # --- Ribbon 144F: 12 ribbons x 12 fibers ---
        ct = types["ribbon144"]
        if not ct.ribbon_templates.exists():
            for i in range(1, 13):
                RibbonTemplate.objects.create(
                    fiber_cable_type=ct,
                    buffer_tube_template=None,
                    name=f"Ribbon {i}",
                    position=i,
                    fiber_count=12,
                )
            CableElementTemplate.objects.create(
                fiber_cable_type=ct,
                name="Central Strength Member",
                element_type="central_member",
            )

    def _create_network_topology(self, mfrs):
        """Create 3-site fiber topology with individual strand FrontPorts.

        Topology (star via SC-001, 12F per trunk, profile=single-1c12p):

            SW-Alpha-1/2 -> PP-Alpha === Trunk-A ===|
                                                     |
            SW-Bravo-1/2 -> PP-Bravo === Trunk-B ===+=== SC-001
                                                     |
          SW-Charlie-1/2 -> PP-Charlie = Trunk-C ===|

        Each panel: 1 RearPort(positions=12) + 12 FrontPorts (F1-F12, one per strand)
        Closure:    3 RearPorts(positions=12) + 36 FrontPorts (one per strand per cable)

        Splice plan at SC-001:
          Cable-A strands 1-4  <-> Cable-B strands 1-4   (Alpha<->Bravo)
          Cable-A strands 5-8  <-> Cable-C strands 1-4   (Alpha<->Charlie)
          Cable-B strands 5-8  <-> Cable-C strands 5-8   (Bravo<->Charlie)
          Strands 9-12 on each cable: dark (spare capacity)

        Patch cables (duplex, multi-termination, no profile):
          [Interface] --cable-- [FP strand N, FP strand N+1]
          1 interface on side A, 2 FrontPorts on side B.

        Trace path (e.g. Alpha->Bravo strand 1):
          Interface -> Panel FP F1 ->
          PortMapping(rp_pos=1) -> Panel RP(pos=12) -> [trunk, 1C12P] ->
          Closure RP-A(pos=12) -> PortMapping(rp_pos=1) -> Closure FP(splice) ->
          [splice cable, simplex] -> Closure FP(splice) ->
          PortMapping(rp_pos=1) -> Closure RP-B(pos=12) -> [trunk, 1C12P] ->
          Panel RP(pos=12) -> PortMapping(rp_pos=1) -> Panel FP F1 ->
          Interface
        """
        self.stdout.write("Creating 3-site network topology...")

        # --- Device types ---
        panel_dt, _ = DeviceType.objects.get_or_create(
            manufacturer=mfrs["Corning"],
            model="CCH Panel 12P",
            defaults={"slug": "cch-panel-12p"},
        )
        switch_dt, _ = DeviceType.objects.get_or_create(
            manufacturer=mfrs["CommScope"],
            model="Generic Switch",
            defaults={"slug": "generic-switch"},
        )
        closure_dt, _ = DeviceType.objects.get_or_create(
            manufacturer=mfrs["Corning"],
            model="Coyote Closure",
            defaults={"slug": "coyote-closure"},
        )

        # --- Roles ---
        panel_role, _ = DeviceRole.objects.update_or_create(
            name="Patch Panel",
            defaults={"slug": "patch-panel", "color": "4caf50"},
        )
        switch_role, _ = DeviceRole.objects.update_or_create(
            name="Switch",
            defaults={"slug": "switch", "color": "2196f3"},
        )
        closure_role, _ = DeviceRole.objects.update_or_create(
            name="Splice Closure",
            defaults={"slug": "splice-closure", "color": "ff9800"},
        )

        # --- 3 Sites ---
        sites = {}
        for name in ("Alpha", "Bravo", "Charlie"):
            sites[name], _ = Site.objects.get_or_create(
                name=f"Site {name}",
                defaults={"slug": f"site-{name.lower()}"},
            )

        # --- Splice closure SC-001 (at Site Alpha) ---
        closure, _ = Device.objects.get_or_create(
            name="SC-001",
            defaults={"site": sites["Alpha"], "role": closure_role, "device_type": closure_dt},
        )

        # Splice tray modules
        tray_mt, _ = ModuleType.objects.get_or_create(
            manufacturer=mfrs["Corning"],
            model="12F Splice Tray",
            defaults={},
        )
        for tray_num in range(1, 4):
            bay, _ = ModuleBay.objects.get_or_create(
                device=closure,
                name=f"Tray Slot {tray_num}",
                defaults={"position": str(tray_num)},
            )
            Module.objects.get_or_create(
                device=closure,
                module_bay=bay,
                defaults={"module_type": tray_mt, "status": "active"},
            )

        # --- Closure ports: 3 cable entries x 12 strands ---
        side_map = {"A": "Alpha", "B": "Bravo", "C": "Charlie"}
        if not RearPort.objects.filter(device=closure).exists():
            for side, site_label in side_map.items():
                rp, _ = RearPort.objects.get_or_create(
                    device=closure,
                    name=f"Cable-{side} ({site_label})",
                    defaults={"type": "splice", "positions": STRAND_COUNT},
                )
                for strand in range(1, STRAND_COUNT + 1):
                    strand_color = EIA_STRAND_COLORS[strand][0]
                    fp, _ = FrontPort.objects.get_or_create(
                        device=closure,
                        name=f"Cable-{side} F{strand}",
                        defaults={"type": "splice", "color": strand_color},
                    )
                    PortMapping.objects.get_or_create(
                        device=closure,
                        front_port=fp,
                        rear_port=rp,
                        defaults={"front_port_position": 1, "rear_port_position": strand},
                    )

        # --- Patch panels, switches, trunk cables per site ---
        panels = {}
        switches = {}
        trunk_cables = {}
        side_for_site = {"Alpha": "A", "Bravo": "B", "Charlie": "C"}

        for name, site in sites.items():
            # Patch panel
            panel, _ = Device.objects.get_or_create(
                name=f"PP-{name}",
                defaults={"site": site, "role": panel_role, "device_type": panel_dt},
            )
            panels[name] = panel

            # Panel ports: 1 RearPort(positions=12) + 12 FrontPorts (F1-F12)
            # Each FrontPort is a single LC adapter for one strand.
            # FP "F1" → PortMapping → trunk RP position 1
            if not RearPort.objects.filter(device=panel).exists():
                rp, _ = RearPort.objects.get_or_create(
                    device=panel,
                    name="Trunk",
                    defaults={"type": "lc-upc", "positions": STRAND_COUNT},
                )
                for strand in range(1, STRAND_COUNT + 1):
                    strand_color = EIA_STRAND_COLORS[strand][0]
                    fp, _ = FrontPort.objects.get_or_create(
                        device=panel,
                        name=f"F{strand}",
                        defaults={"type": "lc-upc", "color": strand_color},
                    )
                    PortMapping.objects.get_or_create(
                        device=panel,
                        front_port=fp,
                        rear_port=rp,
                        defaults={"front_port_position": 1, "rear_port_position": strand},
                    )

            # 2 switches per site
            site_switches = []
            for sw_num in (1, 2):
                sw, _ = Device.objects.get_or_create(
                    name=f"SW-{name}-{sw_num}",
                    defaults={"site": site, "role": switch_role, "device_type": switch_dt},
                )
                site_switches.append(sw)
            switches[name] = site_switches

            # Trunk cable: Panel RP <-> Closure RP (single-1c12p)
            side = side_for_site[name]
            panel_rp = RearPort.objects.get(device=panel, name="Trunk")
            closure_rp = RearPort.objects.get(device=closure, name=f"Cable-{side} ({name})")

            if not panel_rp.cable:
                cable = Cable(
                    a_terminations=[panel_rp],
                    b_terminations=[closure_rp],
                    profile=CableProfileChoices.SINGLE_1C12P,
                    type=CableTypeChoices.TYPE_SMF_OS2,
                    color="ffeb3b",
                    label=f"Trunk {name}",
                    length=500,
                    length_unit="m",
                )
                cable.clean()
                cable.save()
                trunk_cables[name] = cable

        # --- Splice cables (per-strand, simplex, no profile) ---
        # A(1-4)<->B(1-4): Alpha<->Bravo     (4 strands = 2 duplex pairs)
        # A(5-8)<->C(1-4): Alpha<->Charlie    (4 strands = 2 duplex pairs)
        # B(5-8)<->C(5-8): Bravo<->Charlie    (4 strands = 2 duplex pairs)
        # Strands 9-12 on each cable are dark (spare capacity)
        splice_configs = [
            ("A", 1, "B", 1, 4),
            ("A", 5, "C", 1, 4),
            ("B", 5, "C", 5, 4),
        ]
        splice_cables_created = 0
        for side_a, start_a, side_b, start_b, count in splice_configs:
            for i in range(count):
                fp_a = FrontPort.objects.get(device=closure, name=f"Cable-{side_a} F{start_a + i}")
                fp_b = FrontPort.objects.get(device=closure, name=f"Cable-{side_b} F{start_b + i}")
                if fp_a.cable or fp_b.cable:
                    continue
                cable = Cable(
                    a_terminations=[fp_a],
                    b_terminations=[fp_b],
                    type=CableTypeChoices.TYPE_SMF_OS2,
                    label=f"Splice: {fp_a.name} \u2194 {fp_b.name}",
                )
                cable.clean()
                cable.save()
                splice_cables_created += 1

        # --- Duplex patch cables: Interface -> [FP-N, FP-N+1] (multi-termination, no profile) ---
        # SW-{site}-1: xe-0/0/1 -> F1, F2  (strands 1,2 — routed to first splice group)
        # SW-{site}-2: xe-0/0/1 -> F5, F6  (strands 5,6 — routed to second splice group)
        patch_configs = {
            "Alpha": [(0, 1, 2), (1, 5, 6)],
            "Bravo": [(0, 1, 2), (1, 5, 6)],
            "Charlie": [(0, 1, 2), (1, 5, 6)],
        }
        patch_created = 0
        for site_name, sw_configs in patch_configs.items():
            panel = panels[site_name]
            for sw_idx, strand_tx, strand_rx in sw_configs:
                sw = switches[site_name][sw_idx]
                intf, _ = Interface.objects.get_or_create(
                    device=sw,
                    name="xe-0/0/1",
                    defaults={"type": "10gbase-x-sfpp"},
                )
                fp_tx = FrontPort.objects.get(device=panel, name=f"F{strand_tx}")
                fp_rx = FrontPort.objects.get(device=panel, name=f"F{strand_rx}")
                if intf.cable or fp_tx.cable or fp_rx.cable:
                    continue
                cable = Cable(
                    a_terminations=[intf],
                    b_terminations=[fp_tx, fp_rx],
                    type=CableTypeChoices.TYPE_SMF_OS2,
                    color="ffeb3b",
                    label=f"{sw.name} xe-0/0/1 \u2192 {panel.name} F{strand_tx}/F{strand_rx}",
                    length=3,
                    length_unit="m",
                )
                cable.clean()
                cable.save()
                patch_created += 1

        self.stdout.write(
            f"  Created 3 sites, 3 panels, 6 switches, 1 closure, "
            f"{len(trunk_cables)} trunk cables, {splice_cables_created} splice cables, "
            f"{patch_created} patch cables."
        )

        return {
            "sites": sites,
            "panels": panels,
            "switches": switches,
            "closure": closure,
            "trunk_cables": trunk_cables,
        }

    def _create_fiber_cables(self, cable_types, topology):
        """Create FiberCable metadata records for the trunk cables."""
        self.stdout.write("Creating fiber cable instances...")
        trunk_cables = topology["trunk_cables"]
        ct = cable_types["tight12"]

        created = 0
        for name, cable in trunk_cables.items():
            if FiberCable.objects.filter(cable=cable).exists():
                continue
            FiberCable.objects.create(
                cable=cable,
                fiber_cable_type=ct,
                serial_number=f"SN-TRUNK-{name.upper()}",
            )
            created += 1

        self.stdout.write(f"  Created {created} fiber cable records.")

    def _create_splice_plans(self, mfrs, topology):
        """Create SplicePlan and SplicePlanEntry records for the closure splices."""
        self.stdout.write("Creating splice plans...")
        closure = topology["closure"]

        # OneToOne: only one plan per closure. Create or update a single plan.
        plan, created = SplicePlan.objects.get_or_create(
            closure=closure,
            defaults={
                "name": "Main Splices",
                "description": "All per-strand splices for this closure",
                "status": "applied",
            },
        )

        entry_configs = [
            ("A", 1, "B", 1, 4),
            ("A", 5, "C", 1, 4),
            ("B", 5, "C", 5, 4),
        ]

        if created:
            for side_a, start_a, side_b, start_b, count in entry_configs:
                for i in range(count):
                    fiber_a = FrontPort.objects.get(
                        device=closure,
                        name=f"Cable-{side_a} F{start_a + i}",
                    )
                    fiber_b = FrontPort.objects.get(
                        device=closure,
                        name=f"Cable-{side_b} F{start_b + i}",
                    )
                    tray = fiber_a.module
                    SplicePlanEntry.objects.create(plan=plan, tray=tray, fiber_a=fiber_a, fiber_b=fiber_b)

        self.stdout.write(
            f"  Created splice plan with {SplicePlanEntry.objects.filter(plan__closure=closure).count()} entries."
        )

    def _rebuild_cable_paths(self):
        """Rebuild all CablePaths from switch Interfaces."""
        self.stdout.write("Rebuilding cable paths...")
        CablePath.objects.all().delete()

        created = 0
        for intf in Interface.objects.filter(device__name__startswith="SW-"):
            if intf._path is not None:
                continue
            cp = CablePath.from_origin([intf])
            if cp:
                cp.save()
                created += 1

        self.stdout.write(f"  Rebuilt {created} cable paths.")
