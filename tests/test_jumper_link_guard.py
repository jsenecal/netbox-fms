"""Splice jumpers must not be linkable as FiberCables (issue #132).

Applying a splice plan creates one dcim.Cable per fiber pair, terminated
on two tray FrontPorts of the same closure. Those jumpers are not fiber
topology: the Cable detail page must not offer "Link Fiber Cable" on
them, and FiberCable must refuse to attach to one.
"""

import pytest
from dcim.models import Cable, Device, RearPort
from django.core.exceptions import ValidationError
from django.test import TestCase

from netbox_fms.models import FiberCable, FiberCableType
from netbox_fms.services import is_intra_closure_jumper
from netbox_fms.template_content import CableFiberCablePanel
from tests.conftest import make_closure_with_tray, make_front_port, render_left_page


class TestIsIntraClosureJumper(TestCase):
    @classmethod
    def setUpTestData(cls):
        rig = make_closure_with_tray("JG", port_count=2)
        cls.closure = rig.closure
        cls.fp1, cls.fp2 = rig.ports
        cls.far_device = Device.objects.create(name="JG-Far", site=rig.site, device_type=rig.device_type, role=rig.role)
        cls.far_fp = make_front_port(cls.far_device, "JG-Far-FP")
        cls.rear_port = RearPort.objects.create(device=cls.closure, name="JG-RP", type="splice", positions=2)

    def test_jumper_between_front_ports_of_one_device(self):
        cable = Cable.objects.create(a_terminations=[self.fp1], b_terminations=[self.fp2], length=0, length_unit="m")
        assert is_intra_closure_jumper(cable) is True

    def test_cable_between_front_ports_of_two_devices(self):
        cable = Cable.objects.create(a_terminations=[self.fp1], b_terminations=[self.far_fp])
        assert is_intra_closure_jumper(cable) is False

    def test_cable_terminated_on_rear_port(self):
        cable = Cable.objects.create(a_terminations=[self.rear_port], b_terminations=[self.far_fp])
        assert is_intra_closure_jumper(cable) is False

    def test_unterminated_cable(self):
        cable = Cable.objects.create()
        assert is_intra_closure_jumper(cable) is False


class TestFiberCableRejectsJumper(TestCase):
    @classmethod
    def setUpTestData(cls):
        rig = make_closure_with_tray("JGC", port_count=2)
        cls.fp1, cls.fp2 = rig.ports
        cls.fct = FiberCableType.objects.create(
            manufacturer=rig.mfr,
            model="JGC-FCT",
            construction="tight_buffer",
            strand_count=2,
        )
        cls.jumper = Cable.objects.create(a_terminations=[cls.fp1], b_terminations=[cls.fp2], length=0, length_unit="m")

    def test_clean_rejects_jumper_cable(self):
        fc = FiberCable(cable=self.jumper, fiber_cable_type=self.fct)
        with pytest.raises(ValidationError):
            fc.full_clean()


class TestCablePanelSkipsJumper(TestCase):
    """CableFiberCablePanel must not offer "Link Fiber Cable" on a jumper."""

    @classmethod
    def setUpTestData(cls):
        rig = make_closure_with_tray("JGP", port_count=2)
        cls.fp1, cls.fp2 = rig.ports
        cls.far_device = Device.objects.create(
            name="JGP-Far", site=rig.site, device_type=rig.device_type, role=rig.role
        )
        cls.far_fp = make_front_port(cls.far_device, "JGP-Far-FP")

    def test_no_link_action_for_jumper(self):
        jumper = Cable.objects.create(a_terminations=[self.fp1], b_terminations=[self.fp2], length=0, length_unit="m")
        assert "Link Fiber Cable" not in render_left_page(CableFiberCablePanel, jumper)

    def test_link_action_kept_for_topology_cable(self):
        cable = Cable.objects.create(a_terminations=[self.fp1], b_terminations=[self.far_fp])
        assert "Link Fiber Cable" in render_left_page(CableFiberCablePanel, cable)
