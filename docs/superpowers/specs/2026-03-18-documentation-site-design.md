# NetBox FMS Documentation Site — Design Spec

**Date:** 2026-03-18
**Status:** Draft
**Repository:** github.com/jsenecal/netbox-fms
**Plugin Version:** v0.1.0

## Overview

Comprehensive documentation site for the netbox-fms NetBox plugin, built with Zensical (the static site generator from the Material for MkDocs team). Primary audience is NetBox admins installing and using the plugin; secondary audience is developers extending or contributing to it.

## Site Structure

```
docs/
├── zensical.yaml
├── index.md                          # Project overview, feature highlights, quick links
├── getting-started/
│   ├── installation.md               # pip install, NetBox plugin config, migrations
│   ├── configuration.md              # Plugin settings, permissions
│   └── quickstart.md                 # End-to-end: cable type → cable → splice plan
├── user-guide/
│   ├── concepts.md                   # Type/Instance pattern, construction cases, EIA-598 colors
│   ├── fiber-cable-types.md          # Creating/managing cable type blueprints
│   ├── fiber-cables.md               # Creating cables, auto-instantiation, linking topology
│   ├── splice-planning.md            # SpliceProject, plans, entries, diff, draw.io export
│   ├── fiber-circuits.md             # Provisioning, path tracing, loss budgets
│   └── device-fiber-overview.md      # Device tab, closure cable entries, gland assignment
├── developer/
│   ├── architecture.md               # Data model hierarchy, signal flow, service layer
│   ├── api-examples.md               # Curated REST/GraphQL examples (5-6 workflows)
│   └── contributing.md               # Dev environment, tests, adding-a-model checklist
├── reference/
│   ├── choices.md                    # All ChoiceSet values
│   └── cable-profiles.md             # Strand-count-to-profile mapping table, registration via PluginConfig.ready()
└── superpowers/                      # Existing plans/specs (excluded from site nav)
```

## Navigation

Four top-level groups:

1. **Getting Started** — installation, configuration, quickstart
2. **User Guide** — concepts, cable types, cables, splicing, circuits, device overview
3. **Developer** — architecture, API examples, contributing
4. **Reference** — choices, cable profiles

## Content Approach

### Getting Started

Concise, task-oriented. Installation covers pip install, `PLUGINS` config in `configuration.py`, running migrations, and verifying the plugin loads. Quickstart walks through one complete workflow end-to-end so users see value immediately.

### User Guide

Each page follows a consistent pattern:
- Brief concept explanation with Mermaid diagram where helpful
- Step-by-step instructions for key workflows
- Notes on edge cases or gotchas
- Cross-references to related pages

`concepts.md` is the anchor page — explains the Type/Instance pattern (analogous to NetBox's Device/DeviceType), the four construction cases (loose tube, ribbon-in-tube, central-core ribbon, tight buffer), and EIA-598 automatic fiber coloring. Other pages reference back rather than re-explaining.

### Developer

Lighter weight than the user guide:
- `architecture.md` — data model hierarchy diagram, service layer overview (`services.py`, `provisioning.py`, `trace.py`, `export.py`, `constants.py`), signal flow
- `api-examples.md` — 5-6 curated examples showing common workflows via curl and Python. Points users to NetBox's built-in browsable API and GraphQL explorer for full reference
- `contributing.md` — dev environment setup (Docker devcontainer), running tests, lint/format commands, the "adding a new model" checklist

### Reference

Tables of all choice values (from `choices.py`) and cable profiles (from `cable_profiles.py`). Minimal prose.

## Diagrams

Mermaid diagrams for:
- **Type/Instance hierarchy** — FiberCableType → templates → FiberCable → instances
- **Construction case decision tree** — which templates produce which instance structure
- **Fiber path trace flow** — FrontPort → PortMapping → RearPort → Cable → repeat
- **Splice planning workflow** — project → plan → entries → diff → apply
- **Circuit provisioning flow** — device selection → path discovery → proposal → creation

## Zensical Configuration

- Config file: `docs/zensical.yaml` (Zensical can also read `mkdocs.yml` format; use whichever Zensical's docs recommend)
- Project name: "NetBox FMS"
- Repository URL: `https://github.com/jsenecal/netbox-fms`
- Mermaid diagram rendering enabled
- `superpowers/` excluded from navigation
- Default theme with minimal customization

## Build Tooling

New Makefile targets:
- `make docs` — build the Zensical site (`zensical build`)
- `make docs-serve` — live preview with auto-rebuild (`zensical serve`)
- Both targets assume `zensical` is installed in the environment

## Out of Scope

- **Playwright screenshots** — deferred to a follow-up task. When added, a script in `docs/screenshots/` would capture key views and save to `docs/assets/screenshots/`
- **Auto-generated API reference** — users pointed to NetBox's browsable API instead
- **Changelog** — can be added later from git history

## Dependencies

- `zensical` Python package (added to dev dependencies in `pyproject.toml`)
- No other external dependencies

## Constraints

- No changes to existing `docs/superpowers/` plans or specs
- Documentation must be accurate for v0.1.0 of the plugin
- All content derived from current codebase state
