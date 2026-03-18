"""Tests for StorageMethodChoices and SplicePlanEntry.is_express field."""

import pytest

from netbox_fms.choices import StorageMethodChoices


@pytest.mark.django_db
class TestStorageMethodChoices:
    """Verify all 5 StorageMethodChoices constants exist."""

    def test_coil_constant(self):
        assert StorageMethodChoices.COIL == "coil"

    def test_figure_8_constant(self):
        assert StorageMethodChoices.FIGURE_8 == "figure_8"

    def test_in_tray_constant(self):
        assert StorageMethodChoices.IN_TRAY == "in_tray"

    def test_on_pole_constant(self):
        assert StorageMethodChoices.ON_POLE == "on_pole"

    def test_in_vault_constant(self):
        assert StorageMethodChoices.IN_VAULT == "in_vault"

    def test_choices_tuple_has_five_entries(self):
        assert len(StorageMethodChoices.CHOICES) == 5


@pytest.mark.django_db
class TestSplicePlanEntryIsExpress:
    """Test is_express field on SplicePlanEntry."""

    @pytest.fixture
    def setup_data(self):
        from dcim.models import Device, DeviceRole, DeviceType, FrontPort, Manufacturer, Module, ModuleBay, ModuleType
        from django.contrib.contenttypes.models import ContentType
        from dcim.models import Site

        site = Site.objects.create(name="SL Test Site", slug="sl-test-site")
        mfr = Manufacturer.objects.create(name="SL Test Mfr", slug="sl-test-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Closure", slug="sl-closure")
        role = DeviceRole.objects.create(name="SL Splice Closure", slug="sl-splice-closure")
        closure = Device.objects.create(name="SL-Closure-1", site=site, device_type=dt, role=role)
        mt = ModuleType.objects.create(manufacturer=mfr, model="SL Tray")
        mb = ModuleBay.objects.create(device=closure, name="SL-Bay-1")
        tray = Module.objects.create(device=closure, module_bay=mb, module_type=mt)
        fp_a = FrontPort.objects.create(device=closure, module=tray, name="SL-FP-A", type="lc")
        fp_b = FrontPort.objects.create(device=closure, module=tray, name="SL-FP-B", type="lc")

        from netbox_fms.models import SplicePlan

        plan = SplicePlan.objects.create(closure=closure, name="SL Test Plan")
        return {
            "plan": plan,
            "tray": tray,
            "fp_a": fp_a,
            "fp_b": fp_b,
        }

    def test_is_express_defaults_to_false(self, setup_data):
        from netbox_fms.models import SplicePlanEntry

        entry = SplicePlanEntry.objects.create(
            plan=setup_data["plan"],
            tray=setup_data["tray"],
            fiber_a=setup_data["fp_a"],
            fiber_b=setup_data["fp_b"],
        )
        assert entry.is_express is False

    def test_is_express_can_be_set_true(self, setup_data):
        from netbox_fms.models import SplicePlanEntry

        entry = SplicePlanEntry.objects.create(
            plan=setup_data["plan"],
            tray=setup_data["tray"],
            fiber_a=setup_data["fp_a"],
            fiber_b=setup_data["fp_b"],
            is_express=True,
        )
        assert entry.is_express is True
