# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- The splice plan apply endpoint
  (`POST /api/plugins/fms/splice-plans/{id}/apply/`) no longer bypasses the
  approval workflow. Applying now requires the plan to be in `approved`
  status (other statuses get a 409 with an explanatory message) and the
  requesting user to hold the `approve_spliceplan` permission (403
  otherwise). The status gate is enforced in the `apply_diff()` service so
  every apply path is covered, and the closure Pending Work batch apply now
  requires `approve_spliceplan` as well. After a successful apply the plan
  automatically transitions to `archived`, matching the batch apply
  behavior. (#111)

### Added

- Splice editor express support: the splice detail panel shows an Express
  row with a Set/Clear toggle for planned splices, and a toolbar "Express"
  mode marks new connections as pass-through at creation time. The
  bulk-update endpoint now accepts and persists `is_express` on added
  entries (it previously dropped the flag), the closure-strands API exposes
  `plan_is_express` per strand, and express plan splices render with a
  distinct tight-dash line style. (#117)
- Splice editor: new "Tube" mode bulk-splices two buffer tubes
  fiber-to-fiber. Click a tube header on each side; when both tubes have
  the same number of unspliced fibers, the editor queues 1:1 pending
  splices in positional order (already spliced, pending, or
  circuit-protected fibers are skipped). Mismatched or fully spliced
  tubes get an explanatory status message instead. (#116)
- Splice editor: errors and blocked-action warnings now appear as
  persistent, dismissible alerts above the canvas instead of the 3-second
  stats bar flash (informational status keeps the flash). The editor also
  shows preflight warnings on load when buffer tubes are not assigned to
  any splice tray, when no splice plan exists for the closure, or when
  only non-draft plans exist. Fixes #115.
- DIN IEC 60304 fiber color scheme -- `FiberCableType.color_scheme` now
  offers the German DIN VDE 0888 fiber sequence (Red, Green, Blue, Yellow,
  White, Grey, Brown, Violet, Turquoise, Black, Orange, Pink) alongside
  EIA/TIA-598 and ABNT NBR 14771. The default is unchanged. Refs #107.
- Device pickers in the wizard flows (closure cable wizard far end device,
  circuit wizard origin/destination devices, slack loop insertion closure)
  now offer NetBox's object selector popup, allowing devices to be found
  by site, location, rack, and other filters instead of scrolling a flat
  list of all devices. Fixes #88.
- Splice closure creation wizard: **FMS > Add Splice Closure** creates the
  closure Device with named "Tray 1..N" module bays, tray modules, and
  optional express basket bays in one atomic action. Requires tray
  ModuleTypes marked with a TrayProfile.
- Closure cable wizard: **Add Cable** on a closure's Fiber Overview tab
  creates the dcim.Cable, FiberCable, per-tube rear ports, per-strand
  front ports, port mappings, cable terminations, cable profile, and blank
  gland entries at both end devices in one atomic three-step flow. This is
  the first UI path that can create a cable between two bare closures.
- `FiberCableType.color_scheme` -- selects the fiber strand color standard
  (EIA/TIA-598, the previous hardcoded behavior and still the default, or
  ABNT NBR 14771 for Brazilian plant) used to auto-assign strand colors at
  FiberCable creation. Changing the scheme later does not recolor existing
  cables, mirroring component-template semantics. Exposed in forms, CSV
  import, bulk edit, filters, table column, REST API, and GraphQL.
  Buffer tube and ribbon template color pickers now group choices by the
  parent type's standard (position-ordered, with an "Other" fallback
  group). Fixes #60.
- Tube assignments now manage dcim port placement: assigning a buffer tube
  to a splice tray moves the tube's closure-side strand FrontPorts onto the
  tray module, re-pointing follows tray/tube changes, and deleting the
  assignment returns the ports to device level. Ports already owned by a
  different module block the save with a list of conflicts until the new
  `confirm_reassign` flag (form checkbox / REST field) is set. This is what
  makes applied splices visible to the splice-state reader, which only
  considers FrontPorts on tray modules. Pre-existing assignments are not
  back-filled; re-save an assignment to sync its ports. (#68)
- `terminated_device_id` filter on FiberCable (REST API and UI): cables with
  a dcim termination on the given device. The Closure Cable Entry form's
  Fiber Cable dropdown now chains on the selected Closure so only cables
  physically terminated at that closure are offered. (#92)
- `closure_id` filter on BufferTube (REST API and UI): tubes of fiber
  cables entering a given closure, via ClosureCableEntry. The Tube
  Assignment form's Buffer Tube dropdown now chains on the selected
  Closure so only tubes of cables entering that closure are offered. (#58)

### Changed

- The splice editor's "Save & Apply" action is now "Save & Submit for
  approval": it saves the pending entries and transitions the draft plan
  to `pending_approval` instead of applying splices directly. Applying
  happens later from the approved plan's detail page or the closure's
  Pending Work tab. After a successful submit the editor switches to
  read-only mode, since only draft plans are editable. (#112)
- The splice plan REST endpoint now accepts `status` writes and enforces
  the plan lifecycle on them: draft plans can be submitted for approval
  by any user with change permission (`submitted_by` is filled in from
  the requesting user), while approving, rejecting another user's
  submission, reopening, or archiving a non-draft plan requires the
  `approve_spliceplan` permission. New plans must still be created as
  drafts. Previously `status` was silently ignored on write. (#112)

- The "Fiber Cable" card on NetBox's Cable detail page now links to the FMS
  FiberCable instance, so Cable -> FiberCable navigation is one click away
  (the reverse link already existed). (#57)
- Import forms now declare choice fields as `CSVChoiceField` (`construction`
  and `color_scheme` on FiberCableType, `storage_method` on SlackLoop) so the
  bulk-import UI documents the valid values for each column.
- Docs: documented the full splice-closure preparation workflow (closure device, tray module types with TrayProfiles, module bays/modules, ClosureCableEntry before TubeAssignment, tray-module FrontPorts) in the quickstart and splice-planning guide; added TrayProfile and TubeAssignment to the splice-planning core objects and a Tray Assignments section to the device fiber overview guide. Removed patch-panel framing -- the plugin's workflows are closure-centric and patch panels are not modeled at this time. Fixed the quickstart incorrectly stating that a SpliceProject is associated with a closure (the SplicePlan targets the closure; the project is an optional grouping).

### Removed

- The Provision Ports flow: the modal on the FiberCable page, the
  `provision_strands()` helper, and the `/api/plugins/fms/provision-ports/`
  REST endpoint (breaking). It created ports without cable terminations,
  leaving them invisible to the Fiber Overview and untraceable. Greenfield
  port creation is handled by the closure cable wizard; adopting existing
  ports remains covered by Link Topology.

### Fixed

- Fiber Overview no longer lists the front-port jumper cables that applying a
  splice plan creates. The cable table now shows only cables that terminate on
  a rear port of the closure or that already carry a FiberCable, so splice
  jumpers no longer appear as unlinked cables offering a "Link Topology"
  button, and the Cables counter no longer counts them. The link-topology
  endpoint also rejects cables outside the closure's fiber topology. Fixes #93.
- The splice editor's "Save & Apply" button saved the entries and then
  form-POSTed to the read-only pending-changes page, which only accepts
  GET -- the browser landed on a 405 error page after a half-finished
  operation. The renamed "Save & Submit for approval" flow now performs
  every call with fetch and reports success or failure in the editor's
  alert area instead of navigating away. When the closure had no plan
  yet, the same button skipped the plan quick-create step and died with
  "No bulk update URL"; it now opens the quick-create modal first, just
  like plain Save. (#112)
- The Slack Loops layer on the netbox-pathways interactive map now declares a
  `url_template`, so the map sidebar's detail pane shows a "View Details" link
  to the slack loop instance. Refs jsenecal/netbox-pathways#81.
- Bulk edit forms no longer silently overwrite choice fields that were left
  untouched: `construction`, `sheath_material`, `deployment`, `fire_rating`,
  and `mark_unit` on FiberCableType, `element_type` on CableElementTemplate,
  `storage_method` on SlackLoop, `status` on FiberCircuit, and `tray_role` on
  TrayProfile now offer a blank "no change" option, matching the existing
  `marker_type` fields. Previously the first choice was preselected and
  applied to every selected object on save.
- `create_sample_data` no longer passes the removed
  `SlackLoop.length_unit` kwarg (which crashed both full and --simple
  modes) and sets `mark_unit` on the sample cable types so slack loop
  marks remain expressed in meters. (#56)
- Navigation: the Fiber Circuit Paths and Splice Plan Entries menu
  entries now show the create (+) button for users with the matching
  add permission. (#63)
- "Apply all Approved Plans" on the closure Pending Work tab raised
  `TransactionManagementError` ("select_for_update cannot be used outside
  of a transaction") because the plan queryset was locked before entering
  the atomic block. The whole apply-all operation now runs inside a single
  transaction. ([#65](https://github.com/jsenecal/netbox-fms/issues/65))
- `create_sample_data` provisioned FrontPorts and Interfaces with
  `bulk_create()`, which skips `post_save` and leaves NetBox's device
  counter caches (`front_port_count`, `interface_count`) at zero. Since
  device component tabs hide when their counter badge is empty, the Front
  Ports tab disappeared from provisioned devices even though the ports
  existed. The command now emits `post_save` for each bulk-created
  component, mirroring NetBox core's own pattern. (#62)
- Link Topology: cables terminated on multiple rear ports now map all
  strands. Per-rear-port positions are offset into global strand
  positions instead of clobbering each other, which previously linked
  only the first module's front ports and reported a spurious count
  mismatch. (#64)

### Security

- Four custom API views bypassed NetBox object-level permissions. The
  fiber-circuit-nodes viewset and the fiber-circuits/protecting view
  ignored `ObjectPermission` constraints, serving every row to any user
  with a model-level view permission; the fiber-claims and
  closure-strands views required only authentication, disclosing splice
  plans, strand maps, and circuit names to users with no permissions at
  all. All querysets feeding those responses are now restricted to the
  requesting user's permitted objects, matching the enforcement the
  `NetBoxModelViewSet`-based endpoints have always had. Reported
  alongside jsenecal/netbox-pathways#123.

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
