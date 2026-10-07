"""Bulk tube assignment: same assignments and port moves as the per-object path."""

from unittest.mock import patch

from dcim.models import Device, FrontPort
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from netbox_fms.bulk import TubeSpec, assign_tubes
from netbox_fms.jobs import PathAnalysisJob
from netbox_fms.models import BufferTubeTemplate, FiberCableType, PathAnalysisQueue, TubeAssignment
from netbox_fms.services import create_closure_cable
from tests.conftest import (
    is_indexed,
    make_infra,
    make_tray_module,
    make_tray_type,
    place_in_rack,
    rolled_back,
    saves_seen,
)

TRAY_LABELS = {"netbox_fms": {"front_port_label_template": "{% if tray %}{{ tray }}/{% endif %}F{{ strand }}"}}


def dump_assignments(closure, far):
    """Assignments of the closure and where every strand port of both devices sits, by name."""
    trays = dict(closure.modules.values_list("pk", "module_bay__name"))
    return {
        "assignments": sorted(
            (a.buffer_tube.position, trays[a.tray_id], a.position, a.notes, tuple(sorted(a.custom_field_data.items())))
            for a in TubeAssignment.objects.filter(closure=closure).select_related("buffer_tube")
        ),
        "closure_ports": {p.name: (trays.get(p.module_id), p.label) for p in FrontPort.objects.filter(device=closure)},
        "far_ports": {p.name: p.module_id for p in FrontPort.objects.filter(device=far)},
    }


class BulkTubeCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        site, mfr, dt, role = make_infra("BTU")
        cls.far = Device.objects.create(name="BTU-FAR", site=site, device_type=dt, role=role)
        cls.closure = place_in_rack(
            Device.objects.create(name="BTU-CLOSURE", site=site, device_type=dt, role=role), "BTU"
        )
        cls.other = Device.objects.create(name="BTU-OTHER", site=site, device_type=dt, role=role)
        tray_type = make_tray_type(mfr, "BTU-TRAY", splice_capacity=24)
        cls.tray1 = make_tray_module(cls.closure, tray_type, "Tray 1")
        cls.tray2 = make_tray_module(cls.closure, tray_type, "Tray 2")
        cls.plain = make_tray_module(cls.closure, make_tray_type(mfr, "BTU-PLAIN", role=None), "Plain")
        cls.basket = make_tray_module(cls.closure, make_tray_type(mfr, "BTU-BASKET", role="express_basket"), "Basket")
        cls.foreign_tray = make_tray_module(cls.other, tray_type, "Tray 1")
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="BTU-LT24", strand_count=24, construction="loose_tube"
        )
        for position in (1, 2):
            BufferTubeTemplate.objects.create(
                fiber_cable_type=fct, name=f"T{position}", position=position, fiber_count=12
            )
        cls.cable, _ = create_closure_cable(device_a=cls.far, device_b=cls.closure, fiber_cable_type=fct)
        cls.elsewhere, _ = create_closure_cable(device_a=cls.far, device_b=cls.other, fiber_cable_type=fct)
        cls.tube1, cls.tube2 = cls.cable.buffer_tubes.order_by("position")

    def specs(self):
        return [TubeSpec(self.tube1.pk, self.tray1.pk), TubeSpec(self.tube2.pk, self.tray2.pk)]

    def reference(self):
        for spec in self.specs():
            TubeAssignment.objects.create(
                closure=self.closure, tray_id=spec.tray_id, buffer_tube_id=spec.buffer_tube_id
            )


class TestEquivalence(BulkTubeCase):
    def test_quiet_mode_stores_what_the_per_object_path_stores(self):
        _, expected = rolled_back(self.reference, lambda: dump_assignments(self.closure, self.far))
        assign_tubes(self.closure, self.specs(), notify=False)
        found = dump_assignments(self.closure, self.far)
        assert found == expected
        assert sum(1 for tray, _label in found["closure_ports"].values() if tray == "Tray 1") == 12
        assert set(found["far_ports"].values()) == {None}

    def test_quiet_mode_queues_the_closure_for_analysis(self):
        with patch.object(PathAnalysisJob, "enqueue"), self.captureOnCommitCallbacks(execute=True):
            assign_tubes(self.closure, self.specs(), notify=False)
        queued = set(PathAnalysisQueue.objects.values_list("device_id", "reason"))
        assert queued == {(self.closure.pk, "bulk_operation")}

    def test_interactive_mode_saves_each_assignment(self):
        _, expected = rolled_back(self.reference, lambda: dump_assignments(self.closure, self.far))
        with saves_seen(TubeAssignment) as seen:
            rows = assign_tubes(self.closure, self.specs())
        assert dump_assignments(self.closure, self.far) == expected
        assert sorted(pk for _model, pk, created in seen if created) == sorted(row.pk for row in rows)

    def test_quiet_mode_fires_no_post_save(self):
        with saves_seen(TubeAssignment, FrontPort) as seen:
            assign_tubes(self.closure, self.specs(), notify=False)
        assert seen == []

    def test_custom_field_data_is_stored(self):
        from core.models import ObjectType
        from extras.models import CustomField

        field = CustomField.objects.create(name="btu_origin", type="text")
        field.object_types.set([ObjectType.objects.get_for_model(TubeAssignment)])
        (row,) = assign_tubes(
            self.closure, [TubeSpec(self.tube1.pk, self.tray1.pk, {"btu_origin": "import"})], notify=False
        )
        row.refresh_from_db()
        assert row.custom_field_data["btu_origin"] == "import"

    @override_settings(PLUGINS_CONFIG=TRAY_LABELS)
    def test_quiet_mode_rerenders_labels_that_name_the_tray(self):
        _, expected = rolled_back(self.reference, lambda: dump_assignments(self.closure, self.far))
        assign_tubes(self.closure, self.specs(), notify=False)
        found = dump_assignments(self.closure, self.far)
        assert found == expected
        labels = {label for _tray, label in found["closure_ports"].values()}
        assert any(label.startswith("Tray 1") and label.endswith("/F1") for label in labels)

    @override_settings(PLUGINS_CONFIG=TRAY_LABELS)
    def test_quiet_mode_indexes_the_rerendered_labels(self):
        assign_tubes(self.closure, self.specs(), notify=False)
        port = FrontPort.objects.filter(device=self.closure, module=self.tray1).first()
        assert port.label.startswith("Tray 1")
        assert is_indexed(port, port.label)


class TestValidation(BulkTubeCase):
    def assert_rejected(self, specs, fragment):
        with self.assertRaises(ValidationError) as raised:
            assign_tubes(self.closure, specs, notify=False)
        assert fragment in " ".join(raised.exception.messages)
        assert not TubeAssignment.objects.filter(closure=self.closure).exists()

    def test_a_tray_of_another_device_is_rejected(self):
        self.assert_rejected([TubeSpec(self.tube1.pk, self.foreign_tray.pk)], "closure")

    def test_a_module_without_a_tray_profile_is_rejected(self):
        self.assert_rejected([TubeSpec(self.tube1.pk, self.plain.pk)], "splice tray")

    def test_an_express_basket_is_rejected(self):
        self.assert_rejected([TubeSpec(self.tube1.pk, self.basket.pk)], "splice tray")

    def test_a_tube_whose_cable_does_not_enter_the_closure_is_rejected(self):
        outsider = self.elsewhere.buffer_tubes.first()
        self.assert_rejected([TubeSpec(outsider.pk, self.tray1.pk)], "enter")

    def test_a_tube_named_twice_is_rejected(self):
        self.assert_rejected(
            [TubeSpec(self.tube1.pk, self.tray1.pk), TubeSpec(self.tube1.pk, self.tray2.pk)], "2 times"
        )

    def test_a_tube_already_assigned_is_rejected(self):
        TubeAssignment.objects.create(closure=self.closure, tray=self.tray1, buffer_tube=self.tube1)
        with self.assertRaises(ValidationError) as raised:
            assign_tubes(self.closure, [TubeSpec(self.tube1.pk, self.tray2.pk)], notify=False)
        assert "already assigned" in " ".join(raised.exception.messages)
        assert TubeAssignment.objects.filter(closure=self.closure).count() == 1
