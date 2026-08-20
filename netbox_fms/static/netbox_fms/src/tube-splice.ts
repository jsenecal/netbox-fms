/**
 * Pure pairing logic for bulk tube-to-tube splicing.
 *
 * Given the fiber lists of two tubes (one per side of the editor), compute
 * the 1:1 fiber pairs to splice in positional sequence, or a human-readable
 * rejection reason when the tubes do not qualify.
 */

/** Minimal fiber facts the pairing decision needs. */
export interface TubeFiberInfo {
  /** Strand ID. */
  id: number;
  /** Front port ID used by the save payload; null means not spliceable. */
  frontPortId: number | null;
  /** Already spliced (live or planned). */
  spliced: boolean;
  /** Already part of a pending (unsaved) splice. */
  pendingAdd: boolean;
  /** Protected by a circuit; must never be touched. */
  isProtected: boolean;
  /** Display label for messages. */
  label: string;
}

export type TubePairingResult =
  | { ok: true; pairs: Array<{ a: TubeFiberInfo; b: TubeFiberInfo }> }
  | { ok: false; reason: string };

/** A fiber is available for bulk splicing when nothing already claims it. */
function availableFibers(fibers: TubeFiberInfo[]): TubeFiberInfo[] {
  return fibers.filter(
    (f) => f.frontPortId !== null && !f.spliced && !f.pendingAdd && !f.isProtected,
  );
}

/**
 * Pair the available fibers of two tubes 1:1 in positional order.
 *
 * The i-th available fiber on the left is paired with the i-th available
 * fiber on the right (input order is the tube's positional order). Fibers
 * that are already spliced, pending, or protected are not available; both
 * tubes must have the same non-zero number of available fibers.
 */
export function pairTubeFibers(
  left: TubeFiberInfo[],
  right: TubeFiberInfo[],
): TubePairingResult {
  const leftAvail = availableFibers(left);
  const rightAvail = availableFibers(right);

  if (leftAvail.length === 0 && rightAvail.length === 0) {
    return { ok: false, reason: 'No spliceable fibers: all fibers in both tubes are already spliced, pending, or protected.' };
  }
  if (leftAvail.length === 0) {
    return { ok: false, reason: 'Left tube has no spliceable fibers (already spliced, pending, or protected).' };
  }
  if (rightAvail.length === 0) {
    return { ok: false, reason: 'Right tube has no spliceable fibers (already spliced, pending, or protected).' };
  }
  if (leftAvail.length !== rightAvail.length) {
    return {
      ok: false,
      reason:
        `Unspliced fiber counts do not match: left tube has ${leftAvail.length}, ` +
        `right tube has ${rightAvail.length}. Splice the remainder individually.`,
    };
  }

  return {
    ok: true,
    pairs: leftAvail.map((a, i) => ({ a, b: rightAvail[i] })),
  };
}
