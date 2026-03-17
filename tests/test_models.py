from dcim.models import Cable, Device, DeviceRole, DeviceType, Manufacturer, Module, ModuleBay, ModuleType, Site
from django.db import IntegrityError
from django.test import TestCase

from netbox_fms.choices import SplicePlanStatusChoices
from netbox_fms.models import ClosureCableEntry, FiberCable, FiberCableType, SplicePlan, SplicePlanEntry, SpliceProject
from netbox_fms.views import provision_strands
from tests.conftest import make_front_port


class TestSplicePlanStatusChoices(TestCase):
    def test_has_draft(self):
        assert SplicePlanStatusChoices.DRAFT == "draft"

    def test_has_pending_review(self):
        assert SplicePlanStatusChoices.PENDING_REVIEW == "pending_review"

    def test_has_ready_to_apply(self):
        assert SplicePlanStatusChoices.READY_TO_APPLY == "ready_to_apply"

    def test_has_applied(self):
        assert SplicePlanStatusChoices.APPLIED == "applied"

    def test_mode_choices_removed(self):
        """SplicePlanModeChoices should no longer exist."""
        import netbox_fms.choices as ch

        assert not hasattr(ch, "SplicePlanModeChoices")


class TestSpliceProject(TestCase):
    def test_create_project(self):
        project = SpliceProject.objects.create(
            name="Main St CO → Elm St Drop",
            description="Route fiber project",
        )
        assert project.pk is not None
        assert str(project) == "Main St CO → Elm St Drop"

    def test_get_absolute_url(self):
        project = SpliceProject.objects.create(name="Test Project")
        assert "/splice-projects/" in project.get_absolute_url()


class TestSplicePlanRework(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Test Site", slug="test-site")
        manufacturer = Manufacturer.objects.create(name="Test Mfr", slug="test-mfr")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="Closure", slug="closure")
        role = DeviceRole.objects.create(name="Splice Closure", slug="splice-closure")
        cls.closure = Device.objects.create(name="Closure-1", site=site, device_type=device_type, role=role)
        cls.project = SpliceProject.objects.create(name="Test Project")

    def test_create_plan_with_new_fields(self):
        from netbox_fms.choices import SplicePlanStatusChoices

        plan = SplicePlan.objects.create(
            closure=self.closure,
            name="Plan 1",
            status=SplicePlanStatusChoices.DRAFT,
        )
        assert plan.pk is not None
        assert plan.cached_diff is None
        assert plan.diff_stale is True
        assert plan.project is None

    def test_plan_with_project(self):
        plan = SplicePlan.objects.create(
            closure=self.closure,
            name="Plan 1",
            project=self.project,
        )
        assert plan.project == self.project
        assert self.project.plans.count() == 1

    def test_unique_closure_constraint(self):
        from django.db import IntegrityError

        SplicePlan.objects.create(closure=self.closure, name="Plan 1")
        with self.assertRaises(IntegrityError):
            SplicePlan.objects.create(closure=self.closure, name="Plan 2")

    def test_no_mode_field(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Plan 1")
        assert not hasattr(plan, "mode")

    def test_no_tray_field(self):
        SplicePlan.objects.create(closure=self.closure, name="Plan 1")
        assert not hasattr(SplicePlan, "tray")

    def test_no_implement_method(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Plan 1")
        assert not hasattr(plan, "implement")

    def test_no_rollback_method(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Plan 1")
        assert not hasattr(plan, "rollback")


class TestSplicePlanEntryRework(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Test Site 2", slug="test-site-2")
        manufacturer = Manufacturer.objects.create(name="Test Mfr 2", slug="test-mfr-2")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="Closure 2", slug="closure-2")
        role = DeviceRole.objects.create(name="Splice Closure 2", slug="splice-closure-2")
        cls.closure = Device.objects.create(name="Closure-2", site=site, device_type=device_type, role=role)
        cls.plan = SplicePlan.objects.create(closure=cls.closure, name="Plan")

        # Create a tray (Module) on the closure
        module_type = ModuleType.objects.create(manufacturer=manufacturer, model="Tray-12")
        bay = ModuleBay.objects.create(device=cls.closure, name="Tray Slot 1")
        cls.tray = Module.objects.create(device=cls.closure, module_bay=bay, module_type=module_type)

        # Create FrontPorts on the tray module using make_front_port helper
        cls.fp_a = make_front_port(device=cls.closure, module=cls.tray, name="F1")
        cls.fp_b = make_front_port(device=cls.closure, module=cls.tray, name="F2")

    def test_create_entry_with_frontports(self):
        entry = SplicePlanEntry.objects.create(
            plan=self.plan,
            tray=self.tray,
            fiber_a=self.fp_a,
            fiber_b=self.fp_b,
        )
        assert entry.pk is not None

    def test_entry_notes_field(self):
        entry = SplicePlanEntry.objects.create(
            plan=self.plan,
            tray=self.tray,
            fiber_a=self.fp_a,
            fiber_b=self.fp_b,
            notes="Splice with blue heat-shrink",
        )
        assert entry.notes == "Splice with blue heat-shrink"

    def test_no_cable_field(self):
        assert not hasattr(SplicePlanEntry, "cable")

    def test_no_mode_override_field(self):
        entry = SplicePlanEntry.objects.create(plan=self.plan, tray=self.tray, fiber_a=self.fp_a, fiber_b=self.fp_b)
        assert not hasattr(entry, "mode_override")

    def test_unique_fiber_a_per_plan(self):
        """Each FrontPort can appear as fiber_a at most once per plan."""
        fp_c = make_front_port(device=self.closure, module=self.tray, name="F3")
        SplicePlanEntry.objects.create(plan=self.plan, tray=self.tray, fiber_a=self.fp_a, fiber_b=fp_c)
        with self.assertRaises(IntegrityError):
            SplicePlanEntry.objects.create(plan=self.plan, tray=self.tray, fiber_a=self.fp_a, fiber_b=self.fp_b)

    def test_unique_fiber_b_per_plan(self):
        """Each FrontPort can appear as fiber_b at most once per plan."""
        fp_c = make_front_port(device=self.closure, module=self.tray, name="F4")
        SplicePlanEntry.objects.create(plan=self.plan, tray=self.tray, fiber_a=self.fp_a, fiber_b=self.fp_b)
        with self.assertRaises(IntegrityError):
            SplicePlanEntry.objects.create(plan=self.plan, tray=self.tray, fiber_a=fp_c, fiber_b=self.fp_b)


class TestClosureCableEntry(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Test Site 3", slug="test-site-3")
        manufacturer = Manufacturer.objects.create(name="Test Mfr 3", slug="test-mfr-3")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="Closure 3", slug="closure-3")
        role = DeviceRole.objects.create(name="Splice Closure 3", slug="splice-closure-3")
        cls.closure = Device.objects.create(name="Closure-3", site=site, device_type=device_type, role=role)
        fct = FiberCableType.objects.create(
            manufacturer=manufacturer,
            model="Test Cable Type",
            construction="loose_tube",
            fiber_type="smf_os2",
            strand_count=12,
        )
        from dcim.models import Cable

        cable = Cable.objects.create()
        cls.fiber_cable = FiberCable.objects.create(cable=cable, fiber_cable_type=fct)

    def test_create_entry(self):
        entry = ClosureCableEntry.objects.create(
            closure=self.closure,
            fiber_cable=self.fiber_cable,
            entrance_label="Gland A",
        )
        assert entry.pk is not None

    def test_entrance_label_field_exists(self):
        entry = ClosureCableEntry.objects.create(
            closure=self.closure,
            fiber_cable=self.fiber_cable,
            entrance_label="Gland A",
        )
        assert entry.entrance_label == "Gland A"
        assert entry.pk is not None

    def test_entrance_port_field_removed(self):
        field_names = [f.name for f in ClosureCableEntry._meta.get_fields()]
        assert "entrance_port" not in field_names
        assert "entrance_label" in field_names

    def test_unique_together_closure_fiber_cable(self):
        ClosureCableEntry.objects.create(
            closure=self.closure,
            fiber_cable=self.fiber_cable,
            entrance_label="Gland A",
        )
        with self.assertRaises(IntegrityError):
            ClosureCableEntry.objects.create(
                closure=self.closure,
                fiber_cable=self.fiber_cable,
                entrance_label="Gland B",
            )

    def test_str_uses_entrance_label(self):
        entry = ClosureCableEntry.objects.create(
            closure=self.closure,
            fiber_cable=self.fiber_cable,
            entrance_label="Gland C",
        )
        assert "Gland C" in str(entry)

    def test_get_absolute_url(self):
        entry = ClosureCableEntry.objects.create(
            closure=self.closure,
            fiber_cable=self.fiber_cable,
            entrance_label="Gland D",
        )
        assert "/closure-cable-entries/" in entry.get_absolute_url()


class TestProvisionStrandsHelper(TestCase):
    """Uses setUp (not setUpTestData) because each test provisions strands,
    mutating FiberStrand.front_port_a. Tests need isolated FiberCable instances."""

    def setUp(self):
        from dcim.models import Module, ModuleBay, ModuleType

        site = Site.objects.create(name="Prov Test Site", slug="prov-test-site")
        manufacturer = Manufacturer.objects.create(name="Prov Mfr", slug="prov-mfr")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="Prov Closure", slug="prov-closure")
        role = DeviceRole.objects.create(name="Prov Role", slug="prov-role")
        self.device = Device.objects.create(name="Prov-Device", site=site, device_type=device_type, role=role)

        module_type = ModuleType.objects.create(manufacturer=manufacturer, model="Tray-1")
        bay = ModuleBay.objects.create(device=self.device, name="Bay 1")
        self.module = Module.objects.create(device=self.device, module_bay=bay, module_type=module_type)

        self.fct = FiberCableType.objects.create(
            manufacturer=manufacturer,
            model="Prov-FCT",
            construction="loose_tube",
            fiber_type="smf_os2",
            strand_count=4,
        )

    def test_provision_creates_ports_on_module(self):
        from dcim.models import FrontPort, RearPort

        cable = Cable.objects.create()
        fiber_cable = FiberCable.objects.create(cable=cable, fiber_cable_type=self.fct)
        provision_strands(fiber_cable, self.device, module=self.module, port_type="splice")

        rp = RearPort.objects.filter(device=self.device, module=self.module)
        assert rp.count() == 1

        fps = FrontPort.objects.filter(device=self.device, module=self.module)
        assert fps.count() == 4

        for strand in fiber_cable.fiber_strands.all():
            assert strand.front_port_a is not None
            assert strand.front_port_a.module == self.module

    def test_provision_creates_ports_without_module(self):
        from dcim.models import FrontPort, RearPort

        cable = Cable.objects.create()
        fiber_cable = FiberCable.objects.create(cable=cable, fiber_cable_type=self.fct)
        provision_strands(fiber_cable, self.device, port_type="splice")

        rp = RearPort.objects.filter(device=self.device, module__isnull=True)
        assert rp.count() == 1

        fps = FrontPort.objects.filter(device=self.device, module__isnull=True)
        assert fps.count() == 4
