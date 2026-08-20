"""Tests for carrying the express flag through the splice editor backend.

Regression tests for issue #117: the visual splice editor had no way to set
SplicePlanEntry.is_express, and the bulk-update endpoint silently dropped it.
"""

from dcim.models import Cable, Device
from django.test import TestCase

from netbox_fms.choices import SplicePlanStatusChoices
from netbox_fms.models import FiberCable, FiberCableType, SplicePlan, SplicePlanEntry
from tests.conftest import make_authed_client, make_closure_with_tray, make_front_port


class TestBulkUpdateExpressFlag(TestCase):
    """bulk_update_entries must accept and persist is_express on added entries."""

    def setUp(self):
        rig = make_closure_with_tray("EX")
        self.fp1, self.fp2 = rig.ports
        self.plan = SplicePlan.objects.create(
            closure=rig.closure,
            name="EX Plan",
            status=SplicePlanStatusChoices.DRAFT,
        )
        self.client = make_authed_client("ex-user")
        self.url = f"/api/plugins/fms/splice-plans/{self.plan.pk}/bulk-update/"

    def _post(self, add):
        return self.client.post(
            self.url,
            {"add": add, "remove": []},
            format="json",
            HTTP_X_CHANGELOG_MESSAGE="express flag test",
        )

    def test_add_with_is_express_persists(self):
        resp = self._post([{"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk, "is_express": True}])
        assert resp.status_code == 200
        entry = SplicePlanEntry.objects.get(plan=self.plan, fiber_a=self.fp1, fiber_b=self.fp2)
        assert entry.is_express is True

    def test_add_defaults_to_not_express(self):
        resp = self._post([{"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk}])
        assert resp.status_code == 200
        entry = SplicePlanEntry.objects.get(plan=self.plan, fiber_a=self.fp1, fiber_b=self.fp2)
        assert entry.is_express is False

    def test_re_add_updates_express_on_existing_entry(self):
        """Re-adding the same fiber pair with a new flag replaces the entry."""
        self._post([{"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk}])
        resp = self._post([{"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk, "is_express": True}])
        assert resp.status_code == 200
        entry = SplicePlanEntry.objects.get(plan=self.plan, fiber_a=self.fp1, fiber_b=self.fp2)
        assert entry.is_express is True

    def test_response_entries_include_is_express(self):
        resp = self._post([{"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk, "is_express": True}])
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        assert len(entries) == 1
        assert entries[0]["is_express"] is True


class TestClosureStrandsExpressExposure(TestCase):
    """The closure-strands view must expose the plan entry's express flag."""

    @classmethod
    def setUpTestData(cls):
        rig = make_closure_with_tray("EXS", port_count=4)
        cls.closure = rig.closure
        far_device = Device.objects.create(name="EXS-Far", site=rig.site, device_type=rig.device_type, role=rig.role)
        far_fp = make_front_port(far_device, "EXS-Far-FP")
        cable = Cable.objects.create(a_terminations=[rig.ports[0]], b_terminations=[far_fp])
        fct = FiberCableType.objects.create(
            manufacturer=rig.mfr, model="EXS-TB4", strand_count=4, construction="tight_buffer"
        )
        fc = FiberCable.objects.create(cable=cable, fiber_cable_type=fct)

        cls.strands = list(fc.fiber_strands.order_by("position"))
        for strand, fp in zip(cls.strands, rig.ports, strict=True):
            strand.front_port_a = fp
            strand.save()

        cls.plan = SplicePlan.objects.create(
            closure=cls.closure,
            name="EXS Plan",
            status=SplicePlanStatusChoices.DRAFT,
        )
        SplicePlanEntry.objects.create(
            plan=cls.plan, tray=rig.tray, fiber_a=rig.ports[0], fiber_b=rig.ports[1], is_express=True
        )
        SplicePlanEntry.objects.create(plan=cls.plan, tray=rig.tray, fiber_a=rig.ports[2], fiber_b=rig.ports[3])

    def setUp(self):
        self.client = make_authed_client("exs-user")

    def test_plan_is_express_exposed_per_strand(self):
        resp = self.client.get(f"/api/plugins/fms/closure-strands/{self.closure.pk}/?plan_id={self.plan.pk}")
        assert resp.status_code == 200
        strands = {s["id"]: s for s in resp.data["cables"][0]["loose_strands"]}
        express_pair = (self.strands[0].pk, self.strands[1].pk)
        normal_pair = (self.strands[2].pk, self.strands[3].pk)
        for pk in express_pair:
            assert strands[pk]["plan_is_express"] is True
        for pk in normal_pair:
            assert strands[pk]["plan_is_express"] is False
