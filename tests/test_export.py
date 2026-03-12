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
