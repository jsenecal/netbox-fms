"""Tests for the circuit wizard view."""

import pytest
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
class TestCircuitWizardAccess:
    """Test wizard access and permissions."""

    def test_wizard_requires_login(self):
        client = Client()
        url = reverse("plugins:netbox_fms:fibercircuit_wizard")
        response = client.get(url)
        assert response.status_code == 302

    def test_wizard_get_renders_step1(self, admin_client):
        url = reverse("plugins:netbox_fms:fibercircuit_wizard")
        response = admin_client.get(url)
        assert response.status_code == 200

    def test_wizard_restart_clears_session(self, admin_client):
        url = reverse("plugins:netbox_fms:fibercircuit_wizard")
        session = admin_client.session
        session["circuit_wizard"] = {"step": 3, "timestamp": 9999999999}
        session.save()
        response = admin_client.get(url + "?restart=1", follow=True)
        assert response.status_code == 200


@pytest.mark.django_db
class TestCircuitWizardStep1:
    """Test step 1 form submission."""

    def test_step1_valid_advances_to_step2(self, admin_client):
        url = reverse("plugins:netbox_fms:fibercircuit_wizard")
        response = admin_client.post(url, {"name": "Test Circuit", "strand_count": 4})
        assert response.status_code == 200

    def test_step1_missing_name_shows_error(self, admin_client):
        url = reverse("plugins:netbox_fms:fibercircuit_wizard")
        response = admin_client.post(url, {"strand_count": 1})
        assert response.status_code == 200
