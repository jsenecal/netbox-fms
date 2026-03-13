# Closure Fiber Overview Tab — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Fiber Overview" device tab for splice closures with HTMX modal actions and clean up plugin navigation.

**Architecture:** New device tab registered via `@register_model_view` showing cable/fiber status table with contextual HTMX modals (Create FiberCable, Provision Strands, Edit Gland Label). ClosureCableEntry model simplified by replacing `entrance_port` FK with `entrance_label` CharField. Three menu items removed from navigation.

**Tech Stack:** Django 5.x, NetBox 4.5+ plugin API, HTMX (bundled with NetBox), Bootstrap 5

**Spec:** `docs/superpowers/specs/2026-03-13-closure-fiber-overview-design.md`

---

## Chunk 1: Data Model Migration & Updates

### Task 1: ClosureCableEntry Migration — Add entrance_label

Add the new `entrance_label` CharField to ClosureCableEntry while keeping the old `entrance_port` FK. This is step 1 of the 3-step migration.

**Files:**
- Modify: `netbox_fms/models.py:845-882`
- Create: `netbox_fms/migrations/0008_closurecableentry_entrance_label.py` (auto-generated)
- Test: `tests/test_models.py`

- [ ] **Step 1: Add entrance_label field to the model**

In `netbox_fms/models.py`, add `entrance_label` to the `ClosureCableEntry` class (keep `entrance_port` for now):

```python
# After the entrance_port field (around line 866), add:
entrance_label = models.CharField(
    max_length=100,
    blank=True,
    verbose_name=_("entrance label"),
    help_text=_("Free-text gland/entrance name"),
)
```

- [ ] **Step 2: Generate the migration**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py makemigrations netbox_fms -n closurecableentry_entrance_label
```

Expected: Creates `netbox_fms/migrations/0008_closurecableentry_entrance_label.py` adding the field.

- [ ] **Step 3: Apply the migration**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py migrate netbox_fms
```

Expected: Migration applies successfully.

- [ ] **Step 4: Verify the field exists**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "
from netbox_fms.models import ClosureCableEntry
f = ClosureCableEntry._meta.get_field('entrance_label')
print(f'Field: {f.name}, max_length={f.max_length}, blank={f.blank}')
print('entrance_port still exists:', hasattr(ClosureCableEntry, 'entrance_port'))
"
```

Expected: Shows entrance_label with max_length=100, blank=True. entrance_port still exists.

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/models.py netbox_fms/migrations/0008_*.py
git commit -m "feat: add entrance_label field to ClosureCableEntry (step 1/3)"
```

---

### Task 2: Data Migration — Copy entrance_port.name to entrance_label

Create a data migration that copies `entrance_port.name` into `entrance_label` for existing rows.

**Files:**
- Create: `netbox_fms/migrations/0009_populate_entrance_label.py` (hand-written)

- [ ] **Step 1: Create the data migration**

Create `netbox_fms/migrations/0009_populate_entrance_label.py`:

```python
from django.db import migrations


def copy_entrance_port_name(apps, schema_editor):
    ClosureCableEntry = apps.get_model("netbox_fms", "ClosureCableEntry")
    for entry in ClosureCableEntry.objects.select_related("entrance_port").filter(
        entrance_port__isnull=False
    ):
        entry.entrance_label = entry.entrance_port.name
        entry.save(update_fields=["entrance_label"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_fms", "0008_closurecableentry_entrance_label"),
    ]

    operations = [
        migrations.RunPython(copy_entrance_port_name, noop),
    ]
```

- [ ] **Step 2: Apply the data migration**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py migrate netbox_fms
```

Expected: Migration applies successfully.

- [ ] **Step 3: Commit**

```bash
git add netbox_fms/migrations/0009_populate_entrance_label.py
git commit -m "feat: data migration to copy entrance_port.name to entrance_label (step 2/3)"
```

---

### Task 3: Schema Migration — Drop entrance_port, Update Model

Remove `entrance_port` FK, update `unique_together`, `ordering`, and `__str__`. Update all downstream files: form, serializer, filter, table, template, GraphQL.

**Files:**
- Modify: `netbox_fms/models.py:845-882`
- Modify: `netbox_fms/forms.py:442-468`
- Modify: `netbox_fms/api/serializers.py:258-275`
- Modify: `netbox_fms/filters.py:311-326`
- Modify: `netbox_fms/tables.py:318-328`
- Modify: `netbox_fms/templates/netbox_fms/closurecableentry.html`
- Modify: `netbox_fms/api/views.py` (ClosureCableEntryViewSet queryset)
- Create: `netbox_fms/migrations/0010_*.py` (auto-generated)
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_models.py`:

```python
class TestClosureCableEntryMigration(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="CCE Test Site", slug="cce-test-site")
        manufacturer = Manufacturer.objects.create(name="CCE Mfr", slug="cce-mfr")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="CCE Closure", slug="cce-closure")
        role = DeviceRole.objects.create(name="CCE Role", slug="cce-role")
        cls.closure = Device.objects.create(name="CCE-Closure-1", site=site, device_type=device_type, role=role)
        fct = FiberCableType.objects.create(
            manufacturer=manufacturer, model="CCE-FCT", construction="loose_tube",
            fiber_type="smf_os2", strand_count=12,
        )
        cable = Cable.objects.create()
        cls.fiber_cable = FiberCable.objects.create(cable=cable, fiber_cable_type=fct)

    def test_entrance_label_field_exists(self):
        entry = ClosureCableEntry.objects.create(
            closure=self.closure,
            fiber_cable=self.fiber_cable,
            entrance_label="Gland A",
        )
        assert entry.entrance_label == "Gland A"
        assert entry.pk is not None

    def test_entrance_port_field_removed(self):
        field_names = [f.name for f in ClosureCableEntry._meta.get_fields()]
        assert "entrance_port" not in field_names
        assert "entrance_label" in field_names

    def test_unique_together_closure_fiber_cable(self):
        ClosureCableEntry.objects.create(
            closure=self.closure,
            fiber_cable=self.fiber_cable,
            entrance_label="Gland A",
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            ClosureCableEntry.objects.create(
                closure=self.closure,
                fiber_cable=self.fiber_cable,
                entrance_label="Gland B",
            )

    def test_str_uses_entrance_label(self):
        entry = ClosureCableEntry.objects.create(
            closure=self.closure,
            fiber_cable=self.fiber_cable,
            entrance_label="Gland C",
        )
        assert "Gland C" in str(entry)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_models.py::TestClosureCableEntryMigration -v
```

Expected: FAIL — `entrance_port` still exists and is required, `unique_together` is wrong.

- [ ] **Step 3: Update the model**

In `netbox_fms/models.py`, replace the `ClosureCableEntry` class:

Remove the `entrance_port` field entirely. Update `Meta` and `__str__`:

```python
class ClosureCableEntry(NetBoxModel):
    """Tracks which gland/entrance on a closure each fiber cable enters through."""

    closure = models.ForeignKey(
        to="dcim.Device",
        on_delete=models.CASCADE,
        related_name="cable_entries",
        verbose_name=_("closure"),
    )
    fiber_cable = models.ForeignKey(
        to="netbox_fms.FiberCable",
        on_delete=models.CASCADE,
        related_name="closure_entries",
        verbose_name=_("fiber cable"),
    )
    entrance_label = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("entrance label"),
        help_text=_("Free-text gland/entrance name"),
    )
    notes = models.TextField(
        verbose_name=_("notes"),
        blank=True,
    )

    class Meta:
        ordering = ("closure", "entrance_label")
        unique_together = (("closure", "fiber_cable"),)
        verbose_name = _("closure cable entry")
        verbose_name_plural = _("closure cable entries")

    def __str__(self):
        label = self.entrance_label or "—"
        return f"{self.closure} → {label} ({self.fiber_cable})"

    def get_absolute_url(self):
        return reverse("plugins:netbox_fms:closurecableentry", args=[self.pk])
```

- [ ] **Step 4: Update the form**

In `netbox_fms/forms.py`, update `ClosureCableEntryForm` (around line 442):

```python
class ClosureCableEntryForm(NetBoxModelForm):
    closure = DynamicModelChoiceField(queryset=Device.objects.all(), label=_("Closure"))
    fiber_cable = DynamicModelChoiceField(queryset=FiberCable.objects.all(), label=_("Fiber Cable"))

    fieldsets = (
        FieldSet("closure", "fiber_cable", "entrance_label", name=_("Cable Entry")),
        FieldSet("notes", name=_("Notes")),
        FieldSet("tags", name=_("Additional")),
    )

    class Meta:
        model = ClosureCableEntry
        fields = ("closure", "fiber_cable", "entrance_label", "notes", "tags")
```

Update `ClosureCableEntryFilterForm` (around line 458) — remove `entrance_port` references if any, fields stay the same since we only filter by `closure_id`.

- [ ] **Step 5: Update the serializer**

In `netbox_fms/api/serializers.py`, update `ClosureCableEntrySerializer` (around line 258):

Replace `entrance_port` with `entrance_label` in `fields` and `brief_fields`:

```python
class ClosureCableEntrySerializer(NetBoxModelSerializer):
    class Meta:
        model = ClosureCableEntry
        fields = (
            "id",
            "url",
            "display",
            "closure",
            "fiber_cable",
            "entrance_label",
            "notes",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "closure", "fiber_cable")
```

- [ ] **Step 6: Update the filter**

In `netbox_fms/filters.py`, update `ClosureCableEntryFilterSet` (around line 311):

Replace `entrance_port` with `entrance_label` in `Meta.fields`:

```python
class ClosureCableEntryFilterSet(NetBoxModelFilterSet):
    closure_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Device.objects.all(),
        field_name="closure",
        label=_("Closure (ID)"),
    )

    class Meta:
        model = ClosureCableEntry
        fields = ("id", "closure_id", "fiber_cable", "entrance_label")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            models.Q(notes__icontains=value) | models.Q(entrance_label__icontains=value)
        )
```

- [ ] **Step 7: Update the table**

In `netbox_fms/tables.py`, update `ClosureCableEntryTable` (around line 318):

Replace `entrance_port` with `entrance_label`:

```python
class ClosureCableEntryTable(NetBoxTable):
    pk = columns.ToggleColumn()
    closure = tables.Column(linkify=True, verbose_name=_("Closure"))
    fiber_cable = tables.Column(linkify=True, verbose_name=_("Fiber Cable"))
    entrance_label = tables.Column(verbose_name=_("Entrance Label"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = ClosureCableEntry
        fields = ("pk", "id", "closure", "fiber_cable", "entrance_label", "notes", "actions")
        default_columns = ("pk", "closure", "fiber_cable", "entrance_label", "actions")
```

- [ ] **Step 8: Update the detail template**

In `netbox_fms/templates/netbox_fms/closurecableentry.html`, replace the "Entrance Port" row:

```html
<tr>
    <th scope="row">{% trans "Entrance Label" %}</th>
    <td>{{ object.entrance_label|default:"—" }}</td>
</tr>
```

- [ ] **Step 9: Update the API viewset and list view querysets**

In `netbox_fms/api/views.py`, update `ClosureCableEntryViewSet` queryset — remove `"entrance_port"` from `prefetch_related`:

```python
class ClosureCableEntryViewSet(NetBoxModelViewSet):
    queryset = ClosureCableEntry.objects.prefetch_related("closure", "fiber_cable", "tags")
    serializer_class = ClosureCableEntrySerializer
    filterset_class = ClosureCableEntryFilterSet
```

In `netbox_fms/views.py`, update `ClosureCableEntryListView` queryset (around line 403) — remove `"entrance_port"` from `select_related`:

```python
class ClosureCableEntryListView(generic.ObjectListView):
    queryset = ClosureCableEntry.objects.select_related("closure", "fiber_cable")
    table = ClosureCableEntryTable
    filterset = ClosureCableEntryFilterSet
    filterset_form = ClosureCableEntryFilterForm
```

**Note:** The `ClosureCableEntryFilterForm` has no `entrance_port` references — no changes needed there. The GraphQL types use `fields="__all__"` which auto-adapts to model changes — no GraphQL changes needed.

- [ ] **Step 10: Generate and apply the schema migration**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py makemigrations netbox_fms -n drop_entrance_port
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py migrate netbox_fms
```

Expected: Migration removes `entrance_port`, updates `unique_together` and `ordering`.

- [ ] **Step 11: Run tests to verify they pass**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_models.py::TestClosureCableEntryMigration -v
```

Expected: All 4 tests PASS.

- [ ] **Step 12: Verify all modules import cleanly**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.models import *; from netbox_fms.forms import *; from netbox_fms.filters import *; from netbox_fms.tables import *; from netbox_fms.api.serializers import *"
```

Expected: No import errors.

- [ ] **Step 13: Commit**

```bash
git add netbox_fms/models.py netbox_fms/forms.py netbox_fms/api/serializers.py netbox_fms/filters.py netbox_fms/tables.py netbox_fms/api/views.py netbox_fms/templates/netbox_fms/closurecableentry.html netbox_fms/migrations/0010_*.py tests/test_models.py
git commit -m "feat: drop entrance_port, update ClosureCableEntry to use entrance_label (step 3/3)"
```

---

### Task 4: Extract _provision_strands Helper

Refactor `ProvisionPortsView._provision()` into a standalone helper function that accepts an optional `module` parameter. Both the existing view and the new modal view will use it.

**Files:**
- Modify: `netbox_fms/views.py:565-605` (ProvisionPortsView._provision)
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_models.py`:

```python
from netbox_fms.views import provision_strands


class TestProvisionStrandsHelper(TestCase):
    """Uses setUp (not setUpTestData) because each test provisions strands,
    mutating FiberStrand.front_port. Tests need isolated FiberCable instances."""

    def setUp(self):
        from dcim.models import Module, ModuleBay, ModuleType
        site = Site.objects.create(name="Prov Test Site", slug="prov-test-site")
        manufacturer = Manufacturer.objects.create(name="Prov Mfr", slug="prov-mfr")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="Prov Closure", slug="prov-closure")
        role = DeviceRole.objects.create(name="Prov Role", slug="prov-role")
        self.device = Device.objects.create(name="Prov-Device", site=site, device_type=device_type, role=role)

        module_type = ModuleType.objects.create(manufacturer=manufacturer, model="Tray-1")
        bay = ModuleBay.objects.create(device=self.device, name="Bay 1")
        self.module = Module.objects.create(device=self.device, module_bay=bay, module_type=module_type)

        self.fct = FiberCableType.objects.create(
            manufacturer=manufacturer, model="Prov-FCT", construction="loose_tube",
            fiber_type="smf_os2", strand_count=4,
        )

    def test_provision_creates_ports_on_module(self):
        from dcim.models import FrontPort, RearPort
        cable = Cable.objects.create()
        fiber_cable = FiberCable.objects.create(cable=cable, fiber_cable_type=self.fct)
        provision_strands(fiber_cable, self.device, module=self.module, port_type="splice")

        # RearPort created on module
        rp = RearPort.objects.filter(device=self.device, module=self.module)
        assert rp.count() == 1

        # FrontPorts created on module
        fps = FrontPort.objects.filter(device=self.device, module=self.module)
        assert fps.count() == 4

        # Strands linked
        for strand in fiber_cable.fiber_strands.all():
            assert strand.front_port is not None
            assert strand.front_port.module == self.module

    def test_provision_creates_ports_without_module(self):
        from dcim.models import FrontPort, RearPort
        cable = Cable.objects.create()
        fiber_cable = FiberCable.objects.create(cable=cable, fiber_cable_type=self.fct)
        provision_strands(fiber_cable, self.device, port_type="splice")

        rp = RearPort.objects.filter(device=self.device, module__isnull=True)
        assert rp.count() == 1

        fps = FrontPort.objects.filter(device=self.device, module__isnull=True)
        assert fps.count() == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_models.py::TestProvisionStrandsHelper -v
```

Expected: FAIL — `provision_strands` not importable.

- [ ] **Step 3: Extract the helper function**

In `netbox_fms/views.py`, add a module-level function before `ProvisionPortsView`:

```python
@transaction.atomic
def provision_strands(fiber_cable, device, port_type, module=None):
    """
    Provision dcim FrontPort/RearPort/PortMapping for a FiberCable on a Device.

    If module is provided, all ports are created on that module (in addition to device).
    """
    from dcim.models import FrontPort, PortMapping, RearPort

    strands = fiber_cable.fiber_strands.select_related("buffer_tube").order_by("position")
    strand_count = strands.count()
    if strand_count == 0:
        raise ValueError("This fiber cable has no strands.")

    cable_label = str(fiber_cable.cable) if fiber_cable.cable else f"FiberCable-{fiber_cable.pk}"

    # PortMapping only has device, front_port, rear_port — no module field.
    # RearPort and FrontPort support both device and module.
    component_kwargs = {"device": device}
    if module is not None:
        component_kwargs["module"] = module

    rear_port = RearPort(
        **component_kwargs,
        name=cable_label,
        type=port_type,
        positions=strand_count,
        color="",
    )
    rear_port.save()

    for strand in strands:
        fp = FrontPort(
            **component_kwargs,
            name=strand.name,
            type=port_type,
            color=strand.color,
        )
        fp.save()

        PortMapping.objects.create(
            device=device,
            front_port=fp,
            rear_port=rear_port,
            front_port_position=1,
            rear_port_position=strand.position,
        )

        strand.front_port = fp
        strand.save(update_fields=["front_port"])
```

Then update `ProvisionPortsView` to use the helper. Replace both `_provision` and the relevant parts of `post()`:

```python
def post(self, request):
    form = ProvisionPortsForm(request.POST)
    if not form.is_valid():
        return render(request, "netbox_fms/provision_ports.html", {"form": form})

    fiber_cable = form.cleaned_data["fiber_cable"]
    device = form.cleaned_data["device"]
    port_type = form.cleaned_data["port_type"]

    # Check for already provisioned strands on this device
    already = fiber_cable.fiber_strands.filter(front_port__device=device).exists()
    if already:
        messages.error(request, _("Some strands are already provisioned on this device."))
        return render(request, "netbox_fms/provision_ports.html", {"form": form})

    try:
        provision_strands(fiber_cable, device, port_type)
        strand_count = fiber_cable.fiber_strands.count()
        messages.success(
            request,
            _('Provisioned {count} ports for "{cable}" on {device}.').format(
                count=strand_count, cable=fiber_cable, device=device
            ),
        )
    except ValueError as e:
        messages.error(request, str(e))
        return render(request, "netbox_fms/provision_ports.html", {"form": form})

    return redirect(fiber_cable.get_absolute_url())
```

Remove the `_provision` method entirely — the standalone `provision_strands()` function replaces it.

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_models.py::TestProvisionStrandsHelper -v
```

Expected: Both tests PASS.

- [ ] **Step 5: Run all existing tests to verify no regressions**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add netbox_fms/views.py tests/test_models.py
git commit -m "refactor: extract provision_strands helper with optional module parameter"
```

---

## Chunk 2: Fiber Overview Tab & Templates

### Task 5: Tab Visibility Function & DeviceFiberOverviewView

Create the new tab visibility function and the main overview view.

**Files:**
- Modify: `netbox_fms/views.py`
- Create: `netbox_fms/templates/netbox_fms/device_fiber_overview.html`
- Create: `netbox_fms/templates/netbox_fms/htmx/fiber_overview_row.html`
- Test: `tests/test_fiber_overview.py`

- [ ] **Step 1: Write the failing test for tab visibility**

Create `tests/test_fiber_overview.py`:

```python
from django.test import TestCase, RequestFactory
from dcim.models import Cable, Device, DeviceRole, DeviceType, Manufacturer, Module, ModuleBay, ModuleType, Site

from netbox_fms.models import FiberCable, FiberCableType
from netbox_fms.views import _device_has_modules_or_fiber_cables


class TestFiberOverviewTabVisibility(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="FO Vis Site", slug="fo-vis-site")
        manufacturer = Manufacturer.objects.create(name="FO Mfr", slug="fo-mfr")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="FO Model", slug="fo-model")
        role = DeviceRole.objects.create(name="FO Role", slug="fo-role")
        cls.device = Device.objects.create(name="FO-Device", site=site, device_type=device_type, role=role)

        cls.manufacturer = manufacturer
        cls.site = site
        cls.device_type = device_type
        cls.role = role

    def test_hidden_for_plain_device(self):
        assert _device_has_modules_or_fiber_cables(self.device) is False

    def test_visible_when_device_has_module(self):
        module_type = ModuleType.objects.create(manufacturer=self.manufacturer, model="FO Tray")
        bay = ModuleBay.objects.create(device=self.device, name="FO Bay 1")
        Module.objects.create(device=self.device, module_bay=bay, module_type=module_type)
        assert _device_has_modules_or_fiber_cables(self.device) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_overview.py::TestFiberOverviewTabVisibility -v
```

Expected: FAIL — `_device_has_modules_or_fiber_cables` not importable.

- [ ] **Step 3: Implement the visibility function**

In `netbox_fms/views.py`, add before the existing `_device_has_splice_plan_or_fiber_cables`:

```python
def _device_has_modules_or_fiber_cables(device):
    """Return True if device has modules (trays) or FiberCable terminations."""
    if device.modules.exists():
        return True
    from dcim.models import CableTermination

    cable_ids = (
        CableTermination.objects.filter(_device_id=device.pk)
        .exclude(cable__isnull=True)
        .values_list("cable_id", flat=True)
        .distinct()
    )
    return FiberCable.objects.filter(cable_id__in=cable_ids).exists()
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_overview.py::TestFiberOverviewTabVisibility -v
```

Expected: Both tests PASS.

- [ ] **Step 5: Write the failing test for the overview view**

Add to `tests/test_fiber_overview.py`:

```python
from django.contrib.auth.models import User


class TestFiberOverviewView(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="FOV Site", slug="fov-site")
        manufacturer = Manufacturer.objects.create(name="FOV Mfr", slug="fov-mfr")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="FOV Closure", slug="fov-closure")
        role = DeviceRole.objects.create(name="FOV Role", slug="fov-role")
        cls.device = Device.objects.create(name="FOV-Closure", site=site, device_type=device_type, role=role)
        cls.user = User.objects.create_user(username="fov_testuser", password="testpass", is_superuser=True)

    def test_fiber_overview_returns_200(self):
        self.client.force_login(self.user)
        url = f"/dcim/devices/{self.device.pk}/fiber-overview/"
        response = self.client.get(url)
        assert response.status_code == 200

    def test_fiber_overview_context_has_stats(self):
        self.client.force_login(self.user)
        url = f"/dcim/devices/{self.device.pk}/fiber-overview/"
        response = self.client.get(url)
        assert "stats" in response.context
        assert "cable_rows" in response.context
```

- [ ] **Step 6: Run test to verify it fails**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_overview.py::TestFiberOverviewView -v
```

Expected: FAIL — 404, view not registered yet.

- [ ] **Step 7: Implement _build_cable_row helper**

In `netbox_fms/views.py`, add the shared helper function:

```python
def _build_cable_row(device, rearport):
    """Build context dict for a single cable row in the Fiber Overview table."""
    from dcim.models import CableTermination, RearPort
    from django.contrib.contenttypes.models import ContentType

    rp_ct = ContentType.objects.get_for_model(RearPort)
    term = CableTermination.objects.filter(
        termination_type=rp_ct,
        termination_id=rearport.pk,
    ).select_related("cable").first()

    cable = term.cable if term else None
    fiber_cable = None
    strand_info = None
    gland_entry = None

    if cable:
        fiber_cable = FiberCable.objects.filter(cable=cable).first()
        if fiber_cable:
            total = fiber_cable.fiber_strands.count()
            provisioned = fiber_cable.fiber_strands.filter(front_port__device=device).count()
            strand_info = {"provisioned": provisioned, "total": total}
            gland_entry = ClosureCableEntry.objects.filter(
                closure=device, fiber_cable=fiber_cable
            ).first()

    return {
        "rearport": rearport,
        "cable": cable,
        "fiber_cable": fiber_cable,
        "strand_info": strand_info,
        "gland_entry": gland_entry,
    }
```

- [ ] **Step 8: Implement DeviceFiberOverviewView**

In `netbox_fms/views.py`, add the view:

```python
@register_model_view(Device, "fiber_overview", path="fiber-overview")
class DeviceFiberOverviewView(View):
    """Fiber Overview tab on a dcim.Device detail page."""

    tab = ViewTab(
        label=_("Fiber Overview"),
        visible=_device_has_modules_or_fiber_cables,
        weight=1400,
    )

    def get(self, request, pk):
        device = get_object_or_404(Device, pk=pk)

        from dcim.models import RearPort

        module_rearports = RearPort.objects.filter(
            device=device, module__isnull=False
        ).select_related("module")

        cable_rows = [_build_cable_row(device, rp) for rp in module_rearports]

        plan = SplicePlan.objects.filter(closure=device).first()

        stats = {
            "tray_count": device.modules.count(),
            "cable_count": sum(1 for r in cable_rows if r["cable"]),
            "fiber_cable_count": sum(1 for r in cable_rows if r["fiber_cable"]),
            "strand_provisioned": sum(
                r["strand_info"]["provisioned"] for r in cable_rows if r["strand_info"]
            ),
            "strand_total": sum(
                r["strand_info"]["total"] for r in cable_rows if r["strand_info"]
            ),
        }

        return render(request, "netbox_fms/device_fiber_overview.html", {
            "object": device,
            "device": device,
            "cable_rows": cable_rows,
            "plan": plan,
            "stats": stats,
            "tab": self.tab,
        })
```

- [ ] **Step 9: Create the row partial template**

Create `netbox_fms/templates/netbox_fms/htmx/fiber_overview_row.html`:

```html
{% load helpers %}
{% load i18n %}
<tr id="row-rp-{{ row.rearport.pk }}">
    <td>
        {% if row.cable %}
            <a href="{{ row.cable.get_absolute_url }}">{{ row.cable }}</a>
        {% else %}
            <span class="text-muted">—</span>
        {% endif %}
    </td>
    <td>{{ row.rearport.module.name }} / {{ row.rearport.name }}</td>
    <td>
        {% if row.fiber_cable %}
            <a href="{{ row.fiber_cable.get_absolute_url }}">{{ row.fiber_cable }}</a>
        {% else %}
            <span class="text-muted">—</span>
        {% endif %}
    </td>
    <td>
        {% if row.gland_entry and row.gland_entry.entrance_label %}
            {{ row.gland_entry.entrance_label }}
        {% else %}
            <span class="text-muted">—</span>
        {% endif %}
    </td>
    <td>
        {% if row.strand_info %}
            {{ row.strand_info.provisioned }}/{{ row.strand_info.total }} provisioned
        {% else %}
            <span class="text-muted">—</span>
        {% endif %}
    </td>
    <td>
        {% if row.cable and not row.fiber_cable %}
            {% if perms.netbox_fms.add_fibercable %}
            <button type="button" class="btn btn-sm btn-success"
                    hx-get="{% url 'plugins:netbox_fms:fiber_overview_create_fibercable' pk=device.pk %}?cable_id={{ row.cable.pk }}"
                    hx-target="#modal-container" hx-swap="innerHTML">
                <i class="mdi mdi-plus"></i> Create FiberCable
            </button>
            {% endif %}
        {% elif row.fiber_cable and row.strand_info and row.strand_info.provisioned == 0 %}
            {% if perms.dcim.add_frontport %}
            <button type="button" class="btn btn-sm btn-primary"
                    hx-get="{% url 'plugins:netbox_fms:fiber_overview_provision_strands' pk=device.pk %}?fiber_cable_id={{ row.fiber_cable.pk }}"
                    hx-target="#modal-container" hx-swap="innerHTML">
                <i class="mdi mdi-lan-connect"></i> Provision Strands
            </button>
            {% endif %}
        {% elif row.fiber_cable and row.strand_info and row.strand_info.provisioned > 0 %}
            <span class="text-success"><i class="mdi mdi-check-circle"></i></span>
        {% endif %}
        {% if row.fiber_cable %}
            {% if perms.netbox_fms.add_closurecableentry or perms.netbox_fms.change_closurecableentry %}
            <button type="button" class="btn btn-sm btn-outline-secondary ms-1"
                    hx-get="{% url 'plugins:netbox_fms:fiber_overview_update_gland' pk=device.pk %}?fiber_cable_id={{ row.fiber_cable.pk }}&rearport_id={{ row.rearport.pk }}"
                    hx-target="#modal-container" hx-swap="innerHTML">
                <i class="mdi mdi-pencil"></i>
            </button>
            {% endif %}
        {% endif %}
    </td>
</tr>
```

- [ ] **Step 10: Create the main overview template**

Create `netbox_fms/templates/netbox_fms/device_fiber_overview.html`:

```html
{% extends 'dcim/device/base.html' %}
{% load helpers %}
{% load i18n %}

{% block content %}
<div class="row mb-3">
    <div class="col">
        <div class="card">
            <h5 class="card-header">{% trans "Fiber Management Summary" %}</h5>
            <div class="card-body">
                {# Stats bar #}
                <div class="row text-center mb-3">
                    <div class="col">
                        <h4>{{ stats.tray_count }}</h4>
                        <small class="text-muted">{% trans "Trays" %}</small>
                    </div>
                    <div class="col">
                        <h4>{{ stats.cable_count }}</h4>
                        <small class="text-muted">{% trans "Cables Connected" %}</small>
                    </div>
                    <div class="col">
                        <h4>{{ stats.fiber_cable_count }}</h4>
                        <small class="text-muted">{% trans "FiberCables" %}</small>
                    </div>
                    <div class="col">
                        <h4>{{ stats.strand_provisioned }}/{{ stats.strand_total }}</h4>
                        <small class="text-muted">{% trans "Strands Provisioned" %}</small>
                    </div>
                    <div class="col">
                        {% if plan %}
                            <h4><span class="badge bg-{{ plan.status }}">{{ plan.get_status_display }}</span></h4>
                        {% else %}
                            <h4><span class="text-muted">{% trans "None" %}</span></h4>
                        {% endif %}
                        <small class="text-muted">{% trans "Splice Plan" %}</small>
                    </div>
                </div>

                {# Cable/Fiber status table #}
                {% if cable_rows %}
                <div class="table-responsive">
                    <table class="table table-hover">
                        <thead>
                            <tr>
                                <th>{% trans "Cable" %}</th>
                                <th>{% trans "Tray (RearPort)" %}</th>
                                <th>{% trans "FiberCable" %}</th>
                                <th>{% trans "Gland" %}</th>
                                <th>{% trans "Strands" %}</th>
                                <th>{% trans "Actions" %}</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for row in cable_rows %}
                                {% include "netbox_fms/htmx/fiber_overview_row.html" with row=row device=device %}
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% else %}
                <div class="text-muted text-center py-3">
                    {% trans "No module-attached RearPorts found. Add modules (trays) and connect cables to see fiber status here." %}
                </div>
                {% endif %}
            </div>
        </div>
    </div>
</div>

{# Splice Plan section #}
<div class="row mb-3">
    <div class="col">
        <div class="card">
            <h5 class="card-header">{% trans "Splice Plan" %}</h5>
            <div class="card-body">
                {% if plan %}
                    <p>
                        <strong>{{ plan.name }}</strong>
                        <span class="badge bg-{{ plan.status }}">{{ plan.get_status_display }}</span>
                    </p>
                    <a href="{{ plan.get_absolute_url }}" class="btn btn-sm btn-outline-primary">
                        <i class="mdi mdi-eye"></i> {% trans "View Plan" %}
                    </a>
                    <a href="{% url 'dcim:device' pk=device.pk %}splice-editor/" class="btn btn-sm btn-outline-secondary">
                        <i class="mdi mdi-pencil"></i> {% trans "Splice Editor" %}
                    </a>
                {% else %}
                    <p class="text-muted">{% trans "No splice plan" %}</p>
                    <a href="{% url 'plugins:netbox_fms:spliceplan_add' %}?closure={{ device.pk }}" class="btn btn-sm btn-success">
                        <i class="mdi mdi-plus"></i> {% trans "Create Plan" %}
                    </a>
                {% endif %}
            </div>
        </div>
    </div>
</div>

{# HTMX modal container #}
<div id="modal-container"></div>

{% endblock %}
```

- [ ] **Step 11: Run tests to verify they pass**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_overview.py::TestFiberOverviewView -v
```

Expected: Both tests PASS.

- [ ] **Step 12: Commit**

```bash
git add netbox_fms/views.py netbox_fms/templates/netbox_fms/device_fiber_overview.html netbox_fms/templates/netbox_fms/htmx/fiber_overview_row.html tests/test_fiber_overview.py
git commit -m "feat: add Fiber Overview device tab with stats and cable status table"
```

---

### Task 6: URL Patterns for Action Views

Register the three HTMX action view URLs. The views don't exist yet — we'll create placeholder views that return 501 so the URL wiring can be tested.

**Files:**
- Modify: `netbox_fms/urls.py`
- Modify: `netbox_fms/views.py`

- [ ] **Step 1: Add required imports and placeholder views**

In `netbox_fms/views.py`, add these imports at the top of the file (alongside existing imports):

```python
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.urls import reverse
from dcim.models import Cable, Module
```

Then add placeholder views at the bottom:


class CreateFiberCableFromCableView(LoginRequiredMixin, View):
    def get(self, request, pk):
        return HttpResponse("Not implemented", status=501)

    def post(self, request, pk):
        return HttpResponse("Not implemented", status=501)


class ProvisionStrandsFromOverviewView(LoginRequiredMixin, View):
    def get(self, request, pk):
        return HttpResponse("Not implemented", status=501)

    def post(self, request, pk):
        return HttpResponse("Not implemented", status=501)


class UpdateGlandLabelView(LoginRequiredMixin, View):
    def get(self, request, pk):
        return HttpResponse("Not implemented", status=501)

    def post(self, request, pk):
        return HttpResponse("Not implemented", status=501)
```

- [ ] **Step 2: Add URL patterns**

In `netbox_fms/urls.py`, add after the existing URL patterns (before `urlpatterns` closing bracket):

```python
# Fiber Overview HTMX actions
path(
    "fiber-overview/<int:pk>/create-fiber-cable/",
    views.CreateFiberCableFromCableView.as_view(),
    name="fiber_overview_create_fibercable",
),
path(
    "fiber-overview/<int:pk>/provision-strands/",
    views.ProvisionStrandsFromOverviewView.as_view(),
    name="fiber_overview_provision_strands",
),
path(
    "fiber-overview/<int:pk>/update-gland/",
    views.UpdateGlandLabelView.as_view(),
    name="fiber_overview_update_gland",
),
```

- [ ] **Step 3: Verify URL resolution**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "
from django.urls import reverse
print(reverse('plugins:netbox_fms:fiber_overview_create_fibercable', kwargs={'pk': 1}))
print(reverse('plugins:netbox_fms:fiber_overview_provision_strands', kwargs={'pk': 1}))
print(reverse('plugins:netbox_fms:fiber_overview_update_gland', kwargs={'pk': 1}))
"
```

Expected: Prints three valid URL paths.

- [ ] **Step 4: Commit**

```bash
git add netbox_fms/urls.py netbox_fms/views.py
git commit -m "feat: register URL patterns and placeholder views for Fiber Overview actions"
```

---

## Chunk 3: HTMX Modal Actions & Navigation Cleanup

### Task 7: CreateFiberCableFromCableView + Modal Template

Implement the Create FiberCable HTMX modal action.

**Files:**
- Modify: `netbox_fms/views.py` (replace placeholder)
- Create: `netbox_fms/templates/netbox_fms/htmx/create_fiber_cable_modal.html`
- Test: `tests/test_fiber_overview.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_fiber_overview.py`:

```python
class TestCreateFiberCableAction(TestCase):
    @classmethod
    def setUpTestData(cls):
        from dcim.models import RearPort, Module, ModuleBay, ModuleType, CableTermination
        from django.contrib.contenttypes.models import ContentType

        site = Site.objects.create(name="CFC Site", slug="cfc-site")
        manufacturer = Manufacturer.objects.create(name="CFC Mfr", slug="cfc-mfr")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="CFC Closure", slug="cfc-closure")
        role = DeviceRole.objects.create(name="CFC Role", slug="cfc-role")
        cls.device = Device.objects.create(name="CFC-Closure", site=site, device_type=device_type, role=role)

        module_type = ModuleType.objects.create(manufacturer=manufacturer, model="CFC Tray")
        bay = ModuleBay.objects.create(device=cls.device, name="CFC Bay")
        cls.module = Module.objects.create(device=cls.device, module_bay=bay, module_type=module_type)

        cls.rearport = RearPort.objects.create(device=cls.device, module=cls.module, name="RP1", type="splice", positions=1)
        cls.cable = Cable.objects.create()

        rp_ct = ContentType.objects.get_for_model(RearPort)
        CableTermination.objects.create(
            cable=cls.cable,
            termination_type=rp_ct,
            termination_id=cls.rearport.pk,
            cable_end="A",
        )

        cls.fct = FiberCableType.objects.create(
            manufacturer=manufacturer, model="CFC-FCT", construction="loose_tube",
            fiber_type="smf_os2", strand_count=12,
        )
        cls.user = User.objects.create_user(username="cfc_testuser", password="testpass", is_superuser=True)

    def test_get_returns_modal_form(self):
        self.client.force_login(self.user)
        url = f"/plugins/netbox-fms/fiber-overview/{self.device.pk}/create-fiber-cable/?cable_id={self.cable.pk}"
        response = self.client.get(url)
        assert response.status_code == 200
        assert b"modal" in response.content

    def test_post_creates_fiber_cable(self):
        self.client.force_login(self.user)
        url = f"/plugins/netbox-fms/fiber-overview/{self.device.pk}/create-fiber-cable/"
        response = self.client.post(url, {
            "cable_id": self.cable.pk,
            "fiber_cable_type": self.fct.pk,
        })
        assert response.status_code == 200  # HTMX response
        assert response.has_header("HX-Redirect")
        assert FiberCable.objects.filter(cable=self.cable).exists()

    def test_post_duplicate_returns_error(self):
        FiberCable.objects.create(cable=self.cable, fiber_cable_type=self.fct)
        self.client.force_login(self.user)
        url = f"/plugins/netbox-fms/fiber-overview/{self.device.pk}/create-fiber-cable/?cable_id={self.cable.pk}"
        response = self.client.get(url)
        assert response.status_code == 200
        assert b"already exists" in response.content
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_overview.py::TestCreateFiberCableAction -v
```

Expected: FAIL — placeholder returns 501.

- [ ] **Step 3: Create the modal template**

Create `netbox_fms/templates/netbox_fms/htmx/create_fiber_cable_modal.html`:

```html
{% load i18n %}
<div class="modal fade" id="createFiberCableModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">{% trans "Create FiberCable" %}</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            {% if already_exists %}
            <div class="modal-body">
                <div class="alert alert-info mb-0">
                    {% trans "A FiberCable already exists for this cable." %}
                </div>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{% trans "Close" %}</button>
            </div>
            {% else %}
            <form hx-post="{{ post_url }}" hx-target="#modal-container" hx-swap="innerHTML">
                {% csrf_token %}
                <div class="modal-body">
                    <input type="hidden" name="cable_id" value="{{ cable.pk }}">
                    {% if form.errors %}
                    <div class="alert alert-danger">
                        {% for field, errors in form.errors.items %}
                            {% for error in errors %}<p>{{ error }}</p>{% endfor %}
                        {% endfor %}
                    </div>
                    {% endif %}
                    <div class="mb-3">
                        <label class="form-label">{% trans "Cable" %}</label>
                        <input type="text" class="form-control" value="{{ cable }}" disabled>
                    </div>
                    <div class="mb-3">
                        <label for="id_fiber_cable_type" class="form-label">{% trans "Fiber Cable Type" %} *</label>
                        {{ form.fiber_cable_type }}
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{% trans "Cancel" %}</button>
                    <button type="submit" class="btn btn-primary">{% trans "Create" %}</button>
                </div>
            </form>
            {% endif %}
        </div>
    </div>
</div>
<script>
    (() => {
        const el = document.getElementById('createFiberCableModal');
        new bootstrap.Modal(el).show();
        el.addEventListener('hidden.bs.modal', () => el.remove());
    })();
</script>
```

- [ ] **Step 4: Implement CreateFiberCableFromCableView**

In `netbox_fms/views.py`, replace the placeholder:

```python
class CreateFiberCableFromCableView(LoginRequiredMixin, View):
    def get(self, request, pk):
        if not request.user.has_perm("netbox_fms.add_fibercable"):
            return HttpResponse("Permission denied", status=403)
        device = get_object_or_404(Device, pk=pk)
        cable_id = request.GET.get("cable_id")
        cable = get_object_or_404(Cable, pk=cable_id)

        already_exists = FiberCable.objects.filter(cable=cable).exists()

        form = None
        if not already_exists:
            form = CreateFiberCableFromCableForm()

        return render(request, "netbox_fms/htmx/create_fiber_cable_modal.html", {
            "device": device,
            "cable": cable,
            "already_exists": already_exists,
            "form": form,
            "post_url": reverse("plugins:netbox_fms:fiber_overview_create_fibercable", kwargs={"pk": pk}),
        })

    @transaction.atomic
    def post(self, request, pk):
        if not request.user.has_perm("netbox_fms.add_fibercable"):
            return HttpResponse("Permission denied", status=403)
        device = get_object_or_404(Device, pk=pk)
        form = CreateFiberCableFromCableForm(request.POST)
        if not form.is_valid():
            cable = get_object_or_404(Cable, pk=request.POST.get("cable_id"))
            return render(request, "netbox_fms/htmx/create_fiber_cable_modal.html", {
                "device": device,
                "cable": cable,
                "already_exists": False,
                "form": form,
                "post_url": reverse("plugins:netbox_fms:fiber_overview_create_fibercable", kwargs={"pk": pk}),
            })

        cable = get_object_or_404(Cable, pk=form.cleaned_data["cable_id"])
        FiberCable.objects.create(
            cable=cable,
            fiber_cable_type=form.cleaned_data["fiber_cable_type"],
        )

        redirect_url = reverse("dcim:device", kwargs={"pk": pk}) + "fiber-overview/"
        response = HttpResponse(status=200)
        response["HX-Redirect"] = redirect_url
        return response
```

Add the form class to `netbox_fms/forms.py` and import it in `views.py` (`from .forms import ..., CreateFiberCableFromCableForm`):

```python
class CreateFiberCableFromCableForm(forms.Form):
    cable_id = forms.IntegerField(widget=forms.HiddenInput)
    fiber_cable_type = DynamicModelChoiceField(
        queryset=FiberCableType.objects.all(),
        label=_("Fiber Cable Type"),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_overview.py::TestCreateFiberCableAction -v
```

Expected: All 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add netbox_fms/views.py netbox_fms/forms.py netbox_fms/templates/netbox_fms/htmx/create_fiber_cable_modal.html tests/test_fiber_overview.py
git commit -m "feat: implement CreateFiberCable HTMX modal action"
```

---

### Task 8: ProvisionStrandsFromOverviewView + Modal Template

Implement the Provision Strands HTMX modal action.

**Files:**
- Modify: `netbox_fms/views.py` (replace placeholder)
- Modify: `netbox_fms/forms.py`
- Create: `netbox_fms/templates/netbox_fms/htmx/provision_strands_modal.html`
- Test: `tests/test_fiber_overview.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_fiber_overview.py`:

```python
class TestProvisionStrandsAction(TestCase):
    @classmethod
    def setUpTestData(cls):
        from dcim.models import RearPort, Module, ModuleBay, ModuleType, CableTermination, FrontPort
        from django.contrib.contenttypes.models import ContentType

        site = Site.objects.create(name="PS Site", slug="ps-site")
        manufacturer = Manufacturer.objects.create(name="PS Mfr", slug="ps-mfr")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="PS Closure", slug="ps-closure")
        role = DeviceRole.objects.create(name="PS Role", slug="ps-role")
        cls.device = Device.objects.create(name="PS-Closure", site=site, device_type=device_type, role=role)

        module_type = ModuleType.objects.create(manufacturer=manufacturer, model="PS Tray")
        bay = ModuleBay.objects.create(device=cls.device, name="PS Bay")
        cls.module = Module.objects.create(device=cls.device, module_bay=bay, module_type=module_type)

        cls.rearport = RearPort.objects.create(device=cls.device, module=cls.module, name="PS-RP1", type="splice", positions=1)
        cls.cable = Cable.objects.create()

        rp_ct = ContentType.objects.get_for_model(RearPort)
        CableTermination.objects.create(
            cable=cls.cable,
            termination_type=rp_ct,
            termination_id=cls.rearport.pk,
            cable_end="A",
        )

        fct = FiberCableType.objects.create(
            manufacturer=manufacturer, model="PS-FCT", construction="loose_tube",
            fiber_type="smf_os2", strand_count=4,
        )
        cls.fiber_cable = FiberCable.objects.create(cable=cls.cable, fiber_cable_type=fct)

        cls.user = User.objects.create_user(username="ps_testuser", password="testpass", is_superuser=True)

    def test_get_returns_modal_form(self):
        self.client.force_login(self.user)
        url = f"/plugins/netbox-fms/fiber-overview/{self.device.pk}/provision-strands/?fiber_cable_id={self.fiber_cable.pk}"
        response = self.client.get(url)
        assert response.status_code == 200
        assert b"modal" in response.content

    def test_post_provisions_strands_on_module(self):
        from dcim.models import FrontPort

        self.client.force_login(self.user)
        url = f"/plugins/netbox-fms/fiber-overview/{self.device.pk}/provision-strands/"
        response = self.client.post(url, {
            "fiber_cable_id": self.fiber_cable.pk,
            "target_module": self.module.pk,
            "port_type": "splice",
        })
        assert response.status_code == 200
        assert response.has_header("HX-Redirect")

        # Verify FrontPorts created on module
        fps = FrontPort.objects.filter(device=self.device, module=self.module)
        assert fps.count() == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_overview.py::TestProvisionStrandsAction -v
```

Expected: FAIL — placeholder returns 501.

- [ ] **Step 3: Add the form**

In `netbox_fms/forms.py`, add (note: `Module` is already imported at the top of `forms.py`). Also import this form in `views.py` (`from .forms import ..., ProvisionStrandsFromOverviewForm`):

```python
class ProvisionStrandsFromOverviewForm(forms.Form):
    fiber_cable_id = forms.IntegerField(widget=forms.HiddenInput)
    target_module = DynamicModelChoiceField(
        queryset=Module.objects.all(),
        label=_("Target Module (Tray)"),
    )
    port_type = forms.ChoiceField(
        choices=PORT_TYPE_CHOICES,
        label=_("Port Type"),
        initial="splice",
    )
```

- [ ] **Step 4: Create the modal template**

Create `netbox_fms/templates/netbox_fms/htmx/provision_strands_modal.html`:

```html
{% load i18n %}
<div class="modal fade" id="provisionStrandsModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">{% trans "Provision Strands" %}</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <form hx-post="{{ post_url }}" hx-target="#modal-container" hx-swap="innerHTML">
                {% csrf_token %}
                <div class="modal-body">
                    <input type="hidden" name="fiber_cable_id" value="{{ fiber_cable.pk }}">
                    {% if error_message %}
                    <div class="alert alert-danger">{{ error_message }}</div>
                    {% endif %}
                    {% if form.errors %}
                    <div class="alert alert-danger">
                        {% for field, errors in form.errors.items %}
                            {% for error in errors %}<p>{{ error }}</p>{% endfor %}
                        {% endfor %}
                    </div>
                    {% endif %}
                    <div class="mb-3">
                        <label class="form-label">{% trans "Fiber Cable" %}</label>
                        <input type="text" class="form-control" value="{{ fiber_cable }}" disabled>
                    </div>
                    <div class="mb-3">
                        <label for="id_target_module" class="form-label">{% trans "Target Module (Tray)" %} *</label>
                        {{ form.target_module }}
                    </div>
                    <div class="mb-3">
                        <label for="id_port_type" class="form-label">{% trans "Port Type" %}</label>
                        {{ form.port_type }}
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{% trans "Cancel" %}</button>
                    <button type="submit" class="btn btn-primary">{% trans "Provision" %}</button>
                </div>
            </form>
        </div>
    </div>
</div>
<script>
    (() => {
        const el = document.getElementById('provisionStrandsModal');
        new bootstrap.Modal(el).show();
        el.addEventListener('hidden.bs.modal', () => el.remove());
    })();
</script>
```

- [ ] **Step 5: Implement ProvisionStrandsFromOverviewView**

In `netbox_fms/views.py`, replace the placeholder:

```python
class ProvisionStrandsFromOverviewView(LoginRequiredMixin, View):
    def get(self, request, pk):
        if not request.user.has_perm("dcim.add_frontport"):
            return HttpResponse("Permission denied", status=403)
        device = get_object_or_404(Device, pk=pk)
        fiber_cable_id = request.GET.get("fiber_cable_id")
        fiber_cable = get_object_or_404(FiberCable, pk=fiber_cable_id)

        # Pre-fill target_module with the module of the RearPort the cable terminates on
        initial = {"fiber_cable_id": fiber_cable.pk}
        if fiber_cable.cable:
            from dcim.models import CableTermination, RearPort
            from django.contrib.contenttypes.models import ContentType
            rp_ct = ContentType.objects.get_for_model(RearPort)
            term = CableTermination.objects.filter(
                cable=fiber_cable.cable,
                termination_type=rp_ct,
            ).select_related("termination").first()
            if term:
                rp = RearPort.objects.filter(pk=term.termination_id).select_related("module").first()
                if rp and rp.module:
                    initial["target_module"] = rp.module.pk

        form = ProvisionStrandsFromOverviewForm(initial=initial)
        # Filter modules to this device
        form.fields["target_module"].queryset = Module.objects.filter(device=device)

        return render(request, "netbox_fms/htmx/provision_strands_modal.html", {
            "device": device,
            "fiber_cable": fiber_cable,
            "form": form,
            "post_url": reverse("plugins:netbox_fms:fiber_overview_provision_strands", kwargs={"pk": pk}),
        })

    def post(self, request, pk):
        if not request.user.has_perm("dcim.add_frontport"):
            return HttpResponse("Permission denied", status=403)
        device = get_object_or_404(Device, pk=pk)
        form = ProvisionStrandsFromOverviewForm(request.POST)
        form.fields["target_module"].queryset = Module.objects.filter(device=device)

        fiber_cable_id = request.POST.get("fiber_cable_id")
        fiber_cable = get_object_or_404(FiberCable, pk=fiber_cable_id)

        if not form.is_valid():
            return render(request, "netbox_fms/htmx/provision_strands_modal.html", {
                "device": device,
                "fiber_cable": fiber_cable,
                "form": form,
                "post_url": reverse("plugins:netbox_fms:fiber_overview_provision_strands", kwargs={"pk": pk}),
            })

        module = form.cleaned_data["target_module"]
        port_type = form.cleaned_data["port_type"]

        # Check already provisioned
        already = fiber_cable.fiber_strands.filter(front_port__device=device).exists()
        if already:
            return render(request, "netbox_fms/htmx/provision_strands_modal.html", {
                "device": device,
                "fiber_cable": fiber_cable,
                "form": form,
                "error_message": _("Strands are already provisioned on this device."),
                "post_url": reverse("plugins:netbox_fms:fiber_overview_provision_strands", kwargs={"pk": pk}),
            })

        try:
            provision_strands(fiber_cable, device, port_type, module=module)
        except ValueError as e:
            return render(request, "netbox_fms/htmx/provision_strands_modal.html", {
                "device": device,
                "fiber_cable": fiber_cable,
                "form": form,
                "error_message": str(e),
                "post_url": reverse("plugins:netbox_fms:fiber_overview_provision_strands", kwargs={"pk": pk}),
            })

        redirect_url = reverse("dcim:device", kwargs={"pk": pk}) + "fiber-overview/"
        response = HttpResponse(status=200)
        response["HX-Redirect"] = redirect_url
        return response
```

- [ ] **Step 6: Run tests to verify they pass**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_overview.py::TestProvisionStrandsAction -v
```

Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add netbox_fms/views.py netbox_fms/forms.py netbox_fms/templates/netbox_fms/htmx/provision_strands_modal.html tests/test_fiber_overview.py
git commit -m "feat: implement Provision Strands HTMX modal action"
```

---

### Task 9: UpdateGlandLabelView + Modal Template

Implement the Edit Gland Label HTMX modal action with in-place row swap.

**Files:**
- Modify: `netbox_fms/views.py` (replace placeholder)
- Create: `netbox_fms/templates/netbox_fms/htmx/edit_gland_modal.html`
- Test: `tests/test_fiber_overview.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_fiber_overview.py`:

```python
class TestUpdateGlandLabelAction(TestCase):
    @classmethod
    def setUpTestData(cls):
        from dcim.models import RearPort, Module, ModuleBay, ModuleType

        site = Site.objects.create(name="GL Site", slug="gl-site")
        manufacturer = Manufacturer.objects.create(name="GL Mfr", slug="gl-mfr")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="GL Closure", slug="gl-closure")
        role = DeviceRole.objects.create(name="GL Role", slug="gl-role")
        cls.device = Device.objects.create(name="GL-Closure", site=site, device_type=device_type, role=role)

        module_type = ModuleType.objects.create(manufacturer=manufacturer, model="GL Tray")
        bay = ModuleBay.objects.create(device=cls.device, name="GL Bay")
        cls.module = Module.objects.create(device=cls.device, module_bay=bay, module_type=module_type)

        cls.rearport = RearPort.objects.create(device=cls.device, module=cls.module, name="GL-RP1", type="splice", positions=1)

        fct = FiberCableType.objects.create(
            manufacturer=manufacturer, model="GL-FCT", construction="loose_tube",
            fiber_type="smf_os2", strand_count=4,
        )
        cable = Cable.objects.create()
        cls.fiber_cable = FiberCable.objects.create(cable=cable, fiber_cable_type=fct)

        cls.user = User.objects.create_user(username="gl_testuser", password="testpass", is_superuser=True)

    def test_get_returns_modal_form(self):
        self.client.force_login(self.user)
        url = (
            f"/plugins/netbox-fms/fiber-overview/{self.device.pk}/update-gland/"
            f"?fiber_cable_id={self.fiber_cable.pk}&rearport_id={self.rearport.pk}"
        )
        response = self.client.get(url)
        assert response.status_code == 200
        assert b"modal" in response.content

    def test_post_creates_closure_cable_entry(self):
        from netbox_fms.models import ClosureCableEntry

        self.client.force_login(self.user)
        url = f"/plugins/netbox-fms/fiber-overview/{self.device.pk}/update-gland/"
        response = self.client.post(url, {
            "fiber_cable_id": self.fiber_cable.pk,
            "rearport_id": self.rearport.pk,
            "entrance_label": "Gland X",
        })
        assert response.status_code == 200
        assert b"<tr" in response.content  # Returns row fragment

        entry = ClosureCableEntry.objects.get(closure=self.device, fiber_cable=self.fiber_cable)
        assert entry.entrance_label == "Gland X"

    def test_post_updates_existing_entry(self):
        from netbox_fms.models import ClosureCableEntry

        ClosureCableEntry.objects.create(
            closure=self.device,
            fiber_cable=self.fiber_cable,
            entrance_label="Old Label",
        )

        self.client.force_login(self.user)
        url = f"/plugins/netbox-fms/fiber-overview/{self.device.pk}/update-gland/"
        response = self.client.post(url, {
            "fiber_cable_id": self.fiber_cable.pk,
            "rearport_id": self.rearport.pk,
            "entrance_label": "New Label",
        })
        assert response.status_code == 200

        entry = ClosureCableEntry.objects.get(closure=self.device, fiber_cable=self.fiber_cable)
        assert entry.entrance_label == "New Label"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_overview.py::TestUpdateGlandLabelAction -v
```

Expected: FAIL — placeholder returns 501.

- [ ] **Step 3: Create the modal template**

Create `netbox_fms/templates/netbox_fms/htmx/edit_gland_modal.html`:

```html
{% load i18n %}
<div class="modal fade" id="editGlandModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">{% trans "Edit Gland Label" %}</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <form hx-post="{{ post_url }}"
                  hx-target="#row-rp-{{ rearport_id }}" hx-swap="outerHTML">
                {% csrf_token %}
                <div class="modal-body">
                    <input type="hidden" name="fiber_cable_id" value="{{ fiber_cable.pk }}">
                    <input type="hidden" name="rearport_id" value="{{ rearport_id }}">
                    <div class="mb-3">
                        <label class="form-label">{% trans "Fiber Cable" %}</label>
                        <input type="text" class="form-control" value="{{ fiber_cable }}" disabled>
                    </div>
                    <div class="mb-3">
                        <label for="id_entrance_label" class="form-label">{% trans "Entrance Label" %}</label>
                        <input type="text" class="form-control" id="id_entrance_label"
                               name="entrance_label" value="{{ current_label }}" maxlength="100"
                               placeholder="e.g. Gland A">
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{% trans "Cancel" %}</button>
                    <button type="submit" class="btn btn-primary">{% trans "Save" %}</button>
                </div>
            </form>
        </div>
    </div>
</div>
<script>
    (() => {
        const el = document.getElementById('editGlandModal');
        const modal = new bootstrap.Modal(el);
        modal.show();
        el.addEventListener('hidden.bs.modal', () => el.remove());
    })();
</script>
```

- [ ] **Step 4: Implement UpdateGlandLabelView**

In `netbox_fms/views.py`, replace the placeholder:

```python
class UpdateGlandLabelView(LoginRequiredMixin, View):
    def get(self, request, pk):
        if not request.user.has_perm("netbox_fms.change_closurecableentry") and not request.user.has_perm("netbox_fms.add_closurecableentry"):
            return HttpResponse("Permission denied", status=403)
        device = get_object_or_404(Device, pk=pk)
        fiber_cable_id = request.GET.get("fiber_cable_id")
        fiber_cable = get_object_or_404(FiberCable, pk=fiber_cable_id)
        rearport_id = request.GET.get("rearport_id")

        entry = ClosureCableEntry.objects.filter(
            closure=device, fiber_cable=fiber_cable
        ).first()
        current_label = entry.entrance_label if entry else ""

        return render(request, "netbox_fms/htmx/edit_gland_modal.html", {
            "device": device,
            "fiber_cable": fiber_cable,
            "rearport_id": rearport_id,
            "current_label": current_label,
            "post_url": reverse("plugins:netbox_fms:fiber_overview_update_gland", kwargs={"pk": pk}),
        })

    def post(self, request, pk):
        if not request.user.has_perm("netbox_fms.change_closurecableentry") and not request.user.has_perm("netbox_fms.add_closurecableentry"):
            return HttpResponse("Permission denied", status=403)
        device = get_object_or_404(Device, pk=pk)
        fiber_cable_id = request.POST.get("fiber_cable_id")
        fiber_cable = get_object_or_404(FiberCable, pk=fiber_cable_id)
        rearport_id = request.POST.get("rearport_id")
        entrance_label = request.POST.get("entrance_label", "").strip()

        entry, _created = ClosureCableEntry.objects.update_or_create(
            closure=device,
            fiber_cable=fiber_cable,
            defaults={"entrance_label": entrance_label},
        )

        # Return the updated row partial — dismiss modal via HX-Trigger
        from dcim.models import RearPort
        rearport = get_object_or_404(RearPort, pk=rearport_id)
        row = _build_cable_row(device, rearport)

        response = render(request, "netbox_fms/htmx/fiber_overview_row.html", {
            "device": device,
            "row": row,
        })
        response["HX-Trigger"] = "modalClose"
        return response
```

Add a small script to the main overview template to handle `modalClose` events. Add before the closing `{% endblock %}` in `device_fiber_overview.html`:

```html
<script>
    document.body.addEventListener('modalClose', () => {
        const modal = document.querySelector('.modal.show');
        if (modal) bootstrap.Modal.getInstance(modal)?.hide();
    });
</script>
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_overview.py::TestUpdateGlandLabelAction -v
```

Expected: All 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add netbox_fms/views.py netbox_fms/templates/netbox_fms/htmx/edit_gland_modal.html netbox_fms/templates/netbox_fms/device_fiber_overview.html tests/test_fiber_overview.py
git commit -m "feat: implement Edit Gland Label HTMX modal with in-place row swap"
```

---

### Task 10: Navigation Cleanup

Remove Splice Entries, Cable Entries, and Provision Ports from the plugin menu.

**Files:**
- Modify: `netbox_fms/navigation.py`
- Test: `tests/test_fiber_overview.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_fiber_overview.py`:

```python
class TestNavigationCleanup(TestCase):
    def test_removed_items_not_in_menu(self):
        from netbox_fms.navigation import menu

        link_texts = []
        for group_name, items in menu.groups:
            for item in items:
                link_texts.append(item.link_text)

        assert "Splice Entries" not in link_texts
        assert "Cable Entries" not in link_texts
        assert "Provision Ports" not in link_texts

    def test_kept_items_in_menu(self):
        from netbox_fms.navigation import menu

        link_texts = []
        for group_name, items in menu.groups:
            for item in items:
                link_texts.append(item.link_text)

        assert "Fiber Cable Types" in link_texts
        assert "Fiber Cables" in link_texts
        assert "Splice Projects" in link_texts
        assert "Splice Plans" in link_texts
        assert "Fiber Path Losses" in link_texts
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_overview.py::TestNavigationCleanup -v
```

Expected: FAIL — removed items still present.

- [ ] **Step 3: Update navigation.py**

Read `netbox_fms/navigation.py` and remove the `PluginMenuItem` entries for:
- "Splice Entries" (the one with `link="plugins:netbox_fms:spliceplanentry_list"`)
- "Cable Entries" (the one with `link="plugins:netbox_fms:closurecableentry_list"`)
- "Provision Ports" (the one with `link="plugins:netbox_fms:provision_ports"`)

Keep all other entries. The resulting "Splice Planning" group should only have "Splice Projects" and "Splice Plans".

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_fiber_overview.py::TestNavigationCleanup -v
```

Expected: Both tests PASS.

- [ ] **Step 5: Run ALL tests to verify no regressions**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add netbox_fms/navigation.py tests/test_fiber_overview.py
git commit -m "feat: remove Splice Entries, Cable Entries, Provision Ports from plugin menu"
```

---

### Task 11: Final Integration Test

Run all tests, verify imports, verify the full feature works end-to-end.

**Files:**
- No new files

- [ ] **Step 1: Verify all modules import cleanly**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "
import django; django.setup()
from netbox_fms.models import *
from netbox_fms.forms import *
from netbox_fms.filters import *
from netbox_fms.tables import *
from netbox_fms.api.serializers import *
from netbox_fms.views import (
    _device_has_modules_or_fiber_cables,
    _build_cable_row,
    provision_strands,
    DeviceFiberOverviewView,
    CreateFiberCableFromCableView,
    ProvisionStrandsFromOverviewView,
    UpdateGlandLabelView,
)
print('All imports OK')
"
```

Expected: "All imports OK"

- [ ] **Step 2: Run full test suite**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v
```

Expected: All tests pass.

- [ ] **Step 3: Run linting**

Run:
```bash
cd /opt/netbox-fms && ruff check netbox_fms/ && ruff format --check netbox_fms/
```

Expected: No errors.

- [ ] **Step 4: Fix any lint issues and commit if needed**

If lint issues found:
```bash
cd /opt/netbox-fms && ruff check --fix netbox_fms/ && ruff format netbox_fms/
git add -u && git commit -m "style: fix lint issues"
```
