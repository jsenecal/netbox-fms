from dcim.models import (
    Cable,
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
from django.db import IntegrityError, models
from django.test import TestCase

from netbox_fms.choices import FiberCircuitStatusChoices
from netbox_fms.models import FiberCircuit, FiberCircuitNode, FiberCircuitPath


class TestFiberCircuitNode(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Node Site", slug="node-site")
        mfr = Manufacturer.objects.create(name="Node Mfr", slug="node-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="NodeDev", slug="nodedev")
        role = DeviceRole.objects.create(name="Node Role", slug="node-role")
        device = Device.objects.create(name="NodeDev-1", site=site, device_type=dt, role=role)
        mt = ModuleType.objects.create(manufacturer=mfr, model="NodeTray")
        bay = ModuleBay.objects.create(device=device, name="Bay1")
        tray = Module.objects.create(device=device, module_bay=bay, module_type=mt)
        cls.fp = FrontPort.objects.create(device=device, module=tray, name="NF1", type="lc")
        cls.cable = Cable.objects.create()
        cls.circuit = FiberCircuit.objects.create(
            name="Node-Test",
            status=FiberCircuitStatusChoices.ACTIVE,
            strand_count=1,
        )
        cls.path = FiberCircuitPath.objects.create(
            circuit=cls.circuit,
            position=1,
            origin=cls.fp,
            path=[],
            is_complete=False,
        )

    def test_create_cable_node(self):
        node = FiberCircuitNode.objects.create(path=self.path, position=1, cable=self.cable)
        assert node.pk is not None

    def test_create_front_port_node(self):
        node = FiberCircuitNode.objects.create(path=self.path, position=2, front_port=self.fp)
        assert node.pk is not None

    def test_unique_position_per_path(self):
        FiberCircuitNode.objects.create(path=self.path, position=1, cable=self.cable)
        with self.assertRaises(IntegrityError):
            FiberCircuitNode.objects.create(path=self.path, position=1, front_port=self.fp)

    def test_protect_cable_deletion(self):
        cable = Cable.objects.create()
        FiberCircuitNode.objects.create(path=self.path, position=10, cable=cable)
        with self.assertRaises(models.ProtectedError):
            cable.delete()

    def test_protect_front_port_deletion(self):
        site = Site.objects.create(name="FP Prot Site", slug="fp-prot-site")
        mfr = Manufacturer.objects.create(name="FP Prot Mfr", slug="fp-prot-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="FPProtDev", slug="fpprotdev")
        role = DeviceRole.objects.create(name="FP Prot Role", slug="fp-prot-role")
        dev = Device.objects.create(name="FPProtDev-1", site=site, device_type=dt, role=role)
        fp = FrontPort.objects.create(device=dev, name="ProtFP", type="lc")
        FiberCircuitNode.objects.create(path=self.path, position=11, front_port=fp)
        with self.assertRaises(models.ProtectedError):
            fp.delete()

    def test_cascade_on_path_delete(self):
        circuit = FiberCircuit.objects.create(
            name="Cascade-Test",
            status=FiberCircuitStatusChoices.ACTIVE,
            strand_count=1,
        )
        path = FiberCircuitPath.objects.create(
            circuit=circuit,
            position=1,
            origin=self.fp,
            path=[],
            is_complete=False,
        )
        cable = Cable.objects.create()
        FiberCircuitNode.objects.create(path=path, position=1, cable=cable)
        path_pk = path.pk
        assert FiberCircuitNode.objects.filter(path_id=path_pk).count() == 1
        path.delete()
        assert FiberCircuitNode.objects.filter(path_id=path_pk).count() == 0


class TestFiberCircuitLifecycle(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="LC Site", slug="lc-site")
        mfr = Manufacturer.objects.create(name="LC Mfr", slug="lc-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="LCDev", slug="lcdev")
        role = DeviceRole.objects.create(name="LC Role", slug="lc-role")
        device = Device.objects.create(name="LCDev-1", site=site, device_type=dt, role=role)
        cls.fp = FrontPort.objects.create(device=device, name="LF1", type="lc")
        cls.cable = Cable.objects.create()

    def test_decommission_deletes_nodes(self):
        circuit = FiberCircuit.objects.create(
            name="Decomm-Test",
            status=FiberCircuitStatusChoices.ACTIVE,
            strand_count=1,
        )
        path = FiberCircuitPath.objects.create(
            circuit=circuit,
            position=1,
            origin=self.fp,
            path=[{"type": "cable", "id": self.cable.pk}],
            is_complete=False,
        )
        FiberCircuitNode.objects.create(path=path, position=1, cable=self.cable)
        assert FiberCircuitNode.objects.filter(path__circuit=circuit).count() == 1

        circuit.status = FiberCircuitStatusChoices.DECOMMISSIONED
        circuit.save()

        assert FiberCircuitNode.objects.filter(path__circuit=circuit).count() == 0

    def test_reactivate_rebuilds_nodes(self):
        circuit = FiberCircuit.objects.create(
            name="Reactivate-Test",
            status=FiberCircuitStatusChoices.DECOMMISSIONED,
            strand_count=1,
        )
        path = FiberCircuitPath.objects.create(
            circuit=circuit,
            position=1,
            origin=self.fp,
            path=[{"type": "cable", "id": self.cable.pk}],
            is_complete=False,
        )
        assert FiberCircuitNode.objects.filter(path__circuit=circuit).count() == 0

        circuit.status = FiberCircuitStatusChoices.ACTIVE
        circuit.save()

        assert FiberCircuitNode.objects.filter(path__circuit=circuit).count() == 1
        node = FiberCircuitNode.objects.get(path=path)
        assert node.cable_id == self.cable.pk
