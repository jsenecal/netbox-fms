"""Tests for the netbox_fms GraphQL layer (filters and the registered schema)."""

import pytest


class TestGraphQLFilterImports:
    """Verify all GraphQL filter classes import cleanly."""

    def test_import_fiber_cable_type_filter(self):
        from netbox_fms.graphql.filters import FiberCableTypeFilter

        assert FiberCableTypeFilter is not None

    def test_import_buffer_tube_template_filter(self):
        from netbox_fms.graphql.filters import BufferTubeTemplateFilter

        assert BufferTubeTemplateFilter is not None

    def test_import_ribbon_template_filter(self):
        from netbox_fms.graphql.filters import RibbonTemplateFilter

        assert RibbonTemplateFilter is not None

    def test_import_cable_element_template_filter(self):
        from netbox_fms.graphql.filters import CableElementTemplateFilter

        assert CableElementTemplateFilter is not None

    def test_import_fiber_cable_filter(self):
        from netbox_fms.graphql.filters import FiberCableFilter

        assert FiberCableFilter is not None

    def test_import_splice_plan_filter(self):
        from netbox_fms.graphql.filters import SplicePlanFilter

        assert SplicePlanFilter is not None

    def test_import_splice_plan_entry_filter(self):
        from netbox_fms.graphql.filters import SplicePlanEntryFilter

        assert SplicePlanEntryFilter is not None

    def test_import_splice_project_filter(self):
        from netbox_fms.graphql.filters import SpliceProjectFilter

        assert SpliceProjectFilter is not None

    def test_import_closure_cable_entry_filter(self):
        from netbox_fms.graphql.filters import ClosureCableEntryFilter

        assert ClosureCableEntryFilter is not None

    def test_import_fiber_circuit_filter(self):
        from netbox_fms.graphql.filters import FiberCircuitFilter

        assert FiberCircuitFilter is not None

    def test_import_fiber_circuit_path_filter(self):
        from netbox_fms.graphql.filters import FiberCircuitPathFilter

        assert FiberCircuitPathFilter is not None

    def test_import_slack_loop_filter(self):
        from netbox_fms.graphql.filters import SlackLoopFilter

        assert SlackLoopFilter is not None

    def test_filters_all_exports(self):
        """Verify __all__ contains exactly the expected filters."""
        from netbox_fms.graphql import filters

        expected = {
            "FiberCableTypeFilter",
            "FiberAttenuationSpecFilter",
            "BufferTubeTemplateFilter",
            "RibbonTemplateFilter",
            "CableElementTemplateFilter",
            "FiberCableFilter",
            "SplicePlanFilter",
            "SplicePlanEntryFilter",
            "SpliceProjectFilter",
            "ClosureCableEntryFilter",
            "FiberCircuitFilter",
            "FiberCircuitPathFilter",
            "FiberStrandPathFilter",
            "SlackLoopFilter",
            "TrayProfileFilter",
            "TubeAssignmentFilter",
        }
        assert set(filters.__all__) == expected


@pytest.mark.django_db
class TestGraphQLFilterInstantiation:
    """Verify filter classes can be instantiated with default None values."""

    def test_fiber_cable_type_filter_instantiation(self):
        from netbox_fms.graphql.filters import FiberCableTypeFilter

        f = FiberCableTypeFilter(id=None, construction=None, is_armored=None, deployment=None, strand_count=None)
        assert f.id is None

    def test_fiber_cable_filter_instantiation(self):
        from netbox_fms.graphql.filters import FiberCableFilter

        f = FiberCableFilter(id=None, fiber_cable_type_id=None, cable_id=None, name=None)
        assert f.name is None

    def test_splice_plan_filter_instantiation(self):
        from netbox_fms.graphql.filters import SplicePlanFilter

        f = SplicePlanFilter(id=None, name=None, status=None, closure_id=None, project_id=None)
        assert f.status is None

    def test_fiber_circuit_filter_instantiation(self):
        from netbox_fms.graphql.filters import FiberCircuitFilter

        f = FiberCircuitFilter(id=None, name=None, cid=None, status=None, strand_count=None)
        assert f.cid is None

    def test_slack_loop_filter_instantiation(self):
        from netbox_fms.graphql.filters import SlackLoopFilter

        f = SlackLoopFilter(
            id=None, fiber_cable_id=None, site_id=None, location_id=None, storage_method=None, length_unit=None
        )
        assert f.storage_method is None


@pytest.mark.django_db
class TestRegisteredSchema:
    """The plugin's query fields are part of NetBox's assembled GraphQL schema (#202)."""

    @staticmethod
    def _query(client, query):
        body = client.post("/graphql/", {"query": query}, content_type="application/json").json()
        assert "errors" not in body, (query, body["errors"])
        return body["data"]

    def test_every_list_field_resolves(self):
        from netbox_fms.graphql.schema import NetBoxFMSQuery
        from tests.conftest import superuser_client

        client = superuser_client("gql")
        list_fields = [f.name for f in NetBoxFMSQuery.__strawberry_definition__.fields if f.name.endswith("_list")]
        for field in list_fields:
            assert self._query(client, f"{{ {field} {{ id }} }}") == {field: []}

    def test_strand_path_assignments_respect_object_permissions(self):
        from netbox_fms.choices import FiberCircuitStatusChoices
        from netbox_fms.models import FiberCircuit, FiberCircuitPath, FiberStrandPath
        from tests.conftest import assign_strand_path, make_strand_path, ui_client_with

        path = make_strand_path()
        visible, hidden = (
            FiberCircuit.objects.create(name=name, status=FiberCircuitStatusChoices.ACTIVE, strand_count=1)
            for name in ("GQL-visible", "GQL-hidden")
        )
        shown = assign_strand_path(visible, path)
        assign_strand_path(hidden, path, active=False)
        client = ui_client_with(
            "gql-constrained",
            [(FiberStrandPath, ["view"], None), (FiberCircuitPath, ["view"], {"circuit__name": "GQL-visible"})],
        )

        data = self._query(client, "{ fiber_strand_path_list { assignments { id } } }")

        assert data == {"fiber_strand_path_list": [{"assignments": [{"id": str(shown.pk)}]}]}
