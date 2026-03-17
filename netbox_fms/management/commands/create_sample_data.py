"""Create realistic sample data for the netbox-fms plugin.

Topology: Metro fiber ring with a central office (CO), 4 distribution hubs,
and 8 splice closures connecting them with 48F loose-tube cables (4 tubes x 12F).

  CO ── SC-1 ── Hub-North ── SC-2 ── SC-3 ── Hub-East
  │                                              │
  SC-8                                         SC-4
  │                                              │
  Hub-West ── SC-7 ── SC-6 ── Hub-South ── SC-5

Each closure has 2-3 incoming cables and splice trays.
"""

from dcim.choices import CableTypeChoices
from dcim.models import (
    Cable,
    CableTermination,
    Device,
    DeviceRole,
    DeviceType,
    FrontPort,
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
    ClosureCableEntry,
    FiberCable,
    FiberCableType,
    SplicePlan,
    SplicePlanEntry,
)

# EIA/TIA-598 fiber strand color code (12 standard colors)
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

# Tube colors (same EIA palette)
TUBE_COLORS = {1: "0000ff", 2: "ff8000", 3: "00ff00", 4: "8b4513"}


class Command(BaseCommand):
    help = "Create realistic sample data: metro fiber ring with 8 splice closures"

    @transaction.atomic
    def handle(self, *args, **options):
        self._ensure_admin_user()
        mfr = self._get_or_create_manufacturer()
        fct = self._get_or_create_cable_type(mfr)
        roles = self._get_or_create_roles()
        device_types = self._get_or_create_device_types(mfr)
        tray_module_type = self._get_or_create_tray_module_type(mfr)

        sites = self._create_sites()
        devices = self._create_devices(sites, roles, device_types)
        self._create_tray_modules(devices, tray_module_type)

        cables = self._create_cables_and_fiber_cables(devices, fct)
        self._create_closure_ports_and_link_strands(devices, cables, tray_module_type)
        self._create_splice_plans(devices, cables)

        self.stdout.write(self.style.SUCCESS("Sample data created successfully."))

    def _ensure_admin_user(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "admin")
            self.stdout.write("  Created admin user (admin/admin)")

    def _get_or_create_manufacturer(self):
        mfr, _ = Manufacturer.objects.get_or_create(name="Corning", defaults={"slug": "corning"})
        return mfr

    def _get_or_create_cable_type(self, mfr):
        fct, created = FiberCableType.objects.get_or_create(
            manufacturer=mfr,
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
            self.stdout.write("  Created FiberCableType: 48F loose tube (4x12)")
            # 4 buffer tube templates
            for t in range(1, 5):
                BufferTubeTemplate.objects.create(
                    fiber_cable_type=fct,
                    name=f"T{t}",
                    position=t,
                    color=TUBE_COLORS[t],
                    fiber_count=12,
                )
            CableElementTemplate.objects.create(
                fiber_cable_type=fct, name="Central Strength Member", element_type="central_member"
            )
        return fct

    def _get_or_create_roles(self):
        co_role, _ = DeviceRole.objects.get_or_create(name="Central Office", defaults={"slug": "central-office"})
        hub_role, _ = DeviceRole.objects.get_or_create(name="Distribution Hub", defaults={"slug": "distribution-hub"})
        closure_role, _ = DeviceRole.objects.get_or_create(name="Splice Closure", defaults={"slug": "splice-closure"})
        return {"co": co_role, "hub": hub_role, "closure": closure_role}

    def _get_or_create_device_types(self, mfr):
        co_dt, _ = DeviceType.objects.get_or_create(
            manufacturer=mfr, model="ODF-96", defaults={"slug": "odf-96"}
        )
        hub_dt, _ = DeviceType.objects.get_or_create(
            manufacturer=mfr, model="ODF-48", defaults={"slug": "odf-48"}
        )
        closure_dt, _ = DeviceType.objects.get_or_create(
            manufacturer=mfr, model="FOSC-450D", defaults={"slug": "fosc-450d"}
        )
        return {"co": co_dt, "hub": hub_dt, "closure": closure_dt}

    def _get_or_create_tray_module_type(self, mfr):
        mt, _ = ModuleType.objects.get_or_create(
            manufacturer=mfr, model="24F Splice Tray", defaults={}
        )
        return mt

    def _create_sites(self):
        self.stdout.write("Creating sites...")
        site_defs = [
            ("Metro CO", "metro-co"),
            ("Hub North", "hub-north"),
            ("Hub East", "hub-east"),
            ("Hub South", "hub-south"),
            ("Hub West", "hub-west"),
        ]
        sites = {}
        for name, slug in site_defs:
            sites[slug], _ = Site.objects.get_or_create(name=name, defaults={"slug": slug})
        return sites

    def _create_devices(self, sites, roles, device_types):
        self.stdout.write("Creating devices...")
        devices = {}

        # Central Office
        devices["CO"], _ = Device.objects.get_or_create(
            name="CO-Main",
            defaults={"site": sites["metro-co"], "role": roles["co"], "device_type": device_types["co"]},
        )

        # Distribution Hubs
        for direction, slug in [("North", "hub-north"), ("East", "hub-east"), ("South", "hub-south"), ("West", "hub-west")]:
            devices[f"Hub-{direction}"], _ = Device.objects.get_or_create(
                name=f"Hub-{direction}",
                defaults={"site": sites[slug], "role": roles["hub"], "device_type": device_types["hub"]},
            )

        # 8 Splice Closures
        closure_sites = {
            "SC-1": "metro-co",
            "SC-2": "hub-north",
            "SC-3": "hub-east",
            "SC-4": "hub-east",
            "SC-5": "hub-south",
            "SC-6": "hub-south",
            "SC-7": "hub-west",
            "SC-8": "hub-west",
        }
        for name, site_slug in closure_sites.items():
            devices[name], _ = Device.objects.get_or_create(
                name=name,
                defaults={"site": sites[site_slug], "role": roles["closure"], "device_type": device_types["closure"]},
            )

        self.stdout.write(f"  Created {len(devices)} devices")
        return devices

    def _create_tray_modules(self, devices, tray_mt):
        """Create splice tray modules on each closure. 4 trays per closure (one per tube)."""
        self.stdout.write("Creating splice tray modules...")
        closures = [d for name, d in devices.items() if name.startswith("SC-")]
        for closure in closures:
            if closure.modules.exists():
                continue
            for i in range(1, 5):
                bay, _ = ModuleBay.objects.get_or_create(
                    device=closure, name=f"Tray Slot {i}", defaults={"position": str(i)}
                )
                Module.objects.get_or_create(
                    device=closure, module_bay=bay, defaults={"module_type": tray_mt, "status": "active"}
                )

    def _create_cables_and_fiber_cables(self, devices, fct):
        """Create the fiber ring cables and their FiberCable metadata.

        Ring topology:
        CO -> SC-1 -> Hub-North -> SC-2 -> SC-3 -> Hub-East -> SC-4 -> SC-5 -> Hub-South -> SC-6 -> SC-7 -> Hub-West -> SC-8 -> CO
        """
        self.stdout.write("Creating cables and fiber cables...")
        # Define cable segments: (label, A-side device, B-side device)
        segments = [
            ("CO → SC-1", "CO", "SC-1"),
            ("SC-1 → Hub-North", "SC-1", "Hub-North"),
            ("Hub-North → SC-2", "Hub-North", "SC-2"),
            ("SC-2 → SC-3", "SC-2", "SC-3"),
            ("SC-3 → Hub-East", "SC-3", "Hub-East"),
            ("Hub-East → SC-4", "Hub-East", "SC-4"),
            ("SC-4 → SC-5", "SC-4", "SC-5"),
            ("SC-5 → Hub-South", "Hub-South", "SC-5"),
            ("Hub-South → SC-6", "Hub-South", "SC-6"),
            ("SC-6 → SC-7", "SC-6", "SC-7"),
            ("SC-7 → Hub-West", "SC-7", "Hub-West"),
            ("Hub-West → SC-8", "Hub-West", "SC-8"),
            ("SC-8 → CO", "SC-8", "CO"),
        ]

        cables = {}
        for label, a_name, b_name in segments:
            existing = Cable.objects.filter(label=label).first()
            if existing:
                cables[label] = {
                    "cable": existing,
                    "fiber_cable": FiberCable.objects.filter(cable=existing).first(),
                    "a_device": devices[a_name],
                    "b_device": devices[b_name],
                }
                continue

            cable = Cable(
                type=CableTypeChoices.TYPE_SMF_OS2,
                label=label,
                length=500 + hash(label) % 2000,
                length_unit="m",
                color="ffeb3b",
            )
            cable.save()

            fc = FiberCable.objects.create(
                cable=cable,
                fiber_cable_type=fct,
                serial_number=f"SN-{label.replace(' ', '-').replace('→', 'to')}",
            )

            cables[label] = {
                "cable": cable,
                "fiber_cable": fc,
                "a_device": devices[a_name],
                "b_device": devices[b_name],
            }

        self.stdout.write(f"  Created {len(cables)} cable segments with FiberCable records")
        return cables

    def _create_closure_ports_and_link_strands(self, devices, cables, tray_mt):
        """For each device, create RearPorts (one per tube per cable) and FrontPorts on trays.
        Link FiberStrands to their FrontPorts on each side."""
        self.stdout.write("Creating ports and linking strands...")
        rp_ct = ContentType.objects.get_for_model(RearPort)

        for label, info in cables.items():
            cable = info["cable"]
            fc = info["fiber_cable"]
            if not fc:
                continue

            for side, device, cable_end in [("A", info["a_device"], "A"), ("B", info["b_device"], "B")]:
                # Check if ports already exist for this cable on this device
                existing_terms = CableTermination.objects.filter(
                    cable=cable, cable_end=cable_end, termination_type=rp_ct
                )
                if existing_terms.exists():
                    continue

                tubes = list(fc.buffer_tubes.all().order_by("position"))
                strands = list(fc.fiber_strands.all().order_by("position"))
                trays = list(Module.objects.filter(device=device).order_by("module_bay__position"))
                fk_field = "front_port_a" if cable_end == "A" else "front_port_b"

                if tubes:
                    # One RearPort per tube
                    strand_idx = 0
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
                            cable=cable, cable_end=cable_end,
                            termination_type=rp_ct, termination_id=rp.pk,
                        )

                        for pos_in_tube, strand in enumerate(tube_strands, 1):
                            fp = FrontPort.objects.create(
                                device=device,
                                module=tray,
                                name=f"#{cable.pk}:T{tube.position}:F{strand.position}",
                                type="splice",
                                color=EIA_COLORS.get(pos_in_tube, "cccccc"),
                            )
                            PortMapping.objects.create(
                                device=device, front_port=fp, rear_port=rp,
                                front_port_position=1, rear_port_position=pos_in_tube,
                            )
                            setattr(strand, fk_field, fp)
                            strand.save(update_fields=[fk_field])
                else:
                    # Single RearPort
                    tray = trays[0] if trays else None
                    rp = RearPort.objects.create(
                        device=device,
                        module=tray,
                        name=f"#{cable.pk}",
                        type="splice",
                        positions=len(strands),
                    )
                    CableTermination.objects.create(
                        cable=cable, cable_end=cable_end,
                        termination_type=rp_ct, termination_id=rp.pk,
                    )
                    for strand in strands:
                        fp = FrontPort.objects.create(
                            device=device,
                            module=tray,
                            name=f"#{cable.pk}:F{strand.position}",
                            type="splice",
                            color=EIA_COLORS.get(strand.position, "cccccc"),
                        )
                        PortMapping.objects.create(
                            device=device, front_port=fp, rear_port=rp,
                            front_port_position=1, rear_port_position=strand.position,
                        )
                        setattr(strand, fk_field, fp)
                        strand.save(update_fields=[fk_field])

        self.stdout.write("  Ports created and strands linked")

    def _create_splice_plans(self, devices, cables):
        """Create splice plans on each closure with some sample splices.
        Each closure splices through-traffic: tube-for-tube from cable A to cable B."""
        self.stdout.write("Creating splice plans...")

        # Find which cables terminate on each closure
        closures = {name: dev for name, dev in devices.items() if name.startswith("SC-")}

        for name, closure in closures.items():
            if SplicePlan.objects.filter(closure=closure).exists():
                continue

            plan = SplicePlan.objects.create(
                closure=closure,
                name=f"{name} Splice Plan",
                description=f"Through-splices at {name}",
                status="draft",
            )

            # Find all FrontPorts on this closure's tray modules, grouped by cable
            fps_by_cable = {}
            for fp in FrontPort.objects.filter(device=closure, module__isnull=False).order_by("name"):
                # Extract cable PK from name like "#42:T1:F1"
                if fp.name.startswith("#"):
                    try:
                        cable_pk = int(fp.name.split(":")[0][1:])
                        fps_by_cable.setdefault(cable_pk, []).append(fp)
                    except (ValueError, IndexError):
                        pass

            # Get list of cable PKs on this closure
            cable_pks = sorted(fps_by_cable.keys())
            if len(cable_pks) < 2:
                continue

            # Splice first 12 strands of cable A to first 12 strands of cable B
            cable_a_fps = fps_by_cable[cable_pks[0]][:12]
            cable_b_fps = fps_by_cable[cable_pks[1]][:12]

            entries_created = 0
            for fp_a, fp_b in zip(cable_a_fps, cable_b_fps):
                tray = fp_a.module
                if tray:
                    SplicePlanEntry.objects.create(
                        plan=plan, tray=tray, fiber_a=fp_a, fiber_b=fp_b
                    )
                    entries_created += 1

            # If there's a third cable, splice some of its strands to the second cable
            if len(cable_pks) >= 3:
                cable_c_fps = fps_by_cable[cable_pks[2]][:12]
                cable_b_remaining = fps_by_cable[cable_pks[1]][12:24]
                for fp_c, fp_b in zip(cable_c_fps, cable_b_remaining):
                    tray = fp_c.module
                    if tray:
                        SplicePlanEntry.objects.create(
                            plan=plan, tray=tray, fiber_a=fp_c, fiber_b=fp_b
                        )
                        entries_created += 1

            self.stdout.write(f"  {name}: {entries_created} splice entries")

        self.stdout.write(f"  Created splice plans for {len(closures)} closures")
