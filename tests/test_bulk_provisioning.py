"""Bulk port provisioning: same ports, mappings and strand links as the per-object path."""

from dcim.models import Cable, FrontPort, PortMapping, RearPort
from django.db import connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from netbox_fms import naming
from netbox_fms.models import BufferTubeTemplate, FiberCable, FiberCableType, FiberStrand
from netbox_fms.services import (
    _compile_label_templates,
    _port_context_builder,
    _provision_device_ports,
    _render_port_label,
    create_closure_cable,
    generate_port_names,
    rear_group_context,
    ribbon_ordinals,
    strand_port_groups,
)
from netbox_fms.signals import fms_portmapping_bypass
from netbox_fms.trace import trace_fiber_path
from tests.conftest import make_closure_pair, make_ribbon_in_tube_type
from tests.test_bulk_splices import saves_seen

VOLATILE = {"id", "created", "last_updated"}


def provision_reference(fc, device, port_type, fk_field, warnings):
    """The per-object implementation the bulk one replaces, kept here as the equivalence reference."""
    provisioned = []
    strands = list(fc.fiber_strands.select_related("buffer_tube", "ribbon").order_by("position"))
    compiled = _compile_label_templates()
    end = "A" if fk_field == "front_port_a" else "B"
    groups = strand_port_groups(strands)
    ordered_strands = [strand for _container, group_strands in groups for strand in group_strands]
    names = generate_port_names(
        fc, device, end, ordered_strands, [group for _container, group in groups], ribbon_ordinals(strands)
    )
    if names.fallback:
        warnings.append(names.fallback)
    front_names = iter(names.fronts)
    _ctx = _port_context_builder(fc, device, end)
    with fms_portmapping_bypass():
        for (container, group_strands), rear_name in zip(groups, names.rears, strict=True):
            rp = RearPort.objects.create(
                device=device,
                name=rear_name,
                label=_render_port_label(compiled, naming.REAR_PORT_LABEL, rear_group_context(_ctx, group_strands)),
                type=port_type,
                positions=len(group_strands),
            )
            for i, strand in enumerate(group_strands, start=1):
                fp = FrontPort.objects.create(
                    device=device,
                    name=next(front_names),
                    label=_render_port_label(compiled, naming.FRONT_PORT_LABEL, _ctx(strand=strand)),
                    type=port_type,
                )
                PortMapping.objects.create(
                    device=device, front_port=fp, rear_port=rp, front_port_position=1, rear_port_position=i
                )
                setattr(strand, fk_field, fp)
                strand.save(update_fields=[fk_field])
            provisioned.append((container, rp, len(group_strands)))
    return provisioned


def columns(obj):
    return {f.attname: getattr(obj, f.attname) for f in obj._meta.concrete_fields if f.attname not in VOLATILE}


def dump_ports(fc, device, fk_field):
    """Every stored column of the device's ports and mappings, and the strand links, keyed by names."""
    fronts = {p.pk: p for p in FrontPort.objects.filter(device=device)}
    rears = {p.pk: p for p in RearPort.objects.filter(device=device)}
    mappings = {}
    for pm in PortMapping.objects.filter(device=device):
        row = columns(pm)
        del row["front_port_id"], row["rear_port_id"]
        mappings[(fronts[pm.front_port_id].name, rears[pm.rear_port_id].name)] = row
    device.refresh_from_db()
    return {
        "fronts": {p.name: columns(p) for p in fronts.values()},
        "rears": {p.name: columns(p) for p in rears.values()},
        "mappings": mappings,
        "strands": {
            s.position: fronts[getattr(s, f"{fk_field}_id")].name
            for s in FiberStrand.objects.filter(fiber_cable=fc)
            if getattr(s, f"{fk_field}_id")
        },
        "counters": (device.front_port_count, device.rear_port_count),
    }


def rolled_back(fn, fc, device, fk_field):
    with transaction.atomic():
        result = fn()
        snapshot = dump_ports(fc, device, fk_field)
        transaction.set_rollback(True)
    return result, snapshot


class BulkProvisioningCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        rig = make_closure_pair("BPV")
        cls.dev_a, cls.dev_b = rig.dev_a, rig.dev_b
        tubed = FiberCableType.objects.create(
            manufacturer=rig.mfr, model="BPV-LT48", strand_count=48, construction="loose_tube"
        )
        for position in range(1, 5):
            BufferTubeTemplate.objects.create(
                fiber_cable_type=tubed, name=f"T{position}", position=position, fiber_count=12
            )
        tight = FiberCableType.objects.create(
            manufacturer=rig.mfr, model="BPV-TB6", strand_count=6, construction="tight_buffer"
        )
        ribbon = make_ribbon_in_tube_type(rig.mfr, "BPV-RIT", tubes=2, ribbons_per_tube=2)
        cls.types = {"loose tube": tubed, "tight buffer": tight, "ribbon in tube": ribbon}
        cls.tubed = tubed

    def fiber_cable(self, fct):
        cable = Cable()
        cable.save()
        return FiberCable.objects.create(cable=cable, fiber_cable_type=fct)


class TestEquivalence(BulkProvisioningCase):
    def test_both_modes_store_what_the_per_object_path_stores(self):
        for name, fct in self.types.items():
            fc = self.fiber_cable(fct)
            args = (fc, self.dev_a, "splice", "front_port_a")
            reference, expected = rolled_back(
                lambda a=args: provision_reference(*a, []), fc, self.dev_a, "front_port_a"
            )
            for notify in (False, True):
                with self.subTest(construction=name, notify=notify):
                    provisioned, found = rolled_back(
                        lambda a=args, n=notify: _provision_device_ports(*a, [], notify=n),
                        fc,
                        self.dev_a,
                        "front_port_a",
                    )
                    assert found == expected
                    assert expected["strands"] and expected["counters"][0] == len(expected["fronts"])
                    assert [(c, rp.name, n) for c, rp, n in provisioned] == [(c, rp.name, n) for c, rp, n in reference]


class TestModes(BulkProvisioningCase):
    def test_quiet_mode_fires_no_post_save(self):
        fc = self.fiber_cable(self.tubed)
        with saves_seen(FrontPort, RearPort, PortMapping, FiberStrand) as seen:
            _provision_device_ports(fc, self.dev_a, "splice", "front_port_a", [], notify=False)
        assert seen == []

    def test_interactive_mode_announces_every_created_object(self):
        fc = self.fiber_cable(self.tubed)
        with saves_seen(FrontPort, RearPort, PortMapping) as seen:
            _provision_device_ports(fc, self.dev_a, "splice", "front_port_a", [])
        created = [model for model, _pk, was_created in seen if was_created]
        assert (created.count(FrontPort), created.count(RearPort), created.count(PortMapping)) == (48, 4, 48)

    def test_quiet_provisioning_of_one_cable_end_is_a_handful_of_queries(self):
        fc = self.fiber_cable(self.tubed)
        with CaptureQueriesContext(connection) as queries:
            _provision_device_ports(fc, self.dev_a, "splice", "front_port_a", [], notify=False)
        assert len(queries) < 40, len(queries)


class TestQuietCable(BulkProvisioningCase):
    def test_a_quietly_created_cable_counts_its_ports_and_traces_end_to_end(self):
        fc, warnings = create_closure_cable(
            device_a=self.dev_a, device_b=self.dev_b, fiber_cable_type=self.tubed, notify=False
        )
        assert warnings == []
        for device in (self.dev_a, self.dev_b):
            device.refresh_from_db()
            assert device.front_port_count == FrontPort.objects.filter(device=device).count() == 48
            assert device.rear_port_count == RearPort.objects.filter(device=device).count() == 4
        strand = fc.fiber_strands.get(position=17)
        result = trace_fiber_path(strand.front_port_a)
        assert result["is_complete"] is True
        assert result["destination"].pk == strand.front_port_b_id
