from contextlib import contextmanager

from dcim.models import (
    Cable,
    CableTermination,
    Device,
    FrontPort,
    PortMapping,
    RearPort,
    Site,
)
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TransactionTestCase

from netbox_fms.choices import SplicePlanStatusChoices
from netbox_fms.models import FiberCable, FiberCableType, SplicePlan, SplicePlanEntry
from netbox_fms.signals import fms_portmapping_bypass
from tests.conftest import connect_front_ports, make_closure_with_tray, make_infra


def make_mapping(device, front_port, rear_port, rear_port_position=1):
    """Create a FrontPort-to-RearPort PortMapping, positions defaulting to 1."""
    return PortMapping.objects.create(
        device=device,
        front_port=front_port,
        rear_port=rear_port,
        front_port_position=1,
        rear_port_position=rear_port_position,
    )


class TestDiffCacheInvalidation(TransactionTestCase):
    def setUp(self):
        rig = make_closure_with_tray("Sig")
        self.closure = rig.closure
        self.fp1, self.fp2 = rig.ports

    def test_cable_create_invalidates_cache(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Plan")
        plan.diff_stale = False
        plan.cached_diff = {"some": "data"}
        plan.save(update_fields=["diff_stale", "cached_diff"])

        cable = connect_front_ports(self.fp1, self.fp2)
        cable.save()  # Trigger post_save again after terminations exist

        plan.refresh_from_db()
        assert plan.diff_stale is True

    def test_cable_delete_invalidates_cache(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Plan")
        cable = connect_front_ports(self.fp1, self.fp2)

        plan.diff_stale = False
        plan.cached_diff = {"some": "data"}
        plan.save(update_fields=["diff_stale", "cached_diff"])

        cable.delete()

        plan.refresh_from_db()
        assert plan.diff_stale is True

    def test_unrelated_cable_does_not_invalidate(self):
        plan = SplicePlan.objects.create(closure=self.closure, name="Plan")
        plan.diff_stale = False
        plan.cached_diff = {"some": "data"}
        plan.save(update_fields=["diff_stale", "cached_diff"])

        # Cable with no terminations on our closure
        cable = Cable.objects.create(length=10, length_unit="m")
        cable.save()

        plan.refresh_from_db()
        assert plan.diff_stale is False


class TestPortMappingProtection(TransactionTestCase):
    """FMS-managed port pairs are protected; unrelated pairs are not."""

    def setUp(self):
        site, mfr, dt, role = make_infra("PM")
        self.device = Device.objects.create(name="PM-Device", site=site, device_type=dt, role=role)

        self.fct = FiberCableType.objects.create(model="PM-FCT", manufacturer=mfr, strand_count=2)
        cable = Cable.objects.create(label="PM Cable")
        self.fc = FiberCable.objects.create(cable=cable, fiber_cable_type=self.fct)

        self.rp_ct = ContentType.objects.get_for_model(RearPort)
        self.rp = RearPort.objects.create(device=self.device, name="PM Cable", type="splice", positions=2)
        CableTermination.objects.create(
            cable=cable, cable_end="A", termination_type=self.rp_ct, termination_id=self.rp.pk
        )
        self.fp = FrontPort.objects.create(device=self.device, name="PM:F1", type="splice")
        # Land the first strand on the front port, as provisioning/adoption
        # would: the strand FK is what marks the port pair FMS-managed.
        self.fc.fiber_strands.filter(position=1).update(front_port_a=self.fp)

    def _create_mapping(self):
        """Create the fixture PortMapping under the FMS bypass."""
        with fms_portmapping_bypass():
            return make_mapping(self.device, self.fp, self.rp)

    def test_external_portmapping_create_blocked(self):
        with self.assertRaises(ValidationError):
            make_mapping(self.device, self.fp, self.rp)

    def test_bypass_allows_portmapping_create(self):
        pm = self._create_mapping()
        assert pm.pk is not None

    def test_external_portmapping_delete_blocked(self):
        pm = self._create_mapping()
        with self.assertRaises(ValidationError):
            pm.delete()

    def test_device_delete_cascades_portmappings(self):
        """Deleting the closure itself must not be blocked by the guard (issue #136)."""
        self._create_mapping()
        device_pk = self.device.pk
        self.device.delete()
        assert not Device.objects.filter(pk=device_pk).exists()
        assert not PortMapping.objects.filter(device_id=device_pk).exists()

    def test_device_queryset_delete_cascades_portmappings(self):
        """Bulk device deletion must not be blocked by the guard either (issue #136)."""
        self._create_mapping()
        device_pk = self.device.pk
        Device.objects.filter(pk=device_pk).delete()
        assert not Device.objects.filter(pk=device_pk).exists()

    @contextmanager
    def _netbox_45_shaped_delete(self):
        """Install a DeleteMixin.delete without forwarding (the NetBox 4.5
        shape), apply the shim, and yield the unpatched function; the real
        delete is restored on exit.
        """
        from django.db import router
        from netbox.models import deletion

        from netbox_fms.monkey_patches import patch_delete_origin

        original = deletion.DeleteMixin.delete

        def delete(self, using=None, keep_parents=False):
            using = using or router.db_for_write(self.__class__, instance=self)
            collector = deletion.CustomCollector(using=using)
            collector.collect([self], keep_parents=keep_parents)
            return collector.delete()

        deletion.DeleteMixin.delete = delete
        try:
            patch_delete_origin()
            yield delete
        finally:
            deletion.DeleteMixin.delete = original

    def test_patch_delete_origin_restores_forwarding(self):
        """NetBox 4.5 shim (issue #136): when DeleteMixin.delete does not
        forward the deletion origin to its collector, patch_delete_origin()
        must replace it with one that does, so deleting a closure still
        cascades through its protected PortMappings.
        """
        from netbox.models import deletion

        with self._netbox_45_shaped_delete() as unpatched:
            assert deletion.DeleteMixin.delete is not unpatched
            self._create_mapping()
            device_pk = self.device.pk
            self.device.delete()
            assert not Device.objects.filter(pk=device_pk).exists()

    def test_patched_delete_rejects_unsaved_instance(self):
        """The shim keeps upstream's guard: an instance whose pk is None
        cannot be deleted (issue #136).
        """
        with self._netbox_45_shaped_delete():
            with self.assertRaises(ValueError):
                Device(name="PM-Unsaved").delete()

    def test_unrelated_mapping_on_fms_device_unprotected(self):
        """Regression test for issue #172: a housing holding one FMS cable
        must not lock unrelated port pairs (e.g. an MPO pigtail) on the
        same device.
        """
        self._create_mapping()
        rp2 = RearPort.objects.create(device=self.device, name="MPO-RP", type="lc", positions=1)
        fp2 = FrontPort.objects.create(device=self.device, name="MPO-FP", type="lc")

        pm = make_mapping(self.device, fp2, rp2)
        assert pm.pk is not None

        pm.delete()
        assert not PortMapping.objects.filter(front_port=fp2).exists()

    def test_new_mapping_onto_fms_rear_port_blocked(self):
        """A free position on a rear port serving FMS strands is still FMS
        territory: wedging a foreign front port onto it is blocked.
        """
        self._create_mapping()
        fp2 = FrontPort.objects.create(device=self.device, name="PM:FX", type="splice")

        with self.assertRaises(ValidationError):
            make_mapping(self.device, fp2, self.rp, rear_port_position=2)

    def test_repointing_fms_mapping_away_blocked(self):
        """Repointing an FMS mapping at innocent ports is still an external
        change to FMS state: the previous port pair must be checked too.
        """
        pm = self._create_mapping()
        rp2 = RearPort.objects.create(device=self.device, name="Free-RP", type="lc", positions=1)
        fp2 = FrontPort.objects.create(device=self.device, name="Free-FP", type="lc")

        pm.front_port = fp2
        pm.rear_port = rp2
        pm.rear_port_position = 1
        with self.assertRaises(ValidationError):
            pm.save()

    def test_far_end_rear_port_without_strands_unprotected(self):
        """Regression test for issue #172: a panel whose rear port merely
        terminates an FMS trunk, with no strands landed on its front
        ports, stays user-managed.
        """
        site = Site.objects.create(name="Panel Site", slug="panel-site")
        panel = Device.objects.create(
            name="Panel", site=site, device_type=self.device.device_type, role=self.device.role
        )
        rp_b = RearPort.objects.create(device=panel, name="Panel-RP", type="splice", positions=2)
        CableTermination.objects.create(
            cable=self.fc.cable, cable_end="B", termination_type=self.rp_ct, termination_id=rp_b.pk
        )
        fp_b = FrontPort.objects.create(device=panel, name="Panel-FP", type="lc")

        pm = make_mapping(panel, fp_b, rp_b)
        assert pm.pk is not None

    def test_null_port_ids_are_not_fms_managed(self):
        """A missing FK id must not match strands via IS NULL lookups: a
        malformed mapping is rejected by the database, never by the guard.
        """
        from netbox_fms.signals import _front_port_is_fms_managed, _rear_port_is_fms_managed

        # The fixture cable still has unlanded strands (NULL front_port
        # FKs), which an unguarded id=None filter would match.
        assert _front_port_is_fms_managed(None) is False
        assert _rear_port_is_fms_managed(None) is False

    def test_non_fms_device_unprotected(self):
        site, _mfr, dt, role = make_infra("NF")
        device2 = Device.objects.create(name="NF-Device", site=site, device_type=dt, role=role)
        rp2 = RearPort.objects.create(device=device2, name="NF-RP", type="8p8c", positions=1)
        fp2 = FrontPort.objects.create(device=device2, name="NF-FP", type="8p8c")
        pm = make_mapping(device2, fp2, rp2)
        assert pm.pk is not None


class TestPlanPortProtection(TransactionTestCase):
    """Front ports spliced in a live plan are protected without a strand."""

    def setUp(self):
        rig = make_closure_with_tray("PP")
        self.closure = rig.closure
        self.pigtail, fiber_b = rig.ports
        self.plan = SplicePlan.objects.create(closure=self.closure, name="PP Plan")
        SplicePlanEntry.objects.create(plan=self.plan, tray=rig.tray, fiber_a=self.pigtail, fiber_b=fiber_b)

        self.rp = RearPort.objects.create(device=self.closure, name="PP-RP", type="lc", positions=1)

    def _create_pigtail_mapping(self):
        return make_mapping(self.closure, self.pigtail, self.rp)

    def test_mapping_on_live_plan_port_blocked(self):
        """A strand-less pigtail referenced by a non-archived plan entry
        cannot have its mapping changed externally (issue #172).
        """
        with self.assertRaises(ValidationError):
            self._create_pigtail_mapping()

    def test_mapping_on_archived_plan_port_allowed(self):
        """Archiving the plan releases its ports back to the user."""
        SplicePlan.objects.filter(pk=self.plan.pk).update(status=SplicePlanStatusChoices.ARCHIVED)
        pm = self._create_pigtail_mapping()
        assert pm.pk is not None


class TestPortNaming(TransactionTestCase):
    """FMS-provisioned ports carry pk-based, absolute-number names."""

    def setUp(self):
        site, self.mfr, dt, role = make_infra("PN")
        self.device = Device.objects.create(name="PN-Device", site=site, device_type=dt, role=role)

    def test_tubed_provisioning_uses_pk_and_absolute_numbers(self):
        from netbox_fms.models import BufferTubeTemplate, FiberCableType
        from netbox_fms.services import link_cable_topology

        fct = FiberCableType.objects.create(model="PN-FCT", manufacturer=self.mfr, strand_count=4)
        for i in (1, 2):
            BufferTubeTemplate.objects.create(fiber_cable_type=fct, name=f"T{i}", position=i, fiber_count=2)
        cable = Cable.objects.create(label="CO-Downtown")

        link_cable_topology(cable, fct, self.device)

        rp_names = set(RearPort.objects.filter(device=self.device).values_list("name", flat=True))
        assert rp_names == {f"{cable.pk}:T1", f"{cable.pk}:T2"}
        # Front ports number fibers absolutely across the cable, never per tube.
        fp_names = set(FrontPort.objects.filter(device=self.device).values_list("name", flat=True))
        assert fp_names == {f"{cable.pk}:F{n}" for n in (1, 2, 3, 4)}

    def test_no_tube_provisioning_uses_bare_pk_rear_port(self):
        from netbox_fms.models import FiberCableType
        from netbox_fms.services import link_cable_topology

        fct = FiberCableType.objects.create(model="PN-FCT2", manufacturer=self.mfr, strand_count=2)
        cable = Cable.objects.create(label="CO-East")

        link_cable_topology(cable, fct, self.device)

        rp = RearPort.objects.filter(device=self.device).first()
        assert rp.name == str(cable.pk), f"Got: {rp.name}"

        fp_names = set(FrontPort.objects.filter(device=self.device).values_list("name", flat=True))
        assert fp_names == {f"{cable.pk}:F1", f"{cable.pk}:F2"}

    def test_unlabeled_cable_gets_the_same_names(self):
        """The name never embeds the display label, so its absence changes nothing."""
        from netbox_fms.models import FiberCableType
        from netbox_fms.services import link_cable_topology

        fct = FiberCableType.objects.create(model="PN-FCT3", manufacturer=self.mfr, strand_count=1)
        cable = Cable.objects.create()

        link_cable_topology(cable, fct, self.device)

        rp = RearPort.objects.filter(device=self.device).first()
        assert rp.name == str(cable.pk), f"Got: {rp.name}"


class TestPortNamesWriteOnce(TransactionTestCase):
    """pk-based names are write-once: a cable relabel never renames ports."""

    def setUp(self):
        site, self.mfr, dt, role = make_infra("NS")
        self.device = Device.objects.create(name="NS-Device", site=site, device_type=dt, role=role)

    def test_cable_relabel_changes_labels_not_names(self):
        from netbox_fms.models import BufferTubeTemplate, FiberCableType
        from netbox_fms.services import link_cable_topology

        fct = FiberCableType.objects.create(model="NS-FCT", manufacturer=self.mfr, strand_count=2)
        BufferTubeTemplate.objects.create(fiber_cable_type=fct, name="T1", position=1, fiber_count=2)
        cable = Cable.objects.create(label="Old Label")
        link_cable_topology(cable, fct, self.device)

        names_before = {
            (type(p).__name__, p.pk): p.name
            for model in (RearPort, FrontPort)
            for p in model.objects.filter(device=self.device)
        }

        cable.label = "New Label"
        cable.save()

        names_after = {
            (type(p).__name__, p.pk): p.name
            for model in (RearPort, FrontPort)
            for p in model.objects.filter(device=self.device)
        }
        assert names_after == names_before

        # The display layer still follows the relabel.
        rp = RearPort.objects.filter(device=self.device).first()
        assert "New Label" in rp.label
