"""Tests for StorageMethodChoices, SplicePlanEntry.is_express field, and SlackLoop model."""

from decimal import Decimal

import pytest
from django.db import IntegrityError, connection

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


@pytest.mark.django_db
class TestSlackLoopModel:
    """Tests for SlackLoop model."""

    @pytest.fixture(autouse=True)
    def setup_data(self):
        from dcim.models import Cable, Manufacturer, Site, Location
        from netbox_fms.models import FiberCable, FiberCableType

        site = Site.objects.create(name="SLM-Site", slug="slm-site")
        location = Location.objects.create(name="SLM-Location", slug="slm-location", site=site)
        mfr = Manufacturer.objects.create(name="SLM-Mfr", slug="slm-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="SLM-FCT",
            fiber_type="smf_os2",
            construction="tight_buffer",
            strand_count=1,
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO dcim_cable (type, status, label, color, comments, description, profile, custom_field_data, created, last_updated) VALUES (%s, %s, '', '', '', '', '{}', '{}', NOW(), NOW()) RETURNING id",
                ["smf-os2", "connected"],
            )
            cable_id = cursor.fetchone()[0]
        cable = Cable.objects.get(pk=cable_id)
        fc = FiberCable.objects.create(fiber_cable_type=fct, cable=cable)

        self.site = site
        self.location = location
        self.fiber_cable = fc
        self.cable = cable

    def test_create_slack_loop(self):
        from netbox_fms.models import SlackLoop

        sl = SlackLoop.objects.create(
            fiber_cable=self.fiber_cable,
            site=self.site,
            start_mark=Decimal("100.00"),
            end_mark=Decimal("120.00"),
            length_unit="m",
        )
        assert sl.pk is not None

    def test_loop_length_property(self):
        from netbox_fms.models import SlackLoop

        sl = SlackLoop.objects.create(
            fiber_cable=self.fiber_cable,
            site=self.site,
            start_mark=Decimal("100.00"),
            end_mark=Decimal("150.00"),
            length_unit="m",
        )
        assert sl.loop_length == Decimal("50.00")

    def test_auto_swap_marks(self):
        from netbox_fms.models import SlackLoop

        sl = SlackLoop.objects.create(
            fiber_cable=self.fiber_cable,
            site=self.site,
            start_mark=Decimal("200.00"),
            end_mark=Decimal("100.00"),
            length_unit="m",
        )
        assert sl.start_mark == Decimal("100.00")
        assert sl.end_mark == Decimal("200.00")

    def test_negative_marks_rejected(self):
        from django.core.exceptions import ValidationError
        from netbox_fms.models import SlackLoop

        sl = SlackLoop(
            fiber_cable=self.fiber_cable,
            site=self.site,
            start_mark=Decimal("-10.00"),
            end_mark=Decimal("100.00"),
            length_unit="m",
        )
        with pytest.raises(ValidationError) as exc_info:
            sl.clean()
        assert "start_mark" in exc_info.value.message_dict

    def test_with_location(self):
        from netbox_fms.models import SlackLoop

        sl = SlackLoop.objects.create(
            fiber_cable=self.fiber_cable,
            site=self.site,
            location=self.location,
            start_mark=Decimal("0.00"),
            end_mark=Decimal("10.00"),
            length_unit="m",
        )
        assert sl.location == self.location

    def test_with_storage_method(self):
        from netbox_fms.models import SlackLoop

        sl = SlackLoop.objects.create(
            fiber_cable=self.fiber_cable,
            site=self.site,
            start_mark=Decimal("0.00"),
            end_mark=Decimal("10.00"),
            length_unit="m",
            storage_method=StorageMethodChoices.COIL,
        )
        assert sl.storage_method == "coil"

    def test_str(self):
        from netbox_fms.models import SlackLoop

        sl = SlackLoop.objects.create(
            fiber_cable=self.fiber_cable,
            site=self.site,
            start_mark=Decimal("100.00"),
            end_mark=Decimal("120.00"),
            length_unit="m",
        )
        s = str(sl)
        assert "100.00" in s
        assert "120.00" in s

    def test_get_absolute_url(self):
        from netbox_fms.models import SlackLoop

        sl = SlackLoop.objects.create(
            fiber_cable=self.fiber_cable,
            site=self.site,
            start_mark=Decimal("0.00"),
            end_mark=Decimal("5.00"),
            length_unit="m",
        )
        assert "/slack-loops/" in sl.get_absolute_url()

    def test_unique_together(self):
        from netbox_fms.models import SlackLoop

        SlackLoop.objects.create(
            fiber_cable=self.fiber_cable,
            site=self.site,
            start_mark=Decimal("50.00"),
            end_mark=Decimal("60.00"),
            length_unit="m",
        )
        with pytest.raises(IntegrityError):
            SlackLoop.objects.create(
                fiber_cable=self.fiber_cable,
                site=self.site,
                start_mark=Decimal("50.00"),
                end_mark=Decimal("60.00"),
                length_unit="m",
            )

    def test_cascade_delete_with_fiber_cable(self):
        from dcim.models import Cable, Manufacturer
        from netbox_fms.models import FiberCable, FiberCableType, SlackLoop

        # Use dedicated objects for cascade test
        mfr = Manufacturer.objects.create(name="SLM-Cascade-Mfr", slug="slm-cascade-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="SLM-Cascade-FCT",
            fiber_type="smf_os2",
            construction="tight_buffer",
            strand_count=1,
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO dcim_cable (type, status, label, color, comments, description, profile, custom_field_data, created, last_updated) VALUES (%s, %s, '', '', '', '', '{}', '{}', NOW(), NOW()) RETURNING id",
                ["smf-os2", "connected"],
            )
            cable_id = cursor.fetchone()[0]
        cable = Cable.objects.get(pk=cable_id)
        fc = FiberCable.objects.create(fiber_cable_type=fct, cable=cable)

        sl = SlackLoop.objects.create(
            fiber_cable=fc,
            site=self.site,
            start_mark=Decimal("0.00"),
            end_mark=Decimal("10.00"),
            length_unit="m",
        )
        sl_pk = sl.pk
        fc.delete()
        assert not SlackLoop.objects.filter(pk=sl_pk).exists()
