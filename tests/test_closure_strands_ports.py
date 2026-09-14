"""Closure-strands API must not lose splices on device-level front ports.

Regression tests for issue #108: the visual splice editor saved plan
entries but rendered nothing after reload. The closure-strands endpoint
built its plan and live splice lookups only from tray-mounted front
ports (module set), yet a strand's closure-side port legitimately sits
at device level while its buffer tube is unassigned (and returns there
when a tube assignment is deleted). Entries touching such a port were
silently dropped, while the fiber-claims endpoint (ghost lines) has no
such filter -- exactly the reported asymmetry.
"""

from dcim.models import Cable, Device, RearPort
from django.test import TestCase

from netbox_fms.choices import SplicePlanStatusChoices
from netbox_fms.models import FiberCable, FiberCableType, SplicePlan, SplicePlanEntry
from tests.conftest import make_authed_client, make_closure_with_tray, make_front_port


class TestClosureStrandsDeviceLevelPorts(TestCase):
    @classmethod
    def setUpTestData(cls):
        rig = make_closure_with_tray("DLP", port_count=2)
        cls.closure = rig.closure
        cls.tray = rig.tray
        cls.tray_fp1, cls.tray_fp2 = rig.ports
        # Closure-side ports of tubes that are not assigned to any tray
        cls.dev_fp1 = make_front_port(cls.closure, "DLP-Dev-F1")
        cls.dev_fp2 = make_front_port(cls.closure, "DLP-Dev-F2")
        cls.dev_fp3 = make_front_port(cls.closure, "DLP-Dev-F3")

        cls.far_device = Device.objects.create(
            name="DLP-Far", site=rig.site, device_type=rig.device_type, role=rig.role
        )
        far_fp = make_front_port(cls.far_device, "DLP-Far-FP")

        rp = RearPort.objects.create(device=cls.closure, name="DLP-RP", type="splice", positions=5)
        cable = Cable.objects.create(
            a_terminations=[rp], b_terminations=[make_front_port(cls.far_device, "DLP-Far-RPFP")]
        )
        fct = FiberCableType.objects.create(
            manufacturer=rig.mfr, model="DLP-TB5", strand_count=5, construction="tight_buffer"
        )
        fc = FiberCable.objects.create(cable=cable, fiber_cable_type=fct)

        s1, s2, s3, s4, s5 = list(fc.fiber_strands.order_by("position"))
        s1.front_port_a = cls.tray_fp1
        s1.save()
        s2.front_port_a = cls.dev_fp1
        s2.save()
        # Local end is B: the far device owns front_port_a
        s3.front_port_a = far_fp
        s3.front_port_b = cls.dev_fp2
        s3.save()
        s4.front_port_a = cls.tray_fp2
        s4.save()
        s5.front_port_a = cls.dev_fp3
        s5.save()
        cls.strands = [s1, s2, s3, s4, s5]

        # Plan splice between a tray port and a device-level port, as the
        # bulk-update endpoint records it (fiber_a must be tray-mounted,
        # fiber_b is not checked).
        cls.plan = SplicePlan.objects.create(closure=cls.closure, name="DLP Plan", status=SplicePlanStatusChoices.DRAFT)
        SplicePlanEntry.objects.create(plan=cls.plan, tray=cls.tray, fiber_a=cls.tray_fp1, fiber_b=cls.dev_fp1)

        # Live splice jumper between a tray port and a device-level port
        # (applied while assigned, tube unassigned afterwards).
        Cable.objects.create(a_terminations=[cls.tray_fp2], b_terminations=[cls.dev_fp3], length=0, length_unit="m")

    def _get_strands(self):
        client = make_authed_client("dlp-user")
        resp = client.get(f"/api/plugins/fms/closure-strands/{self.closure.pk}/?plan_id={self.plan.pk}")
        assert resp.status_code == 200
        return {s["id"]: s for s in resp.data["cables"][0]["loose_strands"]}

    def test_plan_entry_on_device_level_port_renders(self):
        strands = self._get_strands()
        s1, s2 = self.strands[0], self.strands[1]
        assert strands[s1.pk]["plan_spliced_to"] == s2.pk
        assert strands[s2.pk]["plan_spliced_to"] == s1.pk

    def test_live_splice_on_device_level_port_renders(self):
        strands = self._get_strands()
        s4, s5 = self.strands[3], self.strands[4]
        assert strands[s4.pk]["live_spliced_to"] == s5.pk
        assert strands[s5.pk]["live_spliced_to"] == s4.pk

    def test_local_device_port_preferred_over_far_end(self):
        strands = self._get_strands()
        s3 = self.strands[2]
        assert strands[s3.pk]["front_port_a_id"] == self.dev_fp2.pk
