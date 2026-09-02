"""Tests for device-scoped port selection on the circuit path form (issue #137)."""

from django.test import TestCase
from utilities.forms.fields import DynamicModelChoiceField

from netbox_fms.forms import FiberCircuitPathForm


class TestFiberCircuitPathFormPortSelection(TestCase):
    """FiberCircuitPathForm scopes origin/destination ports to a chosen device (#137).

    The origin and destination fields used to be plain ModelChoiceFields that
    rendered every FrontPort in the database into the page, which made the form
    unusable (duplicate port names across devices) and unbearably slow with
    thousands of ports.
    """

    def test_origin_is_api_backed_and_scoped_to_origin_device(self):
        field = FiberCircuitPathForm().fields["origin"]
        assert isinstance(field, DynamicModelChoiceField)
        assert field.query_params == {"device_id": "$origin_device"}
        assert field.context == {"parent": "device"}

    def test_destination_is_api_backed_and_scoped_to_destination_device(self):
        field = FiberCircuitPathForm().fields["destination"]
        assert isinstance(field, DynamicModelChoiceField)
        assert field.query_params == {"device_id": "$destination_device"}
        assert field.context == {"parent": "device"}
        assert field.required is False

    def test_device_selectors_back_fill_from_saved_ports(self):
        form = FiberCircuitPathForm()
        origin_device = form.fields["origin_device"]
        destination_device = form.fields["destination_device"]
        for field in (origin_device, destination_device):
            assert field.selector is True
            assert field.required is False
        assert origin_device.initial_params == {"frontports": "$origin"}
        assert destination_device.initial_params == {"frontports": "$destination"}
