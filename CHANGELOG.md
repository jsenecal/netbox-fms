# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-05-26

### Added

- `FiberAttenuationSpec` model -- per-wavelength manufacturer max attenuation (dB/km) attached to a `FiberCableType`. Multiple rows per cable type let one product cover several operating wavelengths (1310/1550/1625, 850/1300, CWDM/DWDM grid). Unique on `(fiber_cable_type, wavelength_nm)`. Full plugin checklist (forms, tables, filters, views, urls, REST + GraphQL, navigation, templates).
- `FiberCableType.get_attenuation(wavelength_nm)` helper returning the max-loss spec value (Decimal dB/km) or `None`.
- `FiberCable.calculated_loss_db` -- per-cable read-only `@property` returning `[(wavelength_nm, loss_db), ...]` tuples computed as `glass_length_km * spec.max_loss_db_per_km` for each spec on the cable type. Empty when `glass_length` is unresolvable or no specs exist.
- `FiberCircuitPath.calculated_loss_db` is now a read-only `@property` returning `[(wavelength_nm, loss_db), ...]` tuples; it consumes per-cable values from `FiberCable.calculated_loss_db` and intersects wavelengths across all cables in the path.
- `FiberCircuitPath.get_calculated_loss_db(wavelength_nm=None)` helper returning the Decimal loss at a single wavelength (defaults to the path's own `wavelength_nm`).
- `FiberCable.clean()` now rejects a linked `dcim.Cable` whose `type` is not a fibre type (one of `FIBER_CABLE_TYPES`: SMF/MMF variants).
- `FiberCableType.outer_diameter` (FloatField, mm-implicit) -- manufacturer spec for the cable's outer diameter; required input for conduit-fill and pull-tension calculations.
- `FiberCableType.twist_factor_ratio` (FloatField, dimensionless) -- manufacturer spec for the helical pitch / lay factor; the ratio of glass-length excess over sheath length.
- `FiberCableType.mark_unit` (CharField, `CableLengthUnitChoices`, blank) -- the unit of the distance markings printed on the cable jacket by the manufacturer. Empty means "no sheath markings on this cable type".
- `FiberCable.glass_length` -- read-only property computing `cable.length * (1 + fiber_cable_type.twist_factor_ratio)` in the cable's `length_unit`. Returns `None` when either operand is missing. Exposed in REST and GraphQL.
- `FiberCable.start_mark` / `end_mark` (Decimal max_digits=10 dp=2, nullable) -- absolute sheath-distance reference frame at the A-end and B-end of the cable, read in the cable type's `mark_unit`. `save()` swaps the two if inverted; `clean()` checks non-negative and that the type declares a `mark_unit`.
- `FiberCable.installed_by` -- FK to `tenancy.Tenant`, `on_delete=PROTECT`, nullable. Names the contractor or workforce that physically installed the cable.
- `SlackLoop.mark_unit` -- read-only `@property` delegating to `fiber_cable.fiber_cable_type.mark_unit`. The model `__str__` and detail templates now use this.
- Forms (main / import / bulk-edit), table, REST + GraphQL serializers/types, search index display, and detail templates updated for the cable-type fields and the derived FiberCable property.
- Canonical normalize-toolkit CI/CD shape: 5 GHA workflows (`ci.yml`, `publish.yml`, `docs.yml`, `release-drafter.yml`, `pr-title.yml`) + `.github/release-drafter.yml`.
- `.pre-commit-config.yaml` with ruff hooks + standard pre-commit-hooks + a `commit-msg` stage that rejects AI/Claude attribution lines.
- `.git-template/hooks/commit-msg` (canonical hook tracked in-tree, referenced by pre-commit).
- `uv.lock` committed for reproducible CI/dev environments.

### Changed

- Forms (main / import / bulk-edit / filter), tables, REST + GraphQL serializers/types, search index display_attrs, and detail templates updated for the three additions and the SlackLoop unit move.
- CI: switched dependency installation to `uv` for faster caching; expanded matrix testing now uses self-contained `configuration.py` (no reliance on NetBox's example) with `DATABASES` in PostGIS form. Codecov upload uses OIDC (tokenless).
- `publish.yml` split into `build` (unprivileged) + `publish-to-pypi` (`environment: pypi` with `id-token: write`).
- `pyproject.toml`: added `extend-exclude = ["**/migrations/*.py"]`, ignored `N806` globally (Django `User = get_user_model()` idiom), explicit `[tool.ruff.format]` config, bumpver `CHANGELOG.md` file pattern so the Unreleased section is promoted on every version bump.
- README aligned to canonical skeleton (badges, Compatibility table, Documentation links, Contributing section).

### Removed

- `FiberCableType.fiber_type` and the plugin's `FiberTypeChoices` -- this duplicated NetBox's built-in `dcim.Cable.type` (`CableTypeChoices`). The fibre classification (SMF/MMF, OS1/OS2/OM1..5) now lives only on the `dcim.Cable` instance; `FiberCable.clean()` validates the linked Cable carries a fibre `type` from `FIBER_CABLE_TYPES`. Detail templates that previously rendered `get_fiber_type_display` now read `cable.get_type_display`.
- `FiberCircuitPath.calculated_loss_db` as a stored field -- replaced with a computed property (see Added). Forms no longer accept a manually entered value.
- `SlackLoop.length_unit` -- redundant with `FiberCableType.mark_unit`. The marking unit is a manufacturer/type property, not a per-instance choice; the existing `length_unit` field is dropped and any pre-existing values are backfilled into the cable type's `mark_unit` (modal value per type) by the migration before the column is removed.

### Fixed

- PyPI wheel now ships the plugin's `static/` directory -- the built-in stylesheets (`css/splice_editor.css`, `css/fms-components.css`) and bundled JS (`dist/splice-editor.min.js`, `dist/fms-htmx.min.js`, `dist/trace-view.min.js`, plus sourcemaps). Previously `pyproject.toml` `package-data` only listed `templates/**/*`, so `pip install netbox-fms` produced an install with no static assets and `collectstatic` had nothing to copy, causing 404s on the splice editor page (#48). The TypeScript source, `node_modules/`, and esbuild config are intentionally excluded -- they are only needed to rebuild the assets, not to run them.

## [0.1.0] - 2026-02-18

First public release of NetBox FMS, a fiber management plugin for NetBox 4.5+.

### Added

- **FiberCableType / FiberCable** -- blueprint and instance pattern for fiber cables with auto-instantiation of buffer tubes, ribbons, strands, and cable elements.
- **Four construction cases** -- loose tube, ribbon-in-tube, central-core ribbon, and tight buffer.
- **Splice planning** -- `SpliceProject` and `SplicePlan` with strand-to-strand entry mapping, diff computation against live state, quick-add workflow, and draw.io export.
- **Fiber circuits** -- end-to-end circuit provisioning with DAG-based pathfinding, multi-hop tracing, and protection circuit queries.
- **Device fiber overview** -- aggregated fiber view per device with closure cable entry management and gland labeling.
- **Slack loops** -- tracking of slack loop locations and storage methods at splice closures, with insert-into-closure workflow.
- **Link topology** -- cable topology linking with port provisioning and cable profile assignment.
- **Full API coverage** -- REST API (21 serializers, 20 viewsets) and GraphQL (16 types) for all models.
- **Search integration** -- `FiberCableType`, `FiberCable`, `SplicePlan`, `SpliceProject`, `FiberCircuit`, and `SlackLoop` indexed in NetBox global search.
- **Interactive splice editor** -- TypeScript/D3-based visual splice editor with drag-and-drop.
