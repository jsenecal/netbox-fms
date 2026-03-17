# Security Hardening Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all authentication, authorization, and input validation gaps across views and API endpoints.

**Architecture:** Add `LoginRequiredMixin` to unprotected views, add permission checks to API custom actions, validate hidden form fields against device context, and narrow broad exception handling.

**Tech Stack:** Django, Django REST Framework, NetBox plugin API

---

## File Map

| File | Changes |
|------|---------|
| `netbox_fms/views.py` | Add `LoginRequiredMixin` to 6 views, narrow `except Exception` to specific types |
| `netbox_fms/api/views.py` | Add permission checks to 5 custom actions on `SplicePlanViewSet`, add duplicate-provision guard to `ProvisionPortsAPIView` |
| `netbox_fms/forms.py` | Add `clean()` methods to `CreateFiberCableFromCableForm` and `ProvisionStrandsFromOverviewForm` |
| `tests/test_security.py` | New file — permission-denied and input validation tests |

---

## Chunk 1: View Authentication & Exception Narrowing

### Task 1: Add LoginRequiredMixin to Unprotected Views

**Files:**
- Modify: `netbox_fms/views.py:319-401, 581-636`
- Test: `tests/test_security.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_security.py`:

```python
from django.test import TestCase
from dcim.models import Cable, Device, DeviceRole, DeviceType, Manufacturer, Site

from netbox_fms.models import FiberCable, FiberCableType, SplicePlan


class TestUnauthenticatedAccess(TestCase):
    """Verify all custom views reject unauthenticated requests."""

    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="Auth Site", slug="auth-site")
        manufacturer = Manufacturer.objects.create(name="Auth Mfr", slug="auth-mfr")
        device_type = DeviceType.objects.create(
            manufacturer=manufacturer, model="Auth Closure", slug="auth-closure"
        )
        role = DeviceRole.objects.create(name="Auth Role", slug="auth-role")
        cls.device = Device.objects.create(
            name="Auth-Device", site=site, device_type=device_type, role=role
        )
        fct = FiberCableType.objects.create(
            manufacturer=manufacturer, model="Auth-FCT",
            construction="loose_tube", fiber_type="smf_os2", strand_count=12,
        )
        cable = Cable.objects.create()
        cls.fiber_cable = FiberCable.objects.create(cable=cable, fiber_cable_type=fct)
        cls.plan = SplicePlan.objects.create(
            closure=cls.device, name="Auth Plan", status="draft",
        )

    def test_quick_add_form_requires_login(self):
        response = self.client.get("/plugins/fms/splice-plans/quick-add-form/")
        assert response.status_code == 302
        assert "/login/" in response.url

    def test_import_from_device_requires_login(self):
        response = self.client.post(
            f"/plugins/fms/splice-plans/{self.plan.pk}/import/"
        )
        assert response.status_code == 302
        assert "/login/" in response.url

    def test_apply_view_requires_login(self):
        response = self.client.get(
            f"/plugins/fms/splice-plans/{self.plan.pk}/apply/"
        )
        assert response.status_code == 302
        assert "/login/" in response.url

    def test_export_drawio_requires_login(self):
        response = self.client.get(
            f"/plugins/fms/splice-plans/{self.plan.pk}/export/"
        )
        assert response.status_code == 302
        assert "/login/" in response.url

    def test_provision_ports_requires_login(self):
        response = self.client.get("/plugins/fms/provision-ports/")
        assert response.status_code == 302
        assert "/login/" in response.url

    def test_splice_editor_requires_login(self):
        response = self.client.get(
            f"/plugins/fms/splice-plans/{self.plan.pk}/editor/"
        )
        assert response.status_code == 302
        assert "/login/" in response.url
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_security.py::TestUnauthenticatedAccess -v
```

Expected: FAIL — views return 200 instead of 302 redirect.

- [ ] **Step 3: Add LoginRequiredMixin to all 6 views**

In `netbox_fms/views.py`, modify each class declaration. `LoginRequiredMixin` is already imported at line 3.

Change line 319:
```python
class SplicePlanQuickAddFormView(LoginRequiredMixin, View):
```

Change line 338:
```python
class SplicePlanImportFromDeviceView(LoginRequiredMixin, View):
```

Change line 356:
```python
class SplicePlanApplyView(LoginRequiredMixin, View):
```

Change line 388:
```python
class SplicePlanExportDrawioView(LoginRequiredMixin, View):
```

Change line 581:
```python
class ProvisionPortsView(LoginRequiredMixin, View):
```

Change line 624:
```python
class SpliceEditorView(LoginRequiredMixin, View):
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_security.py::TestUnauthenticatedAccess -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/views.py tests/test_security.py
git commit -m "security: add LoginRequiredMixin to 6 unprotected views"
```

---

### Task 2: Narrow Broad Exception Handling

**Files:**
- Modify: `netbox_fms/views.py:351, 383`
- Modify: `netbox_fms/api/views.py:151, 162`

- [ ] **Step 1: Narrow exception types in views.py**

In `netbox_fms/views.py`, change line 351 in `SplicePlanImportFromDeviceView.post`:

```python
        except (ValueError, ValidationError) as e:
```

Add the import at the top of the file if not present — `ValidationError` is already imported in models but not views. Add to imports:
```python
from django.core.exceptions import ValidationError
```

Change line 383 in `SplicePlanApplyView.post`:

```python
        except (ValueError, ValidationError, IntegrityError) as e:
```

Add to imports:
```python
from django.db import IntegrityError
```

Wait — `IntegrityError` is in `django.db`. Check existing imports: line 4 has `from django.db import models, transaction`. Update to:
```python
from django.db import IntegrityError, models, transaction
```

- [ ] **Step 2: Narrow exception types in api/views.py**

In `netbox_fms/api/views.py`, change line 151 in `import_from_device`:

```python
        except (ValueError, ValidationError) as e:
```

Add import:
```python
from django.core.exceptions import ValidationError
```

Change line 162 in `apply_plan`:

```python
        except (ValueError, ValidationError) as e:
```

- [ ] **Step 3: Run full test suite**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add netbox_fms/views.py netbox_fms/api/views.py
git commit -m "security: narrow broad exception handling to specific types"
```

---

## Chunk 2: API Permission Checks & Form Validation

### Task 3: Add Permission Checks to API Custom Actions

**Files:**
- Modify: `netbox_fms/api/views.py:143-226`
- Test: `tests/test_security.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_security.py`:

```python
from django.contrib.auth.models import User
from rest_framework.test import APIClient


class TestAPIActionPermissions(TestCase):
    """Verify custom API actions check permissions beyond just authentication."""

    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="APIPerm Site", slug="apiperm-site")
        manufacturer = Manufacturer.objects.create(name="APIPerm Mfr", slug="apiperm-mfr")
        device_type = DeviceType.objects.create(
            manufacturer=manufacturer, model="APIPerm Closure", slug="apiperm-closure"
        )
        role = DeviceRole.objects.create(name="APIPerm Role", slug="apiperm-role")
        cls.device = Device.objects.create(
            name="APIPerm-Device", site=site, device_type=device_type, role=role
        )
        cls.plan = SplicePlan.objects.create(
            closure=cls.device, name="APIPerm Plan", status="draft",
        )
        # User with NO permissions
        cls.readonly_user = User.objects.create_user(
            username="apiperm_readonly", password="testpass"
        )
        # Superuser for comparison
        cls.super_user = User.objects.create_user(
            username="apiperm_super", password="testpass", is_superuser=True
        )

    def test_import_from_device_requires_change_permission(self):
        client = APIClient()
        client.force_authenticate(user=self.readonly_user)
        url = f"/api/plugins/fms/splice-plans/{self.plan.pk}/import-from-device/"
        response = client.post(url)
        assert response.status_code == 403

    def test_apply_plan_requires_change_permission(self):
        client = APIClient()
        client.force_authenticate(user=self.readonly_user)
        url = f"/api/plugins/fms/splice-plans/{self.plan.pk}/apply/"
        response = client.post(url)
        assert response.status_code == 403

    def test_bulk_update_requires_change_permission(self):
        client = APIClient()
        client.force_authenticate(user=self.readonly_user)
        url = f"/api/plugins/fms/splice-plans/{self.plan.pk}/bulk-update/"
        response = client.post(url, {"add": [], "remove": []}, format="json")
        assert response.status_code == 403

    def test_diff_requires_view_permission(self):
        client = APIClient()
        client.force_authenticate(user=self.readonly_user)
        url = f"/api/plugins/fms/splice-plans/{self.plan.pk}/diff/"
        response = client.get(url)
        assert response.status_code == 403

    def test_quick_add_requires_add_permission(self):
        client = APIClient()
        client.force_authenticate(user=self.readonly_user)
        url = "/api/plugins/fms/splice-plans/quick-add/"
        response = client.post(url, {
            "closure": self.device.pk,
            "name": "Test Plan",
            "status": "draft",
        }, format="json")
        assert response.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_security.py::TestAPIActionPermissions -v
```

Expected: FAIL — actions return 200/201 instead of 403.

- [ ] **Step 3: Add permission checks to each action**

In `netbox_fms/api/views.py`, add permission checking to each custom action. Use DRF's `self.check_object_permissions()` or manual checks:

Update `import_from_device` (line 143):
```python
    @action(detail=True, methods=["post"], url_path="import-from-device")
    def import_from_device(self, request, pk=None):
        plan = self.get_object()
        if not request.user.has_perm("netbox_fms.change_spliceplan"):
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )
        from ..services import import_live_state

        try:
            count = import_live_state(plan)
            return Response({"imported": count})
        except (ValueError, ValidationError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
```

Update `apply_plan` (line 154):
```python
    @action(detail=True, methods=["post"], url_path="apply")
    def apply_plan(self, request, pk=None):
        plan = self.get_object()
        if not request.user.has_perm("netbox_fms.change_spliceplan"):
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )
        from ..services import apply_diff

        try:
            result = apply_diff(plan)
            return Response(result)
        except (ValueError, ValidationError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
```

Update `get_diff` (line 165):
```python
    @action(detail=True, methods=["get"], url_path="diff")
    def get_diff(self, request, pk=None):
        plan = self.get_object()
        if not request.user.has_perm("netbox_fms.view_spliceplan"):
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )
        from ..services import get_or_recompute_diff

        diff = get_or_recompute_diff(plan)
        return Response(diff)
```

Update `bulk_update_entries` (line 173):
```python
    @action(detail=True, methods=["post"], url_path="bulk-update")
    def bulk_update_entries(self, request, pk=None):
        plan = self.get_object()
        if not request.user.has_perm("netbox_fms.change_spliceplan"):
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )
        # ... rest unchanged
```

Update `quick_add` (line 221):
```python
    @action(detail=False, methods=["post"], url_path="quick-add")
    def quick_add(self, request):
        if not request.user.has_perm("netbox_fms.add_spliceplan"):
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = SplicePlanSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_security.py::TestAPIActionPermissions -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/api/views.py tests/test_security.py
git commit -m "security: add permission checks to all API custom actions"
```

---

### Task 4: Validate Hidden Form Fields Against Device Context

**Files:**
- Modify: `netbox_fms/views.py:818-847, 887-944`
- Test: `tests/test_security.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_security.py`:

```python
class TestHiddenFieldTampering(TestCase):
    """Verify HTMX views reject tampered hidden field values."""

    @classmethod
    def setUpTestData(cls):
        from dcim.models import Module, ModuleBay, ModuleType, RearPort

        site = Site.objects.create(name="Tamper Site", slug="tamper-site")
        manufacturer = Manufacturer.objects.create(name="Tamper Mfr", slug="tamper-mfr")
        device_type = DeviceType.objects.create(
            manufacturer=manufacturer, model="Tamper Closure", slug="tamper-closure"
        )
        role = DeviceRole.objects.create(name="Tamper Role", slug="tamper-role")
        cls.device = Device.objects.create(
            name="Tamper-Device", site=site, device_type=device_type, role=role
        )
        # Second device that the cable does NOT terminate on
        cls.other_device = Device.objects.create(
            name="Other-Device", site=site, device_type=device_type, role=role
        )

        fct = FiberCableType.objects.create(
            manufacturer=manufacturer, model="Tamper-FCT",
            construction="loose_tube", fiber_type="smf_os2", strand_count=4,
        )

        # Cable on cls.device
        cls.cable_on_device = Cable.objects.create()
        cls.fc_on_device = FiberCable.objects.create(
            cable=cls.cable_on_device, fiber_cable_type=fct
        )

        # Cable on other_device (not terminating on cls.device)
        cls.cable_on_other = Cable.objects.create()
        cls.fc_on_other = FiberCable.objects.create(
            cable=cls.cable_on_other, fiber_cable_type=fct
        )

        cls.user = User.objects.create_user(
            username="tamper_user", password="testpass", is_superuser=True
        )

    def test_create_fibercable_rejects_unrelated_cable(self):
        """POST cable_id for a cable that doesn't terminate on the device."""
        self.client.force_login(self.user)
        fct = FiberCableType.objects.first()
        url = f"/plugins/fms/fiber-overview/{self.device.pk}/create-fiber-cable/"
        response = self.client.post(url, {
            "cable_id": self.cable_on_other.pk,
            "fiber_cable_type": fct.pk,
        })
        # Should either return 400/404 or re-render form with error
        assert response.status_code in (400, 404) or b"error" in response.content.lower() or b"alert" in response.content.lower()

    def test_provision_strands_rejects_unrelated_fibercable(self):
        """POST fiber_cable_id for a cable that doesn't terminate on the device."""
        from dcim.models import Module, ModuleBay, ModuleType

        module_type = ModuleType.objects.create(manufacturer=Manufacturer.objects.first(), model="Tamper Tray")
        bay = ModuleBay.objects.create(device=self.device, name="Tamper Bay")
        module = Module.objects.create(device=self.device, module_bay=bay, module_type=module_type)

        self.client.force_login(self.user)
        url = f"/plugins/fms/fiber-overview/{self.device.pk}/provision-strands/"
        response = self.client.post(url, {
            "fiber_cable_id": self.fc_on_other.pk,
            "target_module": module.pk,
            "port_type": "splice",
        })
        assert response.status_code in (400, 404) or b"error" in response.content.lower() or b"alert" in response.content.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_security.py::TestHiddenFieldTampering -v
```

Expected: FAIL — views accept any cable_id/fiber_cable_id without checking device context.

- [ ] **Step 3: Add validation to CreateFiberCableFromCableView.post**

In `netbox_fms/views.py`, in the `post` method of `CreateFiberCableFromCableView` (around line 838), after getting the cable, validate it terminates on the device:

```python
    @transaction.atomic
    def post(self, request, pk):
        if not request.user.has_perm("netbox_fms.add_fibercable"):
            return HttpResponse("Permission denied", status=403)
        device = get_object_or_404(Device, pk=pk)
        form = CreateFiberCableFromCableForm(request.POST)
        if not form.is_valid():
            cable = get_object_or_404(Cable, pk=request.POST.get("cable_id"))
            return render(
                request,
                "netbox_fms/htmx/create_fiber_cable_modal.html",
                {
                    "device": device,
                    "cable": cable,
                    "already_exists": False,
                    "form": form,
                    "post_url": reverse("plugins:netbox_fms:fiber_overview_create_fibercable", kwargs={"pk": pk}),
                },
            )

        cable = get_object_or_404(Cable, pk=form.cleaned_data["cable_id"])

        # Validate cable terminates on this device
        from dcim.models import CableTermination

        if not CableTermination.objects.filter(cable=cable, _device_id=device.pk).exists():
            return HttpResponse("Cable does not terminate on this device", status=400)

        FiberCable.objects.create(
            cable=cable,
            fiber_cable_type=form.cleaned_data["fiber_cable_type"],
        )

        redirect_url = reverse("dcim:device", kwargs={"pk": pk}) + "fiber-overview/"
        response = HttpResponse(status=200)
        response["HX-Redirect"] = redirect_url
        return response
```

- [ ] **Step 4: Add validation to ProvisionStrandsFromOverviewView.post**

In `netbox_fms/views.py`, in `ProvisionStrandsFromOverviewView.post` (around line 894), after getting fiber_cable, validate it belongs to the device:

After line `fiber_cable = get_object_or_404(FiberCable, pk=fiber_cable_id)`, add:

```python
        # Validate fiber_cable's cable terminates on this device
        from dcim.models import CableTermination

        if fiber_cable.cable and not CableTermination.objects.filter(
            cable=fiber_cable.cable, _device_id=device.pk
        ).exists():
            return HttpResponse("Fiber cable does not terminate on this device", status=400)
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_security.py -v
```

Expected: All tests PASS.

- [ ] **Step 6: Run full test suite for regressions**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add netbox_fms/views.py tests/test_security.py
git commit -m "security: validate hidden form fields against device context"
```
