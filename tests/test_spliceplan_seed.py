"""Seeding of new splice plans from the closure's live state.

Regression tests for issue #174: a plan created on a closure with live
splices must initialize as "keep everything" (entries mirroring the live
state, diff empty) instead of "delete everything" (no entries, every live
pair classified as a pending remove).
"""

from django.test import TestCase

from netbox_fms.forms import SplicePlanForm
from netbox_fms.models import SplicePlan, SplicePlanEntry
from netbox_fms.services import get_or_recompute_diff, import_live_state
from tests.conftest import connect_front_ports, make_authed_client, make_closure_with_tray


def _create_plan_via_form(closure, name):
    """Create a plan the way SplicePlanEditView does: through SplicePlanForm."""
    form = SplicePlanForm(data={"closure": closure.pk, "name": name})
    assert form.is_valid(), form.errors
    return form.save()


def _diff_totals(plan):
    """Sum add/remove/unchanged pair counts across all trays of the diff."""
    totals = {"add": 0, "remove": 0, "unchanged": 0}
    for tray_diff in get_or_recompute_diff(plan).values():
        for key in totals:
            totals[key] += len(tray_diff.get(key, []))
    return totals


class TestFormCreateSeedsLiveState(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rig = make_closure_with_tray("SEED", port_count=4)
        connect_front_ports(cls.rig.ports[0], cls.rig.ports[1])
        connect_front_ports(cls.rig.ports[2], cls.rig.ports[3])

    def test_create_seeds_entries_and_diff_shows_keep(self):
        """A new plan mirrors the live splices; nothing is pending (issue #174)."""
        plan = _create_plan_via_form(self.rig.closure, "Seeded Plan")

        assert plan.entries.count() == 2
        seeded_pairs = {frozenset((e.fiber_a_id, e.fiber_b_id)) for e in plan.entries.all()}
        assert seeded_pairs == {
            frozenset((self.rig.ports[0].pk, self.rig.ports[1].pk)),
            frozenset((self.rig.ports[2].pk, self.rig.ports[3].pk)),
        }
        assert _diff_totals(plan) == {"add": 0, "remove": 0, "unchanged": 2}

    def test_edit_does_not_reseed(self):
        """Saving an existing plan must not resurrect deliberately removed entries."""
        plan = _create_plan_via_form(self.rig.closure, "Edited Plan")
        plan.entries.filter(fiber_a=self.rig.ports[0]).delete()

        form = SplicePlanForm(
            data={"closure": self.rig.closure.pk, "name": "Edited Plan v2"},
            instance=SplicePlan.objects.get(pk=plan.pk),
        )
        assert form.is_valid(), form.errors
        form.save()

        assert plan.entries.count() == 1


class TestApiCreateSeedsLiveState(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rig = make_closure_with_tray("SEEDAPI", port_count=2)
        connect_front_ports(cls.rig.ports[0], cls.rig.ports[1])

    def setUp(self):
        self.client = make_authed_client("seed-api")

    def test_api_create_seeds_entries(self):
        """POST /splice-plans/ bootstraps the plan from live state (issue #174)."""
        resp = self.client.post(
            "/api/plugins/fms/splice-plans/",
            {"closure": self.rig.closure.pk, "name": "API Seeded"},
            format="json",
        )
        assert resp.status_code == 201, resp.content

        plan = SplicePlan.objects.get(pk=resp.json()["id"])
        entry = plan.entries.get()
        assert {entry.fiber_a_id, entry.fiber_b_id} == {self.rig.ports[0].pk, self.rig.ports[1].pk}


class TestReimportIsIdempotent(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rig = make_closure_with_tray("SEEDRE", port_count=4)
        connect_front_ports(cls.rig.ports[0], cls.rig.ports[1])
        connect_front_ports(cls.rig.ports[2], cls.rig.ports[3])

    def test_reimport_on_seeded_plan_skips_existing_entries(self):
        """Import from device on an already-seeded plan is a no-op, not an error.

        Regression test for issue #174 follow-up: auto-seeded plans already
        hold every live pair, so a re-import must skip them instead of
        tripping the (plan, fiber) unique constraints.
        """
        plan = _create_plan_via_form(self.rig.closure, "Reimport Plan")
        assert plan.entries.count() == 2

        result = import_live_state(plan)

        assert result["imported"] == 0
        assert result["skipped_existing"] == 2
        assert plan.entries.count() == 2

    def test_reimport_picks_up_new_live_splices_only(self):
        """A live splice created after seeding imports without touching the rest."""
        plan = _create_plan_via_form(self.rig.closure, "Sync Plan")
        plan.entries.filter(fiber_a=self.rig.ports[2]).delete()
        plan.entries.filter(fiber_b=self.rig.ports[2]).delete()

        result = import_live_state(plan)

        assert result["imported"] == 1
        assert result["skipped_existing"] == 1
        pairs = {frozenset((e.fiber_a_id, e.fiber_b_id)) for e in plan.entries.all()}
        assert pairs == {
            frozenset((self.rig.ports[0].pk, self.rig.ports[1].pk)),
            frozenset((self.rig.ports[2].pk, self.rig.ports[3].pk)),
        }


class TestSeedRespectsFiberExclusivity(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rig = make_closure_with_tray("SEEDX", port_count=4)
        connect_front_ports(cls.rig.ports[0], cls.rig.ports[1])
        connect_front_ports(cls.rig.ports[2], cls.rig.ports[3])
        cls.other_plan = SplicePlan.objects.create(closure=cls.rig.closure, name="Claimer")
        SplicePlanEntry.objects.create(
            plan=cls.other_plan,
            tray=cls.rig.tray,
            fiber_a=cls.rig.ports[0],
            fiber_b=cls.rig.ports[1],
        )

    def test_import_skips_claimed_fibers_and_reports_count(self):
        """Fibers claimed by another active plan are skipped, not a hard error."""
        plan = SplicePlan.objects.create(closure=self.rig.closure, name="Second Plan")
        result = import_live_state(plan)

        assert result["imported"] == 1
        assert result["skipped_claimed"] == 1
        entry = plan.entries.get()
        assert {entry.fiber_a_id, entry.fiber_b_id} == {self.rig.ports[2].pk, self.rig.ports[3].pk}

    def test_form_create_succeeds_despite_claimed_fibers(self):
        """Plan creation on a partially claimed closure seeds only the free fibers."""
        plan = _create_plan_via_form(self.rig.closure, "Second Form Plan")

        entry = plan.entries.get()
        assert {entry.fiber_a_id, entry.fiber_b_id} == {self.rig.ports[2].pk, self.rig.ports[3].pk}
