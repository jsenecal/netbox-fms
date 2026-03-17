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
