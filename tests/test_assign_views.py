"""Plugin logic behind the Assign fibers action, the circuit wizard and the path analysis pages.

Covers the picker form translation, the permission and constraint branches of the UI actions (a
constrained user must not assign, acknowledge or even see what the REST API would refuse them), the
wizard's one transaction, and the restricted context of the read-only pages.
"""

from unittest.mock import patch

from circuits.models import Circuit
from dcim.models import Cable, Device, FrontPort
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from netbox_fms.choices import FiberCircuitStatusChoices
from netbox_fms.forms import AssignFibersForm, AssignFibersSelectionForm, picker_kwargs
from netbox_fms.models import (
    FiberCableType,
    FiberCircuit,
    FiberCircuitPath,
    FiberStrandPath,
    PathAnalysisQueue,
    PathAnomaly,
)
from netbox_fms.path_analysis import run_reconcile
from netbox_fms.services import create_closure_cable
from netbox_fms.views import CircuitWizardView
from tests.conftest import (
    assign_strand_path,
    make_closure_pair,
    make_provider_circuit,
    make_strand_path,
    ui_client_with,
    user_with,
)


def _superuser_client(username):
    client = Client()
    client.force_login(get_user_model().objects.create_superuser(username, f"{username}@example.com", "pw"))
    return client


class _PlantMixin:
    """Two closures joined by a two-strand fiber cable, analyzed into two paths."""

    prefix = "AV"

    @classmethod
    def setUpTestData(cls):
        pair = make_closure_pair(cls.prefix)
        cls.dev_a, cls.dev_b = pair.dev_a, pair.dev_b
        fct = FiberCableType.objects.create(
            manufacturer=pair.mfr, model=f"{cls.prefix}-2", strand_count=2, construction="tight_buffer"
        )
        create_closure_cable(device_a=cls.dev_a, device_b=cls.dev_b, fiber_cable_type=fct, port_type="lc")
        run_reconcile()
        cls.paths = list(FiberStrandPath.objects.order_by("pk"))
        cls.ids_csv = ",".join(str(p.pk) for p in cls.paths)

    def make_circuit(self, name, **fields):
        fields.setdefault("strand_count", 2)
        fields.setdefault("status", FiberCircuitStatusChoices.ACTIVE)
        return FiberCircuit.objects.create(name=name, **fields)

    def assign_url(self, circuit):
        return reverse("plugins:netbox_fms:fibercircuit_assign", args=[circuit.pk])


class TestAssignForms(_PlantMixin, TestCase):
    prefix = "AVF"

    def test_must_pass_through_keeps_the_submitted_order(self):
        user = user_with("avf-all", [(Device, ["view"], None)])
        form = AssignFibersForm({"must_pass_through": [self.dev_b.pk, self.dev_a.pk]}, user=user)
        assert form.is_valid(), form.errors
        kwargs = picker_kwargs(form.cleaned_data)
        assert [d.pk for d in kwargs["must_pass_through"]] == [self.dev_b.pk, self.dev_a.pk]
        assert kwargs["allow_incomplete"] is False
        assert kwargs["ends_at"] == []

    def test_selection_form_parses_the_path_ids(self):
        form = AssignFibersSelectionForm({"strand_paths": "7, 3,11", "allow_incomplete": "on"})
        assert form.is_valid(), form.errors
        assert form.cleaned_data["strand_paths"] == [7, 3, 11]
        assert not AssignFibersSelectionForm({"strand_paths": "7,x"}).is_valid()

    def test_device_fields_only_accept_devices_the_user_may_view(self):
        user = user_with("avf-one", [(Device, ["view"], {"pk": self.dev_a.pk})])
        form = AssignFibersForm({"ends_at": [self.dev_a.pk, self.dev_b.pk]}, user=user)
        assert not form.is_valid()
        assert "ends_at" in form.errors
        assert AssignFibersForm({"ends_at": [self.dev_a.pk]}, user=user).is_valid()


class TestAssignAction(_PlantMixin, TestCase):
    prefix = "AVA"

    def _grants(self, **overrides):
        grants = {
            "circuit": (FiberCircuit, ["view", "change"], None),
            "paths": (FiberStrandPath, ["view"], None),
            "assignment": (FiberCircuitPath, ["add", "view"], None),
        }
        grants.update(overrides)
        return [g for g in grants.values() if g is not None]

    def test_assign_action_assigns_the_selected_paths(self):
        circuit = self.make_circuit("AVA-C")
        client = _superuser_client("ava-admin")
        response = client.post(self.assign_url(circuit), {"action": "assign", "strand_paths": self.ids_csv})
        assert response.status_code == 302
        assert list(circuit.paths.order_by("position").values_list("strand_path_id", flat=True)) == [
            p.pk for p in self.paths
        ]

    def test_search_lists_groups_of_the_remaining_strand_count(self):
        circuit = self.make_circuit("AVA-S")
        client = ui_client_with("ava-search", self._grants())
        response = client.post(self.assign_url(circuit), {})
        assert response.status_code == 200
        assert [g["path_ids"] for g in response.context["groups"]] == [[p.pk for p in self.paths]]

    def test_search_refuses_a_circuit_with_every_strand_assigned(self):
        circuit = self.make_circuit("AVA-FULL", strand_count=1)
        assign_strand_path(circuit, self.paths[0])
        response = ui_client_with("ava-full", self._grants()).post(self.assign_url(circuit), {})
        assert response.status_code == 200
        assert response.context["groups"] is None

    def test_groups_with_a_path_the_user_cannot_view_are_not_offered(self):
        circuit = self.make_circuit("AVA-HID")
        client = ui_client_with("ava-hid", self._grants(paths=(FiberStrandPath, ["view"], {"pk": self.paths[0].pk})))
        response = client.post(self.assign_url(circuit), {})
        assert response.context["groups"] == []

    def test_user_without_add_on_assignments_is_refused(self):
        circuit = self.make_circuit("AVA-NOADD")
        client = ui_client_with("ava-noadd", self._grants(assignment=None))
        assert client.get(self.assign_url(circuit)).status_code == 403
        assert (
            client.post(self.assign_url(circuit), {"action": "assign", "strand_paths": self.ids_csv}).status_code == 403
        )
        assert not circuit.paths.exists()

    def test_circuit_outside_the_users_change_permission_is_not_found(self):
        circuit = self.make_circuit("AVA-OUT")
        other = self.make_circuit("AVA-IN")
        client = ui_client_with("ava-out", self._grants(circuit=(FiberCircuit, ["view", "change"], {"pk": other.pk})))
        assert client.get(self.assign_url(circuit)).status_code == 404
        assert client.get(self.assign_url(other)).status_code == 200

    def test_selection_outside_the_users_path_view_is_refused(self):
        circuit = self.make_circuit("AVA-SEL")
        client = ui_client_with("ava-sel", self._grants(paths=(FiberStrandPath, ["view"], {"pk": self.paths[0].pk})))
        response = client.post(self.assign_url(circuit), {"action": "assign", "strand_paths": self.ids_csv})
        assert response.status_code == 302
        assert response.url == self.assign_url(circuit)
        assert not circuit.paths.exists()

    def test_assignments_outside_the_users_add_constraint_roll_back(self):
        circuit = self.make_circuit("AVA-CON")
        client = ui_client_with(
            "ava-con", self._grants(assignment=(FiberCircuitPath, ["add", "view"], {"position": 99}))
        )
        response = client.post(self.assign_url(circuit), {"action": "assign", "strand_paths": self.ids_csv})
        assert response.status_code == 403
        assert not circuit.paths.exists()

    def test_assignment_errors_are_reported_without_assigning(self):
        circuit = self.make_circuit("AVA-ERR", strand_count=1)
        client = _superuser_client("ava-err")
        response = client.post(
            self.assign_url(circuit), {"action": "assign", "strand_paths": self.ids_csv}, follow=True
        )
        assert "exceed" in " ".join(str(m) for m in response.context["messages"])
        assert not circuit.paths.exists()

    def test_malformed_selection_goes_back_to_the_picker_with_the_error(self):
        circuit = self.make_circuit("AVA-BAD")
        response = _superuser_client("ava-bad").post(
            self.assign_url(circuit), {"action": "assign", "strand_paths": "x"}, follow=True
        )
        assert response.redirect_chain[-1][0] == self.assign_url(circuit)
        assert "must be integers" in " ".join(str(m) for m in response.context["messages"])

    def test_circuit_page_lists_only_assignments_of_viewable_paths(self):
        circuit = self.make_circuit("AVA-PAGE")
        for path in self.paths:
            assign_strand_path(circuit, path)
        client = ui_client_with(
            "ava-page",
            self._grants(paths=(FiberStrandPath, ["view"], {"pk": self.paths[0].pk}))
            + [(FiberCircuitPath, ["view", "change"], None)],
        )
        response = client.get(circuit.get_absolute_url())
        assert [a.strand_path_id for a in response.context["paths"]] == [self.paths[0].pk]


class TestAcknowledgeAction(_PlantMixin, TestCase):
    prefix = "AVK"

    def setUp(self):
        self.circuit = self.make_circuit("AVK-C")
        self.assignment = assign_strand_path(self.circuit, self.paths[0], is_broken=True, broken_reason="moved")
        self.url = reverse("plugins:netbox_fms:fibercircuit_acknowledge_route", args=[self.circuit.pk])

    def _grants(self, **overrides):
        grants = {
            "circuit": (FiberCircuit, ["view", "change"], None),
            "assignment": (FiberCircuitPath, ["view", "change"], None),
        }
        grants.update(overrides)
        return [g for g in grants.values() if g is not None]

    def test_acknowledge_accepts_the_current_route(self):
        response = ui_client_with("avk-ok", self._grants()).post(self.url)
        assert response.status_code == 302
        self.assignment.refresh_from_db()
        assert not self.assignment.is_broken

    def test_acknowledge_needs_change_on_assignments(self):
        client = ui_client_with("avk-noperm", self._grants(assignment=None))
        assert client.post(self.url).status_code == 403
        self.assignment.refresh_from_db()
        assert self.assignment.is_broken

    def test_acknowledge_respects_assignment_constraints(self):
        client = ui_client_with(
            "avk-con", self._grants(assignment=(FiberCircuitPath, ["view", "change"], {"position": 99}))
        )
        assert client.post(self.url).status_code == 403
        self.assignment.refresh_from_db()
        assert self.assignment.is_broken


class TestCircuitWizard(_PlantMixin, TestCase):
    prefix = "AVW"

    def _walk(self, client, name, extra_step2=None):
        url = reverse("plugins:netbox_fms:fibercircuit_wizard")
        basics = {"name": name, "strand_count": 2, "status": FiberCircuitStatusChoices.PLANNED}
        assert client.post(url, basics).status_code == 200
        step2 = {"ends_at": [self.dev_a.pk, self.dev_b.pk], **(extra_step2 or {})}
        assert client.post(url, step2).status_code == 200
        review = client.post(url, {"selected_group": 0})
        assert review.status_code == 200
        assert review.context["status_label"] == "Planned"
        return url

    def test_wizard_creates_the_circuit_and_its_assignments_together(self):
        client = _superuser_client("avw-wiz")
        url = self._walk(client, "AVW-W")
        response = client.post(url, {"confirm": "1"})
        circuit = FiberCircuit.objects.get(name="AVW-W")
        assert response.status_code == 302 and response.url == circuit.get_absolute_url()
        assert circuit.paths.count() == 2
        assert FiberCircuitPath.objects.filter(circuit=circuit).count() == 2

    def test_wizard_rolls_the_circuit_back_when_assignment_fails(self):
        client = _superuser_client("avw-fail")
        url = self._walk(client, "AVW-F")
        with patch("netbox_fms.assignment.assign_paths", side_effect=ValidationError("taken")):
            response = client.post(url, {"confirm": "1"})
        assert response.status_code == 200
        assert not FiberCircuit.objects.filter(name="AVW-F").exists()

    def test_wizard_needs_add_on_circuits_and_assignments(self):
        url = reverse("plugins:netbox_fms:fibercircuit_wizard")
        for username, grants in (
            ("avw-nopath", [(FiberCircuit, ["add"], None)]),
            ("avw-nocircuit", [(FiberCircuitPath, ["add"], None)]),
        ):
            client = ui_client_with(username, grants)
            assert client.get(url).status_code == 403
            assert client.post(url, {"name": "AVW-N"}).status_code == 403

    def test_step_two_rejects_devices_the_user_cannot_view(self):
        client = ui_client_with(
            "avw-dev",
            [
                (FiberCircuit, ["add", "view"], None),
                (FiberCircuitPath, ["add"], None),
                (Device, ["view"], {"pk": self.dev_a.pk}),
            ],
        )
        url = reverse("plugins:netbox_fms:fibercircuit_wizard")
        client.post(url, {"name": "AVW-D", "strand_count": 2, "status": FiberCircuitStatusChoices.PLANNED})
        response = client.post(url, {"ends_at": [self.dev_b.pk]})
        assert response.status_code == 200
        assert "ends_at" in response.context["form"].errors
        assert client.get(url).context["current_step"] == 2

    def test_circuit_outside_the_users_add_constraint_rolls_back(self):
        client = ui_client_with(
            "avw-con",
            [
                (FiberCircuit, ["add", "view"], {"name": "AVW-OK"}),
                (FiberStrandPath, ["view"], None),
                (FiberCircuitPath, ["add", "view"], None),
                (Device, ["view"], None),
            ],
        )
        url = self._walk(client, "AVW-NOPE")
        assert client.post(url, {"confirm": "1"}).status_code == 403
        assert not FiberCircuit.objects.filter(name="AVW-NOPE").exists()

    def test_paths_the_user_cannot_view_are_refused_at_the_last_step(self):
        client = ui_client_with(
            "avw-view",
            [
                (FiberCircuit, ["add", "view"], None),
                (FiberStrandPath, ["view"], None),
                (FiberCircuitPath, ["add", "view"], None),
                (Device, ["view"], None),
            ],
        )
        url = self._walk(client, "AVW-V")
        # The user's view permission narrows between picking the group and confirming it.
        from users.models import ObjectPermission

        ObjectPermission.objects.filter(name="avw-view-1").update(constraints={"pk": self.paths[0].pk})
        response = client.post(url, {"confirm": "1"})
        assert response.status_code == 200
        assert not FiberCircuit.objects.filter(name="AVW-V").exists()

    def test_back_restart_and_bad_input_keep_the_wizard_state(self):
        client = _superuser_client("avw-nav")
        url = reverse("plugins:netbox_fms:fibercircuit_wizard")
        assert client.post(url, {"name": ""}).status_code == 200  # invalid basics stay on step 1
        client.post(url, {"name": "AVW-NAV", "strand_count": 2, "status": FiberCircuitStatusChoices.PLANNED})
        assert client.get(url).context["current_step"] == 2
        assert client.post(url, {"ends_at": [self.dev_a.pk], "avoid_devices": [self.dev_a.pk]}).status_code == 200
        assert client.get(url).context["current_step"] == 2  # nothing assignable survives the filters
        client.post(url, {"ends_at": [self.dev_a.pk]})
        client.post(url, {"selected_group": "x"})
        assert client.get(url).context["current_step"] == 3
        client.post(url, {"_back": "1"})
        assert client.get(url).context["current_step"] == 2
        assert client.get(url + "?restart=1").status_code == 302
        assert client.get(url).context["current_step"] == 1

    def test_stale_wizard_state_is_dropped(self):
        client = _superuser_client("avw-ttl")
        url = reverse("plugins:netbox_fms:fibercircuit_wizard")
        client.post(url, {"name": "AVW-TTL", "strand_count": 2, "status": FiberCircuitStatusChoices.PLANNED})
        with patch.object(CircuitWizardView, "SESSION_TTL", -1):
            assert client.get(url).context["current_step"] == 1

    def test_htmx_requests_render_the_step_fragment_only(self):
        client = _superuser_client("avw-hx")
        url = reverse("plugins:netbox_fms:fibercircuit_wizard")
        response = client.get(url, HTTP_HX_REQUEST="true")
        assert response.status_code == 200
        assert "circuit_wizard.html" not in [t.name for t in response.templates]


class TestPathAnalysisPages(_PlantMixin, TestCase):
    prefix = "AVP"

    def test_hops_hide_cables_and_provider_circuits_the_user_cannot_view(self):
        pc = make_provider_circuit("AVP")
        cable = Cable.objects.first()
        path = make_strand_path(cable, pc.circuit)
        url = reverse("plugins:netbox_fms:fiberstrandpath", args=[path.pk])
        only_path = (FiberStrandPath, ["view"], None)

        response = ui_client_with("avp-hidden", [only_path]).get(url)
        rows = response.context["hop_rows"]
        assert [(r["cable"], r["cable_hidden"], r["provider_circuit"], r["provider_circuit_hidden"]) for r in rows] == [
            (None, True, None, False),
            (None, False, None, True),
        ]

        seeing = ui_client_with("avp-seeing", [only_path, (Cable, ["view"], None), (Circuit, ["view"], None)]).get(url)
        rows = seeing.context["hop_rows"]
        assert rows[0]["cable"] == cable and rows[1]["provider_circuit"] == pc.circuit

    def test_hops_hide_strands_and_end_ports_the_user_cannot_view(self):
        path = self.paths[0]
        url = reverse("plugins:netbox_fms:fiberstrandpath", args=[path.pk])
        response = ui_client_with("avp-strand", [(FiberStrandPath, ["view"], None)]).get(url)
        assert all(r["strand"] is None and r["strand_hidden"] for r in response.context["hop_rows"])
        assert response.context["end_a_port"] is None and response.context["end_a_hidden"]

    def test_path_list_shows_hop_counts_and_only_viewable_assignments(self):
        circuit = self.make_circuit("AVP-C")
        assign_strand_path(circuit, self.paths[0])
        url = reverse("plugins:netbox_fms:fiberstrandpath_list")
        admin = _superuser_client("avp-list").get(url)
        table = admin.context["table"]
        rows = {row.record.pk: row for row in table.rows}
        assert rows[self.paths[0].pk].get_cell("hop_count") == 1
        assert "AVP-C" in str(rows[self.paths[0].pk].get_cell("assigned_to"))
        assert str(rows[self.paths[1].pk].get_cell("assigned_to")) == "-"

        hidden = ui_client_with("avp-list2", [(FiberStrandPath, ["view"], None)]).get(url)
        row = next(r for r in hidden.context["table"].rows if r.record.pk == self.paths[0].pk)
        assert str(row.get_cell("assigned_to")) == "-"

    def test_list_filters_narrow_the_results(self):
        assign_strand_path(self.make_circuit("AVP-F"), self.paths[0])
        client = _superuser_client("avp-filter")
        response = client.get(reverse("plugins:netbox_fms:fiberstrandpath_list"), {"assigned": "False"})
        assert [row.record.pk for row in response.context["table"].rows] == [self.paths[1].pk]
        loop = PathAnomaly.objects.create(kind="loop")
        PathAnomaly.objects.create(kind="dangling_reference")
        response = client.get(reverse("plugins:netbox_fms:pathanomaly_list"), {"kind": "loop"})
        assert [row.record.pk for row in response.context["table"].rows] == [loop.pk]
        PathAnalysisQueue.objects.create(device=self.dev_a, reason="cable_changed")
        PathAnalysisQueue.objects.create(device=self.dev_b, reason="cable_changed")
        response = client.get(reverse("plugins:netbox_fms:pathanalysisqueue_list"), {"device_id": self.dev_a.pk})
        assert [row.record.device_id for row in response.context["table"].rows] == [self.dev_a.pk]

    def test_hidden_device_of_a_visible_end_port_is_marked_hidden(self):
        path = self.paths[0]
        url = reverse("plugins:netbox_fms:fiberstrandpath", args=[path.pk])
        client = ui_client_with("avp-dev", [(FiberStrandPath, ["view"], None), (FrontPort, ["view"], None)])
        response = client.get(url)
        assert response.context["end_a_port"] is not None
        assert response.context["end_a_device"] is None and response.context["end_a_device_hidden"]
