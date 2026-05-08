"""Tests for SplicePlanEntry.is_express and SlackLoop model behaviour.

Per project memory: framework-only tests (CharField round-trip, unique-together,
cascade delete, choice constant string values) are skipped. Only our own logic
is exercised here -- save() swap, clean() validators, computed property,
__str__, get_absolute_url.
"""

from decimal import Decimal

import pytest
from django.db import connection

# Tests for StorageMethodChoices constants were removed: asserting that a
# ChoiceSet exposes specific string keys is framework / round-trip behaviour.


@pytest.mark.django_db
class TestSplicePlanEntryIsExpress:
    """Test is_express field on SplicePlanEntry."""

    @pytest.fixture
    def setup_data(self):
        from dcim.models import (
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
    """Tests for SlackLoop model logic (our save/clean/property/__str__)."""

    @pytest.fixture(autouse=True)
    def setup_data(self):
        from dcim.choices import CableLengthUnitChoices
        from dcim.models import Cable, Location, Manufacturer, Site

        from netbox_fms.models import FiberCable, FiberCableType

        site = Site.objects.create(name="SLM-Site", slug="slm-site")
        location = Location.objects.create(name="SLM-Location", slug="slm-location", site=site)
        mfr = Manufacturer.objects.create(name="SLM-Mfr", slug="slm-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="SLM-FCT",
            construction="tight_buffer",
            strand_count=1,
            mark_unit=CableLengthUnitChoices.UNIT_METER,
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO dcim_cable (type, status, label, color, comments, description, profile, "
                "custom_field_data, created, last_updated) "
                "VALUES (%s, %s, '', '', '', '', '{}', '{}', NOW(), NOW()) RETURNING id",
                ["smf-os2", "connected"],
            )
            cable_id = cursor.fetchone()[0]
        cable = Cable.objects.get(pk=cable_id)
        fc = FiberCable.objects.create(fiber_cable_type=fct, cable=cable)

        self.site = site
        self.location = location
        self.fct = fct
        self.fiber_cable = fc
        self.cable = cable

    def test_loop_length_property(self):
        from netbox_fms.models import SlackLoop

        sl = SlackLoop.objects.create(
            fiber_cable=self.fiber_cable,
            site=self.site,
            start_mark=Decimal("100.00"),
            end_mark=Decimal("150.00"),
        )
        assert sl.loop_length == Decimal("50.00")

    def test_auto_swap_marks(self):
        from netbox_fms.models import SlackLoop

        sl = SlackLoop.objects.create(
            fiber_cable=self.fiber_cable,
            site=self.site,
            start_mark=Decimal("200.00"),
            end_mark=Decimal("100.00"),
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
        )
        with pytest.raises(ValidationError) as exc_info:
            sl.clean()
        assert "start_mark" in exc_info.value.message_dict

    def test_clean_requires_mark_unit_on_type(self):
        """clean() rejects a slack loop on a cable type that declares no mark_unit."""
        from django.core.exceptions import ValidationError

        from netbox_fms.models import FiberCable, FiberCableType, SlackLoop

        unmarked_fct = FiberCableType.objects.create(
            manufacturer=self.fct.manufacturer,
            model="SLM-Unmarked-FCT",
            construction="tight_buffer",
            strand_count=1,
            mark_unit="",
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO dcim_cable (type, status, label, color, comments, description, profile, "
                "custom_field_data, created, last_updated) "
                "VALUES (%s, %s, '', '', '', '', '{}', '{}', NOW(), NOW()) RETURNING id",
                ["smf-os2", "connected"],
            )
            cable_id = cursor.fetchone()[0]
        from dcim.models import Cable

        cable = Cable.objects.get(pk=cable_id)
        fc = FiberCable.objects.create(fiber_cable_type=unmarked_fct, cable=cable)

        sl = SlackLoop(
            fiber_cable=fc,
            site=self.site,
            start_mark=Decimal("0.00"),
            end_mark=Decimal("10.00"),
        )
        with pytest.raises(ValidationError):
            sl.clean()

    def test_str_includes_marks_and_unit(self):
        from netbox_fms.models import SlackLoop

        sl = SlackLoop.objects.create(
            fiber_cable=self.fiber_cable,
            site=self.site,
            start_mark=Decimal("100.00"),
            end_mark=Decimal("120.00"),
        )
        s = str(sl)
        assert "100.00" in s
        assert "120.00" in s
        # mark_unit comes from fiber_cable_type, set to "m" in setUp
        assert "m" in s

    def test_get_absolute_url(self):
        from netbox_fms.models import SlackLoop

        sl = SlackLoop.objects.create(
            fiber_cable=self.fiber_cable,
            site=self.site,
            start_mark=Decimal("0.00"),
            end_mark=Decimal("5.00"),
        )
        assert "/slack-loops/" in sl.get_absolute_url()

    def test_mark_unit_property_delegates_to_type(self):
        from netbox_fms.models import SlackLoop

        sl = SlackLoop.objects.create(
            fiber_cable=self.fiber_cable,
            site=self.site,
            start_mark=Decimal("0.00"),
            end_mark=Decimal("5.00"),
        )
        assert sl.mark_unit == self.fct.mark_unit
