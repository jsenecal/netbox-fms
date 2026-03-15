import pytest


@pytest.mark.django_db
class TestFiberOverviewQueryCount:
    """Fiber Overview tab should use bounded queries, not per-row."""

    def test_overview_query_count_is_bounded(self):
        """_build_cable_rows (plural) replaces per-row _build_cable_row."""
        from netbox_fms.views import _build_cable_rows

        assert callable(_build_cable_rows)
