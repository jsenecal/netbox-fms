import type {
  CableGroupData,
  LayoutNode,
  LegendSection,
  PendingChange,
  SpliceEntry,
  StatsData,
  StrandData,
  TrayData,
  TubeData,
} from './types';

// -----------------------------------------------------------------------
// Layout constants
// -----------------------------------------------------------------------
export const COLUMN_WIDTH = 280;
export const STRAND_HEIGHT = 20;
export const STRAND_DOT_R = 5;
export const TUBE_ROW_H = 18;
export const CABLE_ROW_H = 32;
export const GROUP_PAD = 6;
export const HEADER_HEIGHT = 4;
export const TOP_PAD = 10;
export const TUBE_INDENT = 14;
export const TUBE_DOT_R = 4;
export const MIN_HEIGHT = 500;

// -----------------------------------------------------------------------
// State
// -----------------------------------------------------------------------
export class EditorState {
  cableGroups: CableGroupData[] = [];
  trays: TrayData[] = [];
  activeTrayFilter: number | null = null;
  leftNodes: LayoutNode[] = [];
  rightNodes: LayoutNode[] = [];
  spliceEntries: SpliceEntry[] = [];
  pendingChanges: PendingChange[] = [];
  leftOffset = 0;
  rightOffset = 0;
  selectedStrandId: number | null = null;
  selectedSpliceKeys: Set<string> = new Set();
  showLive = true;
  showPlanned = true;
  showUnspliced = true;

  /** Key for a splice entry (order-independent). */
  spliceKey(a: number, b: number): string {
    return Math.min(a, b) + '-' + Math.max(a, b);
  }

  toggleSpliceSelection(sourceId: number, targetId: number): void {
    const key = this.spliceKey(sourceId, targetId);
    if (this.selectedSpliceKeys.has(key)) {
      this.selectedSpliceKeys.delete(key);
    } else {
      this.selectedSpliceKeys.add(key);
    }
  }

  isSpliceSelected(sourceId: number, targetId: number): boolean {
    return this.selectedSpliceKeys.has(this.spliceKey(sourceId, targetId));
  }

  clearSpliceSelection(): void {
    this.selectedSpliceKeys.clear();
  }

  /** Delete all selected splices as pending removals. */
  deleteSelectedSplices(): number {
    let count = 0;
    for (const key of this.selectedSpliceKeys) {
      const entry = this.spliceEntries.find(
        (e) => this.spliceKey(e.sourceId, e.targetId) === key,
      );
      if (entry) {
        // Need front port IDs — find from layout nodes
        const aNode = [...this.leftNodes, ...this.rightNodes].find(
          (n) => n.type === 'strand' && n.id === entry.sourceId,
        );
        const bNode = [...this.leftNodes, ...this.rightNodes].find(
          (n) => n.type === 'strand' && n.id === entry.targetId,
        );
        if (aNode?.frontPortId && bNode?.frontPortId) {
          this.removePendingSplice(entry.sourceId, entry.targetId, aNode.frontPortId, bNode.frontPortId);
          count++;
        }
      }
    }
    this.selectedSpliceKeys.clear();
    return count;
  }

  /** Undo/redo stacks */
  private undoStack: PendingChange[][] = [];
  private redoStack: PendingChange[][] = [];

  /** Track which side each cable is on: fiber_cable_id -> 'left' | 'right' */
  private sideAssignment: Map<number, 'left' | 'right'> = new Map();

  /** Build a lookup map: strand ID -> StrandData. */
  private strandMap: Map<number, StrandData> = new Map();

  /** Set tray filter and rebuild layout. */
  setTrayFilter(trayId: number | null): void {
    this.activeTrayFilter = trayId;
    this.rebuildLayout();
  }

  /** Load cable groups from API and rebuild layout. */
  loadCableGroups(groups: CableGroupData[], trays?: TrayData[]): void {
    this.cableGroups = groups;
    if (trays) this.trays = trays;
    this.strandMap.clear();
    for (const cg of groups) {
      for (const tube of cg.tubes) {
        for (const s of tube.strands) this.strandMap.set(s.id, s);
      }
      for (const s of cg.loose_strands) this.strandMap.set(s.id, s);
    }
    // Initialize side assignments if not already set
    if (this.sideAssignment.size === 0) {
      const mid = Math.ceil(groups.length / 2);
      groups.forEach((cg, i) => {
        this.sideAssignment.set(cg.fiber_cable_id, i < mid ? 'left' : 'right');
      });
    }
    this.rebuildLayout();
  }

  /** Get strand data by ID. */
  getStrand(id: number): StrandData | undefined {
    return this.strandMap.get(id);
  }

  /** Find the cable group and tube containing a strand. */
  findStrandContext(strandId: number): { cable: CableGroupData; tube: TubeData | null } | null {
    for (const cable of this.cableGroups) {
      for (const tube of cable.tubes) {
        if (tube.strands.some(s => s.id === strandId)) {
          return { cable, tube };
        }
      }
      if (cable.loose_strands.some(s => s.id === strandId)) {
        return { cable, tube: null };
      }
    }
    return null;
  }

  /** Rebuild column layouts and collect splice entries. */
  rebuildLayout(): void {
    const leftCables = this.cableGroups.filter((cg) => this.sideAssignment.get(cg.fiber_cable_id) === 'left');
    const rightCables = this.cableGroups.filter((cg) => this.sideAssignment.get(cg.fiber_cable_id) !== 'left');
    this.leftNodes = this.layoutColumn(leftCables);
    this.rightNodes = this.layoutColumn(rightCables);
    this.collectSpliceEntries();
    this.leftOffset = 0;
    this.rightOffset = 0;
  }

  /** Move a cable to the other side and rebuild layout. */
  moveCable(fiberCableId: number): void {
    const current = this.sideAssignment.get(fiberCableId) ?? 'left';
    this.sideAssignment.set(fiberCableId, current === 'left' ? 'right' : 'left');
    this.rebuildLayout();
  }

  // -------------------------------------------------------------------
  // Pending changes
  // -------------------------------------------------------------------

  private snapshotForUndo(): void {
    this.undoStack.push(structuredClone(this.pendingChanges));
    this.redoStack = [];
  }

  addPendingSplice(
    strandA: number, strandB: number,
    portA: number, portB: number,
  ): void {
    const exists = this.pendingChanges.some(
      (p) => p.action === 'add' &&
        ((p.fiberA === strandA && p.fiberB === strandB) ||
         (p.fiberA === strandB && p.fiberB === strandA)),
    );
    if (!exists) {
      this.snapshotForUndo();
      this.pendingChanges.push({
        action: 'add', fiberA: strandA, fiberB: strandB,
        portA, portB,
      });
    }
  }

  removePendingSplice(strandA: number, strandB: number, portA: number, portB: number): void {
    this.snapshotForUndo();
    const addIdx = this.pendingChanges.findIndex(
      (p) => p.action === 'add' &&
        ((p.fiberA === strandA && p.fiberB === strandB) ||
         (p.fiberA === strandB && p.fiberB === strandA)),
    );
    if (addIdx >= 0) {
      this.pendingChanges.splice(addIdx, 1);
      return;
    }
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

  undo(): void {
    if (this.undoStack.length === 0) return;
    this.redoStack.push(structuredClone(this.pendingChanges));
    this.pendingChanges = this.undoStack.pop()!;
  }

  redo(): void {
    if (this.redoStack.length === 0) return;
    this.undoStack.push(structuredClone(this.pendingChanges));
    this.pendingChanges = this.redoStack.pop()!;
  }

  canUndo(): boolean { return this.undoStack.length > 0; }
  canRedo(): boolean { return this.redoStack.length > 0; }

  /** Check if a strand is already involved in a pending-add. */
  isStrandPendingAdd(strandId: number): boolean {
    return this.pendingChanges.some(
      (p) => p.action === 'add' && (p.fiberA === strandId || p.fiberB === strandId),
    );
  }

  /** Remove pending-add entries involving this strand (for re-splicing). */
  undoPendingAddForStrand(strandId: number): void {
    this.snapshotForUndo();
    this.pendingChanges = this.pendingChanges.filter(
      (p) => !(p.action === 'add' && (p.fiberA === strandId || p.fiberB === strandId)),
    );
  }

  hasPendingChanges(): boolean {
    return this.pendingChanges.length > 0;
  }

  clearPending(): void {
    this.pendingChanges = [];
    this.undoStack = [];
    this.redoStack = [];
  }

  /** Get pending changes as bulk update payload (uses front_port_a_ids).
   *  Automatically includes implicit removals for superseded splices. */
  getPendingPayload(): { add: Array<{ fiber_a: number; fiber_b: number }>; remove: Array<{ fiber_a: number; fiber_b: number }> } {
    const add: Array<{ fiber_a: number; fiber_b: number }> = [];
    const remove: Array<{ fiber_a: number; fiber_b: number }> = [];

    // Collect strands involved in pending adds
    const addedStrands = new Set<number>();
    for (const p of this.pendingChanges) {
      if (p.action === 'add') {
        addedStrands.add(p.fiberA);
        addedStrands.add(p.fiberB);
      }
    }

    // Auto-remove existing splices superseded by pending adds
    const removedKeys = new Set<string>();
    for (const p of this.pendingChanges) {
      if (p.action === 'remove') {
        remove.push({ fiber_a: p.portA, fiber_b: p.portB });
        removedKeys.add(this.spliceKey(p.fiberA, p.fiberB));
      }
    }
    for (const entry of this.spliceEntries) {
      if (addedStrands.has(entry.sourceId) || addedStrands.has(entry.targetId)) {
        const key = this.spliceKey(entry.sourceId, entry.targetId);
        if (!removedKeys.has(key)) {
          // Find front port IDs for this existing splice
          const aNode = [...this.leftNodes, ...this.rightNodes].find(
            (n) => n.type === 'strand' && n.id === entry.sourceId,
          );
          const bNode = [...this.leftNodes, ...this.rightNodes].find(
            (n) => n.type === 'strand' && n.id === entry.targetId,
          );
          if (aNode?.frontPortId && bNode?.frontPortId) {
            remove.push({ fiber_a: aNode.frontPortId, fiber_b: bNode.frontPortId });
            removedKeys.add(key);
          }
        }
      }
    }

    for (const p of this.pendingChanges) {
      if (p.action === 'add') {
        add.push({ fiber_a: p.portA, fiber_b: p.portB });
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
  // Component data builders
  // -------------------------------------------------------------------

  /** Compute aggregate stats for the stats bar. */
  computeStats(): StatsData {
    let liveSpliceCount = 0;
    let plannedSpliceCount = 0;
    for (const entry of this.spliceEntries) {
      if (entry.isLive) liveSpliceCount++;
      if (entry.isPlan && !entry.isLive) plannedSpliceCount++;
    }
    const strandCount = [...this.leftNodes, ...this.rightNodes].filter(
      (n) => n.type === 'strand',
    ).length;
    return {
      cableCount: this.cableGroups.length,
      strandCount,
      liveSpliceCount,
      plannedSpliceCount,
      pendingCount: this.pendingChanges.length,
      planName: null,
      planStatus: null,
    };
  }

  /** Build legend sections based on current visible state. */
  buildLegendSections(): LegendSection[] {
    const sections: LegendSection[] = [];

    // Splice types section
    const hasLive = this.spliceEntries.some((e) => e.isLive);
    const hasPlan = this.spliceEntries.some((e) => e.isPlan && !e.isLive);
    const hasPendingAdd = this.pendingChanges.some((p) => p.action === 'add');
    const hasPendingRemove = this.pendingChanges.some((p) => p.action === 'remove');
    const hasProtected = [...this.leftNodes, ...this.rightNodes].some(
      (n) => n.type === 'strand' && n.isProtected,
    );

    const spliceItems: LegendSection['items'] = [];
    if (hasLive) {
      spliceItems.push({ type: 'line', color: '#28a745', label: 'Live splice' });
    }
    if (hasPlan) {
      spliceItems.push({ type: 'line', color: '#17a2b8', dashed: true, label: 'Planned splice' });
    }
    if (hasPendingAdd) {
      spliceItems.push({ type: 'line', color: '#ffc107', dashed: true, label: 'Pending add' });
    }
    if (hasPendingRemove) {
      spliceItems.push({ type: 'line', color: '#dc3545', dashed: true, label: 'Pending delete' });
    }
    if (hasProtected) {
      spliceItems.push({ type: 'icon', icon: '\uD83D\uDD12', label: 'Protected (circuit)' });
    }
    if (spliceItems.length > 0) {
      sections.push({ title: 'Splices', items: spliceItems });
    }

    // Tube colors section — collect unique visible tube colors
    const tubeColors = new Map<string, string>();
    for (const n of [...this.leftNodes, ...this.rightNodes]) {
      if (n.type === 'tube' && n.color && n.label) {
        const key = n.color;
        if (!tubeColors.has(key)) {
          tubeColors.set(key, n.label);
        }
      }
    }
    if (tubeColors.size > 0) {
      const tubeItems: LegendSection['items'] = [];
      for (const [color, label] of tubeColors) {
        tubeItems.push({ type: 'dot', color: `#${color}`, label });
      }
      sections.push({ title: 'Tubes', items: tubeItems });
    }

    return sections;
  }

  // -------------------------------------------------------------------
  // Layout helpers
  // -------------------------------------------------------------------

  private layoutColumn(cables: CableGroupData[]): LayoutNode[] {
    const nodes: LayoutNode[] = [];
    let y = TOP_PAD;
    const trayFilter = this.activeTrayFilter;

    for (const cg of cables) {
      nodes.push({
        type: 'cable',
        label: cg.cable_label,
        y,
        hidden: false,
        cableId: cg.fiber_cable_id,
        fiberType: cg.fiber_type,
        strandCount: cg.strand_count,
        farDeviceName: cg.far_device_name,
        farDeviceUrl: cg.far_device_url,
      });
      y += CABLE_ROW_H;

      for (const tube of cg.tubes) {
        // When a tray filter is active, skip tubes that don't match
        if (trayFilter !== null) {
          const tubeTrayId = tube.tray_assignment?.tray_id ?? null;
          if (tubeTrayId !== trayFilter) continue;
        }

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
            frontPortId: s.front_port_a_id,
            liveSplicedTo: s.live_spliced_to,
            planEntryId: s.plan_entry_id,
            planSplicedTo: s.plan_spliced_to,
            isProtected: s.protected,
            circuitName: s.circuit_name,
            circuitUrl: s.circuit_url,
            tubeId: tube.id,
            parentTubeNode: tubeNode,
          });
          y += STRAND_HEIGHT;
        }
        y += GROUP_PAD;
      }

      // Loose strands: only shown when no tray filter is active
      if (trayFilter === null) {
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
            frontPortId: s.front_port_a_id,
            liveSplicedTo: s.live_spliced_to,
            planEntryId: s.plan_entry_id,
            planSplicedTo: s.plan_spliced_to,
            isProtected: s.protected,
            circuitName: s.circuit_name,
            circuitUrl: s.circuit_url,
            tubeId: undefined,
            parentTubeNode: undefined,
          });
          y += STRAND_HEIGHT;
        }
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
