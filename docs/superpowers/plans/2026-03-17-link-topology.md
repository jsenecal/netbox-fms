# Link/Define Cable Topology Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken "Create FiberCable" + "Provision Strands" two-step flow with a single "Link Topology" action that correctly adopts existing ports or creates new ones, using tube-level RearPorts and trunk cable profiles.

**Architecture:** Expand cable profile registry with trunk profiles, add `get_cable_profile()` to FiberCableType, create `link_cable_topology()` service function that handles adopt-or-create logic, replace the two old modal views with one `LinkTopologyView`. FiberStrand gets `front_port_a`/`front_port_b` FKs for A/B cable sides.

**Tech Stack:** Django 5.2, NetBox 4.5+ plugin API, HTMX modals, PostgreSQL

**Spec:** `docs/superpowers/specs/2026-03-17-link-topology-redesign.md`

---

## File Map

| File | Changes |
|------|---------|
| `netbox_fms/models.py` | Rename `front_port` → `front_port_a`, add `front_port_b`. Fix `get_strand_count_from_templates()`. Add `get_cable_profile()`. |
| `netbox_fms/migrations/0013_*.py` | 3-step migration: add `front_port_a`, copy data, drop `front_port`, add `front_port_b` |
| `netbox_fms/cable_profiles.py` | Add trunk profile classes, expand `FIBER_CABLE_PROFILES` registry |
| `netbox_fms/monkey_patches.py` | Update choice group labels for trunk profiles |
| `netbox_fms/services.py` | Add `NeedsMappingConfirmation`, `propose_port_mapping()`, `link_cable_topology()` |
| `netbox_fms/views.py` | Add `LinkTopologyView`, rewrite `_build_cable_rows()`, remove old views |
| `netbox_fms/forms.py` | Add `LinkTopologyForm`, remove old forms |
| `netbox_fms/urls.py` | Add link-topology URL, remove old URLs |
| `netbox_fms/templates/netbox_fms/htmx/link_topology_modal.html` | New: FiberCableType selection + profile warning |
| `netbox_fms/templates/netbox_fms/htmx/link_topology_confirm.html` | New: port mapping confirmation table |
| `netbox_fms/templates/netbox_fms/htmx/fiber_overview_row.html` | Update: single "Link Topology" button |
| `netbox_fms/templates/netbox_fms/device_fiber_overview.html` | Update: row grouping by cable |
| `netbox_fms/api/serializers.py` | Update `front_port` → `front_port_a`/`front_port_b` |
| `netbox_fms/api/views.py` | Update `front_port` references |
| `netbox_fms/tables.py` | Update `front_port` column |
| `netbox_fms/filters.py` | Update `front_port` filter |
| `netbox_fms/export.py` | Update `front_port` references |
| `tests/test_link_topology.py` | New: tests for all new functionality |
| `tests/test_models.py` | Update: `front_port` → `front_port_a` in existing tests |

---

## Chunk 1: Prerequisite Fixes & FiberStrand Migration

### Task 1: Fix `get_strand_count_from_templates()` for ribbon-in-tube

**Files:**
- Modify: `netbox_fms/models.py:158-168`
- Test: `tests/test_link_topology.py`

**Why:** The current method uses `Sum("fiber_count")` which returns 0 for ribbon-in-tube tubes (where `fiber_count` is NULL). This breaks `clean()` validation for ribbon-in-tube FiberCableTypes.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_link_topology.py
import pytest
from dcim.models import Manufacturer
from netbox_fms.models import BufferTubeTemplate, FiberCableType, RibbonTemplate


@pytest.mark.django_db
class TestGetStrandCountFromTemplates:
    def test_ribbon_in_tube_counts_correctly(self):
        mfr = Manufacturer.objects.create(name="RIT-Mfr", slug="rit-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="RIT-24F",
            strand_count=24,
            fiber_type="smf_os2",
            construction="ribbon_in_tube",
        )
        btt = BufferTubeTemplate.objects.create(
            fiber_cable_type=fct,
            name="T1",
            position=1,
            fiber_count=None,
        )
        RibbonTemplate.objects.create(
            fiber_cable_type=fct,
            buffer_tube_template=btt,
            name="R1",
            position=1,
            fiber_count=12,
        )
        RibbonTemplate.objects.create(
            fiber_cable_type=fct,
            buffer_tube_template=btt,
            name="R2",
            position=2,
            fiber_count=12,
        )

        assert fct.get_strand_count_from_templates() == 24

    def test_loose_tube_counts_correctly(self):
        mfr = Manufacturer.objects.create(name="LT-Mfr", slug="lt-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr,
            model="LT-48F",
            strand_count=48,
            fiber_type="smf_os2",
            construction="loose_tube",
        )
        for i in range(1, 5):
            BufferTubeTemplate.objects.create(
                fiber_cable_type=fct,
                name=f"T{i}",
                position=i,
                fiber_count=12,
            )

        assert fct.get_strand_count_from_templates() == 48
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_link_topology.py::TestGetStrandCountFromTemplates::test_ribbon_in_tube_counts_correctly -v`
Expected: FAIL — returns 0 instead of 24

- [ ] **Step 3: Fix `get_strand_count_from_templates()`**

In `netbox_fms/models.py`, replace the method at line 158-161:

```python
    def get_strand_count_from_templates(self):
        """Compute total fiber count from buffer tube templates."""
        return sum(
            btt.get_total_fiber_count()
            for btt in self.buffer_tube_templates.all()
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_link_topology.py::TestGetStrandCountFromTemplates -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/models.py tests/test_link_topology.py
git commit -m "fix: get_strand_count_from_templates handles ribbon-in-tube"
```

---

### Task 2: Rename `front_port` to `front_port_a` and add `front_port_b` (3-step migration)

**Files:**
- Modify: `netbox_fms/models.py:673-681`
- Create: `netbox_fms/migrations/0013_fiberstrand_front_port_a.py`
- Create: `netbox_fms/migrations/0014_populate_front_port_a.py`
- Create: `netbox_fms/migrations/0015_drop_front_port_add_front_port_b.py`

**Why:** FiberStrand needs to track both cable ends. The existing `front_port` FK becomes `front_port_a` (A-side), and a new `front_port_b` FK is added for B-side.

- [ ] **Step 1: Add `front_port_a` field (keeping `front_port` temporarily)**

In `netbox_fms/models.py`, add after the existing `front_port` field (line 681):

```python
    front_port_a = models.ForeignKey(
        to="dcim.FrontPort",
        on_delete=models.SET_NULL,
        related_name="fiber_strands_a",
        blank=True,
        null=True,
        verbose_name=_("front port (A-side)"),
        help_text=_("The dcim FrontPort on the cable's A-side termination."),
    )
```

- [ ] **Step 2: Generate migration**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py makemigrations netbox_fms -n fiberstrand_front_port_a`

- [ ] **Step 3: Create data migration to copy front_port → front_port_a**

Create `netbox_fms/migrations/0014_populate_front_port_a.py`:

```python
from django.db import migrations


def copy_front_port(apps, schema_editor):
    FiberStrand = apps.get_model("netbox_fms", "FiberStrand")
    FiberStrand.objects.filter(front_port__isnull=False).update(front_port_a=models.F("front_port"))


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_fms", "0013_fiberstrand_front_port_a"),
    ]
    operations = [
        migrations.RunPython(copy_front_port, noop),
    ]
```

Note: The data migration should use `F()` expression for efficient bulk update. Import `models` from `django.db` at the top.

- [ ] **Step 4: Apply migrations**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py migrate netbox_fms`

- [ ] **Step 5: Remove old `front_port` field, add `front_port_b`**

In `netbox_fms/models.py`, remove the old `front_port` FK (lines 673-681) and add `front_port_b`:

```python
    front_port_a = models.ForeignKey(
        to="dcim.FrontPort",
        on_delete=models.SET_NULL,
        related_name="fiber_strands_a",
        blank=True,
        null=True,
        verbose_name=_("front port (A-side)"),
        help_text=_("The dcim FrontPort on the cable's A-side termination."),
    )
    front_port_b = models.ForeignKey(
        to="dcim.FrontPort",
        on_delete=models.SET_NULL,
        related_name="fiber_strands_b",
        blank=True,
        null=True,
        verbose_name=_("front port (B-side)"),
        help_text=_("The dcim FrontPort on the cable's B-side termination."),
    )
```

- [ ] **Step 6: Generate migration for drop + add**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py makemigrations netbox_fms -n drop_front_port_add_front_port_b`

- [ ] **Step 7: Apply migration**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py migrate netbox_fms`

- [ ] **Step 8: Commit**

```bash
git add netbox_fms/models.py netbox_fms/migrations/0013_*.py netbox_fms/migrations/0014_*.py netbox_fms/migrations/0015_*.py
git commit -m "feat: rename front_port to front_port_a, add front_port_b for cable A/B sides"
```

---

### Task 3: Update all `front_port` references across codebase

**Files:**
- Modify: `netbox_fms/views.py` (8 occurrences)
- Modify: `netbox_fms/api/serializers.py` (3 occurrences)
- Modify: `netbox_fms/api/views.py` (17 occurrences)
- Modify: `netbox_fms/tables.py` (3 occurrences)
- Modify: `netbox_fms/filters.py` (2 occurrences)
- Modify: `netbox_fms/export.py` (2 occurrences)
- Modify: `netbox_fms/static/netbox_fms/src/state.ts` (3 occurrences)
- Modify: `netbox_fms/static/netbox_fms/src/types.ts` (4 occurrences)
- Modify: `netbox_fms/management/commands/create_sample_data.py` (4 occurrences)
- Modify: `tests/test_models.py`

**Why:** All references to `front_port` on FiberStrand must be updated to `front_port_a` (or both `front_port_a`/`front_port_b` where appropriate).

- [ ] **Step 1: Update views.py**

Replace `front_port` with `front_port_a` in:
- `provision_strands()` function (line 578): `strand.front_port = fp` → `strand.front_port_a = fp`
- `provision_strands()` function (line 579): `save(update_fields=["front_port"])` → `save(update_fields=["front_port_a"])`
- `_build_cable_rows()` (line 696): `front_port__device=device` → use `Q(front_port_a__device=device) | Q(front_port_b__device=device)`
- `ProvisionStrandsFromOverviewView` (line 972): `front_port__device=device` → same Q pattern

- [ ] **Step 2: Update api/serializers.py**

In `FiberStrandSerializer`, replace `front_port` field with `front_port_a` and `front_port_b`.

- [ ] **Step 3: Update api/views.py**

Replace all `front_port` filter references with `front_port_a` (or appropriate A/B logic).

- [ ] **Step 4: Update tables.py**

Replace `front_port` column with `front_port_a` column (and optionally add `front_port_b`).

- [ ] **Step 5: Update filters.py**

Replace `front_port` filter field with `front_port_a`.

- [ ] **Step 6: Update export.py**

Replace `front_port` references.

- [ ] **Step 7: Update TypeScript files**

Replace `front_port` in `state.ts` and `types.ts`.

- [ ] **Step 8: Update create_sample_data.py**

Replace `front_port` references.

- [ ] **Step 9: Update tests/test_models.py**

Replace `front_port` references with `front_port_a`.

- [ ] **Step 10: Verify import is clean**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.models import *; from netbox_fms.forms import *; from netbox_fms.filters import *"`
Expected: No errors

- [ ] **Step 11: Run full test suite**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v`
Expected: All pass

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "refactor: update all front_port references to front_port_a/front_port_b"
```

---

## Chunk 2: Cable Profile Expansion

### Task 4: Add trunk profile classes and expand registry

**Files:**
- Modify: `netbox_fms/cable_profiles.py`
- Test: `tests/test_link_topology.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_link_topology.py (append to existing file)
from netbox_fms.cable_profiles import FIBER_CABLE_PROFILES


@pytest.mark.django_db
class TestCableProfileRegistry:
    def test_single_connector_profiles_exist(self):
        for count in [24, 48, 72, 96, 144, 216, 288, 432]:
            key = f"single-1c{count}p"
            assert key in FIBER_CABLE_PROFILES, f"Missing profile: {key}"
            _label, cls = FIBER_CABLE_PROFILES[key]
            assert cls.a_connectors == {1: count}
            assert cls.b_connectors == cls.a_connectors

    def test_trunk_12_connector_profiles_exist(self):
        for connectors in [2, 4, 6, 8, 12, 18, 24]:
            key = f"trunk-{connectors}c12p"
            assert key in FIBER_CABLE_PROFILES, f"Missing profile: {key}"
            _label, cls = FIBER_CABLE_PROFILES[key]
            assert len(cls.a_connectors) == connectors
            assert all(v == 12 for v in cls.a_connectors.values())
            assert cls.b_connectors == cls.a_connectors

    def test_trunk_24_connector_profiles_exist(self):
        for connectors in [2, 4, 6, 12]:
            key = f"trunk-{connectors}c24p"
            assert key in FIBER_CABLE_PROFILES, f"Missing profile: {key}"
            _label, cls = FIBER_CABLE_PROFILES[key]
            assert len(cls.a_connectors) == connectors
            assert all(v == 24 for v in cls.a_connectors.values())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_link_topology.py::TestCableProfileRegistry -v`
Expected: FAIL — trunk profiles don't exist

- [ ] **Step 3: Add trunk profile classes**

In `netbox_fms/cable_profiles.py`, add a factory function and generate trunk profiles:

```python
def _make_trunk_profile(connectors, positions):
    """Create a trunk cable profile class dynamically."""
    conns = {i: positions for i in range(1, connectors + 1)}
    return type(
        f"Trunk{connectors}C{positions}PCableProfile",
        (BaseCableProfile,),
        {"a_connectors": conns, "b_connectors": conns},
    )


# Trunk profiles: multi-connector
_TRUNK_CONFIGS = [
    # (connectors, positions_per_connector)
    (2, 12), (4, 12), (6, 12), (8, 12), (12, 12), (18, 12), (24, 12),
    (2, 24), (4, 24), (6, 24), (12, 24),
]

FIBER_CABLE_PROFILES = {
    # Single-connector (existing)
    "single-1c24p": ("1C24P", Single1C24PCableProfile),
    "single-1c48p": ("1C48P", Single1C48PCableProfile),
    "single-1c72p": ("1C72P", Single1C72PCableProfile),
    "single-1c96p": ("1C96P", Single1C96PCableProfile),
    "single-1c144p": ("1C144P", Single1C144PCableProfile),
    "single-1c216p": ("1C216P", Single1C216PCableProfile),
    "single-1c288p": ("1C288P", Single1C288PCableProfile),
    "single-1c432p": ("1C432P", Single1C432PCableProfile),
}

# Add trunk profiles to registry
for _c, _p in _TRUNK_CONFIGS:
    _key = f"trunk-{_c}c{_p}p"
    _label = f"{_c}C{_p}P"
    FIBER_CABLE_PROFILES[_key] = (_label, _make_trunk_profile(_c, _p))
```

- [ ] **Step 4: Update monkey_patches.py choice groups**

In `netbox_fms/monkey_patches.py`, split choices into two groups:

```python
def patch_cable_profiles():
    single_choices = tuple(
        (value, label)
        for value, (label, _cls) in FIBER_CABLE_PROFILES.items()
        if value.startswith("single-")
    )
    trunk_choices = tuple(
        (value, label)
        for value, (label, _cls) in FIBER_CABLE_PROFILES.items()
        if value.startswith("trunk-")
    )

    CableProfileChoices.CHOICES = (
        *CableProfileChoices.CHOICES,
        ("Fiber (Single)", single_choices),
        ("Fiber (Trunk)", trunk_choices),
    )
    CableProfileChoices._choices = list(CableProfileChoices.CHOICES)

    profile_field = Cable._meta.get_field("profile")
    profile_field.choices = list(profile_field.choices) + [
        ("Fiber (Single)", list(single_choices)),
        ("Fiber (Trunk)", list(trunk_choices)),
    ]

    _original_profile_class = Cable.profile_class.fget

    def _patched_profile_class(self):
        entry = FIBER_CABLE_PROFILES.get(self.profile)
        if entry:
            return entry[1]
        return _original_profile_class(self)

    Cable.profile_class = property(_patched_profile_class)
```

- [ ] **Step 5: Run tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_link_topology.py::TestCableProfileRegistry -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add netbox_fms/cable_profiles.py netbox_fms/monkey_patches.py tests/test_link_topology.py
git commit -m "feat: add trunk cable profiles and expand registry"
```

---

### Task 5: Add `FiberCableType.get_cable_profile()`

**Files:**
- Modify: `netbox_fms/models.py` (add method after `get_strand_count_from_templates`)
- Test: `tests/test_link_topology.py`

- [ ] **Step 1: Write the tests**

```python
@pytest.mark.django_db
class TestGetCableProfile:
    def test_tight_buffer_returns_single_profile(self):
        mfr = Manufacturer.objects.create(name="TB-Mfr", slug="tb-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="TB-6F", strand_count=6,
            fiber_type="smf_os2", construction="tight_buffer",
        )
        # single-1c6p is a built-in NetBox profile, not in our registry
        # so get_cable_profile() should return None for strand counts
        # not in FIBER_CABLE_PROFILES
        result = fct.get_cable_profile()
        assert result is None  # 6p not in our registry

    def test_tight_buffer_48f_returns_single_profile(self):
        mfr = Manufacturer.objects.create(name="TB48-Mfr", slug="tb48-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="TB-48F", strand_count=48,
            fiber_type="smf_os2", construction="tight_buffer",
        )
        assert fct.get_cable_profile() == "single-1c48p"

    def test_loose_tube_12x12_returns_trunk(self):
        mfr = Manufacturer.objects.create(name="LT12-Mfr", slug="lt12-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="LT-144F", strand_count=144,
            fiber_type="smf_os2", construction="loose_tube",
        )
        for i in range(1, 13):
            BufferTubeTemplate.objects.create(
                fiber_cable_type=fct, name=f"T{i}", position=i,
                fiber_count=12,
            )
        assert fct.get_cable_profile() == "trunk-12c12p"

    def test_ribbon_in_tube_returns_trunk(self):
        mfr = Manufacturer.objects.create(name="RIT2-Mfr", slug="rit2-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="RIT-48F", strand_count=48,
            fiber_type="smf_os2", construction="ribbon_in_tube",
        )
        for i in range(1, 5):
            btt = BufferTubeTemplate.objects.create(
                fiber_cable_type=fct, name=f"T{i}", position=i,
                fiber_count=None,
            )
            RibbonTemplate.objects.create(
                fiber_cable_type=fct, buffer_tube_template=btt,
                name=f"R{i}", position=1, fiber_count=12,
            )
        assert fct.get_cable_profile() == "trunk-4c12p"

    def test_mixed_tube_sizes_returns_none(self):
        mfr = Manufacturer.objects.create(name="MX-Mfr", slug="mx-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="MX-18F", strand_count=18,
            fiber_type="smf_os2", construction="loose_tube",
        )
        BufferTubeTemplate.objects.create(
            fiber_cable_type=fct, name="T1", position=1, fiber_count=12,
        )
        BufferTubeTemplate.objects.create(
            fiber_cable_type=fct, name="T2", position=2, fiber_count=6,
        )
        assert fct.get_cable_profile() is None

    def test_topology_not_in_registry_returns_none(self):
        mfr = Manufacturer.objects.create(name="NR-Mfr", slug="nr-mfr")
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="NR-36F", strand_count=36,
            fiber_type="smf_os2", construction="loose_tube",
        )
        for i in range(1, 4):
            BufferTubeTemplate.objects.create(
                fiber_cable_type=fct, name=f"T{i}", position=i,
                fiber_count=12,
            )
        # trunk-3c12p not in registry
        assert fct.get_cable_profile() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_link_topology.py::TestGetCableProfile -v`
Expected: FAIL — `get_cable_profile()` not defined

- [ ] **Step 3: Implement `get_cable_profile()`**

In `netbox_fms/models.py`, add method to `FiberCableType` after `get_strand_count_from_templates()`:

```python
    def get_cable_profile(self):
        """Derive the cable profile key from the type's template topology.

        Returns the profile key string if found in FIBER_CABLE_PROFILES,
        or None if no matching profile exists.
        """
        from .cable_profiles import FIBER_CABLE_PROFILES

        tubes = list(self.buffer_tube_templates.all())
        if not tubes:
            key = f"single-1c{self.strand_count}p"
            return key if key in FIBER_CABLE_PROFILES else None

        fiber_counts = [t.get_total_fiber_count() for t in tubes]
        if len(set(fiber_counts)) != 1:
            return None

        key = f"trunk-{len(tubes)}c{fiber_counts[0]}p"
        return key if key in FIBER_CABLE_PROFILES else None
```

- [ ] **Step 4: Run tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_link_topology.py::TestGetCableProfile -v`
Expected: PASS (all 6)

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/models.py tests/test_link_topology.py
git commit -m "feat: add FiberCableType.get_cable_profile() method"
```

---

## Chunk 3: Service Function

### Task 6: Add `NeedsMappingConfirmation` exception and `propose_port_mapping()` helper

**Files:**
- Modify: `netbox_fms/services.py`
- Test: `tests/test_link_topology.py`

- [ ] **Step 1: Write the test**

```python
from netbox_fms.services import NeedsMappingConfirmation, propose_port_mapping


@pytest.mark.django_db
class TestProposePortMapping:
    def test_builds_mapping_by_position(self):
        """Given FrontPorts with rear_port_positions, maps strands by position."""
        # This test needs FrontPorts with PortMappings — fixture-heavy.
        # Verify the function is importable and callable.
        assert callable(propose_port_mapping)

    def test_needs_mapping_confirmation_has_proposed_mapping(self):
        exc = NeedsMappingConfirmation(
            proposed_mapping={1: 100, 2: 200},
            warnings=["Count mismatch"],
        )
        assert exc.proposed_mapping == {1: 100, 2: 200}
        assert exc.warnings == ["Count mismatch"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_link_topology.py::TestProposePortMapping -v`
Expected: FAIL — imports not found

- [ ] **Step 3: Implement exception and helper**

In `netbox_fms/services.py`, add at the top (after existing imports):

```python
class NeedsMappingConfirmation(Exception):
    """Raised when existing ports are found and need user confirmation."""

    def __init__(self, proposed_mapping, warnings=None):
        self.proposed_mapping = proposed_mapping
        self.warnings = warnings or []
        super().__init__("Port mapping confirmation required")


def propose_port_mapping(strands, frontports_by_position):
    """Build a position-based mapping from strands to FrontPorts.

    Args:
        strands: QuerySet of FiberStrand ordered by position
        frontports_by_position: dict {rear_port_position: FrontPort}

    Returns: dict {strand_position: frontport_id}
    """
    mapping = {}
    for strand in strands:
        fp = frontports_by_position.get(strand.position)
        if fp:
            mapping[strand.position] = fp.pk
    return mapping
```

- [ ] **Step 4: Run test**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_link_topology.py::TestProposePortMapping -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/services.py tests/test_link_topology.py
git commit -m "feat: add NeedsMappingConfirmation and propose_port_mapping"
```

---

### Task 7: Implement `link_cable_topology()` — greenfield path

**Files:**
- Modify: `netbox_fms/services.py`
- Test: `tests/test_link_topology.py`

**Why:** Start with the simpler greenfield path (no pre-existing ports). Adopt path added in Task 8.

- [ ] **Step 1: Write the tests**

```python
from dcim.models import Cable, CableTermination, Device, DeviceRole, DeviceType, FrontPort, Manufacturer, RearPort, Site
from django.contrib.contenttypes.models import ContentType
from netbox_fms.models import FiberCable, FiberCableType, BufferTubeTemplate
from netbox_fms.services import link_cable_topology


@pytest.mark.django_db
class TestLinkCableTopologyGreenfield:
    def _make_fixtures(self):
        site = Site.objects.create(name="LT-Site", slug="lt-site")
        mfr = Manufacturer.objects.create(name="LT-Mfr2", slug="lt-mfr2")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Closure", slug="closure")
        role = DeviceRole.objects.create(name="LT-Role", slug="lt-role")
        device = Device.objects.create(name="LT-Closure", site=site, device_type=dt, role=role)
        cable = Cable.objects.create()
        return device, cable, mfr

    def test_creates_fiber_cable_and_strands(self):
        device, cable, mfr = self._make_fixtures()
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="GF-12F", strand_count=12,
            fiber_type="smf_os2", construction="tight_buffer",
        )
        fc, warnings = link_cable_topology(cable, fct, device)

        assert fc.cable == cable
        assert fc.fiber_cable_type == fct
        assert fc.fiber_strands.count() == 12

    def test_creates_rearports_per_tube(self):
        device, cable, mfr = self._make_fixtures()
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="GF-48F", strand_count=48,
            fiber_type="smf_os2", construction="loose_tube",
        )
        for i in range(1, 5):
            BufferTubeTemplate.objects.create(
                fiber_cable_type=fct, name=f"T{i}", position=i, fiber_count=12,
            )

        fc, warnings = link_cable_topology(cable, fct, device)

        rps = RearPort.objects.filter(device=device)
        assert rps.count() == 4  # one per tube

    def test_creates_single_rearport_for_no_tubes(self):
        device, cable, mfr = self._make_fixtures()
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="GF-6F", strand_count=6,
            fiber_type="smf_os2", construction="tight_buffer",
        )

        fc, warnings = link_cable_topology(cable, fct, device)

        rps = RearPort.objects.filter(device=device)
        assert rps.count() == 1
        assert rps.first().positions == 6

    def test_creates_frontports_and_links_strands(self):
        device, cable, mfr = self._make_fixtures()
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="GF-12F2", strand_count=12,
            fiber_type="smf_os2", construction="tight_buffer",
        )

        fc, warnings = link_cable_topology(cable, fct, device)

        fps = FrontPort.objects.filter(device=device)
        assert fps.count() == 12
        # All strands linked
        linked = fc.fiber_strands.filter(front_port_a__isnull=False).count()
        assert linked == 12

    def test_sets_cable_profile(self):
        device, cable, mfr = self._make_fixtures()
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="GF-48F2", strand_count=48,
            fiber_type="smf_os2", construction="loose_tube",
        )
        for i in range(1, 5):
            BufferTubeTemplate.objects.create(
                fiber_cable_type=fct, name=f"T{i}", position=i, fiber_count=12,
            )

        fc, warnings = link_cable_topology(cable, fct, device)

        cable.refresh_from_db()
        assert cable.profile == "trunk-4c12p"

    def test_missing_profile_adds_warning(self):
        device, cable, mfr = self._make_fixtures()
        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="GF-36F", strand_count=36,
            fiber_type="smf_os2", construction="loose_tube",
        )
        for i in range(1, 4):
            BufferTubeTemplate.objects.create(
                fiber_cable_type=fct, name=f"T{i}", position=i, fiber_count=12,
            )

        fc, warnings = link_cable_topology(cable, fct, device)

        assert len(warnings) > 0
        assert "profile" in warnings[0].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_link_topology.py::TestLinkCableTopologyGreenfield -v`
Expected: FAIL — `link_cable_topology` not implemented

- [ ] **Step 3: Implement `link_cable_topology()` (greenfield path only)**

In `netbox_fms/services.py`:

```python
from django.db import transaction


@transaction.atomic
def link_cable_topology(cable, fiber_cable_type, device, port_type="splice", port_mapping=None):
    """Create FiberCable, adopt or create ports, set cable profile."""
    from dcim.models import CableTermination, FrontPort, PortMapping, RearPort
    from django.contrib.contenttypes.models import ContentType

    from .models import FiberCable

    # Step 1: Detect pre-existing ports
    rp_ct = ContentType.objects.get_for_model(RearPort)
    existing_rp_ids = set(
        CableTermination.objects.filter(cable=cable)
        .values_list("termination_id", flat=True)
    )
    existing_rps = RearPort.objects.filter(pk__in=existing_rp_ids, device=device)

    if existing_rps.exists() and port_mapping is None:
        # Step 2: Confirmation gate — build proposed mapping
        # (Adopt path — Task 8)
        pass

    # Step 3: Create FiberCable
    fc = FiberCable.objects.create(cable=cable, fiber_cable_type=fiber_cable_type)

    # Step 4: Set cable profile
    warnings = []
    profile_key = fiber_cable_type.get_cable_profile()
    if profile_key:
        cable.profile = profile_key
        cable.save(update_fields=["profile"])
    else:
        warnings.append(
            f"No cable profile exists for this topology. "
            f"Cable trace will not render strand positions."
        )

    # Step 5: Determine cable side
    cable_end = _determine_cable_end(cable, device)

    # Step 6: Greenfield — create ports
    if not existing_rps.exists():
        _create_greenfield_ports(fc, cable, device, port_type, cable_end)

    return fc, warnings


def _determine_cable_end(cable, device):
    """Determine which cable end (A or B) terminates on device. Returns 'A', 'B', or 'AB'."""
    from dcim.models import CableTermination, RearPort
    from django.contrib.contenttypes.models import ContentType

    rp_ct = ContentType.objects.get_for_model(RearPort)
    terms = CableTermination.objects.filter(cable=cable, termination_type=rp_ct)

    sides = set()
    for t in terms:
        rp = RearPort.objects.filter(pk=t.termination_id, device=device).first()
        if rp:
            sides.add(t.cable_end)

    # For greenfield (no pre-existing terms on this device), default to 'A'
    if not sides:
        return "A"
    if sides == {"A", "B"}:
        return "AB"
    return sides.pop()


def _create_greenfield_ports(fc, cable, device, port_type, cable_end):
    """Create RearPorts, FrontPorts, PortMappings, CableTerminations for greenfield."""
    from dcim.models import CableTermination, FrontPort, PortMapping, RearPort
    from django.contrib.contenttypes.models import ContentType

    rp_ct = ContentType.objects.get_for_model(RearPort)
    tubes = list(fc.buffer_tubes.all().order_by("position"))
    strands = list(fc.fiber_strands.all().order_by("position"))
    side = "A" if cable_end in ("A", "AB") else "B"
    fp_fk_field = "front_port_a" if side == "A" else "front_port_b"

    if tubes:
        # One RearPort per tube
        strand_idx = 0
        for tube in tubes:
            tube_strands = [s for s in strands if s.buffer_tube_id == tube.pk]
            rp = RearPort.objects.create(
                device=device,
                name=f"#{cable.pk}:T{tube.position}",
                type=port_type,
                positions=len(tube_strands),
                color="",
            )
            CableTermination.objects.create(
                cable=cable, cable_end=side,
                termination_type=rp_ct, termination_id=rp.pk,
            )
            for pos_in_tube, strand in enumerate(tube_strands, 1):
                fp = FrontPort.objects.create(
                    device=device,
                    name=f"#{cable.pk}:T{tube.position}:F{strand.position}",
                    type=port_type, color=strand.color,
                )
                PortMapping.objects.create(
                    device=device, front_port=fp, rear_port=rp,
                    front_port_position=1, rear_port_position=pos_in_tube,
                )
                setattr(strand, fp_fk_field, fp)
                strand.save(update_fields=[fp_fk_field])
    else:
        # Single RearPort for all strands
        rp = RearPort.objects.create(
            device=device,
            name=f"#{cable.pk}",
            type=port_type,
            positions=len(strands),
            color="",
        )
        CableTermination.objects.create(
            cable=cable, cable_end=side,
            termination_type=rp_ct, termination_id=rp.pk,
        )
        for strand in strands:
            fp = FrontPort.objects.create(
                device=device,
                name=f"#{cable.pk}:F{strand.position}",
                type=port_type, color=strand.color,
            )
            PortMapping.objects.create(
                device=device, front_port=fp, rear_port=rp,
                front_port_position=1, rear_port_position=strand.position,
            )
            setattr(strand, fp_fk_field, fp)
            strand.save(update_fields=[fp_fk_field])
```

- [ ] **Step 4: Run tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_link_topology.py::TestLinkCableTopologyGreenfield -v`
Expected: PASS (all 6)

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/services.py tests/test_link_topology.py
git commit -m "feat: implement link_cable_topology greenfield path"
```

---

### Task 8: Implement `link_cable_topology()` — adopt path

**Files:**
- Modify: `netbox_fms/services.py`
- Test: `tests/test_link_topology.py`

- [ ] **Step 1: Write the tests**

```python
@pytest.mark.django_db
class TestLinkCableTopologyAdopt:
    def _make_closure_with_existing_ports(self):
        """Create a device with pre-existing RearPort/FrontPorts terminated by a cable."""
        site = Site.objects.create(name="AD-Site", slug="ad-site")
        mfr = Manufacturer.objects.create(name="AD-Mfr", slug="ad-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="AD-Closure", slug="ad-closure")
        role = DeviceRole.objects.create(name="AD-Role", slug="ad-role")
        device = Device.objects.create(name="AD-Closure", site=site, device_type=dt, role=role)

        cable = Cable.objects.create()

        # Create pre-existing RearPort + 12 FrontPorts
        rp = RearPort.objects.create(device=device, name="Existing-RP", type="splice", positions=12)
        rp_ct = ContentType.objects.get_for_model(RearPort)
        CableTermination.objects.create(
            cable=cable, cable_end="A",
            termination_type=rp_ct, termination_id=rp.pk,
        )
        from dcim.models import PortMapping
        fps = []
        for i in range(1, 13):
            fp = FrontPort.objects.create(device=device, name=f"EF{i}", type="splice")
            PortMapping.objects.create(
                device=device, front_port=fp, rear_port=rp,
                front_port_position=1, rear_port_position=i,
            )
            fps.append(fp)

        fct = FiberCableType.objects.create(
            manufacturer=mfr, model="AD-12F", strand_count=12,
            fiber_type="smf_os2", construction="tight_buffer",
        )
        return device, cable, fct, fps

    def test_raises_needs_mapping_without_port_mapping(self):
        device, cable, fct, fps = self._make_closure_with_existing_ports()

        with pytest.raises(NeedsMappingConfirmation) as exc_info:
            link_cable_topology(cable, fct, device)

        assert len(exc_info.value.proposed_mapping) == 12

    def test_adopts_existing_ports_with_mapping(self):
        device, cable, fct, fps = self._make_closure_with_existing_ports()

        mapping = {i: fps[i - 1].pk for i in range(1, 13)}
        fc, warnings = link_cable_topology(cable, fct, device, port_mapping=mapping)

        assert fc.fiber_strands.filter(front_port_a__isnull=False).count() == 12
        # No new RearPorts created
        assert RearPort.objects.filter(device=device).count() == 1  # only the pre-existing one

    def test_count_mismatch_raises_with_partial_mapping(self):
        device, cable, fct, fps = self._make_closure_with_existing_ports()

        # Change FiberCableType to have 6 strands instead of 12
        fct.strand_count = 6
        fct.save()

        with pytest.raises(NeedsMappingConfirmation) as exc_info:
            link_cable_topology(cable, fct, device)

        assert len(exc_info.value.proposed_mapping) == 6  # only 6 matched
        assert len(exc_info.value.warnings) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_link_topology.py::TestLinkCableTopologyAdopt -v`
Expected: FAIL — adopt path not implemented (the `pass` in step 2)

- [ ] **Step 3: Implement adopt path**

In `netbox_fms/services.py`, replace the `pass` in the confirmation gate with:

```python
    if existing_rps.exists():
        # Collect FrontPorts mapped to existing RearPorts
        existing_fps = {}
        for rp in existing_rps:
            mappings = PortMapping.objects.filter(rear_port=rp).order_by("rear_port_position")
            for m in mappings:
                existing_fps[m.rear_port_position] = m.front_port

        if port_mapping is None:
            # Build proposed mapping and raise for confirmation
            # Need strands — create FiberCable temporarily to get strand positions
            # Actually, we can derive strand count from the type
            strand_positions = range(1, fiber_cable_type.strand_count + 1)
            proposed = {}
            for pos in strand_positions:
                fp = existing_fps.get(pos)
                if fp:
                    proposed[pos] = fp.pk
            confirmation_warnings = []
            if len(proposed) != fiber_cable_type.strand_count:
                confirmation_warnings.append(
                    f"Count mismatch: {fiber_cable_type.strand_count} strands "
                    f"but {len(existing_fps)} existing ports."
                )
            raise NeedsMappingConfirmation(
                proposed_mapping=proposed,
                warnings=confirmation_warnings,
            )
```

Then after creating FiberCable (step 3), add the adopt path to step 6:

```python
    if existing_rps.exists() and port_mapping is not None:
        # Adopt path
        cable_end = _determine_cable_end(cable, device)
        fp_fk_field = "front_port_a" if cable_end in ("A", "AB") else "front_port_b"
        for strand in fc.fiber_strands.all().order_by("position"):
            fp_id = port_mapping.get(strand.position)
            if fp_id:
                setattr(strand, fp_fk_field, FrontPort.objects.get(pk=fp_id))
                strand.save(update_fields=[fp_fk_field])
    elif not existing_rps.exists():
        _create_greenfield_ports(fc, cable, device, port_type, cable_end)
```

- [ ] **Step 4: Run tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_link_topology.py::TestLinkCableTopologyAdopt -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add netbox_fms/services.py tests/test_link_topology.py
git commit -m "feat: implement link_cable_topology adopt path with NeedsMappingConfirmation"
```

---

## Chunk 4: View & Templates

### Task 9: Add `LinkTopologyForm`

**Files:**
- Modify: `netbox_fms/forms.py`

- [ ] **Step 1: Add form**

```python
PORT_TYPE_CHOICES = (
    ("splice", "Splice"),
    ("lc", "LC"),
    ("sc", "SC"),
    ("mpo", "MPO"),
)


class LinkTopologyForm(forms.Form):
    fiber_cable_type = DynamicModelChoiceField(
        queryset=FiberCableType.objects.all(),
        label=_("Fiber Cable Type"),
    )
    port_type = forms.ChoiceField(
        choices=PORT_TYPE_CHOICES,
        initial="splice",
        label=_("Port Type"),
        required=False,
    )
```

- [ ] **Step 2: Commit**

```bash
git add netbox_fms/forms.py
git commit -m "feat: add LinkTopologyForm"
```

---

### Task 10: Add `LinkTopologyView` and URL

**Files:**
- Modify: `netbox_fms/views.py`
- Modify: `netbox_fms/urls.py`
- Create: `netbox_fms/templates/netbox_fms/htmx/link_topology_modal.html`
- Create: `netbox_fms/templates/netbox_fms/htmx/link_topology_confirm.html`
- Test: `tests/test_link_topology.py`

- [ ] **Step 1: Create modal template**

`netbox_fms/templates/netbox_fms/htmx/link_topology_modal.html`:

```html
{% load i18n %}
<div class="modal-header">
    <h5 class="modal-title">{% trans "Link Cable Topology" %}</h5>
    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
</div>
<form hx-post="{{ post_url }}" hx-target="#htmx-modal-content" hx-swap="innerHTML">
    {% csrf_token %}
    <div class="modal-body">
        <input type="hidden" name="cable_id" value="{{ cable.pk }}">
        {% if profile_warning %}
        <div class="alert alert-danger">
            <strong>{% trans "Warning:" %}</strong> {{ profile_warning }}
        </div>
        {% endif %}
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
        {% if show_port_type %}
        <div class="mb-3">
            <label for="id_port_type" class="form-label">{% trans "Port Type" %}</label>
            {{ form.port_type }}
        </div>
        {% endif %}
    </div>
    <div class="modal-footer">
        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{% trans "Cancel" %}</button>
        {% if profile_warning %}
        <button type="submit" class="btn btn-warning">{% trans "Proceed Without Profile" %}</button>
        {% else %}
        <button type="submit" class="btn btn-primary">{% trans "Link" %}</button>
        {% endif %}
    </div>
</form>
```

- [ ] **Step 2: Create confirmation template**

`netbox_fms/templates/netbox_fms/htmx/link_topology_confirm.html`:

```html
{% load i18n %}
<div class="modal-header">
    <h5 class="modal-title">{% trans "Confirm Port Mapping" %}</h5>
    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
</div>
<form hx-post="{{ post_url }}" hx-target="#htmx-modal-content" hx-swap="innerHTML">
    {% csrf_token %}
    <div class="modal-body">
        <input type="hidden" name="cable_id" value="{{ cable_id }}">
        <input type="hidden" name="fiber_cable_type_id" value="{{ fiber_cable_type_id }}">
        <input type="hidden" name="confirm_mapping" value="1">
        {% if warnings %}
        <div class="alert alert-warning">
            {% for w in warnings %}<p>{{ w }}</p>{% endfor %}
        </div>
        {% endif %}
        <table class="table table-sm">
            <thead>
                <tr>
                    <th>{% trans "Strand Position" %}</th>
                    <th>{% trans "Strand Name" %}</th>
                    <th></th>
                    <th>{% trans "FrontPort" %}</th>
                </tr>
            </thead>
            <tbody>
                {% for entry in mapping_entries %}
                <tr>
                    <td>{{ entry.position }}</td>
                    <td>{{ entry.strand_name }}</td>
                    <td>&rarr;</td>
                    <td>
                        {% if entry.frontport_id %}
                        <input type="hidden" name="mapping_{{ entry.position }}" value="{{ entry.frontport_id }}">
                        {{ entry.frontport_name }}
                        {% else %}
                        <span class="text-muted">{% trans "Unlinked" %}</span>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    <div class="modal-footer">
        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{% trans "Cancel" %}</button>
        <button type="submit" class="btn btn-primary">{% trans "Confirm & Link" %}</button>
    </div>
</form>
```

- [ ] **Step 3: Add `LinkTopologyView`**

In `netbox_fms/views.py`:

```python
class LinkTopologyView(LoginRequiredMixin, View):
    """Link a dcim.Cable to a FiberCableType — creates FiberCable and links strands to ports."""

    def get(self, request, pk):
        if not request.user.has_perm("netbox_fms.add_fibercable"):
            return HttpResponse("Permission denied", status=403)
        device = get_object_or_404(Device, pk=pk)
        cable_id = request.GET.get("cable_id")
        cable = get_object_or_404(Cable, pk=cable_id)

        # Detect if greenfield (show port_type selector) or adopt (hide it)
        from dcim.models import CableTermination, RearPort
        from django.contrib.contenttypes.models import ContentType

        rp_ct = ContentType.objects.get_for_model(RearPort)
        has_existing_ports = CableTermination.objects.filter(
            cable=cable,
        ).filter(
            termination_id__in=RearPort.objects.filter(device=device).values("pk"),
            termination_type=rp_ct,
        ).exists()

        form = LinkTopologyForm()
        return render(request, "netbox_fms/htmx/link_topology_modal.html", {
            "device": device,
            "cable": cable,
            "form": form,
            "show_port_type": not has_existing_ports,
            "post_url": reverse("plugins:netbox_fms:fiber_overview_link_topology", kwargs={"pk": pk}),
        })

    def post(self, request, pk):
        if not request.user.has_perm("netbox_fms.add_fibercable"):
            return HttpResponse("Permission denied", status=403)
        device = get_object_or_404(Device, pk=pk)

        # Check if this is a confirmation POST
        if request.POST.get("confirm_mapping"):
            cable_id = request.POST.get("cable_id")
            cable = get_object_or_404(Cable, pk=cable_id)
            fct_id = request.POST.get("fiber_cable_type_id")
            fct = get_object_or_404(FiberCableType, pk=fct_id)

            # Build port_mapping from form
            port_mapping = {}
            for key, value in request.POST.items():
                if key.startswith("mapping_"):
                    pos = int(key.split("_")[1])
                    port_mapping[pos] = int(value)

            fc, warnings = link_cable_topology(cable, fct, device, port_mapping=port_mapping)
            redirect_url = reverse("dcim:device", kwargs={"pk": pk}) + "fiber-overview/"
            response = HttpResponse(status=200)
            response["HX-Redirect"] = redirect_url
            return response

        # First POST — try to link, may raise NeedsMappingConfirmation
        form = LinkTopologyForm(request.POST)
        if not form.is_valid():
            cable = get_object_or_404(Cable, pk=request.POST.get("cable_id"))
            return render(request, "netbox_fms/htmx/link_topology_modal.html", {
                "device": device, "cable": cable, "form": form,
                "show_port_type": True,
                "post_url": reverse("plugins:netbox_fms:fiber_overview_link_topology", kwargs={"pk": pk}),
            })

        cable = get_object_or_404(Cable, pk=request.POST.get("cable_id"))
        fct = form.cleaned_data["fiber_cable_type"]
        port_type = form.cleaned_data.get("port_type", "splice") or "splice"

        from dcim.models import CableTermination
        if not CableTermination.objects.filter(cable=cable, _device_id=device.pk).exists():
            # Greenfield — cable not yet terminated on this device, that's OK
            pass

        try:
            fc, warnings = link_cable_topology(cable, fct, device, port_type=port_type)
        except NeedsMappingConfirmation as exc:
            # Render confirmation template
            strand_names = [f"F{i}" for i in range(1, fct.strand_count + 1)]
            from dcim.models import FrontPort
            mapping_entries = []
            for pos in range(1, fct.strand_count + 1):
                fp_id = exc.proposed_mapping.get(pos)
                fp_name = None
                if fp_id:
                    fp = FrontPort.objects.filter(pk=fp_id).first()
                    fp_name = fp.name if fp else None
                mapping_entries.append({
                    "position": pos,
                    "strand_name": f"F{pos}",
                    "frontport_id": fp_id,
                    "frontport_name": fp_name,
                })
            return render(request, "netbox_fms/htmx/link_topology_confirm.html", {
                "cable_id": cable.pk,
                "fiber_cable_type_id": fct.pk,
                "mapping_entries": mapping_entries,
                "warnings": exc.warnings,
                "post_url": reverse("plugins:netbox_fms:fiber_overview_link_topology", kwargs={"pk": pk}),
            })

        redirect_url = reverse("dcim:device", kwargs={"pk": pk}) + "fiber-overview/"
        response = HttpResponse(status=200)
        response["HX-Redirect"] = redirect_url
        return response
```

- [ ] **Step 4: Add URL**

In `netbox_fms/urls.py`, add:

```python
    path(
        "fiber-overview/<int:pk>/link-topology/",
        views.LinkTopologyView.as_view(),
        name="fiber_overview_link_topology",
    ),
```

- [ ] **Step 5: Write integration test**

```python
@pytest.mark.django_db
class TestLinkTopologyView:
    def test_get_returns_modal(self, client):
        # Setup device + cable
        site = Site.objects.create(name="LTV-Site", slug="ltv-site")
        mfr = Manufacturer.objects.create(name="LTV-Mfr", slug="ltv-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="LTV-Closure", slug="ltv-closure")
        role = DeviceRole.objects.create(name="LTV-Role", slug="ltv-role")
        device = Device.objects.create(name="LTV-Device", site=site, device_type=dt, role=role)
        cable = Cable.objects.create()

        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_superuser("ltv-admin", "ltv@test.com", "password")
        client.force_login(user)

        url = f"/plugins/fms/fiber-overview/{device.pk}/link-topology/?cable_id={cable.pk}"
        response = client.get(url)
        assert response.status_code == 200
        assert b"Link Cable Topology" in response.content
```

- [ ] **Step 6: Run tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_link_topology.py::TestLinkTopologyView -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add netbox_fms/views.py netbox_fms/urls.py netbox_fms/forms.py \
    netbox_fms/templates/netbox_fms/htmx/link_topology_modal.html \
    netbox_fms/templates/netbox_fms/htmx/link_topology_confirm.html \
    tests/test_link_topology.py
git commit -m "feat: add LinkTopologyView with HTMX modal and confirmation flow"
```

---

## Chunk 5: Fiber Overview Update & Cleanup

### Task 11: Rewrite `_build_cable_rows()` to group by cable

**Files:**
- Modify: `netbox_fms/views.py:660-740`
- Modify: `netbox_fms/templates/netbox_fms/htmx/fiber_overview_row.html`
- Modify: `netbox_fms/templates/netbox_fms/device_fiber_overview.html`

- [ ] **Step 1: Rewrite `_build_cable_rows()`**

Replace the current function with one that groups by cable instead of by RearPort:

```python
def _build_cable_rows(device):
    """Build context dicts for all cable rows, grouped by cable."""
    from dcim.models import CableTermination
    from django.db.models import Q

    from .models import FiberStrand

    # Get all cables terminated on this device
    cable_ids = (
        CableTermination.objects.filter(_device_id=device.pk)
        .exclude(cable__isnull=True)
        .values_list("cable_id", flat=True)
        .distinct()
    )

    cables = Cable.objects.filter(pk__in=cable_ids).order_by("pk")
    fc_by_cable = {
        fc.cable_id: fc
        for fc in FiberCable.objects.filter(cable_id__in=cable_ids).select_related("fiber_cable_type")
    }

    # Strand counts per FiberCable
    fiber_cable_ids = [fc.pk for fc in fc_by_cable.values()]
    strand_totals = {}
    strand_linked = {}
    if fiber_cable_ids:
        from django.db.models import Count

        totals = (
            FiberStrand.objects.filter(fiber_cable_id__in=fiber_cable_ids)
            .values("fiber_cable_id")
            .annotate(
                total=Count("pk"),
                linked=Count("pk", filter=Q(front_port_a__device=device) | Q(front_port_b__device=device)),
            )
        )
        for row in totals:
            strand_totals[row["fiber_cable_id"]] = row["total"]
            strand_linked[row["fiber_cable_id"]] = row["linked"]

    # Gland entries
    gland_by_fc = {}
    if fiber_cable_ids:
        for entry in ClosureCableEntry.objects.filter(closure=device, fiber_cable_id__in=fiber_cable_ids):
            gland_by_fc[entry.fiber_cable_id] = entry

    rows = []
    for cable in cables:
        fc = fc_by_cable.get(cable.pk)
        strand_info = None
        gland_entry = None
        if fc:
            strand_info = {
                "linked": strand_linked.get(fc.pk, 0),
                "total": strand_totals.get(fc.pk, 0),
            }
            gland_entry = gland_by_fc.get(fc.pk)

        rows.append({
            "cable": cable,
            "fiber_cable": fc,
            "strand_info": strand_info,
            "gland_entry": gland_entry,
        })

    return rows
```

- [ ] **Step 2: Update `DeviceFiberOverviewView.get()`**

```python
    def get(self, request, pk):
        device = get_object_or_404(Device, pk=pk)

        cable_rows = _build_cable_rows(device)

        plan = SplicePlan.objects.filter(closure=device).first()

        stats = {
            "tray_count": device.modules.count(),
            "cable_count": len(cable_rows),
            "fiber_cable_count": sum(1 for r in cable_rows if r["fiber_cable"]),
            "strand_linked": sum(r["strand_info"]["linked"] for r in cable_rows if r["strand_info"]),
            "strand_total": sum(r["strand_info"]["total"] for r in cable_rows if r["strand_info"]),
        }

        return render(request, "netbox_fms/device_fiber_overview.html", {
            "object": device, "device": device,
            "cable_rows": cable_rows, "plan": plan, "stats": stats,
            "tab": self.tab,
        })
```

- [ ] **Step 3: Update row template**

Replace `netbox_fms/templates/netbox_fms/htmx/fiber_overview_row.html` with cable-grouped version. Key change: "Link Topology" button instead of "Create FiberCable" / "Provision Strands".

- [ ] **Step 4: Update overview template**

Update column headers in `device_fiber_overview.html` to match new row structure. Change "Strands Provisioned" to "Strands Linked" in stats.

- [ ] **Step 5: Update `_device_has_modules_or_fiber_cables()`**

The tab visibility check may need updating since we no longer key on module RearPorts.

- [ ] **Step 6: Run full test suite**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v`
Expected: All pass (some fiber_overview tests may need updates)

- [ ] **Step 7: Commit**

```bash
git add netbox_fms/views.py netbox_fms/templates/netbox_fms/htmx/fiber_overview_row.html \
    netbox_fms/templates/netbox_fms/device_fiber_overview.html
git commit -m "feat: rewrite Fiber Overview to group by cable with Link Topology button"
```

---

### Task 12: Remove old views, forms, templates, and URLs

**Files:**
- Modify: `netbox_fms/views.py` — remove `CreateFiberCableFromCableView`, `ProvisionStrandsFromOverviewView`
- Modify: `netbox_fms/forms.py` — remove `CreateFiberCableFromCableForm`, `ProvisionStrandsFromOverviewForm`
- Modify: `netbox_fms/urls.py` — remove old URL patterns
- Delete: `netbox_fms/templates/netbox_fms/htmx/create_fiber_cable_modal.html`
- Delete: `netbox_fms/templates/netbox_fms/htmx/provision_strands_modal.html`
- Modify: `tests/test_fiber_overview.py` — update/remove tests referencing old views

- [ ] **Step 1: Remove old views from views.py**

Delete `CreateFiberCableFromCableView` class and `ProvisionStrandsFromOverviewView` class.

- [ ] **Step 2: Remove old forms from forms.py**

Delete `CreateFiberCableFromCableForm` and `ProvisionStrandsFromOverviewForm`.

- [ ] **Step 3: Remove old URL patterns from urls.py**

Remove the `fiber_overview_create_fibercable` and `fiber_overview_provision_strands` path entries.

- [ ] **Step 4: Delete old templates**

```bash
rm netbox_fms/templates/netbox_fms/htmx/create_fiber_cable_modal.html
rm netbox_fms/templates/netbox_fms/htmx/provision_strands_modal.html
```

- [ ] **Step 5: Update tests**

Update `tests/test_fiber_overview.py` to remove/update tests that reference the old views and add tests for the new Link Topology button visibility.

- [ ] **Step 6: Verify import is clean**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.models import *; from netbox_fms.forms import *; from netbox_fms.filters import *; from netbox_fms.views import *"`

- [ ] **Step 7: Run full test suite**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v`
Expected: All pass

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "cleanup: remove old Create FiberCable / Provision Strands views and templates"
```

---

## Summary

| Task | Chunk | Description |
|------|-------|-------------|
| 1 | 1 | Fix `get_strand_count_from_templates()` for ribbon-in-tube |
| 2 | 1 | Rename `front_port` → `front_port_a`, add `front_port_b` (3-step migration) |
| 3 | 1 | Update all `front_port` references across codebase |
| 4 | 2 | Add trunk profile classes and expand registry |
| 5 | 2 | Add `FiberCableType.get_cable_profile()` |
| 6 | 3 | Add `NeedsMappingConfirmation` and `propose_port_mapping()` |
| 7 | 3 | Implement `link_cable_topology()` — greenfield path |
| 8 | 3 | Implement `link_cable_topology()` — adopt path |
| 9 | 4 | Add `LinkTopologyForm` |
| 10 | 4 | Add `LinkTopologyView` with HTMX modal and confirmation |
| 11 | 5 | Rewrite `_build_cable_rows()` to group by cable |
| 12 | 5 | Remove old views, forms, templates, URLs |
