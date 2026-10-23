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

## Finding faulted fiber

- `is_faulted` filter on fiber strands: strands with an open fault, or on a
  cable with an open whole-cable fault.
- `is_faulted` filter on fiber cables: cables with any open fault.
- REST API: `/api/plugins/fms/fiber-faults/`.
- GraphQL: `fiber_fault` and `fiber_fault_list`.
