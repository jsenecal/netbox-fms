# Fiber Faults

A **FiberFault** records one fault event on one [FiberCable](fiber-cables.md):
a cut, a crush, a bad splice-in-the-sheath, anything that makes fibers
unusable. Open faults feed [path analysis](path-analysis.md), so paths that
cross a faulted fiber are flagged defective and circuits riding them break
without anyone having to hunt for them.

---

## Reporting a fault

1. Open the FiberCable and click **Report fault** in the open-faults panel, or
   go to **FMS > Faults > Add**.
2. Pick the cable and, optionally, the affected strands.
3. Set `reported_at` (defaults to now), an optional `location_mark`, a short
   `description` and any `comments`.
4. Save. The fault is created as **Open**.

Bulk import (**FMS > Faults > Import**) accepts whole-cable faults only; add
strand-level faults through the form or the API.

### Whole cable vs strands

- **No strands selected** -- the whole cable is affected (a full cut).
- **Strands selected** -- only those strands are affected. Every strand must
  belong to the fault's cable; the form and the API both reject others.

### Location mark

`location_mark` is the approximate sheath mark of the fault, in the cable
type's mark unit. When the cable has both a start mark and an end mark, the
location mark must lie between them.

---

## Resolving a fault

Set the status to **Resolved**. `resolved_at` is stamped automatically on
resolve and cleared if the fault is reopened. Resolved faults stay on record
but no longer affect paths or circuits.

---

## Defective paths and circuits

While a fault is open:

- A path crossing a faulted strand is flagged `is_defective`. So is a path
  with an unlanded position on a whole-cable-faulted cable.
- The path's hops are not changed, so the break stays visible on the path
  detail page.
- A defective path cannot be assigned to a circuit; the picker never offers
  it and the `assign` API refuses it.
- An active circuit assignment on a path that becomes defective is marked
  broken with reason **Fiber faulted** (`faulted`). Acknowledging the route
  does not clear it, because the route itself has not changed.

### Resolving heals circuits

Creating, changing or resolving a fault queues the affected devices for
re-analysis (the queue entry's reason is **Fault changed**). Once the fault
is resolved, the analysis clears the defective flag and the circuit's
assignments recover with no user action.

---

## Locating a fault

A fault can record where the damage is, in one of two ways:

- **At a closure** (`located_at`): a device where the cable terminates, for a
  broken splice. Deleting the closure deletes the faults located at it.
- **Along the cable** (`distance_from_a`): meters from the cable's A end, for
  damage out on the span.

A fault has one or the other, never both. With netbox-pathways installed, the
plugin works out which route segment (the stretch between two structures on
the cable's route) holds the distance, from the cable's current route each
time; that segment is what the map highlights and what you look at when
planning a replacement. Without netbox-pathways the distance is still
recorded and estimated, it just is not drawn.

### Sources

- **Picked.** You choose the closure or type the distance in the fault form
  (or set `located_at` or `distance_from_a` through the API). With
  netbox-pathways installed, the form also offers a **Route pathway** picker:
  choosing a pathway sets the distance to the middle of the cable's stretch
  through it. A location you pick is **confirmed**.
- **Estimated from a jacket mark.** Read the mark printed on the jacket at the
  damage and enter it as `location_mark`. The distance is
  `|location_mark - start_mark|`, converted to meters.
- **Estimated from an OTDR shot.** Enter the `otdr_origin` (the closure or
  patch-panel device the shot was taken from), the `otdr_distance` in meters
  and, when the origin is not an end of the faulted cable, the `otdr_strand`
  that was shot. The plugin works out how far into the faulted cable the shot
  lands.

If both a jacket mark and OTDR evidence are present, the jacket mark drives
the estimate: a reading taken at the damage beats a distance measured from
elsewhere. The OTDR evidence is kept as corroboration.

### Estimated and confirmed

- **Estimated** means the plugin worked the distance out from evidence. It is
  labelled as an estimate everywhere it appears, and drawn dashed on the map.
- **Confirmed** means a person picked it or accepted the estimate. Editing the
  evidence afterwards does not change a confirmed location.

On the fault page, **Confirm location** turns an estimate into a confirmed
location. **Re-estimate** runs the estimate again against the cable's current
marks and lengths (an estimate is otherwise recomputed only when its evidence
is saved). Re-estimate is not offered once the location is confirmed; clear the
location first to estimate again. Both actions need the `change` permission on
fiber faults. The REST API has the same two actions,
`POST /api/plugins/fms/fiber-faults/<id>/confirm-location/` and
`.../re-estimate/`, which answer 409 when refused.

### How the OTDR estimate walks

1. Start at the origin device and follow the shot strand's analyzed path. With
   no strand given and the origin at an end of the faulted cable, only that
   cable is walked. The walk goes in the direction that reaches the fault's
   cable.
2. Subtract each cable's length (converted to meters) from the distance, and
   stop at the cable where the remaining distance runs out. That cable must be
   the fault's cable.
3. The remaining distance, counted from the end the walk entered, becomes the
   distance from the A end.

### Placing the distance on the route

The cable's route segments are walked from its A end. Recorded slack loops add
their length where they sit on the route; the rest of the difference between
cable length and route length is spread proportionally along the route.
Segment length is the pathway's length, or the length of its geometry. The way
a pathway is drawn does not matter: each one is turned to follow the route
before slack loops are placed. When the route changes, the fault follows it:
nothing about the route is stored on the fault.

### Notes

When an estimate cannot be computed, no distance is stored and the fault shows
one of these notes:

| Note | Meaning |
|------|---------|
| The distance runs past the end of the cable. | The distance exceeds the cable's length. |
| Cable X has no length. | A cable on the walk has no length. |
| The cable has no start mark. | A jacket mark needs the cable's start mark. |
| The shot lands on cable X, not this fault's cable. | The distance runs out on a different cable. |
| The shot's origin is not on the shot strand's path. | The origin device is not on that path. |
| Hop N of the shot's path has no known length. | A plain cable without a length or a provider circuit stops the walk. |
| The shot strand has no analyzed path. | Path analysis has not produced a path for it. |
| The shot strand's path does not cross this fault's cable. | The path never reaches the cable. |

When a distance cannot be placed on the route, the fault page shows why in the
**Route segment** row and the fault is left off the map:

| Note | Meaning |
|------|---------|
| netbox-pathways is not installed. | Segments need netbox-pathways. |
| The cable has no recorded route. | The cable has no route segments. |
| The route has a gap at segment N. | A segment has no pathway or no length. |
| The distance runs past the end of the cable. | The distance exceeds the route. |
| Cable X has no length. | The route walk needs the cable's length. |

A closure or distance is checked against the cable only when it is set or
changed, so a cable re-terminated or shortened later does not block other
edits of the fault, such as resolving it.

### Map layers

With netbox-pathways installed, the main map has a **Fiber Faults** group of
layers, off by default:

- **Fault Segments (Confirmed)** -- solid red lines along the segment that holds the fault.
- **Fault Segments (Estimated)** -- dashed red lines.
- **Faulted Closures** -- points for closures that hold an open fault.

Only open faults you may view appear, and popovers name the fault, its cable
and its location status. The fault page links the segment to the cable's route
map.

### Routing penalty

A cable with any open fault, on a strand or on the whole cable, is damaged. In
the [circuit picker](fiber-circuits.md) a candidate that crosses a damaged
cable ranks below clean ones and carries a **crosses a damaged cable** badge.
It is a yes or no, not a score: two damaged cables rank the same as one, and a
clean route with an extra hop beats a shorter route through a damaged cable.
Resolved faults do not penalize routing. Strands under an open fault still
cannot be assigned at all.

---

## Finding faulted fiber

- `is_faulted` filter on fiber strands: strands with an open fault, or on a
  cable with an open whole-cable fault.
- `is_faulted` filter on fiber cables: cables with any open fault.
- REST API: `/api/plugins/fms/fiber-faults/`.
- GraphQL: `fiber_fault` and `fiber_fault_list`.
