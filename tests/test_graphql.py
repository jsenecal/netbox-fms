"""Smoke tests for the netbox_fms GraphQL layer (types, filters, schema)."""

import pytest


class TestGraphQLTypeImports:
    """Verify all GraphQL type classes import cleanly."""

    def test_import_fiber_cable_type_type(self):
        from netbox_fms.graphql.types import FiberCableTypeType

        assert FiberCableTypeType is not None

    def test_import_buffer_tube_template_type(self):
        from netbox_fms.graphql.types import BufferTubeTemplateType

        assert BufferTubeTemplateType is not None

    def test_import_ribbon_template_type(self):
        from netbox_fms.graphql.types import RibbonTemplateType

        assert RibbonTemplateType is not None

    def test_import_cable_element_template_type(self):
        from netbox_fms.graphql.types import CableElementTemplateType

        assert CableElementTemplateType is not None

    def test_import_fiber_cable_instance_type(self):
        from netbox_fms.graphql.types import FiberCableInstanceType

        assert FiberCableInstanceType is not None

    def test_import_buffer_tube_type(self):
        from netbox_fms.graphql.types import BufferTubeType

        assert BufferTubeType is not None

    def test_import_ribbon_type(self):
        from netbox_fms.graphql.types import RibbonType

        assert RibbonType is not None

    def test_import_fiber_strand_type(self):
        from netbox_fms.graphql.types import FiberStrandType

        assert FiberStrandType is not None

    def test_import_cable_element_type(self):
        from netbox_fms.graphql.types import CableElementType

        assert CableElementType is not None

    def test_import_splice_plan_type(self):
        from netbox_fms.graphql.types import SplicePlanType

        assert SplicePlanType is not None

    def test_import_splice_plan_entry_type(self):
        from netbox_fms.graphql.types import SplicePlanEntryType

        assert SplicePlanEntryType is not None

    def test_import_splice_project_type(self):
        from netbox_fms.graphql.types import SpliceProjectType

        assert SpliceProjectType is not None

    def test_import_closure_cable_entry_type(self):
        from netbox_fms.graphql.types import ClosureCableEntryType

        assert ClosureCableEntryType is not None

    def test_import_fiber_circuit_type(self):
        from netbox_fms.graphql.types import FiberCircuitType

        assert FiberCircuitType is not None

    def test_import_fiber_circuit_path_type(self):
        from netbox_fms.graphql.types import FiberCircuitPathType

        assert FiberCircuitPathType is not None

    def test_import_slack_loop_type(self):
        from netbox_fms.graphql.types import SlackLoopType

        assert SlackLoopType is not None

    def test_types_all_exports(self):
        """Verify __all__ contains exactly the expected types."""
        from netbox_fms.graphql import types

        expected = {
            "FiberCableTypeType",
            "BufferTubeTemplateType",
            "RibbonTemplateType",
            "CableElementTemplateType",
            "FiberCableInstanceType",
            "BufferTubeType",
            "RibbonType",
            "FiberStrandType",
            "CableElementType",
            "SplicePlanType",
            "SplicePlanEntryType",
            "SpliceProjectType",
            "ClosureCableEntryType",
            "FiberCircuitType",
            "FiberCircuitPathType",
            "SlackLoopType",
            "TrayProfileType",
            "TubeAssignmentType",
        }
        assert set(types.__all__) == expected


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
            "SlackLoopFilter",
            "TrayProfileFilter",
            "TubeAssignmentFilter",
        }
        assert set(filters.__all__) == expected


class TestGraphQLSchema:
    """Verify the schema query class and its fields."""

    def test_import_schema(self):
        from netbox_fms.graphql.schema import NetBoxFMSQuery

        assert NetBoxFMSQuery is not None

    def test_schema_list(self):
        from netbox_fms.graphql.schema import schema

        assert isinstance(schema, list)
        assert len(schema) == 1

    def _get_strawberry_field_names(self):
        """Helper to extract field names from the strawberry definition."""
        from netbox_fms.graphql.schema import NetBoxFMSQuery

        defn = NetBoxFMSQuery.__strawberry_definition__
        return {f.name for f in defn.fields}

    def test_query_has_fiber_cable_type_fields(self):
        fields = self._get_strawberry_field_names()
        assert "fiber_cable_type" in fields
        assert "fiber_cable_type_list" in fields

    def test_query_has_buffer_tube_template_fields(self):
        fields = self._get_strawberry_field_names()
        assert "buffer_tube_template" in fields
        assert "buffer_tube_template_list" in fields

    def test_query_has_ribbon_template_fields(self):
        fields = self._get_strawberry_field_names()
        assert "ribbon_template" in fields
        assert "ribbon_template_list" in fields

    def test_query_has_cable_element_template_fields(self):
        fields = self._get_strawberry_field_names()
        assert "cable_element_template" in fields
        assert "cable_element_template_list" in fields

    def test_query_has_fiber_cable_fields(self):
        fields = self._get_strawberry_field_names()
        assert "fiber_cable" in fields
        assert "fiber_cable_list" in fields

    def test_query_has_buffer_tube_fields(self):
        fields = self._get_strawberry_field_names()
        assert "buffer_tube" in fields
        assert "buffer_tube_list" in fields

    def test_query_has_ribbon_fields(self):
        fields = self._get_strawberry_field_names()
        assert "ribbon" in fields
        assert "ribbon_list" in fields

    def test_query_has_fiber_strand_fields(self):
        fields = self._get_strawberry_field_names()
        assert "fiber_strand" in fields
        assert "fiber_strand_list" in fields

    def test_query_has_cable_element_fields(self):
        fields = self._get_strawberry_field_names()
        assert "cable_element" in fields
        assert "cable_element_list" in fields

    def test_query_has_splice_plan_fields(self):
        fields = self._get_strawberry_field_names()
        assert "splice_plan" in fields
        assert "splice_plan_list" in fields

    def test_query_has_splice_plan_entry_fields(self):
        fields = self._get_strawberry_field_names()
        assert "splice_plan_entry" in fields
        assert "splice_plan_entry_list" in fields

    def test_query_has_splice_project_fields(self):
        fields = self._get_strawberry_field_names()
        assert "splice_project" in fields
        assert "splice_project_list" in fields

    def test_query_has_closure_cable_entry_fields(self):
        fields = self._get_strawberry_field_names()
        assert "closure_cable_entry" in fields
        assert "closure_cable_entry_list" in fields

    def test_query_has_fiber_circuit_fields(self):
        fields = self._get_strawberry_field_names()
        assert "fiber_circuit" in fields
        assert "fiber_circuit_list" in fields

    def test_query_has_fiber_circuit_path_fields(self):
        fields = self._get_strawberry_field_names()
        assert "fiber_circuit_path" in fields
        assert "fiber_circuit_path_list" in fields

    def test_query_has_slack_loop_fields(self):
        fields = self._get_strawberry_field_names()
        assert "slack_loop" in fields
        assert "slack_loop_list" in fields

    def test_query_field_count(self):
        """Verify the query class has the expected number of field pairs (18 models x 2)."""
        fields = self._get_strawberry_field_names()
        assert len(fields) == 36  # 18 models x (single + list)


@pytest.mark.django_db
class TestGraphQLFilterInstantiation:
    """Verify filter classes can be instantiated with default None values."""

    def test_fiber_cable_type_filter_instantiation(self):
        from netbox_fms.graphql.filters import FiberCableTypeFilter

        f = FiberCableTypeFilter(
            id=None, construction=None, fiber_type=None, is_armored=None, deployment=None, strand_count=None
        )
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
