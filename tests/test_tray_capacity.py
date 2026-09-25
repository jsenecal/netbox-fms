"""Tests for splice tray capacity and utilization (issue #89)."""

from dcim.models import Cable, FrontPort
from django.contrib.auth import get_user_model
from django.test import TestCase

from netbox_fms.choices import TrayRoleChoices
from netbox_fms.models import BufferTubeTemplate, ClosureCableEntry, FiberCable, FiberCableType, TubeAssignment
from netbox_fms.services import auto_assign_tubes, tray_utilization
from netbox_fms.tables import TubeAssignmentTable
from tests.conftest import (
    connect_front_ports,
    make_authed_client,
    make_closure,
    make_front_port,
    make_tray_module,
    make_tray_type,
)


def _make_tray(closure, mfr, model, bay, splice_capacity, tube_capacity=None, role=TrayRoleChoices.SPLICE_TRAY):
    module_type = make_tray_type(mfr, model, role, splice_capacity=splice_capacity, tube_capacity=tube_capacity)
    return make_tray_module(closure, module_type, bay)


def _make_cable(prefix, closure, mfr, tubes, fibers):
    """A loose-tube cable entering the closure with a near-end port per strand."""
    fct = FiberCableType.objects.create(
        manufacturer=mfr, model=f"{prefix}-{tubes}x{fibers}", construction="loose_tube", strand_count=tubes * fibers
    )
    for i in range(1, tubes + 1):
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name=f"T{i}", position=i, fiber_count=fibers)
    fc = FiberCable.objects.create(cable=Cable.objects.create(), fiber_cable_type=fct)
    for strand in fc.fiber_strands.all():
        strand.front_port_a = make_front_port(closure, f"{prefix}-{fc.pk}-{strand.position}")
        strand.save()
    ClosureCableEntry.objects.create(closure=closure, fiber_cable=fc, entrance_label=f"{prefix}-G{fc.pk}")
    return fc


class TestTrayUtilization(TestCase):
    """tray_utilization counts what lands on each tray against its profile."""

    @classmethod
    def setUpTestData(cls):
        rig = make_closure("TU")
        cls.closure, mfr = rig.closure, rig.mfr
        cls.tray = _make_tray(cls.closure, mfr, "TU Tray", "Bay 1", splice_capacity=12, tube_capacity=2)
        cls.basket = _make_tray(
            cls.closure,
            mfr,
            "TU Basket",
            "Bay 2",
            splice_capacity=0,
            tube_capacity=4,
            role=TrayRoleChoices.EXPRESS_BASKET,
        )
        cls.cable = _make_cable("TU", cls.closure, mfr, tubes=2, fibers=2)
        cls.tubes = list(cls.cable.buffer_tubes.order_by("position"))

    def _assign(self, *tubes):
        for tube in tubes:
            TubeAssignment.objects.create(closure=self.closure, tray=self.tray, buffer_tube=tube)

    def test_empty_tray_reports_zero_usage(self):
        util = tray_utilization(self.closure)[self.tray.pk]
        assert (util.tubes, util.strands, util.splices) == (0, 0, 0)
        assert util.splice_capacity == 12
        assert util.tube_capacity == 2
        assert util.strand_capacity == 24
        assert not util.over_capacity

    def test_counts_assigned_tubes_and_their_strands(self):
        self._assign(*self.tubes)
        util = tray_utilization(self.closure)[self.tray.pk]
        assert util.tubes == 2
        assert util.strands == 4

    def test_counts_live_splices_on_the_tray(self):
        self._assign(*self.tubes)
        ports = list(FrontPort.objects.filter(module=self.tray).order_by("pk"))
        connect_front_ports(ports[0], ports[2])
        util = tray_utilization(self.closure)[self.tray.pk]
        assert util.splices == 1

    def test_splice_to_an_unassigned_strand_counts_on_the_tray_end(self):
        self._assign(self.tubes[0])
        on_tray = FrontPort.objects.filter(module=self.tray).first()
        loose = FrontPort.objects.filter(device=self.closure, module__isnull=True).first()
        connect_front_ports(on_tray, loose)
        util = tray_utilization(self.closure)[self.tray.pk]
        assert util.splices == 1

    def test_express_basket_is_reported_with_tube_capacity_only(self):
        util = tray_utilization(self.closure)[self.basket.pk]
        assert util.tube_capacity == 4
        assert util.tubes == 0
        assert not util.over_capacity

    def test_fiber_overview_card_shows_basket_tube_capacity(self):
        self.client.force_login(get_user_model().objects.create_superuser(username="tu-user", password="test"))
        html = self.client.get(f"/dcim/devices/{self.closure.pk}/fiber-overview/").content.decode()
        assert "4 tubes" in html


class TestOverCapacity(TestCase):
    @classmethod
    def setUpTestData(cls):
        rig = make_closure("OC")
        cls.closure, cls.mfr = rig.closure, rig.mfr
        cls.cable = _make_cable("OC", cls.closure, cls.mfr, tubes=3, fibers=2)
        cls.tubes = list(cls.cable.buffer_tubes.order_by("position"))

    def _tray_with(self, splice_capacity, tube_capacity, tubes):
        tray = _make_tray(
            self.closure, self.mfr, f"OC {splice_capacity}/{tube_capacity}", "Bay 1", splice_capacity, tube_capacity
        )
        for tube in tubes:
            TubeAssignment.objects.create(closure=self.closure, tray=tray, buffer_tube=tube)
        return tray_utilization(self.closure)[tray.pk]

    def test_at_capacity_is_not_over(self):
        util = self._tray_with(splice_capacity=2, tube_capacity=2, tubes=self.tubes[:2])
        assert util.strands == 4
        assert not util.over_strands
        assert not util.over_tubes
        assert not util.over_capacity

    def test_one_tube_past_tube_capacity_is_over(self):
        util = self._tray_with(splice_capacity=6, tube_capacity=2, tubes=self.tubes)
        assert util.over_tubes
        assert not util.over_strands
        assert util.over_capacity

    def test_strands_past_twice_splice_capacity_is_over(self):
        util = self._tray_with(splice_capacity=2, tube_capacity=None, tubes=self.tubes)
        assert util.strands == 6
        assert util.over_strands
        assert util.over_capacity

    def test_null_tube_capacity_is_unlimited(self):
        util = self._tray_with(splice_capacity=6, tube_capacity=None, tubes=self.tubes)
        assert util.tube_capacity is None
        assert not util.over_tubes
        assert not util.over_capacity

    def test_remaining_strands_counts_down_from_twice_splice_capacity(self):
        util = self._tray_with(splice_capacity=4, tube_capacity=None, tubes=self.tubes[:1])
        assert util.remaining_strands == 6


class TestAutoAssignReservesAgainstSplicePositions(TestCase):
    """A 24-position tray physically holds two pairs of 12-fiber tubes."""

    @classmethod
    def setUpTestData(cls):
        rig = make_closure("AA")
        cls.closure, mfr = rig.closure, rig.mfr
        cls.tray1 = _make_tray(cls.closure, mfr, "AA Tray", "Bay 1", splice_capacity=24)
        cls.tray2 = make_tray_module(cls.closure, cls.tray1.module_type, "Bay 2")
        cls.cable_a = _make_cable("AA-A", cls.closure, mfr, tubes=2, fibers=12)
        cls.cable_b = _make_cable("AA-B", cls.closure, mfr, tubes=2, fibers=12)

    def test_two_tube_pairs_fill_one_tray(self):
        auto_assign_tubes(self.closure)
        assert TubeAssignment.objects.filter(tray=self.tray1).count() == 4
        assert not TubeAssignment.objects.filter(tray=self.tray2).exists()

    def test_auto_assign_never_overfills(self):
        third = _make_cable("AA-C", self.closure, self.cable_a.fiber_cable_type.manufacturer, tubes=2, fibers=12)
        auto_assign_tubes(self.closure)
        util = tray_utilization(self.closure)
        assert not util[self.tray1.pk].over_capacity
        assert not util[self.tray2.pk].over_capacity
        assert TubeAssignment.objects.filter(buffer_tube__fiber_cable=third).count() == 2


class TestTubeAssignmentTableUtilization(TestCase):
    @classmethod
    def setUpTestData(cls):
        rig = make_closure("TT")
        cls.closure, mfr = rig.closure, rig.mfr
        cls.tray = _make_tray(cls.closure, mfr, "TT Tray", "Bay 1", splice_capacity=12, tube_capacity=1)
        cable = _make_cable("TT", cls.closure, mfr, tubes=2, fibers=2)
        for tube in cable.buffer_tubes.all():
            TubeAssignment.objects.create(closure=cls.closure, tray=cls.tray, buffer_tube=tube)

    def test_column_shows_tubes_and_strands_against_capacity(self):
        table = TubeAssignmentTable(TubeAssignment.objects.filter(closure=self.closure))
        record = TubeAssignment.objects.filter(closure=self.closure).first()
        html = str(table.render_tray_utilization(record))
        assert "2/1" in html
        assert "4/24" in html
        assert "text-danger" in html


class TestClosureStrandsTrayCapacity(TestCase):
    """The splice editor reports profile capacity, not the live port count."""

    @classmethod
    def setUpTestData(cls):
        rig = make_closure("CS")
        cls.closure, mfr = rig.closure, rig.mfr
        cls.tray = _make_tray(cls.closure, mfr, "CS Tray", "Bay 1", splice_capacity=24)
        cable = _make_cable("CS", cls.closure, mfr, tubes=1, fibers=2)
        TubeAssignment.objects.create(closure=cls.closure, tray=cls.tray, buffer_tube=cable.buffer_tubes.first())

    def test_capacity_comes_from_the_profile(self):
        client = make_authed_client("cs-user")
        resp = client.get(f"/api/plugins/fms/closure-strands/{self.closure.pk}/")
        assert resp.status_code == 200
        tray = next(t for t in resp.data["trays"] if t["id"] == self.tray.pk)
        assert tray["capacity"] == 24


class TestCapacityRendering(TestCase):
    """Over-capacity state is shown, never enforced."""

    @classmethod
    def setUpTestData(cls):
        rig = make_closure("CR")
        cls.closure, mfr = rig.closure, rig.mfr
        cls.tray = _make_tray(cls.closure, mfr, "CR Tray", "Bay 1", splice_capacity=1)
        cable = _make_cable("CR", cls.closure, mfr, tubes=2, fibers=2)
        cls.tubes = list(cable.buffer_tubes.order_by("position"))
        cls.assignment = TubeAssignment.objects.create(closure=cls.closure, tray=cls.tray, buffer_tube=cls.tubes[0])
        cls.user = get_user_model().objects.create_superuser(username="cr-user", password="test")

    def test_assign_modal_flags_a_tray_the_tube_would_overfill_but_offers_it(self):
        self.client.force_login(self.user)
        url = f"/plugins/fms/fiber-overview/{self.closure.pk}/assign-tube/?tube_id={self.tubes[1].pk}"
        html = self.client.get(url).content.decode()
        assert f'value="{self.tray.pk}"' in html
        assert "would exceed capacity" in html

    def test_overfilled_assignment_saves_and_detail_page_flags_it(self):
        TubeAssignment.objects.create(closure=self.closure, tray=self.tray, buffer_tube=self.tubes[1])
        self.client.force_login(self.user)
        html = self.client.get(self.assignment.get_absolute_url()).content.decode()
        assert "Over capacity" in html
        assert "4/2 fibers" in html
