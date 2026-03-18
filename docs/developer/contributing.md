# Contributing

## Development Environment

- The plugin runs inside a Docker devcontainer with NetBox.
- NetBox source is located at `/opt/netbox`. It is not an installable Python module; it is importable at runtime via the Django settings path.
- Plugin source is at `/opt/netbox-fms`.
- Requires Python 3.12+ and NetBox 4.5+.

## Key Commands (from Makefile)

| Command | Description |
|---------|-------------|
| `make lint` | Run ruff linter with auto-fix |
| `make format` | Run ruff formatter |
| `make check` | Run ruff checks without modifying files |
| `make test` | Run full test suite with coverage |
| `make test-fast` | Run tests without coverage |
| `make test-one T=tests/test_models.py::TestClass::test_method` | Run a single test |
| `make test-k K=fiber_cable` | Run tests matching keyword |
| `make migrations` | Generate new migrations |
| `make migrate` | Apply all migrations |
| `make verify` | Verify all plugin modules import cleanly |
| `make validate` | Run all checks (lint + import verification) |

## Ruff Configuration

- **Line length:** 120
- **Target:** Python 3.12
- **Rules:** E, F, W, I, N, UP, S, B, A, C4, DJ, PIE
- **Ignored:**
  - `E501` -- line length is handled by the formatter
  - `S101` -- `assert` in tests is acceptable
  - `DJ01` -- nullable string fields in Django models are permitted

## Adding a New Model Checklist

When adding a model, update **all** of the following files:

1. `models.py` -- model class, add to `__all__`
2. `choices.py` -- if new choice fields are needed
3. `forms.py` -- Form, ImportForm, BulkEditForm, FilterForm
4. `filters.py` -- FilterSet
5. `tables.py` -- Table class
6. `views.py` -- List, Detail, Edit, Delete, Bulk views
7. `urls.py` -- URL patterns
8. `api/serializers.py` -- Serializer
9. `api/views.py` -- ViewSet
10. `api/urls.py` -- Router registration
11. `graphql/types.py`, `graphql/schema.py`, `graphql/filters.py`
12. `templates/netbox_fms/<modelname>.html` -- detail template
13. `search.py` -- if the model should be searchable
14. `navigation.py` -- if the model needs menu entries

## URL Naming Convention

All URL names follow this pattern:

- Detail: `plugins:netbox_fms:<modelname_lowercase>`
- List: `plugins:netbox_fms:<modelname_lowercase>_list`
- Add: `plugins:netbox_fms:<modelname_lowercase>_add`
- Edit: `plugins:netbox_fms:<modelname_lowercase>_edit`
- Delete: `plugins:netbox_fms:<modelname_lowercase>_delete`

## Running Tests

Using the Makefile (recommended):

```bash
make test          # full suite with coverage
make test-fast     # without coverage
make test-one T=tests/test_models.py::TestClass::test_method
```

Or directly:

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v
```
