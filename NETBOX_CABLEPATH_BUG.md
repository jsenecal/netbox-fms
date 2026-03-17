# Bug: CablePath.from_origin() Discards Multi-Position Cable Positions During Profile-Based Tracing

## Summary

`CablePath.from_origin()` in `dcim/models/cables.py` has two bugs that cause multi-position cable connections (e.g. duplex fiber) to only trace a single position. When an interface is connected via a profiled cable that carries multiple positions (such as `single-1c2p` for duplex LC fiber), only the first position is seeded into the position stack, and only the first position is resolved when crossing subsequent profiled cables. This means the trace shows only one strand of a duplex pair instead of both.

## Affected Version

NetBox 4.5+ (cable profiles feature). The bugs are in the profile-based tracing code path introduced with cable profiles.

## Affected File

`netbox/dcim/models/cables.py` — `CablePath.from_origin()` classmethod

## The Problem

### Real-world scenario

A duplex fiber patch cable (profile `single-1c2p`) connects one switch interface to one patch panel FrontPort. The FrontPort has `positions=2`, representing both TX and RX strands. Each position maps via PortMapping to a different strand on the panel's RearPort (e.g. position 1 → strand 1, position 2 → strand 2).

When the interface is connected via the 1C2P profiled cable, `Cable.update_terminations()` creates a `CableTermination` with `positions=[1, 2]`, and the interface's `cable_positions` field is set to `[1, 2]`.

The expected behavior is that `CablePath.from_origin()` traces **both** strands through the full path. The actual behavior is that only strand 1 is traced; strand 2 is silently discarded.

### Topology that demonstrates the bug

```
                        Patch Panel A                          Splice Closure                         Patch Panel B
[SW-A Interface] ─1C2P─ [FP Pair1 (pos=2)] [RP (pos=12)] ─1C12P─ [RP-A (pos=12)] [FP-A F1] ─splice─ [FP-B F1] [RP-B (pos=12)] ─1C12P─ [RP (pos=12)] [FP Pair1 (pos=2)] ─1C2P─ [SW-B Interface]
                         pos1 → RP pos 1                                          [FP-A F2] ─splice─ [FP-B F2]                                         pos1 → RP pos 1
                         pos2 → RP pos 2                                                                                                                pos2 → RP pos 2
```

Expected trace: Interface → FP Pair1 → RP → **F1 + F2** (both strands) → splices → **F1 + F2** → RP → FP Pair1 → Interface

Actual trace (before fix): Interface → FP Pair1 → RP → **F1 only** → splice → **F1 only** → RP → FP Pair1 → Interface

### Bug 1: Only the first cable position is seeded (line 817)

```python
# BEFORE (buggy):
if isinstance(terminations[0], PathEndpoint) and terminations[0].cable_positions:
    position_stack.append([terminations[0].cable_positions[0]])
```

When a `PathEndpoint` (Interface, ConsolePort, etc.) has `cable_positions` set from a profiled cable connection, this line pushes only the **first** position (`[0]`) onto the position stack, discarding all other positions. For a duplex interface with `cable_positions=[1, 2]`, only `[1]` is pushed.

### Bug 2: Only the first position is used when crossing a profiled cable (lines 858-861)

```python
# BEFORE (buggy):
if links[0].profile:
    cable_profile = links[0].profile_class()
    position = position_stack.pop()[0] if position_stack else None
    term, position = cable_profile.get_peer_termination(terminations[0], position)
    remote_terminations = [term]
    position_stack.append([position])
```

When the trace encounters a profiled cable, `position_stack.pop()[0]` extracts the position list but takes only element `[0]`, discarding the rest. Even if the stack correctly contained `[1, 2]`, only position 1 would be passed to `get_peer_termination()`, and only one remote termination would be resolved.

### Why existing tests don't catch this

The existing `test_102_cable_profile_single_1c2p` in `test_cablepaths2.py` uses **separate interfaces** for each position:

```
[IF1] --C1-- [FP1][RP1] --C3(1C2P)-- [RP2][FP3] --C4-- [IF3]
[IF2] --C2-- [FP2]                        [FP4] --C5-- [IF4]
```

Each interface has its own unprofiled patch cable to its own single-position FrontPort. The 1C2P cable is only the trunk between two RearPorts. This means each interface traces a single position independently, producing 4 separate CablePaths. The bug is never triggered because no single interface ever carries multiple positions.

In real fiber deployments, one SFP transceiver (one interface) drives two strands (TX/RX) through a single duplex LC connector. The 1C2P patch cable connects that one interface to one duplex FrontPort with `positions=2`. This is the scenario that exposes the bug.

## The Fix

### Fix 1: Seed all cable positions (line 817)

```python
# AFTER (fixed):
if isinstance(terminations[0], PathEndpoint) and terminations[0].cable_positions:
    position_stack.append(list(terminations[0].cable_positions))
```

Push the complete list of cable positions onto the stack. For a duplex interface with `cable_positions=[1, 2]`, both positions are now preserved.

### Fix 2: Iterate all positions when crossing a profiled cable (lines 858-866)

```python
# AFTER (fixed):
if links[0].profile:
    cable_profile = links[0].profile_class()
    positions = position_stack.pop() if position_stack else [None]
    remote_terminations = []
    new_positions = []
    for pos in positions:
        term, new_pos = cable_profile.get_peer_termination(terminations[0], pos)
        if term not in remote_terminations:
            remote_terminations.append(term)
        new_positions.append(new_pos)
    position_stack.append(new_positions)
```

Instead of taking only `[0]`, iterate all positions from the stack. For each position, resolve the far-end termination via `get_peer_termination()`. Remote terminations are deduplicated (important: in profiles like TRUNK_2C2P, multiple positions on the same connector resolve to the same far-end termination object). All mapped positions are preserved on the stack for downstream hops.

### Why deduplication matters

For a `single-1c2p` cable connecting an interface to a duplex FrontPort, both positions 1 and 2 map to the **same** far-end FrontPort object (it's one FrontPort with 2 positions). Without deduplication, `remote_terminations` would contain the same FrontPort twice, which would cause issues in downstream path recording (Step 7) and next-hop resolution (Step 8). The `if term not in remote_terminations` check ensures each termination object appears only once, while `new_positions` still tracks all position values for correct PortMapping resolution at subsequent FrontPort/RearPort hops.

### Interaction with downstream code

The rest of `from_origin()` already handles multi-position correctly:

- **Step 8, FrontPort branch (lines 914-937):** When `remote_terminations[0].positions > 1`, it pops the position stack and uses `front_port_position__in=positions` to find all matching PortMappings. With the fix, `positions=[1, 2]` correctly resolves both PortMappings for a duplex FrontPort.

- **Step 8, RearPort branch (lines 939-962):** Similarly uses `rear_port_position__in=positions` to find PortMappings. With positions `[1, 2]` on the stack, both strands are resolved to their corresponding FrontPorts.

- **Legacy (positionless) cables:** Unaffected. Splice cables and other unprofiled cables use the legacy code path which resolves remote terminations via CableTermination queries without consulting the position stack. The position stack passes through these hops unchanged.

## Test Results

All 48 existing cable path tests pass with this fix:

- `test_cablepaths.py` — 35 legacy tests: **all pass**
- `test_cablepaths2.py` — 13 profiled tests + 1 skipped: **all pass**

This includes `test_102_cable_profile_single_1c2p`, `test_104_cable_profile_trunk_2c2p`, `test_106_cable_profile_shuffle`, and `test_223_single_path_via_multiple_pass_throughs_with_breakouts` — all of which exercise multi-position profiles.

## Suggested Test Addition

A new test should be added to `test_cablepaths2.py` that models the real-world duplex scenario: one interface connected via a 1C2P profiled cable to a multi-position FrontPort, tracing through a multi-position trunk to a far-end interface. This would catch regressions on the specific code path that was broken.

```
Suggested topology:

[IF1] --C1(1C2P)-- [FP1(pos=2)][RP1(pos=2)] --C2(1C2P)-- [RP2(pos=2)][FP2(pos=2)] --C3(1C2P)-- [IF2]

Where:
- IF1 has cable_positions=[1,2] via C1
- FP1 has positions=2, with PortMappings: fp_pos=1→rp_pos=1, fp_pos=2→rp_pos=2
- C2 is a 1C2P trunk between RP1 and RP2
- FP2 has positions=2, with PortMappings: fp_pos=1→rp_pos=1, fp_pos=2→rp_pos=2
- IF2 has cable_positions=[1,2] via C3

Expected: one complete CablePath from IF1 to IF2 carrying both positions through the entire trace.
```
