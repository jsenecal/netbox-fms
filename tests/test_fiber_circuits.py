from dcim.models import Device, DeviceRole, DeviceType, FrontPort, Manufacturer, Module, ModuleBay, ModuleType, Site
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from netbox_fms.choices import FiberCircuitStatusChoices
from netbox_fms.models import FiberCircuit, FiberCircuitPath


class TestFiberCircuitStatusChoices(TestCase):
    def test_has_planned(self):
        assert FiberCircuitStatusChoices.PLANNED == "planned"

    def test_has_staged(self):
        assert FiberCircuitStatusChoices.STAGED == "staged"

    def test_has_active(self):
        assert FiberCircuitStatusChoices.ACTIVE == "active"

    def test_has_decommissioned(self):
        assert FiberCircuitStatusChoices.DECOMMISSIONED == "decommissioned"


class TestFiberCircuit(TestCase):
    def test_create_circuit(self):
        from netbox_fms.models import FiberCircuit

        circuit = FiberCircuit.objects.create(
            name="DT-CTR-1",
            status=FiberCircuitStatusChoices.PLANNED,
            strand_count=2,
        )
        assert circuit.pk is not None
        assert str(circuit) == "DT-CTR-1"

    def test_optional_fields(self):
        from netbox_fms.models import FiberCircuit

        circuit = FiberCircuit.objects.create(
            name="DT-CTR-2",
            status=FiberCircuitStatusChoices.ACTIVE,
            strand_count=12,
            cid="CARRIER-12345",
            description="Downtown to Central ribbon",
        )
        assert circuit.cid == "CARRIER-12345"
        assert circuit.description == "Downtown to Central ribbon"

    def test_get_absolute_url(self):
        from netbox_fms.models import FiberCircuit

        circuit = FiberCircuit.objects.create(
            name="URL-Test",
            status=FiberCircuitStatusChoices.PLANNED,
            strand_count=1,
        )
        assert "/fiber-circuits/" in circuit.get_absolute_url()

    def test_default_status(self):
        from netbox_fms.models import FiberCircuit

        circuit = FiberCircuit.objects.create(
            name="Default-Status",
            strand_count=2,
        )
        assert circuit.status == FiberCircuitStatusChoices.PLANNED


class TestFiberCircuitPath(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.circuit = FiberCircuit.objects.create(
            name="Path-Test",
            status=FiberCircuitStatusChoices.ACTIVE,
            strand_count=2,
        )
        site = Site.objects.create(name="Path Site", slug="path-site")
        mfr = Manufacturer.objects.create(name="Path Mfr", slug="path-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="PathDev", slug="pathdev")
        role = DeviceRole.objects.create(name="Path Role", slug="path-role")
        device = Device.objects.create(name="PathDev-1", site=site, device_type=dt, role=role)
        mt = ModuleType.objects.create(manufacturer=mfr, model="PathTray")
        bay = ModuleBay.objects.create(device=device, name="Bay1")
        tray = Module.objects.create(device=device, module_bay=bay, module_type=mt)
        cls.fp_a = FrontPort.objects.create(device=device, module=tray, name="PA1", type="lc")
        cls.fp_b = FrontPort.objects.create(device=device, module=tray, name="PA2", type="lc")

    def test_create_path(self):
        path = FiberCircuitPath.objects.create(
            circuit=self.circuit,
            position=1,
            origin=self.fp_a,
            destination=self.fp_b,
            path=[],
            is_complete=True,
        )
        assert path.pk is not None

    def test_unique_position_per_circuit(self):
        FiberCircuitPath.objects.create(
            circuit=self.circuit,
            position=1,
            origin=self.fp_a,
            path=[],
            is_complete=False,
        )
        with self.assertRaises(IntegrityError):
            FiberCircuitPath.objects.create(
                circuit=self.circuit,
                position=1,
                origin=self.fp_b,
                path=[],
                is_complete=False,
            )

    def test_destination_nullable(self):
        path = FiberCircuitPath.objects.create(
            circuit=self.circuit,
            position=1,
            origin=self.fp_a,
            path=[],
            is_complete=False,
        )
        assert path.destination is None

    def test_loss_fields_nullable(self):
        path = FiberCircuitPath.objects.create(
            circuit=self.circuit,
            position=1,
            origin=self.fp_a,
            path=[],
            is_complete=False,
        )
        assert path.calculated_loss_db is None
        assert path.actual_loss_db is None
        assert path.wavelength_nm is None

    def test_wavelength_required_when_loss_set(self):
        path = FiberCircuitPath(
            circuit=self.circuit,
            position=1,
            origin=self.fp_a,
            path=[],
            is_complete=False,
            calculated_loss_db=3.5,
            wavelength_nm=None,
        )
        with self.assertRaises(ValidationError):
            path.full_clean()

    def test_strand_count_validation(self):
        circuit = FiberCircuit.objects.create(
            name="Small-Circuit",
            status=FiberCircuitStatusChoices.PLANNED,
            strand_count=1,
        )
        FiberCircuitPath.objects.create(
            circuit=circuit,
            position=1,
            origin=self.fp_a,
            path=[],
            is_complete=False,
        )
        path2 = FiberCircuitPath(
            circuit=circuit,
            position=2,
            origin=self.fp_b,
            path=[],
            is_complete=False,
        )
        with self.assertRaises(ValidationError):
            path2.full_clean()
