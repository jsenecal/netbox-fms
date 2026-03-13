import type {
  CableGroupData,
  LayoutNode,
  PendingChange,
  SpliceEntry,
  StrandData,
} from './types';

// -----------------------------------------------------------------------
// Layout constants
// -----------------------------------------------------------------------
export const COLUMN_WIDTH = 280;
export const STRAND_HEIGHT = 20;
export const STRAND_DOT_R = 5;
export const TUBE_ROW_H = 18;
export const CABLE_ROW_H = 22;
export const GROUP_PAD = 6;
export const HEADER_HEIGHT = 28;
export const TOP_PAD = 10;
export const TUBE_INDENT = 14;
export const TUBE_DOT_R = 4;
export const MIN_HEIGHT = 500;

// -----------------------------------------------------------------------
// State
// -----------------------------------------------------------------------
export class EditorState {
  cableGroups: CableGroupData[] = [];
  leftNodes: LayoutNode[] = [];
  rightNodes: LayoutNode[] = [];
  spliceEntries: SpliceEntry[] = [];
  pendingChanges: PendingChange[] = [];
  leftOffset = 0;
  rightOffset = 0;

  /** Build a lookup map: strand ID -> StrandData. */
  private strandMap: Map<number, StrandData> = new Map();

  /** Load cable groups from API and rebuild layout. */
  loadCableGroups(groups: CableGroupData[]): void {
    this.cableGroups = groups;
    this.strandMap.clear();
    for (const cg of groups) {
      for (const tube of cg.tubes) {
        for (const s of tube.strands) this.strandMap.set(s.id, s);
      }
      for (const s of cg.loose_strands) this.strandMap.set(s.id, s);
    }
    this.rebuildLayout();
  }

  /** Get strand data by ID. */
  getStrand(id: number): StrandData | undefined {
    return this.strandMap.get(id);
  }

  /** Rebuild column layouts and collect splice entries. */
  rebuildLayout(): void {
    const mid = Math.ceil(this.cableGroups.length / 2);
    this.leftNodes = this.layoutColumn(this.cableGroups.slice(0, mid));
    this.rightNodes = this.layoutColumn(this.cableGroups.slice(mid));
    this.collectSpliceEntries();
    this.leftOffset = 0;
    this.rightOffset = 0;
  }

  // -------------------------------------------------------------------
  // Pending changes
  // -------------------------------------------------------------------

  addPendingSplice(
    strandA: number, strandB: number,
    portA: number, portB: number,
  ): void {
    // Don't add duplicate
    const exists = this.pendingChanges.some(
      (p) => p.action === 'add' &&
        ((p.fiberA === strandA && p.fiberB === strandB) ||
         (p.fiberA === strandB && p.fiberB === strandA)),
    );
    if (!exists) {
      this.pendingChanges.push({
        action: 'add', fiberA: strandA, fiberB: strandB,
        portA, portB,
      });
    }
  }

  removePendingSplice(strandA: number, strandB: number, portA: number, portB: number): void {
    // Check if we're removing a pending add (cancel it out)
    const addIdx = this.pendingChanges.findIndex(
      (p) => p.action === 'add' &&
        ((p.fiberA === strandA && p.fiberB === strandB) ||
         (p.fiberA === strandB && p.fiberB === strandA)),
    );
    if (addIdx >= 0) {
      this.pendingChanges.splice(addIdx, 1);
      return;
    }
    // Otherwise add a remove entry
    const exists = this.pendingChanges.some(
      (p) => p.action === 'remove' &&
        ((p.fiberA === strandA && p.fiberB === strandB) ||
         (p.fiberA === strandB && p.fiberB === strandA)),
    );
    if (!exists) {
      this.pendingChanges.push({
        action: 'remove', fiberA: strandA, fiberB: strandB,
        portA, portB,
      });
    }
  }

  hasPendingChanges(): boolean {
    return this.pendingChanges.length > 0;
  }

  clearPending(): void {
    this.pendingChanges = [];
  }

  /** Get pending changes as bulk update payload (uses front_port_ids). */
  getPendingPayload(): { add: Array<{ fiber_a: number; fiber_b: number }>; remove: Array<{ fiber_a: number; fiber_b: number }> } {
    const add: Array<{ fiber_a: number; fiber_b: number }> = [];
    const remove: Array<{ fiber_a: number; fiber_b: number }> = [];
    for (const p of this.pendingChanges) {
      if (p.action === 'add') {
        add.push({ fiber_a: p.portA, fiber_b: p.portB });
      } else {
        remove.push({ fiber_a: p.portA, fiber_b: p.portB });
      }
    }
    return { add, remove };
  }

  /**
   * Get re-splices: strands that appear in both a remove and an add.
   * Returns Map of strandId to { oldTarget, newTarget }.
   */
  getReSplices(): Map<number, { oldTarget: number; newTarget: number }> {
    const result = new Map<number, { oldTarget: number; newTarget: number }>();
    const removes = this.pendingChanges.filter((p) => p.action === 'remove');
    const adds = this.pendingChanges.filter((p) => p.action === 'add');

    for (const rem of removes) {
      for (const add of adds) {
        if (rem.fiberA === add.fiberA) {
          result.set(rem.fiberA, { oldTarget: rem.fiberB, newTarget: add.fiberB });
        } else if (rem.fiberA === add.fiberB) {
          result.set(rem.fiberA, { oldTarget: rem.fiberB, newTarget: add.fiberA });
        } else if (rem.fiberB === add.fiberA) {
          result.set(rem.fiberB, { oldTarget: rem.fiberA, newTarget: add.fiberB });
        } else if (rem.fiberB === add.fiberB) {
          result.set(rem.fiberB, { oldTarget: rem.fiberA, newTarget: add.fiberA });
        }
      }
    }
    return result;
  }

  /**
   * Check if a strand is involved in a pending change.
   * Returns the pending change action or null.
   */
  getStrandPendingState(strandId: number): 'add' | 'remove' | null {
    for (const p of this.pendingChanges) {
      if (p.fiberA === strandId || p.fiberB === strandId) {
        return p.action;
      }
    }
    return null;
  }

  /**
   * Check if a specific splice (between two strands) has a pending delete.
   */
  isSplicePendingDelete(strandA: number, strandB: number): boolean {
    return this.pendingChanges.some(
      (p) => p.action === 'remove' &&
        ((p.fiberA === strandA && p.fiberB === strandB) ||
         (p.fiberA === strandB && p.fiberB === strandA)),
    );
  }

  // -------------------------------------------------------------------
  // Layout helpers
  // -------------------------------------------------------------------

  private layoutColumn(cables: CableGroupData[]): LayoutNode[] {
    const nodes: LayoutNode[] = [];
    let y = TOP_PAD;

    for (const cg of cables) {
      nodes.push({
        type: 'cable',
        label: cg.cable_label,
        y,
        hidden: false,
        cableId: cg.fiber_cable_id,
        fiberType: cg.fiber_type,
        strandCount: cg.strand_count,
      });
      y += CABLE_ROW_H;

      for (const tube of cg.tubes) {
        const tubeNode: LayoutNode = {
          type: 'tube',
          label: tube.name,
          color: tube.color,
          stripeColor: tube.stripe_color,
          strandCount: tube.strand_count,
          y,
          hidden: false,
          tubeId: tube.id,
          collapsed: false,
        };
        nodes.push(tubeNode);
        y += TUBE_ROW_H;

        for (const s of tube.strands) {
          nodes.push({
            type: 'strand',
            id: s.id,
            label: s.name,
            color: s.color,
            tubeColor: s.tube_color,
            tubeName: s.tube_name,
            ribbonName: s.ribbon_name,
            ribbonColor: s.ribbon_color,
            y,
            hidden: false,
            frontPortId: s.front_port_id,
            liveSplicedTo: s.live_spliced_to,
            planEntryId: s.plan_entry_id,
            planSplicedTo: s.plan_spliced_to,
            tubeId: tube.id,
            parentTubeNode: tubeNode,
          });
          y += STRAND_HEIGHT;
        }
        y += GROUP_PAD;
      }

      for (const s of cg.loose_strands) {
        nodes.push({
          type: 'strand',
          id: s.id,
          label: s.name,
          color: s.color,
          tubeColor: null,
          tubeName: null,
          ribbonName: s.ribbon_name,
          ribbonColor: s.ribbon_color,
          y,
          hidden: false,
          frontPortId: s.front_port_id,
          liveSplicedTo: s.live_spliced_to,
          planEntryId: s.plan_entry_id,
          planSplicedTo: s.plan_spliced_to,
          tubeId: undefined,
          parentTubeNode: undefined,
        });
        y += STRAND_HEIGHT;
      }
      y += GROUP_PAD;
    }

    return nodes;
  }

  private collectSpliceEntries(): void {
    this.spliceEntries = [];
    const seen = new Set<string>();

    for (const cg of this.cableGroups) {
      const allStrands: StrandData[] = [];
      for (const t of cg.tubes) allStrands.push(...t.strands);
      allStrands.push(...cg.loose_strands);

      for (const s of allStrands) {
        // Live splices
        if (s.live_spliced_to) {
          const key = `live-${Math.min(s.id, s.live_spliced_to)}-${Math.max(s.id, s.live_spliced_to)}`;
          if (!seen.has(key)) {
            seen.add(key);
            this.spliceEntries.push({
              sourceId: s.id,
              targetId: s.live_spliced_to,
              entryId: null,
              isLive: true,
              isPlan: false,
            });
          }
        }
        // Plan splices
        if (s.plan_entry_id && s.plan_spliced_to) {
          const key = `plan-${Math.min(s.id, s.plan_spliced_to)}-${Math.max(s.id, s.plan_spliced_to)}`;
          if (!seen.has(key)) {
            seen.add(key);
            this.spliceEntries.push({
              sourceId: s.id,
              targetId: s.plan_spliced_to,
              entryId: s.plan_entry_id,
              isLive: false,
              isPlan: true,
            });
          }
        }
      }
    }
  }

  /** Recalculate y-positions respecting collapsed tubes. */
  recalcPositions(nodes: LayoutNode[]): void {
    const collapsedTubes = new Set<number>();
    const tubeYMap = new Map<number, number>();

    for (const n of nodes) {
      if (n.type === 'tube' && n.collapsed) collapsedTubes.add(n.tubeId!);
    }

    let y = TOP_PAD;
    for (const n of nodes) {
      if (n.type === 'strand' && n.tubeId !== undefined && collapsedTubes.has(n.tubeId)) {
        n.y = tubeYMap.get(n.tubeId) ?? y;
        n.hidden = true;
        continue;
      }
      n.hidden = false;
      n.y = y;
      if (n.type === 'cable') {
        y += CABLE_ROW_H;
      } else if (n.type === 'tube') {
        tubeYMap.set(n.tubeId!, y);
        y += TUBE_ROW_H;
      } else {
        y += STRAND_HEIGHT;
      }
    }
  }

  /** Get visible strands in a column starting from a given strand ID. */
  getVisibleStrandsFrom(side: 'left' | 'right', startId: number): LayoutNode[] {
    const nodes = side === 'left' ? this.leftNodes : this.rightNodes;
    const strands = nodes.filter((n) => n.type === 'strand' && !n.hidden);
    const idx = strands.findIndex((n) => n.id === startId);
    return idx >= 0 ? strands.slice(idx) : [];
  }

  /**
   * Get visible strands within the same tube, starting from a given strand ID.
   * Used by sequential mode (does not cross tube boundaries).
   */
  getVisibleStrandsInTubeFrom(side: 'left' | 'right', startId: number): LayoutNode[] {
    const nodes = side === 'left' ? this.leftNodes : this.rightNodes;
    const startNode = nodes.find((n) => n.type === 'strand' && n.id === startId);
    if (!startNode) return [];

    const tubeId = startNode.tubeId;
    const strands = nodes.filter(
      (n) => n.type === 'strand' && !n.hidden && n.tubeId === tubeId,
    );
    const idx = strands.findIndex((n) => n.id === startId);
    return idx >= 0 ? strands.slice(idx) : [];
  }

  /** Get column height for rendering. */
  columnHeight(nodes: LayoutNode[]): number {
    const visible = nodes.filter((n) => !n.hidden);
    if (!visible.length) return MIN_HEIGHT;
    const last = visible[visible.length - 1];
    return last.y + STRAND_HEIGHT + TOP_PAD;
  }
}
