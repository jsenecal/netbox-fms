# Changelog

## v0.1.0 -- Initial Beta Release

First public release of NetBox FMS, a fiber management plugin for NetBox 4.5+.

### New Features

- **FiberCableType / FiberCable** -- Blueprint and instance pattern for fiber cables with auto-instantiation of buffer tubes, ribbons, strands, and cable elements
- **Four construction cases** -- Loose tube, ribbon-in-tube, central-core ribbon, and tight buffer
- **Splice planning** -- SpliceProject and SplicePlan with strand-to-strand entry mapping, diff computation against live state, quick-add workflow, and draw.io export
- **Fiber circuits** -- End-to-end circuit provisioning with DAG-based pathfinding, multi-hop tracing, and protection circuit queries
- **Device fiber overview** -- Aggregated fiber view per device with closure cable entry management and gland labeling
- **Slack loops** -- Track slack loop locations and storage methods at splice closures, with insert-into-closure workflow
- **Link topology** -- Cable topology linking with port provisioning and cable profile assignment
- **Full API coverage** -- REST API (21 serializers, 20 viewsets) and GraphQL (16 types) for all models
- **Search integration** -- FiberCableType, FiberCable, SplicePlan, SpliceProject, FiberCircuit, and SlackLoop indexed in NetBox global search
- **Interactive splice editor** -- TypeScript/D3-based visual splice editor with drag-and-drop
