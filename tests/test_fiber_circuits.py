from django.test import TestCase

from netbox_fms.choices import FiberCircuitStatusChoices


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
