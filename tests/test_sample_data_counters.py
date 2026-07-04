"""Regression tests for issue #62: sample-data provisioning must keep
NetBox's device counter caches in sync.

Device component tabs (Front Ports, Interfaces, ...) are hidden when the
corresponding CounterCacheField is zero (ViewTab hide_if_empty). Ports
created via bulk_create() skip post_save, so the counters never increment
and the tabs disappear even though the ports exist.
"""

from dcim.models import Cable, Device, DeviceRole, DeviceType, FrontPort, Manufacturer, RearPort, Site
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from netbox_fms.management.commands.create_sample_data import Command
from netbox_fms.models import FiberCable, FiberCableType


class TestSampleDataCounterSync(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="SDC Site", slug="sdc-site")
        mfr = Manufacturer.objects.create(name="SDC Mfr", slug="sdc-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="SDC Closure", slug="sdc-closure")
        role = DeviceRole.objects.create(name="SDC Role", slug="sdc-role")
        cls.device_a = Device.objects.create(name="SDC-A", site=site, device_type=dt, role=role)
        cls.device_b = Device.objects.create(name="SDC-B", site=site, device_type=dt, role=role)
        cls.fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="SDC-2F",
            construction="tight_buffer",
            strand_count=2,
        )

    def _command(self):
        cmd = Command()
        cmd.rp_ct = ContentType.objects.get_for_model(RearPort)
        cmd.fp_ct = ContentType.objects.get_for_model(FrontPort)
        return cmd

    def test_provisioned_front_ports_update_device_counter(self):
        cable = Cable.objects.create(type="smf-os2")
        fc = FiberCable.objects.create(cable=cable, fiber_cable_type=self.fct)

        self._command()._create_ports_and_link_strands(
            {
                "cable": cable,
                "fiber_cable": fc,
                "a_device": self.device_a,
                "b_device": self.device_b,
            }
        )

        self.device_a.refresh_from_db()
        created = FrontPort.objects.filter(device=self.device_a).count()
        assert created == 2
        assert self.device_a.front_port_count == created

    def test_created_interfaces_update_device_counter(self):
        self._command()._create_interfaces(self.device_a, 2, "eth")

        self.device_a.refresh_from_db()
        assert self.device_a.interface_count == 2
