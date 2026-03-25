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
    Site,
)
from django.test import TestCase

from netbox_fms.models import SplicePlan, SplicePlanEntry
from netbox_fms.services import (
    apply_diff,
    compute_diff,
    get_desired_state,
    get_live_state,
    get_or_recompute_diff,
    import_live_state,
)
from tests.conftest import make_front_port


class TestLiveStateReader(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Svc Site", slug="svc-site")
        mfr = Manufacturer.objects.create(name="Svc Mfr", slug="svc-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Closure", slug="svc-closure")
        role = DeviceRole.objects.create(name="Svc Role", slug="svc-role")
        cls.closure = Device.objects.create(name="C1", site=site, device_type=dt, role=role)

        mt = ModuleType.objects.create(manufacturer=mfr, model="Tray-12")
        bay1 = ModuleBay.objects.create(device=cls.closure, name="Bay 1")
        cls.tray1 = Module.objects.create(device=cls.closure, module_bay=bay1, module_type=mt)
        bay2 = ModuleBay.objects.create(device=cls.closure, name="Bay 2")
        cls.tray2 = Module.objects.create(device=cls.closure, module_bay=bay2, module_type=mt)

        cls.fp1 = make_front_port(device=cls.closure, module=cls.tray1, name="T1-F1")
        cls.fp2 = make_front_port(device=cls.closure, module=cls.tray1, name="T1-F2")
        cls.fp3 = make_front_port(device=cls.closure, module=cls.tray2, name="T2-F1")
        cls.fp4 = make_front_port(device=cls.closure, module=cls.tray2, name="T2-F2")

    def _connect(self, port_a, port_b):
        """Create a 0-length cable between two FrontPorts."""
        from django.contrib.contenttypes.models import ContentType

        fp_ct = ContentType.objects.get_for_model(FrontPort)
        cable = Cable.objects.create(length=0, length_unit="m")
        CableTermination.objects.create(
            cable=cable,
            cable_end="A",
            termination_type=fp_ct,
            termination_id=port_a.pk,
        )
        CableTermination.objects.create(
            cable=cable,
            cable_end="B",
            termination_type=fp_ct,
            termination_id=port_b.pk,
        )
        return cable

    def test_empty_closure(self):
        state = get_live_state(self.closure)
        assert state == {}

    def test_single_splice_on_tray(self):
        self._connect(self.fp1, self.fp2)
        state = get_live_state(self.closure)
        assert self.tray1.pk in state
        pair = (min(self.fp1.pk, self.fp2.pk), max(self.fp1.pk, self.fp2.pk))
        assert pair in state[self.tray1.pk]

    def test_inter_platter_connection(self):
        self._connect(self.fp1, self.fp3)
        state = get_live_state(self.closure)
        assert self.tray1.pk in state
        assert self.tray2.pk in state


class TestDesiredStateAndDiff(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Diff Site", slug="diff-site")
        mfr = Manufacturer.objects.create(name="Diff Mfr", slug="diff-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Closure", slug="diff-closure")
        role = DeviceRole.objects.create(name="Diff Role", slug="diff-role")
        cls.closure = Device.objects.create(name="C-Diff", site=site, device_type=dt, role=role)

        mt = ModuleType.objects.create(manufacturer=mfr, model="Tray")
        bay = ModuleBay.objects.create(device=cls.closure, name="Bay 1")
        cls.tray = Module.objects.create(device=cls.closure, module_bay=bay, module_type=mt)

        cls.fp1 = make_front_port(device=cls.closure, module=cls.tray, name="F1")
        cls.fp2 = make_front_port(device=cls.closure, module=cls.tray, name="F2")
        cls.fp3 = make_front_port(device=cls.closure, module=cls.tray, name="F3")
        cls.fp4 = make_front_port(device=cls.closure, module=cls.tray, name="F4")

        cls.plan = SplicePlan.objects.create(closure=cls.closure, name="Test Plan")

    def test_desired_state_empty_plan(self):
        state = get_desired_state(self.plan)
        assert state == {}

    def test_desired_state_with_entries(self):
        SplicePlanEntry.objects.create(plan=self.plan, tray=self.tray, fiber_a=self.fp1, fiber_b=self.fp2)
        state = get_desired_state(self.plan)
        pair = (min(self.fp1.pk, self.fp2.pk), max(self.fp1.pk, self.fp2.pk))
        assert self.tray.pk in state
        assert pair in state[self.tray.pk]

    def test_diff_add_only(self):
        SplicePlanEntry.objects.create(plan=self.plan, tray=self.tray, fiber_a=self.fp1, fiber_b=self.fp2)
        diff = compute_diff(self.plan)
        tray_diff = diff[self.tray.pk]
        assert len(tray_diff["add"]) == 1
        assert len(tray_diff["remove"]) == 0

    def test_diff_remove_only(self):
        from django.contrib.contenttypes.models import ContentType

        fp_ct = ContentType.objects.get_for_model(FrontPort)
        cable = Cable.objects.create(length=0, length_unit="m")
        CableTermination.objects.create(cable=cable, cable_end="A", termination_type=fp_ct, termination_id=self.fp1.pk)
        CableTermination.objects.create(cable=cable, cable_end="B", termination_type=fp_ct, termination_id=self.fp2.pk)
        diff = compute_diff(self.plan)
        tray_diff = diff[self.tray.pk]
        assert len(tray_diff["add"]) == 0
        assert len(tray_diff["remove"]) == 1

    def test_diff_unchanged(self):
        from django.contrib.contenttypes.models import ContentType

        fp_ct = ContentType.objects.get_for_model(FrontPort)
        cable = Cable.objects.create(length=0, length_unit="m")
        CableTermination.objects.create(cable=cable, cable_end="A", termination_type=fp_ct, termination_id=self.fp1.pk)
        CableTermination.objects.create(cable=cable, cable_end="B", termination_type=fp_ct, termination_id=self.fp2.pk)
        SplicePlanEntry.objects.create(plan=self.plan, tray=self.tray, fiber_a=self.fp1, fiber_b=self.fp2)
        diff = compute_diff(self.plan)
        tray_diff = diff[self.tray.pk]
        assert len(tray_diff["add"]) == 0
        assert len(tray_diff["remove"]) == 0
        assert len(tray_diff["unchanged"]) == 1

    def test_get_or_recompute_caches(self):
        SplicePlanEntry.objects.create(plan=self.plan, tray=self.tray, fiber_a=self.fp1, fiber_b=self.fp2)
        diff = get_or_recompute_diff(self.plan)
        self.plan.refresh_from_db()
        assert self.plan.diff_stale is False
        assert self.plan.cached_diff is not None
        # Second call should use cache
        diff2 = get_or_recompute_diff(self.plan)
        assert diff == diff2


class TestImportLiveState(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Imp Site", slug="imp-site")
        mfr = Manufacturer.objects.create(name="Imp Mfr", slug="imp-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Closure", slug="imp-closure")
        role = DeviceRole.objects.create(name="Imp Role", slug="imp-role")
        cls.closure = Device.objects.create(name="C-Imp", site=site, device_type=dt, role=role)

        mt = ModuleType.objects.create(manufacturer=mfr, model="Tray")
        bay = ModuleBay.objects.create(device=cls.closure, name="Bay 1")
        cls.tray = Module.objects.create(device=cls.closure, module_bay=bay, module_type=mt)

        cls.fp1 = make_front_port(device=cls.closure, module=cls.tray, name="F1")
        cls.fp2 = make_front_port(device=cls.closure, module=cls.tray, name="F2")

    def test_import_creates_entries(self):
        cable = Cable.objects.create(length=0, length_unit="m")
        CableTermination.objects.create(cable=cable, cable_end="A", termination=self.fp1)
        CableTermination.objects.create(cable=cable, cable_end="B", termination=self.fp2)

        plan = SplicePlan.objects.create(closure=self.closure, name="Import Plan")
        count = import_live_state(plan)
        assert count == 1
        assert plan.entries.count() == 1
        entry = plan.entries.first()
        assert {entry.fiber_a_id, entry.fiber_b_id} == {self.fp1.pk, self.fp2.pk}

    def test_import_empty_closure(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Empty Plan")
        count = import_live_state(plan)
        assert count == 0


class TestApplyDiff(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="App Site", slug="app-site")
        mfr = Manufacturer.objects.create(name="App Mfr", slug="app-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Closure", slug="app-closure")
        role = DeviceRole.objects.create(name="App Role", slug="app-role")
        cls.closure = Device.objects.create(name="C-App", site=site, device_type=dt, role=role)

        mt = ModuleType.objects.create(manufacturer=mfr, model="Tray")
        bay = ModuleBay.objects.create(device=cls.closure, name="Bay 1")
        cls.tray = Module.objects.create(device=cls.closure, module_bay=bay, module_type=mt)

        cls.fp1 = make_front_port(device=cls.closure, module=cls.tray, name="F1")
        cls.fp2 = make_front_port(device=cls.closure, module=cls.tray, name="F2")
        cls.fp3 = make_front_port(device=cls.closure, module=cls.tray, name="F3")
        cls.fp4 = make_front_port(device=cls.closure, module=cls.tray, name="F4")

    def test_apply_creates_cables(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Apply Plan")
        SplicePlanEntry.objects.create(plan=plan, tray=self.tray, fiber_a=self.fp1, fiber_b=self.fp2)
        result = apply_diff(plan)
        assert result["added"] == 1
        assert result["removed"] == 0

        from django.contrib.contenttypes.models import ContentType

        fp_ct = ContentType.objects.get_for_model(FrontPort)
        terms = CableTermination.objects.filter(termination_type=fp_ct, termination_id=self.fp1.pk)
        assert terms.exists()

    def test_apply_removes_cables(self):
        cable = Cable.objects.create(length=0, length_unit="m")
        CableTermination.objects.create(cable=cable, cable_end="A", termination=self.fp3)
        CableTermination.objects.create(cable=cable, cable_end="B", termination=self.fp4)

        plan = SplicePlan.objects.create(closure=self.closure, name="Remove Plan")
        result = apply_diff(plan)
        assert result["removed"] == 1
        assert not Cable.objects.filter(pk=cable.pk).exists()

    def test_apply_does_not_change_status(self):
        """apply_diff() no longer changes status — batch apply handles archiving."""
        from netbox_fms.choices import SplicePlanStatusChoices

        plan = SplicePlan.objects.create(closure=self.closure, name="Status Plan")
        apply_diff(plan)
        plan.refresh_from_db()
        assert plan.status == SplicePlanStatusChoices.DRAFT
