"""Tests for device-scoped selection on splice and cable forms (follow-up to issue #137)."""

from django.test import TestCase

from netbox_fms.forms import (
    ClosureCableEntryForm,
    FiberCableForm,
    SplicePlanEntryForm,
    SplicePlanForm,
    TubeAssignmentForm,
)


class TestSplicePlanEntryFormScoping(TestCase):
    """SplicePlanEntryForm scopes plan, tray, and fibers to a chosen closure.

    The tray field used to search every Module in NetBox and the fiber
    fields every FrontPort, even though SplicePlanEntry.clean() rejects
    any port outside the plan's closure and any tray other than fiber_a's
    parent module.
    """

    def test_closure_selector_back_fills_from_plan(self):
        field = SplicePlanEntryForm().fields["closure"]
        assert field.selector is True
        assert field.required is False
        assert field.initial_params == {"splice_plans": "$plan"}

    def test_plan_tray_and_fibers_chain_on_closure(self):
        form = SplicePlanEntryForm()
        assert form.fields["plan"].query_params == {"closure_id": "$closure"}
        assert form.fields["tray"].query_params == {"device_id": "$closure"}
        assert form.fields["fiber_b"].query_params == {"device_id": "$closure"}

    def test_fiber_a_also_chains_on_tray(self):
        """clean() requires tray == fiber_a.module, so the dropdown mirrors it."""
        field = SplicePlanEntryForm().fields["fiber_a"]
        assert field.query_params == {"device_id": "$closure", "module_id": "$tray"}

    def test_fibers_show_parent_device(self):
        form = SplicePlanEntryForm()
        assert form.fields["fiber_a"].context == {"parent": "device"}
        assert form.fields["fiber_b"].context == {"parent": "device"}


class TestFiberCableFormScoping(TestCase):
    """FiberCableForm offers an optional device to narrow the cable dropdown."""

    def test_cable_chains_on_device(self):
        form = FiberCableForm()
        device = form.fields["device"]
        assert device.selector is True
        assert device.required is False
        assert form.fields["cable"].query_params == {"device_id": "$device"}


class TestClosureFieldsUseSelector(TestCase):
    """Closure device pickers offer the advanced selector modal."""

    def test_closure_fields_have_selector(self):
        for form_cls in (SplicePlanForm, ClosureCableEntryForm, TubeAssignmentForm):
            assert form_cls().fields["closure"].selector is True, form_cls.__name__
