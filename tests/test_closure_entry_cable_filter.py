"""Tests for filtering fiber cables by terminated device (issue #92)."""

from dcim.models import Cable, CableTermination, Device, DeviceRole, DeviceType, Manufacturer, RearPort, Site
from django.test import TestCase

from netbox_fms.filters import FiberCableFilterSet
from netbox_fms.forms import ClosureCableEntryForm
from netbox_fms.models import FiberCable, FiberCableType


class TestFiberCableTerminatedDeviceFilter(TestCase):
    """FiberCableFilterSet.terminated_device_id narrows cables to those terminated at a device (#92)."""

    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="CEF Site", slug="cef-site")
        mfr = Manufacturer.objects.create(name="CEF Mfr", slug="cef-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="CEF Closure", slug="cef-closure")
        role = DeviceRole.objects.create(name="CEF Role", slug="cef-role")
        cls.closure_a = Device.objects.create(name="CEF-A", site=site, device_type=dt, role=role)
        cls.closure_b = Device.objects.create(name="CEF-B", site=site, device_type=dt, role=role)

        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="CEF-12F", construction="loose_tube", strand_count=12
        )

        rp_a = RearPort.objects.create(device=cls.closure_a, name="CEF-RP-A", type="splice", positions=12)
        rp_b = RearPort.objects.create(device=cls.closure_b, name="CEF-RP-B", type="splice", positions=12)

        cable_a = Cable.objects.create()
        CableTermination.objects.create(cable=cable_a, cable_end="A", termination=rp_a)
        cls.fc_terminated = FiberCable.objects.create(cable=cable_a, fiber_cable_type=fct)

        cable_b = Cable.objects.create()
        CableTermination.objects.create(cable=cable_b, cable_end="A", termination=rp_b)
        cls.fc_elsewhere = FiberCable.objects.create(cable=cable_b, fiber_cable_type=fct)

        cls.fc_unterminated = FiberCable.objects.create(cable=Cable.objects.create(), fiber_cable_type=fct)

    def test_filter_returns_only_cables_terminated_at_device(self):
        qs = FiberCableFilterSet({"terminated_device_id": [self.closure_a.pk]}, queryset=FiberCable.objects.all()).qs
        assert set(qs) == {self.fc_terminated}

    def test_unfiltered_returns_all(self):
        qs = FiberCableFilterSet({}, queryset=FiberCable.objects.all()).qs
        assert {self.fc_terminated, self.fc_elsewhere, self.fc_unterminated} <= set(qs)

    def test_both_ends_terminated_at_device_not_duplicated(self):
        rp_a2 = RearPort.objects.create(device=self.closure_a, name="CEF-RP-A2", type="splice", positions=12)
        CableTermination.objects.create(cable=self.fc_terminated.cable, cable_end="B", termination=rp_a2)
        qs = FiberCableFilterSet({"terminated_device_id": [self.closure_a.pk]}, queryset=FiberCable.objects.all()).qs
        assert list(qs) == [self.fc_terminated]

    def test_entry_form_chains_fiber_cable_on_closure(self):
        field = ClosureCableEntryForm().fields["fiber_cable"]
        assert field.query_params == {"terminated_device_id": "$closure"}
