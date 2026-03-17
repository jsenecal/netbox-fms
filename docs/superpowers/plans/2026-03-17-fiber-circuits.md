# Fiber Circuits Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Fiber Circuit models that document end-to-end fiber strand paths through cables and splices, with PROTECT-based deletion prevention and a DAG pathfinding provisioning engine.

**Architecture:** Three new models (FiberCircuit, FiberCircuitPath, FiberCircuitNode) follow NetBox's plugin patterns. FiberCircuitPath adapts CablePath's trace algorithm for FrontPort origins. FiberCircuitNode provides relational PROTECT FKs against dcim objects. The existing FiberPathLoss stub is removed and replaced by loss fields on FiberCircuitPath.

**Tech Stack:** Django 5.x, NetBox 4.5+ plugin API, PostgreSQL (CheckConstraint, select_for_update), pytest

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `netbox_fms/choices.py` | Modify | Add `FiberCircuitStatusChoices` |
| `netbox_fms/models.py` | Modify | Remove `FiberPathLoss`, add `FiberCircuit`, `FiberCircuitPath`, `FiberCircuitNode` |
| `netbox_fms/trace.py` | Create | `FiberCircuitPath.from_origin()` trace logic (standalone module for testability) |
| `netbox_fms/provisioning.py` | Create | `FiberCircuit.find_paths()` and `create_from_proposal()` DAG engine |
| `netbox_fms/forms.py` | Modify | Remove FiberPathLoss forms, add FiberCircuit forms |
| `netbox_fms/filters.py` | Modify | Remove FiberPathLoss filter, add FiberCircuit filters |
| `netbox_fms/tables.py` | Modify | Remove FiberPathLoss table, add FiberCircuit tables |
| `netbox_fms/views.py` | Modify | Remove FiberPathLoss views, add FiberCircuit views |
| `netbox_fms/urls.py` | Modify | Remove FiberPathLoss URLs, add FiberCircuit URLs |
| `netbox_fms/api/serializers.py` | Modify | Remove FiberPathLoss serializer, add FiberCircuit serializers |
| `netbox_fms/api/views.py` | Modify | Remove FiberPathLoss viewset, add FiberCircuit viewsets + protecting endpoint |
| `netbox_fms/api/urls.py` | Modify | Update router registrations |
| `netbox_fms/graphql/types.py` | Modify | Remove FiberPathLoss type, add FiberCircuit types |
| `netbox_fms/graphql/schema.py` | Modify | Update query class |
| `netbox_fms/graphql/filters.py` | Modify | Update filters |
| `netbox_fms/search.py` | Modify | Remove FiberPathLoss index, add FiberCircuit index |
| `netbox_fms/navigation.py` | Modify | Update menu entries |
| `netbox_fms/templates/netbox_fms/fibercircuit.html` | Create | Detail template |
| `netbox_fms/templates/netbox_fms/fiberpathloss.html` | Delete | Removed model |
| `tests/test_fiber_circuits.py` | Create | All fiber circuit tests |
| `tests/test_fiber_circuit_trace.py` | Create | Trace engine tests |
| `tests/test_fiber_circuit_protection.py` | Create | PROTECT FK tests |
| `tests/test_fiber_circuit_provisioning.py` | Create | DAG pathfinding tests |
| `tests/test_fiber_circuit_api.py` | Create | API endpoint tests |
| `tests/test_fiber_circuit_performance.py` | Create | Performance benchmarks |

---

## Task 1: Remove FiberPathLoss (full-stack)

Remove the stub model before adding new models to avoid confusion and migration conflicts.

**Files:**
- Modify: `netbox_fms/models.py:20-35` (`__all__`), `netbox_fms/models.py:946-1005` (model)
- Modify: `netbox_fms/forms.py` (remove FiberPathLossForm, FiberPathLossImportForm, FiberPathLossBulkEditForm, FiberPathLossFilterForm)
- Modify: `netbox_fms/filters.py` (remove FiberPathLossFilterSet)
- Modify: `netbox_fms/tables.py` (remove FiberPathLossTable)
- Modify: `netbox_fms/views.py` (remove FiberPathLossListView, FiberPathLossView, FiberPathLossEditView, FiberPathLossDeleteView, FiberPathLossBulkImportView, FiberPathLossBulkEditView, FiberPathLossBulkDeleteView)
- Modify: `netbox_fms/urls.py` (remove FiberPathLoss URL patterns)
- Modify: `netbox_fms/api/serializers.py` (remove FiberPathLossSerializer)
- Modify: `netbox_fms/api/views.py` (remove FiberPathLossViewSet)
- Modify: `netbox_fms/api/urls.py` (remove router registration)
- Modify: `netbox_fms/graphql/types.py` (remove FiberPathLossType)
- Modify: `netbox_fms/graphql/schema.py` (remove query entries)
- Modify: `netbox_fms/graphql/filters.py` (remove filter)
- Modify: `netbox_fms/search.py` (remove FiberPathLossIndex)
- Modify: `netbox_fms/navigation.py` (remove menu entry)
- Delete: `netbox_fms/templates/netbox_fms/fiberpathloss.html`

- [ ] **Step 1: Remove FiberPathLoss from all files**

Search each file listed above for `FiberPathLoss` / `fiberpathloss` / `fiber_path_loss` and remove all references. In `models.py`, remove lines 946-1005 and the `"FiberPathLoss"` entry from `__all__`. Delete the template file.

- [ ] **Step 2: Generate migration**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py makemigrations netbox_fms
```

Expected: Migration created that deletes FiberPathLoss table.

- [ ] **Step 3: Apply migration and verify imports**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py migrate
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.models import *; from netbox_fms.forms import *; from netbox_fms.filters import *"
```

Expected: No errors.

- [ ] **Step 4: Run existing tests**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v
```

Expected: All tests pass (any FiberPathLoss tests should have been removed or will fail — fix if needed).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "refactor: remove FiberPathLoss stub model (replaced by FiberCircuit)"
```

---

## Task 2: Add FiberCircuitStatusChoices

**Files:**
- Modify: `netbox_fms/choices.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_fiber_circuits.py`:

```python
from django.test import TestCase

from netbox_fms.choices import FiberCircuitStatusChoices


class TestFiberCircuitStatusChoices(TestCase):
    def test_has_planned(self):
        assert FiberCircuitStatusChoices.PLANNED == "planned"

    def test_has_staged(self):
        assert FiberCircuitStatusChoices.STAGED == "staged"

    def test_has_active(self):
        assert FiberCircuitStatusChoices.ACTIVE == "active"

    def test_has_decommissioned(self):
        assert FiberCircuitStatusChoices.DECOMMISSIONED == "decommissioned"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_circuits.py -v
```

Expected: ImportError — `FiberCircuitStatusChoices` not found.

- [ ] **Step 3: Implement**

Add to `netbox_fms/choices.py`:

```python
class FiberCircuitStatusChoices(ChoiceSet):
    PLANNED = "planned"
    STAGED = "staged"
    ACTIVE = "active"
    DECOMMISSIONED = "decommissioned"

    CHOICES = (
        (PLANNED, _("Planned")),
        (STAGED, _("Staged")),
        (ACTIVE, _("Active")),
        (DECOMMISSIONED, _("Decommissioned")),
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_circuits.py -v
```

Expected: All 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/choices.py tests/test_fiber_circuits.py && git commit -m "feat: add FiberCircuitStatusChoices"
```

---

## Task 3: Add FiberCircuit model

**Files:**
- Modify: `netbox_fms/models.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_fiber_circuits.py`:

```python
from netbox_fms.models import FiberCircuit
from netbox_fms.choices import FiberCircuitStatusChoices


class TestFiberCircuit(TestCase):
    def test_create_circuit(self):
        circuit = FiberCircuit.objects.create(
            name="DT-CTR-1",
            status=FiberCircuitStatusChoices.PLANNED,
            strand_count=2,
        )
        assert circuit.pk is not None
        assert str(circuit) == "DT-CTR-1"

    def test_optional_fields(self):
        circuit = FiberCircuit.objects.create(
            name="DT-CTR-2",
            status=FiberCircuitStatusChoices.ACTIVE,
            strand_count=12,
            cid="CARRIER-12345",
            description="Downtown to Central ribbon",
        )
        assert circuit.cid == "CARRIER-12345"
        assert circuit.description == "Downtown to Central ribbon"

    def test_get_absolute_url(self):
        circuit = FiberCircuit.objects.create(
            name="URL-Test",
            status=FiberCircuitStatusChoices.PLANNED,
            strand_count=1,
        )
        assert "/fiber-circuits/" in circuit.get_absolute_url()

    def test_default_status(self):
        circuit = FiberCircuit.objects.create(
            name="Default-Status",
            strand_count=2,
        )
        assert circuit.status == FiberCircuitStatusChoices.PLANNED
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_circuits.py::TestFiberCircuit -v
```

Expected: ImportError — `FiberCircuit` not found.

- [ ] **Step 3: Implement FiberCircuit model**

Add to `netbox_fms/models.py` (after the ClosureCableEntry model, replacing the FiberPathLoss section):

```python
# ---------------------------------------------------------------------------
# Fiber circuits
# ---------------------------------------------------------------------------


class FiberCircuit(NetBoxModel):
    """End-to-end logical fiber service with one or more parallel strand paths."""

    name = models.CharField(max_length=200, verbose_name=_("name"))
    cid = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("circuit ID"),
        help_text=_("External circuit identifier"),
    )
    status = models.CharField(
        max_length=50,
        choices=FiberCircuitStatusChoices,
        default=FiberCircuitStatusChoices.PLANNED,
        verbose_name=_("status"),
    )
    description = models.TextField(blank=True, verbose_name=_("description"))
    strand_count = models.PositiveIntegerField(verbose_name=_("strand count"))
    tenant = models.ForeignKey(
        to="tenancy.Tenant",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="fiber_circuits",
        verbose_name=_("tenant"),
    )
    comments = models.TextField(blank=True, verbose_name=_("comments"))

    class Meta:
        ordering = ("name",)
        verbose_name = _("fiber circuit")
        verbose_name_plural = _("fiber circuits")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_fms:fibercircuit", args=[self.pk])
```

Add `"FiberCircuit"` to `__all__`. Add `FiberCircuitStatusChoices` to the choices import.

- [ ] **Step 4: Generate and apply migration**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py makemigrations netbox_fms
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py migrate
```

- [ ] **Step 5: Run tests**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_circuits.py::TestFiberCircuit -v
```

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add netbox_fms/models.py netbox_fms/migrations/ tests/test_fiber_circuits.py && git commit -m "feat: add FiberCircuit model"
```

---

## Task 4: Add FiberCircuitPath model

**Files:**
- Modify: `netbox_fms/models.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_fiber_circuits.py`:

```python
from dcim.models import Cable, Device, DeviceRole, DeviceType, FrontPort, Manufacturer, Module, ModuleBay, ModuleType, Site
from netbox_fms.models import FiberCircuit, FiberCircuitPath
from netbox_fms.choices import FiberCircuitStatusChoices
from django.core.exceptions import ValidationError
from django.db import IntegrityError


class TestFiberCircuitPath(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.circuit = FiberCircuit.objects.create(
            name="Path-Test",
            status=FiberCircuitStatusChoices.ACTIVE,
            strand_count=2,
        )
        site = Site.objects.create(name="Path Site", slug="path-site")
        mfr = Manufacturer.objects.create(name="Path Mfr", slug="path-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="PathDev", slug="pathdev")
        role = DeviceRole.objects.create(name="Path Role", slug="path-role")
        device = Device.objects.create(name="PathDev-1", site=site, device_type=dt, role=role)
        mt = ModuleType.objects.create(manufacturer=mfr, model="PathTray")
        bay = ModuleBay.objects.create(device=device, name="Bay1")
        tray = Module.objects.create(device=device, module_bay=bay, module_type=mt)
        cls.fp_a = FrontPort.objects.create(device=device, module=tray, name="PA1", type="lc")
        cls.fp_b = FrontPort.objects.create(device=device, module=tray, name="PA2", type="lc")

    def test_create_path(self):
        path = FiberCircuitPath.objects.create(
            circuit=self.circuit,
            position=1,
            origin=self.fp_a,
            destination=self.fp_b,
            path=[],
            is_complete=True,
        )
        assert path.pk is not None

    def test_unique_position_per_circuit(self):
        FiberCircuitPath.objects.create(
            circuit=self.circuit,
            position=1,
            origin=self.fp_a,
            path=[],
            is_complete=False,
        )
        with self.assertRaises(IntegrityError):
            FiberCircuitPath.objects.create(
                circuit=self.circuit,
                position=1,
                origin=self.fp_b,
                path=[],
                is_complete=False,
            )

    def test_destination_nullable(self):
        path = FiberCircuitPath.objects.create(
            circuit=self.circuit,
            position=1,
            origin=self.fp_a,
            path=[],
            is_complete=False,
        )
        assert path.destination is None

    def test_loss_fields_nullable(self):
        path = FiberCircuitPath.objects.create(
            circuit=self.circuit,
            position=1,
            origin=self.fp_a,
            path=[],
            is_complete=False,
        )
        assert path.calculated_loss_db is None
        assert path.actual_loss_db is None
        assert path.wavelength_nm is None

    def test_wavelength_required_when_loss_set(self):
        path = FiberCircuitPath(
            circuit=self.circuit,
            position=1,
            origin=self.fp_a,
            path=[],
            is_complete=False,
            calculated_loss_db=3.5,
            wavelength_nm=None,
        )
        with self.assertRaises(ValidationError):
            path.full_clean()

    def test_strand_count_validation(self):
        """Cannot add more paths than strand_count."""
        circuit = FiberCircuit.objects.create(
            name="Small-Circuit",
            status=FiberCircuitStatusChoices.PLANNED,
            strand_count=1,
        )
        FiberCircuitPath.objects.create(
            circuit=circuit, position=1, origin=self.fp_a, path=[], is_complete=False,
        )
        path2 = FiberCircuitPath(
            circuit=circuit, position=2, origin=self.fp_b, path=[], is_complete=False,
        )
        with self.assertRaises(ValidationError):
            path2.full_clean()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_circuits.py::TestFiberCircuitPath -v
```

Expected: ImportError — `FiberCircuitPath` not found.

- [ ] **Step 3: Implement FiberCircuitPath model**

Add to `netbox_fms/models.py` after FiberCircuit:

```python
class FiberCircuitPath(NetBoxModel):
    """One strand's end-to-end journey through cables and splices."""

    circuit = models.ForeignKey(
        to="netbox_fms.FiberCircuit",
        on_delete=models.CASCADE,
        related_name="paths",
        verbose_name=_("circuit"),
    )
    position = models.PositiveIntegerField(verbose_name=_("position"))
    origin = models.ForeignKey(
        to="dcim.FrontPort",
        on_delete=models.PROTECT,
        related_name="fiber_circuit_path_origins",
        verbose_name=_("origin"),
    )
    destination = models.ForeignKey(
        to="dcim.FrontPort",
        on_delete=models.SET_NULL,
        related_name="fiber_circuit_path_destinations",
        blank=True,
        null=True,
        verbose_name=_("destination"),
    )
    path = models.JSONField(default=list, verbose_name=_("path"))
    is_complete = models.BooleanField(default=False, verbose_name=_("complete"))
    calculated_loss_db = models.DecimalField(
        verbose_name=_("calculated loss (dB)"),
        max_digits=6,
        decimal_places=3,
        blank=True,
        null=True,
    )
    actual_loss_db = models.DecimalField(
        verbose_name=_("actual loss (dB)"),
        max_digits=6,
        decimal_places=3,
        blank=True,
        null=True,
    )
    wavelength_nm = models.PositiveIntegerField(
        verbose_name=_("wavelength (nm)"),
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ("circuit", "position")
        unique_together = (("circuit", "position"),)
        verbose_name = _("fiber circuit path")
        verbose_name_plural = _("fiber circuit paths")

    def __str__(self):
        dest = self.destination or "incomplete"
        return f"{self.circuit} path {self.position}: {self.origin} → {dest}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_fms:fibercircuitpath", args=[self.pk])

    def clean(self):
        super().clean()
        # Wavelength required when loss is set
        if (self.calculated_loss_db is not None or self.actual_loss_db is not None) and self.wavelength_nm is None:
            raise ValidationError({"wavelength_nm": _("Wavelength is required when loss values are set.")})
        # Cannot exceed strand_count
        if self.circuit_id:
            existing = self.circuit.paths.exclude(pk=self.pk).count()
            if existing >= self.circuit.strand_count:
                raise ValidationError(
                    _("Cannot add more paths than the circuit's strand count (%(count)s)."),
                    params={"count": self.circuit.strand_count},
                )
```

Add `"FiberCircuitPath"` to `__all__`.

- [ ] **Step 4: Generate and apply migration**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py makemigrations netbox_fms
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py migrate
```

- [ ] **Step 5: Run tests**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_circuits.py::TestFiberCircuitPath -v
```

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add netbox_fms/models.py netbox_fms/migrations/ tests/test_fiber_circuits.py && git commit -m "feat: add FiberCircuitPath model with loss fields and validation"
```

---

## Task 5: Add FiberCircuitNode model

**Files:**
- Modify: `netbox_fms/models.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_fiber_circuit_protection.py`:

```python
from dcim.models import Cable, Device, DeviceRole, DeviceType, FrontPort, Manufacturer, Module, ModuleBay, ModuleType, RearPort, Site
from django.db import IntegrityError, models
from django.test import TestCase

from netbox_fms.choices import FiberCircuitStatusChoices
from netbox_fms.models import FiberCircuit, FiberCircuitNode, FiberCircuitPath


class TestFiberCircuitNode(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Node Site", slug="node-site")
        mfr = Manufacturer.objects.create(name="Node Mfr", slug="node-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="NodeDev", slug="nodedev")
        role = DeviceRole.objects.create(name="Node Role", slug="node-role")
        device = Device.objects.create(name="NodeDev-1", site=site, device_type=dt, role=role)
        mt = ModuleType.objects.create(manufacturer=mfr, model="NodeTray")
        bay = ModuleBay.objects.create(device=device, name="Bay1")
        tray = Module.objects.create(device=device, module_bay=bay, module_type=mt)
        cls.fp = FrontPort.objects.create(device=device, module=tray, name="NF1", type="lc")
        cls.cable = Cable.objects.create()
        cls.circuit = FiberCircuit.objects.create(
            name="Node-Test", status=FiberCircuitStatusChoices.ACTIVE, strand_count=1,
        )
        cls.path = FiberCircuitPath.objects.create(
            circuit=cls.circuit, position=1, origin=cls.fp, path=[], is_complete=False,
        )

    def test_create_cable_node(self):
        node = FiberCircuitNode.objects.create(
            path=self.path, position=1, cable=self.cable,
        )
        assert node.pk is not None

    def test_create_front_port_node(self):
        node = FiberCircuitNode.objects.create(
            path=self.path, position=2, front_port=self.fp,
        )
        assert node.pk is not None

    def test_unique_position_per_path(self):
        FiberCircuitNode.objects.create(path=self.path, position=1, cable=self.cable)
        with self.assertRaises(IntegrityError):
            FiberCircuitNode.objects.create(path=self.path, position=1, front_port=self.fp)

    def test_protect_cable_deletion(self):
        """Cable referenced by node cannot be deleted."""
        cable = Cable.objects.create()
        node = FiberCircuitNode.objects.create(path=self.path, position=10, cable=cable)
        with self.assertRaises(models.ProtectedError):
            cable.delete()

    def test_protect_front_port_deletion(self):
        """FrontPort referenced by node cannot be deleted."""
        site = Site.objects.create(name="FP Prot Site", slug="fp-prot-site")
        mfr = Manufacturer.objects.create(name="FP Prot Mfr", slug="fp-prot-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="FPProtDev", slug="fpprotdev")
        role = DeviceRole.objects.create(name="FP Prot Role", slug="fp-prot-role")
        dev = Device.objects.create(name="FPProtDev-1", site=site, device_type=dt, role=role)
        fp = FrontPort.objects.create(device=dev, name="ProtFP", type="lc")
        FiberCircuitNode.objects.create(path=self.path, position=11, front_port=fp)
        with self.assertRaises(models.ProtectedError):
            fp.delete()

    def test_cascade_on_path_delete(self):
        """Nodes are deleted when path is deleted."""
        circuit = FiberCircuit.objects.create(
            name="Cascade-Test", status=FiberCircuitStatusChoices.ACTIVE, strand_count=1,
        )
        path = FiberCircuitPath.objects.create(
            circuit=circuit, position=1, origin=self.fp, path=[], is_complete=False,
        )
        cable = Cable.objects.create()
        FiberCircuitNode.objects.create(path=path, position=1, cable=cable)
        assert FiberCircuitNode.objects.filter(path=path).count() == 1
        path.delete()
        assert FiberCircuitNode.objects.filter(path=path).count() == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_circuit_protection.py -v
```

Expected: ImportError — `FiberCircuitNode` not found.

- [ ] **Step 3: Implement FiberCircuitNode model**

Add to `netbox_fms/models.py` after FiberCircuitPath:

```python
class FiberCircuitNode(models.Model):
    """Relational index of objects in a fiber circuit path for PROTECT-based deletion prevention."""

    path = models.ForeignKey(
        to="netbox_fms.FiberCircuitPath",
        on_delete=models.CASCADE,
        related_name="nodes",
        verbose_name=_("path"),
    )
    position = models.PositiveIntegerField(verbose_name=_("position"))
    cable = models.ForeignKey(
        to="dcim.Cable",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="fiber_circuit_nodes",
        verbose_name=_("cable"),
    )
    front_port = models.ForeignKey(
        to="dcim.FrontPort",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="fiber_circuit_nodes",
        verbose_name=_("front port"),
    )
    rear_port = models.ForeignKey(
        to="dcim.RearPort",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="fiber_circuit_nodes",
        verbose_name=_("rear port"),
    )
    fiber_strand = models.ForeignKey(
        to="netbox_fms.FiberStrand",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="fiber_circuit_nodes",
        verbose_name=_("fiber strand"),
    )
    splice_entry = models.ForeignKey(
        to="netbox_fms.SplicePlanEntry",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="fiber_circuit_nodes",
        verbose_name=_("splice entry"),
    )

    class Meta:
        ordering = ("path", "position")
        unique_together = (("path", "position"),)
        verbose_name = _("fiber circuit node")
        verbose_name_plural = _("fiber circuit nodes")
        constraints = [
            models.CheckConstraint(
                name="fibercircuitnode_exactly_one_ref",
                check=(
                    models.Q(cable__isnull=False, front_port__isnull=True, rear_port__isnull=True, fiber_strand__isnull=True, splice_entry__isnull=True)
                    | models.Q(cable__isnull=True, front_port__isnull=False, rear_port__isnull=True, fiber_strand__isnull=True, splice_entry__isnull=True)
                    | models.Q(cable__isnull=True, front_port__isnull=True, rear_port__isnull=False, fiber_strand__isnull=True, splice_entry__isnull=True)
                    | models.Q(cable__isnull=True, front_port__isnull=True, rear_port__isnull=True, fiber_strand__isnull=False, splice_entry__isnull=True)
                    | models.Q(cable__isnull=True, front_port__isnull=True, rear_port__isnull=True, fiber_strand__isnull=True, splice_entry__isnull=False)
                ),
            ),
        ]

    def __str__(self):
        for field in ("cable", "front_port", "rear_port", "fiber_strand", "splice_entry"):
            obj = getattr(self, field)
            if obj is not None:
                return f"{field}: {obj}"
        return f"node #{self.position}"
```

Note: `FiberCircuitNode` inherits from `models.Model` (not `NetBoxModel`) — it is an internal index, not a user-facing NetBox object.

Add `"FiberCircuitNode"` to `__all__`.

- [ ] **Step 4: Generate and apply migration**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py makemigrations netbox_fms
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py migrate
```

- [ ] **Step 5: Run tests**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_circuit_protection.py -v
```

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add netbox_fms/models.py netbox_fms/migrations/ tests/test_fiber_circuit_protection.py && git commit -m "feat: add FiberCircuitNode model with PROTECT FKs and CheckConstraint"
```

---

## Task 6: Add FiberCircuit status lifecycle (node management)

When circuit status changes, nodes must be created or deleted accordingly.

**Files:**
- Modify: `netbox_fms/models.py` (FiberCircuit.save override)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_fiber_circuit_protection.py`:

```python
class TestFiberCircuitLifecycle(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="LC Site", slug="lc-site")
        mfr = Manufacturer.objects.create(name="LC Mfr", slug="lc-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="LCDev", slug="lcdev")
        role = DeviceRole.objects.create(name="LC Role", slug="lc-role")
        device = Device.objects.create(name="LCDev-1", site=site, device_type=dt, role=role)
        cls.fp = FrontPort.objects.create(device=device, name="LF1", type="lc")
        cls.cable = Cable.objects.create()

    def test_decommission_deletes_nodes(self):
        circuit = FiberCircuit.objects.create(
            name="Decomm-Test", status=FiberCircuitStatusChoices.ACTIVE, strand_count=1,
        )
        path = FiberCircuitPath.objects.create(
            circuit=circuit, position=1, origin=self.fp,
            path=[{"type": "cable", "id": self.cable.pk}],
            is_complete=False,
        )
        FiberCircuitNode.objects.create(path=path, position=1, cable=self.cable)
        assert FiberCircuitNode.objects.filter(path=path).count() == 1

        circuit.status = FiberCircuitStatusChoices.DECOMMISSIONED
        circuit.save()

        assert FiberCircuitNode.objects.filter(path=path).count() == 0

    def test_reactivate_rebuilds_nodes(self):
        circuit = FiberCircuit.objects.create(
            name="Reactivate-Test", status=FiberCircuitStatusChoices.DECOMMISSIONED, strand_count=1,
        )
        path = FiberCircuitPath.objects.create(
            circuit=circuit, position=1, origin=self.fp,
            path=[{"type": "cable", "id": self.cable.pk}],
            is_complete=False,
        )
        assert FiberCircuitNode.objects.filter(path=path).count() == 0

        circuit.status = FiberCircuitStatusChoices.ACTIVE
        circuit.save()

        assert FiberCircuitNode.objects.filter(path=path).count() == 1
        node = FiberCircuitNode.objects.get(path=path)
        assert node.cable_id == self.cable.pk
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_circuit_protection.py::TestFiberCircuitLifecycle -v
```

Expected: Fails — nodes not deleted/rebuilt on status change.

- [ ] **Step 3: Implement lifecycle in FiberCircuit.save()**

Add to `FiberCircuit`:

```python
def save(self, *args, **kwargs):
    is_new = self.pk is None
    old_status = None
    if not is_new:
        old_status = FiberCircuit.objects.filter(pk=self.pk).values_list("status", flat=True).first()
    super().save(*args, **kwargs)
    if not is_new and old_status != self.status:
        if self.status == FiberCircuitStatusChoices.DECOMMISSIONED:
            # Delete all nodes for all paths
            FiberCircuitNode.objects.filter(path__circuit=self).delete()
        elif old_status == FiberCircuitStatusChoices.DECOMMISSIONED:
            # Rebuild nodes for all paths
            for path in self.paths.all():
                path.rebuild_nodes()
```

Also add `rebuild_nodes()` to `FiberCircuitPath`:

```python
def rebuild_nodes(self):
    """Walk self.path JSON and create FiberCircuitNode rows."""
    from django.db.models import Q
    self.nodes.all().delete()
    position = 1
    for entry in self.path:
        node_type = entry["type"]
        obj_id = entry["id"]
        kwargs = {"path": self, "position": position}
        if node_type == "cable":
            kwargs["cable_id"] = obj_id
        elif node_type == "front_port":
            kwargs["front_port_id"] = obj_id
            # Also protect the FiberStrand associated with this FrontPort
        elif node_type == "rear_port":
            kwargs["rear_port_id"] = obj_id
        elif node_type == "splice_entry":
            kwargs["splice_entry_id"] = obj_id
        FiberCircuitNode.objects.create(**kwargs)
        position += 1
    # Derive fiber_strand nodes from FrontPort pairs
    self._create_strand_nodes(position)

def _create_strand_nodes(self, start_position):
    """Create FiberCircuitNode entries for FiberStrands derived from path FrontPorts."""
    from django.db.models import Q
    fp_ids = [e["id"] for e in self.path if e["type"] == "front_port"]
    strands = FiberStrand.objects.filter(
        Q(front_port_a_id__in=fp_ids) | Q(front_port_b_id__in=fp_ids)
    ).distinct()
    pos = start_position
    for strand in strands:
        FiberCircuitNode.objects.create(
            path=self, position=pos, fiber_strand=strand,
        )
        pos += 1
```

- [ ] **Step 4: Run tests**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_circuit_protection.py -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/models.py tests/test_fiber_circuit_protection.py && git commit -m "feat: add FiberCircuit status lifecycle — node create/delete on status change"
```

---

## Task 7: Implement trace engine

**Files:**
- Create: `netbox_fms/trace.py`
- Modify: `netbox_fms/models.py` (add `from_origin` classmethod)

- [ ] **Step 1: Write failing tests**

Create `tests/test_fiber_circuit_trace.py`:

```python
"""Tests for the fiber circuit trace engine.

These tests create realistic cable/port/splice topologies and verify
that FiberCircuitPath.from_origin() correctly traces through them.

Topology for multi-hop test:
    Closure A                     Closure B                     Closure C
    [FP:a1] → [RP:a1] --Cable1-- [RP:b1] → [FP:b1]
                                  [FP:b1] ==splice== [FP:b2]
                                  [FP:b2] → [RP:b2] --Cable2-- [RP:c1] → [FP:c1]
"""
from dcim.models import (
    Cable, CableTermination, Device, DeviceRole, DeviceType,
    FrontPort, Manufacturer, Module, ModuleBay, ModuleType,
    PortMapping, RearPort, Site,
)
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from netbox_fms.choices import FiberCircuitStatusChoices, SplicePlanStatusChoices
from netbox_fms.models import FiberCircuit, FiberCircuitPath, SplicePlan, SplicePlanEntry


def _make_closure(site, mfr, name):
    """Create a Device with a tray module for testing."""
    dt, _ = DeviceType.objects.get_or_create(manufacturer=mfr, model=f"{name}-Type", slug=f"{name}-type".lower())
    role, _ = DeviceRole.objects.get_or_create(name=f"{name}-Role", slug=f"{name}-role".lower())
    device = Device.objects.create(name=name, site=site, device_type=dt, role=role)
    mt, _ = ModuleType.objects.get_or_create(manufacturer=mfr, model=f"{name}-Tray")
    bay = ModuleBay.objects.create(device=device, name="Bay1")
    tray = Module.objects.create(device=device, module_bay=bay, module_type=mt)
    return device, tray


def _connect_cable(cable, rear_port_a, rear_port_b):
    """Create CableTerminations connecting two RearPorts via a Cable."""
    rp_ct = ContentType.objects.get_for_model(RearPort)
    CableTermination.objects.create(
        cable=cable, cable_end="A", termination_type=rp_ct, termination_id=rear_port_a.pk,
    )
    CableTermination.objects.create(
        cable=cable, cable_end="B", termination_type=rp_ct, termination_id=rear_port_b.pk,
    )


def _make_splice(fp_a, fp_b):
    """Create a 0-length cable between two FrontPorts (splice)."""
    cable = Cable.objects.create(length=0, length_unit="m")
    fp_ct = ContentType.objects.get_for_model(FrontPort)
    CableTermination.objects.create(
        cable=cable, cable_end="A", termination_type=fp_ct, termination_id=fp_a.pk,
    )
    CableTermination.objects.create(
        cable=cable, cable_end="B", termination_type=fp_ct, termination_id=fp_b.pk,
    )
    return cable


class TestTraceSingleCable(TestCase):
    """Trace through a single cable: FP → RP → Cable → RP → FP."""

    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Trace1 Site", slug="trace1-site")
        mfr = Manufacturer.objects.create(name="Trace1 Mfr", slug="trace1-mfr")

        cls.dev_a, cls.tray_a = _make_closure(site, mfr, "ClosureA")
        cls.dev_b, cls.tray_b = _make_closure(site, mfr, "ClosureB")

        # Create rear ports, front ports, and port mappings
        # NetBox 4.5+: FrontPort has no rear_port FK — use PortMapping model
        cls.rp_a = RearPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="RP-A1", type="lc", positions=1)
        cls.fp_a = FrontPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="FP-A1", type="lc")
        PortMapping.objects.create(device=cls.dev_a, front_port=cls.fp_a, rear_port=cls.rp_a, front_port_position=1, rear_port_position=1)

        cls.rp_b = RearPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="RP-B1", type="lc", positions=1)
        cls.fp_b = FrontPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="FP-B1", type="lc")
        PortMapping.objects.create(device=cls.dev_b, front_port=cls.fp_b, rear_port=cls.rp_b, front_port_position=1, rear_port_position=1)

        # Connect cable between rear ports
        cls.cable = Cable.objects.create()
        _connect_cable(cls.cable, cls.rp_a, cls.rp_b)

    def test_single_cable_trace(self):
        result = FiberCircuitPath.from_origin(self.fp_a)
        assert result.origin == self.fp_a
        assert result.destination == self.fp_b
        assert result.is_complete is True
        assert len(result.path) == 5  # FP, RP, Cable, RP, FP

    def test_path_json_format(self):
        result = FiberCircuitPath.from_origin(self.fp_a)
        assert result.path[0] == {"type": "front_port", "id": self.fp_a.pk}
        assert result.path[1] == {"type": "rear_port", "id": self.rp_a.pk}
        assert result.path[2] == {"type": "cable", "id": self.cable.pk}
        assert result.path[3] == {"type": "rear_port", "id": self.rp_b.pk}
        assert result.path[4] == {"type": "front_port", "id": self.fp_b.pk}


class TestTraceMultiHop(TestCase):
    """Trace through 2 cables with a splice at the intermediate closure."""

    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Trace2 Site", slug="trace2-site")
        mfr = Manufacturer.objects.create(name="Trace2 Mfr", slug="trace2-mfr")

        cls.dev_a, cls.tray_a = _make_closure(site, mfr, "MH-ClosA")
        cls.dev_b, cls.tray_b = _make_closure(site, mfr, "MH-ClosB")
        cls.dev_c, cls.tray_c = _make_closure(site, mfr, "MH-ClosC")

        # Closure A: FP → RP (via PortMapping)
        cls.rp_a = RearPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="RP-A", type="lc", positions=1)
        cls.fp_a = FrontPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="FP-A", type="lc")
        PortMapping.objects.create(device=cls.dev_a, front_port=cls.fp_a, rear_port=cls.rp_a, front_port_position=1, rear_port_position=1)

        # Closure B: ingress RP → FP, egress FP → RP (via PortMapping)
        cls.rp_b1 = RearPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="RP-B1", type="lc", positions=1)
        cls.fp_b1 = FrontPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="FP-B1", type="lc")
        PortMapping.objects.create(device=cls.dev_b, front_port=cls.fp_b1, rear_port=cls.rp_b1, front_port_position=1, rear_port_position=1)
        cls.rp_b2 = RearPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="RP-B2", type="lc", positions=1)
        cls.fp_b2 = FrontPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="FP-B2", type="lc")
        PortMapping.objects.create(device=cls.dev_b, front_port=cls.fp_b2, rear_port=cls.rp_b2, front_port_position=1, rear_port_position=1)

        # Closure C: RP → FP (via PortMapping)
        cls.rp_c = RearPort.objects.create(device=cls.dev_c, module=cls.tray_c, name="RP-C", type="lc", positions=1)
        cls.fp_c = FrontPort.objects.create(device=cls.dev_c, module=cls.tray_c, name="FP-C", type="lc")
        PortMapping.objects.create(device=cls.dev_c, front_port=cls.fp_c, rear_port=cls.rp_c, front_port_position=1, rear_port_position=1)

        # Cable 1: A → B
        cls.cable1 = Cable.objects.create()
        _connect_cable(cls.cable1, cls.rp_a, cls.rp_b1)

        # Splice at B: FP-B1 → FP-B2
        cls.splice_cable = _make_splice(cls.fp_b1, cls.fp_b2)

        # Create SplicePlanEntry for the splice
        cls.plan_b = SplicePlan.objects.create(closure=cls.dev_b, name="Plan-B", status=SplicePlanStatusChoices.APPLIED)
        cls.splice_entry = SplicePlanEntry.objects.create(
            plan=cls.plan_b, tray=cls.tray_b, fiber_a=cls.fp_b1, fiber_b=cls.fp_b2,
        )

        # Cable 2: B → C
        cls.cable2 = Cable.objects.create()
        _connect_cable(cls.cable2, cls.rp_b2, cls.rp_c)

    def test_multi_hop_trace(self):
        result = FiberCircuitPath.from_origin(self.fp_a)
        assert result.origin == self.fp_a
        assert result.destination == self.fp_c
        assert result.is_complete is True

    def test_multi_hop_path_length(self):
        result = FiberCircuitPath.from_origin(self.fp_a)
        # FP, RP, Cable, RP, FP, Splice, FP, RP, Cable, RP, FP = 11
        assert len(result.path) == 11

    def test_splice_in_path(self):
        result = FiberCircuitPath.from_origin(self.fp_a)
        splice_entries = [e for e in result.path if e["type"] == "splice_entry"]
        assert len(splice_entries) == 1
        assert splice_entries[0]["id"] == self.splice_entry.pk


class TestTraceIncomplete(TestCase):
    """Trace that terminates at a FrontPort with no outgoing splice."""

    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Trace3 Site", slug="trace3-site")
        mfr = Manufacturer.objects.create(name="Trace3 Mfr", slug="trace3-mfr")

        cls.dev_a, cls.tray_a = _make_closure(site, mfr, "IC-ClosA")
        cls.dev_b, cls.tray_b = _make_closure(site, mfr, "IC-ClosB")

        # Closure A
        cls.rp_a = RearPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="RP-A", type="lc", positions=1)
        cls.fp_a = FrontPort.objects.create(device=cls.dev_a, module=cls.tray_a, name="FP-A", type="lc")
        PortMapping.objects.create(device=cls.dev_a, front_port=cls.fp_a, rear_port=cls.rp_a, front_port_position=1, rear_port_position=1)

        # Closure B — has ingress port but no egress (no splice out)
        cls.rp_b = RearPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="RP-B", type="lc", positions=1)
        cls.fp_b = FrontPort.objects.create(device=cls.dev_b, module=cls.tray_b, name="FP-B", type="lc")
        PortMapping.objects.create(device=cls.dev_b, front_port=cls.fp_b, rear_port=cls.rp_b, front_port_position=1, rear_port_position=1)

        cls.cable = Cable.objects.create()
        _connect_cable(cls.cable, cls.rp_a, cls.rp_b)

    def test_trace_terminates_with_no_splice(self):
        """Path through cable ends at FP-B with no splice — still complete (terminal port)."""
        result = FiberCircuitPath.from_origin(self.fp_a)
        assert result.destination == self.fp_b
        assert result.is_complete is True

    def test_no_port_mapping_incomplete(self):
        """FrontPort with no RearPort mapping → path cannot continue."""
        site = Site.objects.create(name="NoMap Site", slug="nomap-site")
        mfr = Manufacturer.objects.create(name="NoMap Mfr", slug="nomap-mfr")
        dev, tray = _make_closure(site, mfr, "NoMap")
        fp = FrontPort.objects.create(device=dev, module=tray, name="OrphanFP", type="lc")
        # No rear_port set — trace should handle gracefully
        result = FiberCircuitPath.from_origin(fp)
        assert result.is_complete is False
        assert len(result.path) == 1  # Just the origin FP
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_circuit_trace.py -v
```

Expected: Fails — `from_origin` not implemented.

- [ ] **Step 3: Implement trace engine**

Create `netbox_fms/trace.py`:

```python
"""Fiber circuit path trace engine.

Adapted from NetBox's CablePath.from_origin(), stripped of wireless/power/circuit
logic, accepting FrontPort as origin instead of requiring PathEndpoint.

IMPORTANT: NetBox 4.5+ uses the PortMapping model to link FrontPort ↔ RearPort.
FrontPort has NO rear_port or rear_port_position attributes — always query
PortMapping to traverse front-to-rear and rear-to-front.
"""
from dcim.models import CableTermination, FrontPort, PortMapping, RearPort
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from .models import SplicePlanEntry


def trace_fiber_path(origin_front_port):
    """Trace a fiber path starting from a FrontPort.

    Returns a dict with:
        origin: FrontPort
        destination: FrontPort or None
        path: list of {"type": str, "id": int} dicts
        is_complete: bool
    """
    path = []
    current_fp = origin_front_port
    visited_fps = set()
    fp_ct = ContentType.objects.get_for_model(FrontPort)
    rp_ct = ContentType.objects.get_for_model(RearPort)

    while True:
        # Guard against loops
        if current_fp.pk in visited_fps:
            break
        visited_fps.add(current_fp.pk)

        # Step 1: INGRESS — record FrontPort
        path.append({"type": "front_port", "id": current_fp.pk})

        # Follow PortMapping: FrontPort → RearPort
        mapping = PortMapping.objects.filter(
            front_port=current_fp,
        ).select_related("rear_port").first()

        if mapping is None:
            # No port mapping — path cannot continue
            return {
                "origin": origin_front_port,
                "destination": None,
                "path": path,
                "is_complete": False,
            }

        rear_port = mapping.rear_port
        ingress_rp_position = mapping.rear_port_position
        path.append({"type": "rear_port", "id": rear_port.pk})

        # Step 2: CABLE CROSSING — find cable on this RearPort
        term = CableTermination.objects.filter(
            termination_type=rp_ct, termination_id=rear_port.pk,
        ).select_related("cable").first()

        if term is None:
            # No cable attached — path is incomplete
            return {
                "origin": origin_front_port,
                "destination": None,
                "path": path,
                "is_complete": False,
            }

        cable = term.cable
        cable_end = term.cable_end
        path.append({"type": "cable", "id": cable.pk})

        # Find far-end termination
        far_end = "B" if cable_end == "A" else "A"
        far_term = CableTermination.objects.filter(
            cable=cable, cable_end=far_end, termination_type=rp_ct,
        ).first()

        if far_term is None:
            return {
                "origin": origin_front_port,
                "destination": None,
                "path": path,
                "is_complete": False,
            }

        far_rp = RearPort.objects.get(pk=far_term.termination_id)
        path.append({"type": "rear_port", "id": far_rp.pk})

        # Step 3: EGRESS — follow PortMapping: RearPort → FrontPort
        # Match by rear_port_position from the ingress side
        egress_mapping = PortMapping.objects.filter(
            rear_port=far_rp, rear_port_position=ingress_rp_position,
        ).select_related("front_port").first()

        if egress_mapping is None:
            # Try position 1 as fallback (single-position RearPort)
            egress_mapping = PortMapping.objects.filter(
                rear_port=far_rp,
            ).select_related("front_port").first()

        if egress_mapping is None:
            return {
                "origin": origin_front_port,
                "destination": None,
                "path": path,
                "is_complete": False,
            }

        egress_fp = egress_mapping.front_port
        path.append({"type": "front_port", "id": egress_fp.pk})

        # Step 4: SPLICE CHECK — does this FrontPort have a 0-length cable to another FrontPort?
        splice_term = CableTermination.objects.filter(
            termination_type=fp_ct, termination_id=egress_fp.pk,
        ).select_related("cable").first()

        if splice_term is None:
            # No splice — path terminates here (complete)
            return {
                "origin": origin_front_port,
                "destination": egress_fp,
                "path": path,
                "is_complete": True,
            }

        splice_cable = splice_term.cable
        splice_end = splice_term.cable_end
        far_splice_end = "B" if splice_end == "A" else "A"

        far_splice_term = CableTermination.objects.filter(
            cable=splice_cable, cable_end=far_splice_end, termination_type=fp_ct,
        ).first()

        if far_splice_term is None:
            return {
                "origin": origin_front_port,
                "destination": egress_fp,
                "path": path,
                "is_complete": True,
            }

        next_fp = FrontPort.objects.get(pk=far_splice_term.termination_id)

        # Find SplicePlanEntry for this splice
        splice_entry = SplicePlanEntry.objects.filter(
            Q(fiber_a=egress_fp, fiber_b=next_fp) | Q(fiber_a=next_fp, fiber_b=egress_fp)
        ).first()

        if splice_entry:
            path.append({"type": "splice_entry", "id": splice_entry.pk})
        # If no SplicePlanEntry exists (bare cable), still continue but don't record splice_entry

        current_fp = next_fp

    # Loop guard exit
    return {
        "origin": origin_front_port,
        "destination": None,
        "path": path,
        "is_complete": False,
    }
```

Add `from_origin` classmethod and `retrace()` instance method to `FiberCircuitPath` in `models.py`:

```python
@classmethod
def from_origin(cls, front_port):
    """Trace a fiber path from a FrontPort and return an unsaved FiberCircuitPath."""
    from .trace import trace_fiber_path
    result = trace_fiber_path(front_port)
    return cls(
        origin=result["origin"],
        destination=result["destination"],
        path=result["path"],
        is_complete=result["is_complete"],
    )

def retrace(self):
    """Re-trace from origin, update path JSON, and atomically rebuild nodes.

    For decommissioned circuits, updates the JSON path but does not create nodes,
    preserving the lifecycle invariant.
    """
    from .trace import trace_fiber_path
    result = trace_fiber_path(self.origin)
    self.destination = result["destination"]
    self.path = result["path"]
    self.is_complete = result["is_complete"]
    self.save()
    if self.circuit.status != FiberCircuitStatusChoices.DECOMMISSIONED:
        self.rebuild_nodes()
    else:
        self.nodes.all().delete()
```

- [ ] **Step 4: Run tests**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_circuit_trace.py -v
```

Expected: All pass. Debug and fix any issues with PortMapping/CableTermination queries.

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/trace.py netbox_fms/models.py tests/test_fiber_circuit_trace.py && git commit -m "feat: implement fiber circuit trace engine with from_origin() classmethod"
```

---

## Task 8: Add FiberCircuit CRUD stack (forms, filters, tables, views, urls, templates)

**Files:**
- Modify: `netbox_fms/forms.py`
- Modify: `netbox_fms/filters.py`
- Modify: `netbox_fms/tables.py`
- Modify: `netbox_fms/views.py`
- Modify: `netbox_fms/urls.py`
- Create: `netbox_fms/templates/netbox_fms/fibercircuit.html`

- [ ] **Step 1: Add forms**

Add to `netbox_fms/forms.py`:

```python
# --- FiberCircuit ---

class FiberCircuitForm(NetBoxModelForm):
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)
    comments = CommentField()

    fieldsets = (
        FieldSet("name", "cid", "status", "strand_count", "tenant", name=_("Circuit")),
        FieldSet("description", "comments", "tags", name=_("Additional")),
    )

    class Meta:
        model = FiberCircuit
        fields = ("name", "cid", "status", "strand_count", "tenant", "description", "comments", "tags")


class FiberCircuitImportForm(NetBoxModelImportForm):
    class Meta:
        model = FiberCircuit
        fields = ("name", "cid", "status", "strand_count", "description", "comments")


class FiberCircuitBulkEditForm(NetBoxModelBulkEditForm):
    model = FiberCircuit
    status = forms.ChoiceField(choices=FiberCircuitStatusChoices, required=False)
    strand_count = forms.IntegerField(required=False)
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)
    description = forms.CharField(required=False)

    fieldsets = (
        FieldSet("status", "strand_count", "tenant", name=_("Circuit")),
        FieldSet("description", name=_("Additional")),
    )
    nullable_fields = ("tenant", "description")


class FiberCircuitFilterForm(NetBoxModelFilterSetForm):
    model = FiberCircuit
    status = forms.MultipleChoiceField(choices=FiberCircuitStatusChoices, required=False)
    tenant_id = DynamicModelMultipleChoiceField(queryset=Tenant.objects.all(), required=False, label=_("Tenant"))

    fieldsets = (FieldSet("q", "status", "tenant_id"),)
```

Import `Tenant` from `tenancy.models` and `FiberCircuitStatusChoices` from choices.

- [ ] **Step 2: Add filters**

Add to `netbox_fms/filters.py`:

```python
class FiberCircuitFilterSet(NetBoxModelFilterSet):
    status = django_filters.MultipleChoiceFilter(choices=FiberCircuitStatusChoices)
    tenant_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Tenant.objects.all(), field_name="tenant", label="Tenant (ID)",
    )

    class Meta:
        model = FiberCircuit
        fields = ("id", "name", "cid", "status", "strand_count", "tenant")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(models.Q(name__icontains=value) | models.Q(cid__icontains=value) | models.Q(description__icontains=value))
```

- [ ] **Step 3: Add tables**

Add to `netbox_fms/tables.py`:

```python
class FiberCircuitTable(NetBoxTable):
    pk = columns.ToggleColumn()
    name = tables.Column(linkify=True)
    cid = tables.Column(verbose_name="Circuit ID")
    status = tables.Column()
    strand_count = tables.Column()
    tenant = tables.Column(linkify=True)
    path_count = tables.Column(verbose_name="Paths", orderable=True)
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = FiberCircuit
        fields = ("pk", "name", "cid", "status", "strand_count", "tenant", "path_count", "actions")
        default_columns = ("name", "cid", "status", "strand_count", "tenant")
```

- [ ] **Step 4: Add views**

Add to `netbox_fms/views.py`:

```python
# --- FiberCircuit ---

class FiberCircuitListView(generic.ObjectListView):
    queryset = FiberCircuit.objects.annotate(path_count=Count("paths"))
    table = FiberCircuitTable
    filterset = FiberCircuitFilterSet
    filterset_form = FiberCircuitFilterForm


class FiberCircuitView(generic.ObjectView):
    queryset = FiberCircuit.objects.all()

    def get_extra_context(self, request, instance):
        paths = instance.paths.all()
        return {"paths": paths}


class FiberCircuitEditView(generic.ObjectEditView):
    queryset = FiberCircuit.objects.all()
    form = FiberCircuitForm


class FiberCircuitDeleteView(generic.ObjectDeleteView):
    queryset = FiberCircuit.objects.all()


class FiberCircuitBulkImportView(generic.BulkImportView):
    queryset = FiberCircuit.objects.all()
    model_form = FiberCircuitImportForm


class FiberCircuitBulkEditView(generic.BulkEditView):
    queryset = FiberCircuit.objects.all()
    filterset = FiberCircuitFilterSet
    table = FiberCircuitTable
    form = FiberCircuitBulkEditForm


class FiberCircuitBulkDeleteView(generic.BulkDeleteView):
    queryset = FiberCircuit.objects.all()
    filterset = FiberCircuitFilterSet
    table = FiberCircuitTable
```

Add `from django.db.models import Count` at the top of views.py.

- [ ] **Step 5: Add URLs**

Add to `netbox_fms/urls.py`:

```python
# Fiber Circuits
path("fiber-circuits/", views.FiberCircuitListView.as_view(), name="fibercircuit_list"),
path("fiber-circuits/add/", views.FiberCircuitEditView.as_view(), name="fibercircuit_add"),
path("fiber-circuits/import/", views.FiberCircuitBulkImportView.as_view(), name="fibercircuit_import"),
path("fiber-circuits/edit/", views.FiberCircuitBulkEditView.as_view(), name="fibercircuit_bulk_edit"),
path("fiber-circuits/delete/", views.FiberCircuitBulkDeleteView.as_view(), name="fibercircuit_bulk_delete"),
path("fiber-circuits/<int:pk>/", include(get_model_urls("netbox_fms", "fibercircuit"))),
path("fiber-circuits/<int:pk>/", views.FiberCircuitView.as_view(), name="fibercircuit"),
path("fiber-circuits/<int:pk>/edit/", views.FiberCircuitEditView.as_view(), name="fibercircuit_edit"),
path("fiber-circuits/<int:pk>/delete/", views.FiberCircuitDeleteView.as_view(), name="fibercircuit_delete"),
```

- [ ] **Step 6: Create detail template**

Create `netbox_fms/templates/netbox_fms/fibercircuit.html` following the existing template pattern (see `fibercable.html` or `spliceplan.html` for reference). Include:
- Overview panel with name, cid, status, strand_count, tenant, description
- Paths table showing all FiberCircuitPaths

- [ ] **Step 7: Update navigation and search**

Add to `netbox_fms/navigation.py` — add a "Fiber Circuits" entry under a new or existing menu group.

Add to `netbox_fms/search.py`:

```python
@register_search
class FiberCircuitIndex(SearchIndex):
    model = FiberCircuit
    fields = (
        ("name", 100),
        ("cid", 80),
        ("description", 500),
    )
    display_attrs = ("status", "strand_count", "cid")
```

- [ ] **Step 8: Verify imports and run tests**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.forms import *; from netbox_fms.filters import *; from netbox_fms.tables import *"
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v
```

Expected: All pass.

- [ ] **Step 9: Commit**

```bash
git add netbox_fms/forms.py netbox_fms/filters.py netbox_fms/tables.py netbox_fms/views.py netbox_fms/urls.py netbox_fms/navigation.py netbox_fms/search.py netbox_fms/templates/netbox_fms/fibercircuit.html && git commit -m "feat: add FiberCircuit CRUD stack — forms, filters, tables, views, URLs, template"
```

---

## Task 9: Add API serializers, viewsets, and router for FiberCircuit

**Files:**
- Modify: `netbox_fms/api/serializers.py`
- Modify: `netbox_fms/api/views.py`
- Modify: `netbox_fms/api/urls.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_fiber_circuit_api.py`:

```python
from dcim.models import Device, DeviceRole, DeviceType, FrontPort, Manufacturer, Module, ModuleBay, ModuleType, Site
from django.test import TestCase
from rest_framework.test import APIClient

from netbox_fms.choices import FiberCircuitStatusChoices
from netbox_fms.models import FiberCircuit, FiberCircuitPath


class TestFiberCircuitAPI(TestCase):
    @classmethod
    def setUpTestData(cls):
        from users.models import Token
        from django.contrib.auth import get_user_model

        User = get_user_model()
        cls.user = User.objects.create_superuser("apitest", "api@test.com", "testpass")
        cls.token = Token.objects.create(user=cls.user)
        cls.client = APIClient()
        cls.client.credentials(HTTP_AUTHORIZATION=f"Token {cls.token.key}")

        cls.circuit = FiberCircuit.objects.create(
            name="API-Test", status=FiberCircuitStatusChoices.ACTIVE, strand_count=2,
        )

    def test_list_circuits(self):
        response = self.client.get("/api/plugins/netbox-fms/fiber-circuits/")
        assert response.status_code == 200
        assert response.data["count"] >= 1

    def test_get_circuit(self):
        response = self.client.get(f"/api/plugins/netbox-fms/fiber-circuits/{self.circuit.pk}/")
        assert response.status_code == 200
        assert response.data["name"] == "API-Test"

    def test_create_circuit(self):
        response = self.client.post("/api/plugins/netbox-fms/fiber-circuits/", {
            "name": "API-Create",
            "status": "planned",
            "strand_count": 4,
        })
        assert response.status_code == 201
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_circuit_api.py -v
```

Expected: 404 — endpoint not registered.

- [ ] **Step 3: Implement serializers**

Add to `netbox_fms/api/serializers.py`:

```python
class FiberCircuitSerializer(NetBoxModelSerializer):
    class Meta:
        model = FiberCircuit
        fields = (
            "id", "url", "display",
            "name", "cid", "status", "description", "strand_count", "tenant", "comments",
            "tags", "custom_fields", "created", "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "cid", "status")


class FiberCircuitPathSerializer(NetBoxModelSerializer):
    class Meta:
        model = FiberCircuitPath
        fields = (
            "id", "url", "display",
            "circuit", "position", "origin", "destination",
            "path", "is_complete",
            "calculated_loss_db", "actual_loss_db", "wavelength_nm",
            "tags", "custom_fields", "created", "last_updated",
        )
        brief_fields = ("id", "url", "display", "position", "is_complete")


class FiberCircuitNodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = FiberCircuitNode
        fields = (
            "id", "path", "position",
            "cable", "front_port", "rear_port", "fiber_strand", "splice_entry",
        )
        read_only_fields = fields
```

- [ ] **Step 4: Implement viewsets**

Add to `netbox_fms/api/views.py`:

```python
class FiberCircuitViewSet(NetBoxModelViewSet):
    queryset = FiberCircuit.objects.prefetch_related("paths", "tags")
    serializer_class = FiberCircuitSerializer
    filterset_class = FiberCircuitFilterSet


class FiberCircuitPathViewSet(NetBoxModelViewSet):
    queryset = FiberCircuitPath.objects.prefetch_related("tags")
    serializer_class = FiberCircuitPathSerializer


class FiberCircuitNodeViewSet(ModelViewSet):
    queryset = FiberCircuitNode.objects.all()
    serializer_class = FiberCircuitNodeSerializer
    http_method_names = ["get", "head", "options"]  # Read-only
```

Note: `FiberCircuitNodeViewSet` uses DRF's `ModelViewSet` (not `NetBoxModelViewSet`) since it's a plain `models.Model`. Add `from rest_framework.viewsets import ModelViewSet` to imports.

Also add a `retrace` action to `FiberCircuitViewSet`:

```python
from rest_framework.decorators import action

class FiberCircuitViewSet(NetBoxModelViewSet):
    # ... existing code ...

    @action(detail=True, methods=["post"])
    def retrace(self, request, pk=None):
        """Re-trace all paths and rebuild nodes atomically."""
        circuit = self.get_object()
        for path in circuit.paths.all():
            path.retrace()
        serializer = self.get_serializer(circuit)
        return Response(serializer.data)
```

- [ ] **Step 5: Register routes**

Add to `netbox_fms/api/urls.py`:

```python
router.register("fiber-circuits", views.FiberCircuitViewSet)
router.register("fiber-circuit-paths", views.FiberCircuitPathViewSet)
router.register("fiber-circuit-nodes", views.FiberCircuitNodeViewSet)
```

- [ ] **Step 6: Run tests**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_circuit_api.py -v
```

Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add netbox_fms/api/ tests/test_fiber_circuit_api.py && git commit -m "feat: add FiberCircuit API — serializers, viewsets, router"
```

---

## Task 10: Add protection query API endpoint

**Files:**
- Modify: `netbox_fms/api/views.py`
- Modify: `netbox_fms/api/urls.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_fiber_circuit_api.py`:

```python
from dcim.models import Cable
from netbox_fms.models import FiberCircuitNode


class TestProtectionQueryAPI(TestCase):
    @classmethod
    def setUpTestData(cls):
        from users.models import Token
        from django.contrib.auth import get_user_model

        User = get_user_model()
        cls.user = User.objects.create_superuser("prottest", "prot@test.com", "testpass")
        cls.token = Token.objects.create(user=cls.user)
        cls.client = APIClient()
        cls.client.credentials(HTTP_AUTHORIZATION=f"Token {cls.token.key}")

        site = Site.objects.create(name="Prot Site", slug="prot-site")
        mfr = Manufacturer.objects.create(name="Prot Mfr", slug="prot-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="ProtDev", slug="protdev")
        role = DeviceRole.objects.create(name="Prot Role", slug="prot-role")
        device = Device.objects.create(name="ProtDev-1", site=site, device_type=dt, role=role)
        fp = FrontPort.objects.create(device=device, name="ProtFP", type="lc")

        cls.cable = Cable.objects.create()
        cls.circuit = FiberCircuit.objects.create(
            name="Prot-Circuit", status=FiberCircuitStatusChoices.ACTIVE, strand_count=1,
        )
        cls.path = FiberCircuitPath.objects.create(
            circuit=cls.circuit, position=1, origin=fp,
            path=[{"type": "cable", "id": cls.cable.pk}],
            is_complete=False,
        )
        FiberCircuitNode.objects.create(path=cls.path, position=1, cable=cls.cable)

    def test_query_by_cable(self):
        response = self.client.get(f"/api/plugins/netbox-fms/fiber-circuits/protecting/?cable={self.cable.pk}")
        assert response.status_code == 200
        assert len(response.data) >= 1
        assert response.data[0]["id"] == self.circuit.pk

    def test_query_no_match(self):
        other_cable = Cable.objects.create()
        response = self.client.get(f"/api/plugins/netbox-fms/fiber-circuits/protecting/?cable={other_cable.pk}")
        assert response.status_code == 200
        assert len(response.data) == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_circuit_api.py::TestProtectionQueryAPI -v
```

- [ ] **Step 3: Implement protecting endpoint**

Add to `netbox_fms/api/views.py`:

```python
from rest_framework.views import APIView
from rest_framework.response import Response


class FiberCircuitProtectingAPIView(APIView):
    """Return circuits protecting the given objects."""

    def get(self, request):
        filters = models.Q()
        for param, field in [
            ("cable", "nodes__cable_id"),
            ("front_port", "nodes__front_port_id"),
            ("rear_port", "nodes__rear_port_id"),
            ("fiber_strand", "nodes__fiber_strand_id"),
            ("splice_entry", "nodes__splice_entry_id"),
        ]:
            values = request.query_params.get(param)
            if values:
                ids = [int(v) for v in values.split(",")]
                filters |= models.Q(**{f"paths__{field}__in": ids})

        if not filters:
            return Response([])

        circuits = FiberCircuit.objects.filter(filters).distinct()
        serializer = FiberCircuitSerializer(circuits, many=True, context={"request": request})
        return Response(serializer.data)
```

Add to `netbox_fms/api/urls.py`:

```python
urlpatterns = router.urls + [
    # ... existing custom endpoints ...
    path("fiber-circuits/protecting/", views.FiberCircuitProtectingAPIView.as_view(), name="fibercircuit-protecting"),
]
```

**Important:** The `protecting/` path must come before the router URLs or be added to the explicit urlpatterns list after router.urls.

- [ ] **Step 4: Run tests**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_circuit_api.py -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/api/ tests/test_fiber_circuit_api.py && git commit -m "feat: add fiber circuit protection query API endpoint"
```

---

## Task 11: Add GraphQL types for Fiber Circuit models

**Files:**
- Modify: `netbox_fms/graphql/types.py`
- Modify: `netbox_fms/graphql/schema.py`
- Modify: `netbox_fms/graphql/filters.py`

- [ ] **Step 1: Add types**

Add to `netbox_fms/graphql/types.py`:

```python
@strawberry_django.type(FiberCircuit, fields="__all__")
class FiberCircuitType(NetBoxObjectType):
    paths: list[Annotated["FiberCircuitPathType", strawberry.lazy(".types")]]


@strawberry_django.type(FiberCircuitPath, fields="__all__")
class FiberCircuitPathType(NetBoxObjectType):
    circuit: Annotated["FiberCircuitType", strawberry.lazy(".types")]
    nodes: list[Annotated["FiberCircuitNodeType", strawberry.lazy(".types")]]


@strawberry_django.type(FiberCircuitNode, fields="__all__")
class FiberCircuitNodeType:
    path: Annotated["FiberCircuitPathType", strawberry.lazy(".types")]
```

Note: `FiberCircuitNodeType` does NOT inherit `NetBoxObjectType` since `FiberCircuitNode` is a plain `models.Model`.

- [ ] **Step 2: Add schema entries**

Add to the query class in `netbox_fms/graphql/schema.py`:

```python
fiber_circuit: FiberCircuitType = strawberry_django.field()
fiber_circuit_list: list[FiberCircuitType] = strawberry_django.field()
fiber_circuit_path: FiberCircuitPathType = strawberry_django.field()
fiber_circuit_path_list: list[FiberCircuitPathType] = strawberry_django.field()
```

- [ ] **Step 3: Update filters**

Add appropriate filter entries to `netbox_fms/graphql/filters.py` following existing patterns.

- [ ] **Step 4: Verify imports**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.graphql.types import *; from netbox_fms.graphql.schema import *"
```

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/graphql/ && git commit -m "feat: add GraphQL types for FiberCircuit models"
```

---

## Task 12: Add provisioning engine

**Files:**
- Create: `netbox_fms/provisioning.py`
- Modify: `netbox_fms/models.py` (add classmethods)

- [ ] **Step 1: Write failing tests**

Create `tests/test_fiber_circuit_provisioning.py`:

```python
"""Tests for the fiber circuit provisioning engine (find_paths, create_from_proposal)."""
from dcim.models import (
    Cable, CableTermination, Device, DeviceRole, DeviceType,
    FrontPort, Manufacturer, Module, ModuleBay, ModuleType,
    PortMapping, RearPort, Site,
)
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from netbox_fms.choices import FiberCircuitStatusChoices
from netbox_fms.models import FiberCable, FiberCableType, FiberCircuit, FiberCircuitPath, FiberCircuitNode


def _setup_linear_network(site, mfr, num_closures, strands_per_cable=4):
    """Create a linear chain of closures connected by cables.

    Returns (closures, cables, fiber_cables) where closures[0] is origin, closures[-1] is destination.
    Each closure has tray modules with FrontPorts and RearPorts properly mapped.
    """
    closures = []
    cables = []

    rp_ct = ContentType.objects.get_for_model(RearPort)

    for i in range(num_closures):
        dt, _ = DeviceType.objects.get_or_create(manufacturer=mfr, model=f"Net-Closure-{i}", slug=f"net-closure-{i}")
        role, _ = DeviceRole.objects.get_or_create(name="Net-Role", slug="net-role")
        device = Device.objects.create(name=f"Closure-{i}", site=site, device_type=dt, role=role)
        mt, _ = ModuleType.objects.get_or_create(manufacturer=mfr, model=f"Net-Tray-{i}")
        bay = ModuleBay.objects.create(device=device, name="Bay1")
        tray = Module.objects.create(device=device, module_bay=bay, module_type=mt)
        closures.append((device, tray))

    fct = FiberCableType.objects.create(
        manufacturer=mfr, model="Net-FCT", strand_count=strands_per_cable,
        construction="loose_tube", fiber_type="smf_os2",
    )

    # Connect adjacent closures with cables
    for i in range(num_closures - 1):
        dev_a, tray_a = closures[i]
        dev_b, tray_b = closures[i + 1]

        # Create rear ports on each side
        rp_a = RearPort.objects.create(
            device=dev_a, module=tray_a, name=f"RP-out-{i}", type="lc", positions=strands_per_cable,
        )
        rp_b = RearPort.objects.create(
            device=dev_b, module=tray_b, name=f"RP-in-{i+1}", type="lc", positions=strands_per_cable,
        )

        # Create front ports and port mappings (NetBox 4.5+: no rear_port FK on FrontPort)
        for s in range(1, strands_per_cable + 1):
            fp_a = FrontPort.objects.create(
                device=dev_a, module=tray_a, name=f"FP-out-{i}-{s}", type="lc",
            )
            PortMapping.objects.create(
                device=dev_a, front_port=fp_a, rear_port=rp_a,
                front_port_position=s, rear_port_position=s,
            )
            fp_b = FrontPort.objects.create(
                device=dev_b, module=tray_b, name=f"FP-in-{i+1}-{s}", type="lc",
            )
            PortMapping.objects.create(
                device=dev_b, front_port=fp_b, rear_port=rp_b,
                front_port_position=s, rear_port_position=s,
            )

        # Cable connecting the closures
        cable = Cable.objects.create()
        CableTermination.objects.create(
            cable=cable, cable_end="A", termination_type=rp_ct, termination_id=rp_a.pk,
        )
        CableTermination.objects.create(
            cable=cable, cable_end="B", termination_type=rp_ct, termination_id=rp_b.pk,
        )
        cables.append(cable)

    return closures, cables


class TestFindPaths(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name="FindPath Site", slug="findpath-site")
        cls.mfr = Manufacturer.objects.create(name="FindPath Mfr", slug="findpath-mfr")
        cls.closures, cls.cables = _setup_linear_network(cls.site, cls.mfr, num_closures=3, strands_per_cable=4)

    def test_find_single_path(self):
        origin_dev = self.closures[0][0]
        dest_dev = self.closures[-1][0]
        results = FiberCircuit.find_paths(
            origin_device=origin_dev,
            destination_device=dest_dev,
            strand_count=1,
            priorities=["hop_count"],
        )
        assert len(results) > 0

    def test_find_multi_strand_path(self):
        origin_dev = self.closures[0][0]
        dest_dev = self.closures[-1][0]
        results = FiberCircuit.find_paths(
            origin_device=origin_dev,
            destination_device=dest_dev,
            strand_count=2,
            priorities=["hop_count", "strand_adjacency"],
        )
        assert len(results) > 0
        # Each result should have 2 strand assignments
        assert all(len(r["strands"]) == 2 for r in results)


class TestCreateFromProposal(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name="Create Site", slug="create-site")
        cls.mfr = Manufacturer.objects.create(name="Create Mfr", slug="create-mfr")
        cls.closures, cls.cables = _setup_linear_network(cls.site, cls.mfr, num_closures=2, strands_per_cable=4)

    def test_create_circuit_from_proposal(self):
        origin_dev = self.closures[0][0]
        dest_dev = self.closures[-1][0]
        results = FiberCircuit.find_paths(
            origin_device=origin_dev,
            destination_device=dest_dev,
            strand_count=1,
            priorities=["hop_count"],
        )
        assert len(results) > 0

        circuit = FiberCircuit.create_from_proposal(results[0], name_template="Test-{n}")
        assert circuit.pk is not None
        assert circuit.name == "Test-1"
        assert circuit.paths.count() == 1

    def test_auto_increment_name(self):
        origin_dev = self.closures[0][0]
        dest_dev = self.closures[-1][0]
        results = FiberCircuit.find_paths(
            origin_device=origin_dev,
            destination_device=dest_dev,
            strand_count=1,
            priorities=["hop_count"],
        )
        FiberCircuit.create_from_proposal(results[0], name_template="Inc-{n}")
        circuit2 = FiberCircuit.create_from_proposal(results[0], name_template="Inc-{n}")
        assert circuit2.name == "Inc-2"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_circuit_provisioning.py -v
```

Expected: AttributeError — `find_paths` not found.

- [ ] **Step 3: Implement provisioning engine**

Create `netbox_fms/provisioning.py` with the DAG construction, pathfinding, scoring, and proposal creation logic. This is the most complex piece — implement iteratively:

1. DAG construction from CableTermination queries
2. Simple path enumeration (BFS/DFS for simple paths)
3. Strand availability checking per edge
4. Scoring by priority list
5. `create_from_proposal` with transaction, name auto-increment, splice creation

Add classmethods to `FiberCircuit` in `models.py`:

```python
@classmethod
def find_paths(cls, origin_device, destination_device, strand_count, priorities):
    from .provisioning import find_fiber_paths
    return find_fiber_paths(origin_device, destination_device, strand_count, priorities)

@classmethod
def create_from_proposal(cls, proposal, name_template):
    from .provisioning import create_circuit_from_proposal
    return create_circuit_from_proposal(proposal, name_template)
```

The `provisioning.py` module should be self-contained with clear function signatures. See the spec (sections on DAG construction, scoring, create_from_proposal) for detailed requirements.

- [ ] **Step 4: Run tests iteratively**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_circuit_provisioning.py -v
```

Debug and fix until all pass.

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/provisioning.py netbox_fms/models.py tests/test_fiber_circuit_provisioning.py && git commit -m "feat: add fiber circuit provisioning engine — find_paths and create_from_proposal"
```

---

## Task 13: Add splice editor protection integration

**Files:**
- Modify: `netbox_fms/api/views.py` (ClosureStrandsAPIView — add protection info)
- Modify: `netbox_fms/templates/netbox_fms/inc/splice_editor_widget.html` (lock icon rendering)

- [ ] **Step 1: Add protection data to ClosureStrandsAPIView**

In the API view that returns strand data for the splice editor, annotate each strand/splice with protection info:

```python
# For each strand in the response, check if its FrontPort is protected
protected_fp_ids = set(
    FiberCircuitNode.objects.filter(
        front_port_id__in=all_fp_ids,
        path__circuit__status__in=[...non-decommissioned statuses...]
    ).values_list("front_port_id", flat=True)
)
# Add "protected": True/False and "circuit_name": "..." to each strand entry
```

- [ ] **Step 2: Update splice editor JavaScript**

In the splice editor widget, render protected splices with:
- Lock icon overlay
- Tooltip with circuit name
- Non-interactive (disable drag/click handlers)

- [ ] **Step 3: Block splice apply for protected splices**

In the SplicePlan apply action, check for protected splices before executing. Return error if any protected splices would be modified.

- [ ] **Step 4: Test manually and write integration test**

Append to `tests/test_fiber_circuit_api.py`:

```python
class TestSpliceEditorProtection(TestCase):
    # Test that the ClosureStrandsAPIView includes protection info
    # Test that protected splices are marked in the response
    pass  # Implement specific assertions
```

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/api/views.py netbox_fms/templates/ tests/test_fiber_circuit_api.py && git commit -m "feat: integrate fiber circuit protection into splice editor"
```

---

## Task 14: Add performance tests

**Files:**
- Create: `tests/test_fiber_circuit_performance.py`

- [ ] **Step 1: Write performance tests**

```python
import time
from dcim.models import (
    Cable, CableTermination, Device, DeviceRole, DeviceType,
    FrontPort, Manufacturer, Module, ModuleBay, ModuleType,
    RearPort, Site,
)
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from netbox_fms.choices import FiberCircuitStatusChoices
from netbox_fms.models import FiberCircuit, FiberCircuitNode, FiberCircuitPath


class TestTracePerformance(TestCase):
    """Performance tests for the trace engine."""

    @classmethod
    def setUpTestData(cls):
        """Create a long linear chain for performance testing."""
        from tests.test_fiber_circuit_provisioning import _setup_linear_network

        cls.site = Site.objects.create(name="Perf Site", slug="perf-site")
        cls.mfr = Manufacturer.objects.create(name="Perf Mfr", slug="perf-mfr")

        # 50-hop chain (51 closures)
        cls.closures, cls.cables = _setup_linear_network(
            cls.site, cls.mfr, num_closures=51, strands_per_cable=4,
        )
        # TODO: Add splices at each intermediate closure

    def test_trace_50_hops_under_500ms(self):
        origin_fp = FrontPort.objects.filter(
            device=self.closures[0][0], name__startswith="FP-out",
        ).first()
        assert origin_fp is not None

        start = time.monotonic()
        result = FiberCircuitPath.from_origin(origin_fp)
        elapsed = time.monotonic() - start

        assert elapsed < 0.5, f"50-hop trace took {elapsed:.3f}s (target < 0.5s)"
        assert result.is_complete is True


class TestNodeRebuildPerformance(TestCase):
    def test_rebuild_12_paths_100_hops_under_1s(self):
        # Create a circuit with 12 paths, each with 100 entries in path JSON
        # Time the rebuild_nodes() call
        pass  # Implement after trace engine is working


class TestProtectionQueryPerformance(TestCase):
    def test_cable_lookup_under_10ms(self):
        # Create 1000+ FiberCircuitNodes
        # Time a single cable protection query
        pass  # Implement with bulk-created nodes
```

- [ ] **Step 2: Run performance tests**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_circuit_performance.py -v
```

- [ ] **Step 3: Optimize if needed**

If tests fail timing targets, optimize with:
- `select_related` / `prefetch_related` on trace queries
- Bulk `FiberCircuitNode.objects.bulk_create()` in `rebuild_nodes()`
- DB indexes on FiberCircuitNode FK fields (Django adds these by default for FKs)

- [ ] **Step 4: Commit**

```bash
git add tests/test_fiber_circuit_performance.py && git commit -m "test: add fiber circuit performance benchmarks"
```

---

## Task 15: Final integration test and cleanup

- [ ] **Step 1: Run full test suite**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v
```

- [ ] **Step 2: Lint and format**

```bash
ruff check --fix netbox_fms/
ruff format netbox_fms/
```

- [ ] **Step 3: Verify all imports**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "
import django; django.setup()
from netbox_fms.models import *
from netbox_fms.forms import *
from netbox_fms.filters import *
from netbox_fms.tables import *
from netbox_fms.trace import *
from netbox_fms.provisioning import *
from netbox_fms.api.serializers import *
from netbox_fms.graphql.types import *
"
```

- [ ] **Step 4: Commit any final fixes**

```bash
git add -A && git commit -m "chore: final cleanup and lint fixes for fiber circuits"
```
