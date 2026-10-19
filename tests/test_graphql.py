"""Tests for the netbox_fms GraphQL layer (filters and the registered schema)."""

import re
from types import SimpleNamespace

import pytest
from django.test import TestCase


def _query(client, query):
    body = client.post("/graphql/", {"query": query}, content_type="application/json").json()
    assert "errors" not in body, (query, body["errors"])
    return body["data"]


def _list_fields():
    from netbox_fms.graphql.schema import NetBoxFMSQuery

    return {f.name for f in NetBoxFMSQuery.__strawberry_definition__.fields if f.name.endswith("_list")}


@pytest.mark.django_db
class TestRegisteredSchema:
    """The plugin's query fields are part of NetBox's assembled GraphQL schema (#202)."""

    def test_every_list_field_resolves(self):
        from tests.conftest import superuser_client

        client = superuser_client("gql")
        for field in _list_fields():
            assert _query(client, f"{{ {field} {{ id }} }}") == {field: []}

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

        data = _query(client, "{ fiber_strand_path_list { assignments { id } } }")

        assert data == {"fiber_strand_path_list": [{"assignments": [{"id": str(shown.pk)}]}]}


def _filter_world():
    """Two rows of every queryable model, told apart by the field each filter case uses."""
    from dcim.models import Cable

    from netbox_fms.models import (
        BufferTube,
        CableElementTemplate,
        ClosureCableEntry,
        FiberAttenuationSpec,
        FiberCable,
        FiberCableType,
        FiberCircuit,
        FiberStrand,
        RibbonTemplate,
        SlackLoop,
        SplicePlan,
        SplicePlanEntry,
        SpliceProject,
        TubeAssignment,
    )
    from tests.conftest import (
        assign_strand_path,
        make_closure_pair,
        make_front_port,
        make_ribbon_in_tube_type,
        make_strand_path,
        make_tray_module,
        make_tray_type,
    )

    w = SimpleNamespace()
    rig = make_closure_pair("GQLF")
    w.closure_a, w.closure_b = rig.dev_a, rig.dev_b
    w.fct_a = make_ribbon_in_tube_type(rig.mfr, "GQLF-A", tubes=2, ribbons_per_tube=1, fibers=2)
    w.fct_b = FiberCableType.objects.create(
        manufacturer=rig.mfr, model="GQLF-B", construction="tight_buffer", strand_count=2, deployment="indoor"
    )
    w.spec_a, w.spec_b = (
        FiberAttenuationSpec.objects.create(fiber_cable_type=fct, wavelength_nm=1310, max_loss_db_per_km="0.35")
        for fct in (w.fct_a, w.fct_b)
    )
    w.btt_1, w.btt_2 = w.fct_a.buffer_tube_templates.order_by("position")
    w.rt_1, w.rt_2 = (RibbonTemplate.objects.get(buffer_tube_template=btt) for btt in (w.btt_1, w.btt_2))
    w.cet_a = CableElementTemplate.objects.create(fiber_cable_type=w.fct_a, name="SM", element_type="strength_member")
    w.cet_b = CableElementTemplate.objects.create(fiber_cable_type=w.fct_b, name="RC", element_type="ripcord")

    w.fc_a = FiberCable.objects.create(cable=Cable.objects.create(label="GQLF-A"), fiber_cable_type=w.fct_a)
    w.fc_b = FiberCable.objects.create(cable=Cable.objects.create(label="GQLF-B"), fiber_cable_type=w.fct_b)
    w.tube_1, w.tube_2 = BufferTube.objects.filter(fiber_cable=w.fc_a).order_by("position")
    w.ribbon_1, w.ribbon_2 = (tube.ribbons.get() for tube in (w.tube_1, w.tube_2))
    w.strand_a = FiberStrand.objects.filter(fiber_cable=w.fc_a).first()
    w.strand_b = FiberStrand.objects.filter(fiber_cable=w.fc_b).first()
    w.element_a, w.element_b = (fc.cable_elements.get() for fc in (w.fc_a, w.fc_b))

    w.project_a, w.project_b = (SpliceProject.objects.create(name=n) for n in ("GQLF north", "GQLF south"))
    w.plan_a = SplicePlan.objects.create(closure=w.closure_a, name="GQLF-PA", project=w.project_a)
    w.plan_b = SplicePlan.objects.create(closure=w.closure_b, name="GQLF-PB", status="pending_approval")
    w.tray_type_splice = make_tray_type(rig.mfr, "GQLF Tray")
    w.tray_type_express = make_tray_type(rig.mfr, "GQLF Basket", role="express_basket")
    w.profile_splice, w.profile_express = (t.tray_profile for t in (w.tray_type_splice, w.tray_type_express))
    w.tray_a = make_tray_module(w.closure_a, w.tray_type_splice, "Bay A")
    w.tray_b = make_tray_module(w.closure_b, w.tray_type_splice, "Bay B")
    entries = []
    for plan, tray in ((w.plan_a, w.tray_a), (w.plan_b, w.tray_b)):
        ports = [make_front_port(tray.device, f"{plan.name}-{n}", module=tray, port_type="splice") for n in (1, 2)]
        entries.append(SplicePlanEntry.objects.create(plan=plan, tray=tray, fiber_a=ports[0], fiber_b=ports[1]))
    w.entry_a, w.entry_b = entries

    w.cce_a, w.cce_b = (
        ClosureCableEntry.objects.create(closure=closure, fiber_cable=w.fc_a) for closure in (w.closure_a, w.closure_b)
    )
    w.ta_a, w.ta_b = (
        TubeAssignment.objects.create(closure=tray.device, tray=tray, buffer_tube=w.tube_1)
        for tray in (w.tray_a, w.tray_b)
    )
    w.slack_a, w.slack_b = (
        SlackLoop.objects.create(fiber_cable=w.fc_a, site=rig.site, start_mark=m, end_mark=m + 10, storage_method=s)
        for m, s in ((0, "coil"), (100, "figure_8"))
    )

    w.path_a = make_strand_path(w.strand_a)
    w.path_b = make_strand_path(w.strand_b, is_proposed=True)
    w.circuit_a = FiberCircuit.objects.create(name="GQLF-CA", status="active", strand_count=1)
    w.circuit_b = FiberCircuit.objects.create(name="GQLF-CB", status="planned", strand_count=1)
    w.fcp_a = assign_strand_path(w.circuit_a, w.path_a)
    w.fcp_b = assign_strand_path(w.circuit_b, w.path_a, active=False)
    return w


# (list field, filter literal, matching row, non-matching row); "$name" in a
# literal stands for the quoted pk of that world row.
FILTER_CASES = [
    ("fiber_cable_type_list", "{deployment: {exact: INDOOR}}", "fct_b", "fct_a"),
    ("fiber_attenuation_spec_list", "{fiber_cable_type_id: $fct_b}", "spec_b", "spec_a"),
    ("buffer_tube_template_list", '{name: {exact: "T2"}}', "btt_2", "btt_1"),
    ("ribbon_template_list", "{buffer_tube_template_id: $btt_2}", "rt_2", "rt_1"),
    ("cable_element_template_list", "{element_type: {exact: RIPCORD}}", "cet_b", "cet_a"),
    ("fiber_cable_list", '{fiber_cable_type: {model: {exact: "GQLF-B"}}}', "fc_b", "fc_a"),
    ("buffer_tube_list", "{position: {filter_lookup: {exact: 2}}}", "tube_2", "tube_1"),
    ("ribbon_list", "{buffer_tube_id: $tube_2}", "ribbon_2", "ribbon_1"),
    ("fiber_strand_list", "{fiber_cable_id: $fc_b}", "strand_b", "strand_a"),
    ("cable_element_list", "{element_type: {exact: RIPCORD}}", "element_b", "element_a"),
    ("splice_plan_list", "{status: {exact: PENDING_APPROVAL}}", "plan_b", "plan_a"),
    ("splice_plan_entry_list", "{plan_id: $plan_b}", "entry_b", "entry_a"),
    ("splice_project_list", '{name: {i_contains: "SOUTH"}}', "project_b", "project_a"),
    ("closure_cable_entry_list", "{closure_id: $closure_b}", "cce_b", "cce_a"),
    ("fiber_circuit_list", "{status: {exact: PLANNED}}", "circuit_b", "circuit_a"),
    ("fiber_circuit_path_list", "{circuit_id: $circuit_b}", "fcp_b", "fcp_a"),
    ("fiber_strand_path_list", "{is_proposed: {exact: true}}", "path_b", "path_a"),
    ("slack_loop_list", "{storage_method: {exact: FIGURE_8}}", "slack_b", "slack_a"),
    ("tray_profile_list", "{tray_role: {exact: EXPRESS_BASKET}}", "profile_express", "profile_splice"),
    ("tube_assignment_list", "{tray_id: $tray_b}", "ta_b", "ta_a"),
]


class TestListFilters(TestCase):
    """Every list field takes a ``filters`` argument that narrows its rows (#210)."""

    @classmethod
    def setUpTestData(cls):
        cls.w = _filter_world()

    def test_every_list_field_has_a_case(self):
        assert {case[0] for case in FILTER_CASES} == _list_fields()

    def test_filter_keeps_match_and_drops_other(self):
        from tests.conftest import superuser_client

        client = superuser_client("gqlf")
        for field, literal, match, other in FILTER_CASES:
            with self.subTest(field=field):
                filters = re.sub(r"\$(\w+)", lambda m: f'"{getattr(self.w, m.group(1)).pk}"', literal)

                rows = _query(client, f"{{ {field}(filters: {filters}) {{ id }} }}")[field]

                ids = {row["id"] for row in rows}
                assert str(getattr(self.w, match).pk) in ids
                assert str(getattr(self.w, other).pk) not in ids
