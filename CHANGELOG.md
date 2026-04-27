# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Canonical normalize-toolkit CI/CD shape: 5 GHA workflows (`ci.yml`, `publish.yml`, `docs.yml`, `release-drafter.yml`, `pr-title.yml`) + `.github/release-drafter.yml`.
- `.pre-commit-config.yaml` with ruff hooks + standard pre-commit-hooks + a `commit-msg` stage that rejects AI/Claude attribution lines.
- `.git-template/hooks/commit-msg` (canonical hook tracked in-tree, referenced by pre-commit).
- `uv.lock` committed for reproducible CI/dev environments.

### Changed

- CI: switched dependency installation to `uv` for faster caching; expanded matrix testing now uses self-contained `configuration.py` (no reliance on NetBox's example) with `DATABASES` in PostGIS form. Codecov upload uses OIDC (tokenless).
- `publish.yml` split into `build` (unprivileged) + `publish-to-pypi` (`environment: pypi` with `id-token: write`).
- `pyproject.toml`: added `extend-exclude = ["**/migrations/*.py"]`, ignored `N806` globally (Django `User = get_user_model()` idiom), explicit `[tool.ruff.format]` config, bumpver `CHANGELOG.md` file pattern so the Unreleased section is promoted on every version bump.
- README aligned to canonical skeleton (badges, Compatibility table, Documentation links, Contributing section).

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
