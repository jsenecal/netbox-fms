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
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from netbox_fms.models import SplicePlan
from tests.conftest import make_front_port


class TestDiffCacheInvalidation(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Sig Site", slug="sig-site")
        mfr = Manufacturer.objects.create(name="Sig Mfr", slug="sig-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Closure", slug="sig-closure")
        role = DeviceRole.objects.create(name="Sig Role", slug="sig-role")
        cls.closure = Device.objects.create(name="C-Sig", site=site, device_type=dt, role=role)

        mt = ModuleType.objects.create(manufacturer=mfr, model="Tray")
        bay = ModuleBay.objects.create(device=cls.closure, name="Bay 1")
        cls.tray = Module.objects.create(device=cls.closure, module_bay=bay, module_type=mt)

        cls.fp1 = make_front_port(device=cls.closure, module=cls.tray, name="F1")
        cls.fp2 = make_front_port(device=cls.closure, module=cls.tray, name="F2")

    def _make_cable_with_terminations(self, port_a, port_b):
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

    def test_cable_create_invalidates_cache(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Plan")
        plan.diff_stale = False
        plan.cached_diff = {"some": "data"}
        plan.save(update_fields=["diff_stale", "cached_diff"])

        cable = self._make_cable_with_terminations(self.fp1, self.fp2)
        cable.save()  # Trigger post_save again after terminations exist

        plan.refresh_from_db()
        assert plan.diff_stale is True

    def test_cable_delete_invalidates_cache(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Plan")
        cable = self._make_cable_with_terminations(self.fp1, self.fp2)

        plan.diff_stale = False
        plan.cached_diff = {"some": "data"}
        plan.save(update_fields=["diff_stale", "cached_diff"])

        cable.delete()

        plan.refresh_from_db()
        assert plan.diff_stale is True

    def test_unrelated_cable_does_not_invalidate(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Plan")
        plan.diff_stale = False
        plan.cached_diff = {"some": "data"}
        plan.save(update_fields=["diff_stale", "cached_diff"])

        # Cable with no terminations on our closure
        cable = Cable.objects.create(length=10, length_unit="m")
        cable.save()

        plan.refresh_from_db()
        assert plan.diff_stale is False
