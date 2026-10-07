# Path Analysis

Fiber paths are not entered by hand. A background analysis reads the plant
(cable terminations, port mappings, strand landings and splice jumpers),
derives every continuous fiber path, and stores the result. Fiber circuits
then [assign](fiber-circuits.md) those paths. The plant is the only source of
truth: change the plant and the paths follow.

---

## What is analyzed

Four kinds of plant data feed the analysis:

- **Cable terminations** -- which rear ports a `dcim.Cable` joins.
- **Port mappings** -- which front ports sit behind which rear-port position.
- **Strand landings** -- which front ports each `FiberStrand` lands on.
- **Splice jumpers** -- zero-length cables joining two front ports inside a
  closure.

From these the analysis builds a graph of ports (`networkx`) and walks it.
Every fiber is a linear chain, so each strand belongs to exactly one stored
path, whether or not the path is complete.

### Hops

A `FiberStrandPath` is an ordered list of hops. A hop is one of:

| Hop              | When                                                                                  |
| ---------------- | ------------------------------------------------------------------------------------- |
| Strand           | The cable has a `FiberCable`: one hop per strand the fiber runs over.                |
| Plain cable      | The cable has no `FiberCable` (a patch cord, an unmodeled cable).                     |
| Provider circuit | A trunk lands on a `CircuitTermination`: the core circuit is crossed as one opaque hop. |

Splices are implied: two consecutive strand hops that meet at a closure are
spliced there. The provider span contributes no loss; it documents that a
fiber crosses a provider circuit, nothing more.

---

## Ends and completeness

Each end of a path is classified:

- **Terminated** -- the path stops on a front port of any type other than
  `splice`, or on a port patched to an interface.
- **Open** -- a `splice` front port with nothing continuing it, or no port at
  all. An open end records a reason:
    - `unspliced`: glass ends unspliced in a closure where sibling fibers of
      the same cable are spliced.
    - `cable_end`: a cable end with nothing beyond it (a stub, a coil).

A path's **completeness** is `terminated_terminated`, `terminated_open` or
`open_open`. Only a path terminated at both ends is offered for assignment
unless "Allow incomplete paths" is ticked.

An unspliced `splice` port is therefore never a complete end. Older releases
treated it as one.

---

## Anomalies

Some plant shapes are not a single chain. The analysis does not guess: it
records a **Path Anomaly** and does not trace those strands. Anomalies are
replaced on each run, so fixing the plant clears them.

| Kind                   | Meaning                                              | Fix                                                                  |
| ---------------------- | ---------------------------------------------------- | -------------------------------------------------------------------- |
| `too_many_connections` | A port joins more than two fiber connections.        | Remove the extra port mapping, splice or strand landing.             |
| `loop`                 | The fiber connections form a closed loop.            | Break the loop (remove one splice or cable).                         |
| `dangling_reference`   | A strand points at a port or cable that is not there. | Re-land the strand on an existing port or remove the stale link.    |

A stored path that loses all its strands to an anomaly is treated as gone:
an unassigned path is deleted, an assigned one becomes broken as `path_lost`.

---

## Routes

Every path has a `route_key`: a hash of the ordered cables it follows. Paths
with the same key run over the same cables, in the same order, and so share
fate (one cut takes them all). The assignment picker groups paths by route
key, so the strands of one circuit end up on one route.

---

## Proposed and defective paths

- **Proposed** (`is_proposed`) -- the path touches `planned` plant (a planned
  cable, or an end device that is `planned`). The picker offers proposed paths
  only to circuits whose status is `planned`.
- **Defective** (`is_defective`) -- reserved for fault data. Fault inputs are
  not built yet, so this is always `False` today; the picker already skips
  defective paths so that fault support needs no change there.

---

## Keeping it current

Plant changes queue the devices they touch (`PathAnalysisQueue`). The
`Fiber path analysis` job re-analyzes the queued devices after a short window,
once per window no matter how many changes arrive.

| Change                                                              | Devices queued                     |
| ------------------------------------------------------------------- | ---------------------------------- |
| Cable created, changed or deleted                                   | Devices of its terminations        |
| Splice jumper created, changed or deleted                           | The closure                        |
| Cable termination, port mapping or FiberCable changed               | The device concerned               |
| Strand saved                                                        | Devices of the ports it lands on   |
| Closure cable entry changed                                         | The closure                        |
| Bulk import or provisioning that bypasses per-object signals        | The devices written                |

Only devices with a FiberCable connected, or that appear on a stored path,
are queued. A device's last cable being removed still queues it.

How a run behaves:

- The first change schedules the job `path_analysis_window_seconds` (default
  30) later; later changes inside the window join the same run.
- One analysis runs at a time (a database advisory lock); a run that finds the
  lock held reschedules itself one window later.
- A run is one transaction. If it fails, nothing is written and no queue row
  is deleted; the next run retries everything.
- The `Fiber path reconcile` system job rebuilds every path from the whole
  plant every `path_reconcile_interval_minutes` (default 1440, daily) and
  repairs anything that bypassed the signals. It runs when the worker starts.
- To reconcile immediately, run:

```bash
python manage.py reconcile_fiber_paths
```

---

## Settings

| Setting                           | Default | Meaning                                                  |
| --------------------------------- | ------- | -------------------------------------------------------- |
| `path_analysis_window_seconds`    | `30`    | Batching window for the incremental analysis             |
| `path_reconcile_interval_minutes` | `1440`  | Cadence of the whole-plant reconcile                     |
| `reroute_window_ratio`            | `0.2`   | Reserved for the future re-route search; not used yet    |

See [Configuration](../getting-started/configuration.md).

---

## Inspecting the results

Under **FMS > Path Analysis** in the menu:

- **Fiber Paths** -- every stored path, filterable by completeness, proposed,
  defective, assigned, and device. Each path's detail page shows its ends, the
  open-end reasons and its hops.
- **Path Anomalies** -- the plant shapes the analysis refused to trace.
- **Analysis Queue** -- devices waiting for the next run.

All three are read-only. The same data is available from the REST API:

```bash
GET /api/plugins/fms/fiber-strand-paths/?completeness=terminated_terminated&assigned=false
GET /api/plugins/fms/fiber-strand-paths/?device_id=12&cable_id=42
GET /api/plugins/fms/path-anomalies/?kind=loop
GET /api/plugins/fms/path-analysis-queue/
```

`fiber-strand-paths` also filters by `strand_id`, `end_a_port_id`,
`end_b_port_id`, `route_key`, `is_proposed` and `is_defective`. Hops are
embedded in each path.
