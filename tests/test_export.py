from dcim.models import (
    Device,
    DeviceRole,
    DeviceType,
    Manufacturer,
    Module,
    ModuleBay,
    ModuleType,
    Site,
)
from django.test import TestCase

from netbox_fms.export import generate_drawio
from netbox_fms.models import SplicePlan, SplicePlanEntry
from tests.conftest import make_front_port


class TestDrawioExport(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Exp Site", slug="exp-site")
        mfr = Manufacturer.objects.create(name="Exp Mfr", slug="exp-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Closure", slug="exp-closure")
        role = DeviceRole.objects.create(name="Exp Role", slug="exp-role")
        cls.closure = Device.objects.create(name="C-Exp", site=site, device_type=dt, role=role)

        mt = ModuleType.objects.create(manufacturer=mfr, model="Tray")
        bay = ModuleBay.objects.create(device=cls.closure, name="Bay 1")
        cls.tray = Module.objects.create(device=cls.closure, module_bay=bay, module_type=mt)

        cls.fp1 = make_front_port(device=cls.closure, module=cls.tray, name="F1")
        cls.fp2 = make_front_port(device=cls.closure, module=cls.tray, name="F2")

    def test_generates_valid_xml(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Export Plan")
        SplicePlanEntry.objects.create(plan=plan, tray=self.tray, fiber_a=self.fp1, fiber_b=self.fp2)
        xml = generate_drawio(plan)
        assert xml.startswith(("<?xml", "<mxfile"))
        assert "mxGraphModel" in xml

    def test_empty_plan_generates_xml(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Empty Export Plan")
        xml = generate_drawio(plan)
        assert "mxGraphModel" in xml

    def test_contains_fiber_names(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Name Plan")
        SplicePlanEntry.objects.create(plan=plan, tray=self.tray, fiber_a=self.fp1, fiber_b=self.fp2)
        xml = generate_drawio(plan)
        assert "F1" in xml
        assert "F2" in xml

    def test_diff_annotations(self):
        """Entries to add should be annotated green in the export."""
        plan = SplicePlan.objects.create(closure=self.closure, name="Diff Plan")
        SplicePlanEntry.objects.create(plan=plan, tray=self.tray, fiber_a=self.fp1, fiber_b=self.fp2)
        xml = generate_drawio(plan)
        assert "#00CC00" in xml or "green" in xml.lower() or "strokeColor=#00" in xml


class TestExportOrdering(TestCase):
    """Tray ports export in strand order even when names sort the other way."""

    @classmethod
    def setUpTestData(cls):
        cls.mfr = Manufacturer.objects.create(name="EO Mfr", slug="eo-mfr")
        site = Site.objects.create(name="EO Site", slug="eo-site")
        dt = DeviceType.objects.create(manufacturer=cls.mfr, model="EO Closure", slug="eo-closure")
        role = DeviceRole.objects.create(name="EO Role", slug="eo-role")
        cls.dev_a = Device.objects.create(name="EO-A", site=site, device_type=dt, role=role)
        cls.dev_b = Device.objects.create(name="EO-B", site=site, device_type=dt, role=role)
        mt = ModuleType.objects.create(manufacturer=cls.mfr, model="EO Tray")
        bay = ModuleBay.objects.create(device=cls.dev_a, name="Tray 1")
        cls.tray = Module.objects.create(device=cls.dev_a, module_bay=bay, module_type=mt)

    def test_ports_ordered_by_strand_not_name(self):
        from dcim.models import FrontPort

        from netbox_fms.models import BufferTubeTemplate, FiberCableType, TubeAssignment
        from netbox_fms.services import create_closure_cable

        fct = FiberCableType.objects.create(
            manufacturer=self.mfr,
            model="EO-1",
            construction="loose_tube",
            strand_count=3,
            # Reverse lexical order: strand 1 -> Z9, strand 3 -> Z7.
            front_port_name_template="Z{{ 10 - strand }}",
        )
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=3)
        fc, _ = create_closure_cable(
            device_a=self.dev_a,
            device_b=self.dev_b,
            fiber_cable_type=fct,
            cable_attrs={"type": "smf-os2", "label": "EO"},
        )
        TubeAssignment.objects.create(closure=self.dev_a, tray=self.tray, buffer_tube=fc.buffer_tubes.get(position=1))
        plan = SplicePlan.objects.create(name="EO Plan", closure=self.dev_a)

        xml = generate_drawio(plan)
        order = [port.name for port in FrontPort.objects.filter(device=self.dev_a, module=self.tray)]
        positions = [xml.index(name) for name in ["Z9", "Z8", "Z7"]]
        assert positions == sorted(positions), f"cells out of strand order: {order}"
