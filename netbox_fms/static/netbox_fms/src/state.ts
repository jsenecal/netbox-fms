import type {
  BulkUpdatePayload,
  CableGroupData,
  FiberClaim,
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
export const CABLE_ROW_H = 42;
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
  fiberClaims: FiberClaim[] = [];
  claimedPortIds: Set<number> = new Set();

  loadFiberClaims(claims: FiberClaim[]): void {
    this.fiberClaims = claims;
    this.claimedPortIds = new Set<number>();
    for (const c of claims) {
      this.claimedPortIds.add(c.fiber_a);
      this.claimedPortIds.add(c.fiber_b);
    }
  }

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
    // Initialize side assignments — put spliced cables on opposite sides
    if (this.sideAssignment.size === 0) {
      this.assignSidesBySpliceRelationship(groups);
    }
    this.rebuildLayout();
  }

  /** Get strand data by ID. */
  getStrand(id: number): StrandData | undefined {
    return this.strandMap.get(id);
  }

  /** Assign cables to left/right based on splice relationships.
   *  Spliced cables go on opposite sides; balanced by strand count for ties. */
  private assignSidesBySpliceRelationship(groups: CableGroupData[]): void {
    // Build strand-to-cable lookup
    const strandToCable = new Map<number, number>();
    for (const cg of groups) {
      for (const tube of cg.tubes) {
        for (const s of tube.strands) strandToCable.set(s.id, cg.fiber_cable_id);
      }
      for (const s of cg.loose_strands) strandToCable.set(s.id, cg.fiber_cable_id);
    }

    // Build splice edges: cable_id -> set of partner cable_ids
    const edges = new Map<number, Set<number>>();
    for (const cg of groups) {
      const allStrands: StrandData[] = [];
      for (const t of cg.tubes) allStrands.push(...t.strands);
      allStrands.push(...cg.loose_strands);
      for (const s of allStrands) {
        const partnerId = s.live_spliced_to || s.plan_spliced_to;
        if (partnerId) {
          const partnerCable = strandToCable.get(partnerId);
          if (partnerCable && partnerCable !== cg.fiber_cable_id) {
            if (!edges.has(cg.fiber_cable_id)) edges.set(cg.fiber_cable_id, new Set());
            edges.get(cg.fiber_cable_id)!.add(partnerCable);
            if (!edges.has(partnerCable)) edges.set(partnerCable, new Set());
            edges.get(partnerCable)!.add(cg.fiber_cable_id);
          }
        }
      }
    }

    // Greedy 2-coloring: process cables by most connections first,
    // place each on the opposite side of its most-connected partner
    const sorted = [...groups].sort((a, b) => {
      const aEdges = edges.get(a.fiber_cable_id)?.size ?? 0;
      const bEdges = edges.get(b.fiber_cable_id)?.size ?? 0;
      if (bEdges !== aEdges) return bEdges - aEdges;
      return b.strand_count - a.strand_count;
    });

    let leftCount = 0;
    let rightCount = 0;

    for (const cg of sorted) {
      if (this.sideAssignment.has(cg.fiber_cable_id)) continue;

      const partners = edges.get(cg.fiber_cable_id);
      if (partners) {
        // Count how many partners are on each side
        let partnersLeft = 0;
        let partnersRight = 0;
        for (const pid of partners) {
          const side = this.sideAssignment.get(pid);
          if (side === 'left') partnersLeft++;
          else if (side === 'right') partnersRight++;
        }

        // Put this cable on the opposite side from the majority of its partners
        if (partnersLeft > partnersRight) {
          this.sideAssignment.set(cg.fiber_cable_id, 'right');
          rightCount += cg.strand_count || 1;
        } else if (partnersRight > partnersLeft) {
          this.sideAssignment.set(cg.fiber_cable_id, 'left');
          leftCount += cg.strand_count || 1;
        } else {
          // Tie — balance by strand count
          if (leftCount <= rightCount) {
            this.sideAssignment.set(cg.fiber_cable_id, 'left');
            leftCount += cg.strand_count || 1;
          } else {
            this.sideAssignment.set(cg.fiber_cable_id, 'right');
            rightCount += cg.strand_count || 1;
          }
        }
      } else {
        // No splice connections — balance by strand count
        if (leftCount <= rightCount) {
          this.sideAssignment.set(cg.fiber_cable_id, 'left');
          leftCount += cg.strand_count || 1;
        } else {
          this.sideAssignment.set(cg.fiber_cable_id, 'right');
          rightCount += cg.strand_count || 1;
        }
      }
    }
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

    // When a tray filter is active, compute visible tube IDs and loose strand IDs
    // that include splice-adjacent tubes/strands (partner strands).
    let visibleTubeIds: Set<number> | null = null;
    let visibleLooseStrandIds: Set<number> | null = null;
    if (this.activeTrayFilter !== null) {
      const visible = this.computeVisibleIds(this.activeTrayFilter);
      visibleTubeIds = visible.tubeIds;
      visibleLooseStrandIds = visible.looseStrandIds;
    }

    this.leftNodes = this.layoutColumn(leftCables, visibleTubeIds, visibleLooseStrandIds);
    this.rightNodes = this.layoutColumn(rightCables, visibleTubeIds, visibleLooseStrandIds);
    this.collectSpliceEntries();
    this.leftOffset = 0;
    this.rightOffset = 0;
  }

  /** Compute visible tube IDs and loose strand IDs for a given tray filter,
   *  including splice-adjacent tubes and loose strands. */
  private computeVisibleIds(trayId: number): { tubeIds: Set<number>; looseStrandIds: Set<number> } {
    // Step 1: find all strand IDs in tubes assigned to the selected tray
    const selectedStrandIds = new Set<number>();
    const directTubeIds = new Set<number>();
    for (const cg of this.cableGroups) {
      for (const tube of cg.tubes) {
        if (tube.tray_assignment?.tray_id === trayId) {
          directTubeIds.add(tube.id);
          for (const s of tube.strands) {
            selectedStrandIds.add(s.id);
          }
        }
      }
    }

    // Step 2: find splice partners of selected strands
    const partnerStrandIds = new Set<number>();
    for (const cg of this.cableGroups) {
      const allStrands: StrandData[] = [];
      for (const t of cg.tubes) allStrands.push(...t.strands);
      allStrands.push(...cg.loose_strands);

      for (const s of allStrands) {
        if (selectedStrandIds.has(s.id)) {
          if (s.live_spliced_to) partnerStrandIds.add(s.live_spliced_to);
          if (s.plan_spliced_to) partnerStrandIds.add(s.plan_spliced_to);
        }
        if (s.live_spliced_to && selectedStrandIds.has(s.live_spliced_to)) {
          partnerStrandIds.add(s.id);
        }
        if (s.plan_spliced_to && selectedStrandIds.has(s.plan_spliced_to)) {
          partnerStrandIds.add(s.id);
        }
      }
    }

    // Also check pending changes for partners
    for (const p of this.pendingChanges) {
      if (p.action === 'add') {
        if (selectedStrandIds.has(p.fiberA)) partnerStrandIds.add(p.fiberB);
        if (selectedStrandIds.has(p.fiberB)) partnerStrandIds.add(p.fiberA);
      }
    }

    // Step 3: find tubes and loose strands containing partner strands
    const visibleTubeIds = new Set(directTubeIds);
    const visibleLooseStrandIds = new Set<number>();
    for (const cg of this.cableGroups) {
      for (const tube of cg.tubes) {
        if (visibleTubeIds.has(tube.id)) continue;
        for (const s of tube.strands) {
          if (partnerStrandIds.has(s.id)) {
            visibleTubeIds.add(tube.id);
            break;
          }
        }
      }
      // Check loose strands for partners
      for (const s of cg.loose_strands) {
        if (partnerStrandIds.has(s.id)) {
          visibleLooseStrandIds.add(s.id);
        }
      }
    }

    return { tubeIds: visibleTubeIds, looseStrandIds: visibleLooseStrandIds };
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
  getPendingPayload(): BulkUpdatePayload {
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
    if (this.fiberClaims.length > 0) {
      spliceItems.push({ type: 'line' as const, dashed: true, color: '#888', label: 'Other plan claim' });
    }
    if (spliceItems.length > 0) {
      sections.push({ title: 'Splices', items: spliceItems });
    }

    // Tube colors section — collect unique tube colors from all cable groups
    // (not just layout nodes, which may be filtered by tray)
    const tubeColors = new Map<string, string>();
    for (const cg of this.cableGroups) {
      for (const tube of cg.tubes) {
        if (tube.color && tube.name) {
          if (!tubeColors.has(tube.color)) {
            tubeColors.set(tube.color, tube.name);
          }
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

    // Fiber strand colors — collect unique strand colors from layout nodes
    const strandColors = new Map<string, string>();
    for (const n of [...this.leftNodes, ...this.rightNodes]) {
      if (n.type === 'strand' && n.color && n.label && !n.tubeId) {
        if (!strandColors.has(n.color)) {
          strandColors.set(n.color, n.label);
        }
      }
    }
    if (strandColors.size > 0) {
      const fiberItems: LegendSection['items'] = [];
      for (const [color, label] of strandColors) {
        fiberItems.push({ type: 'dot', color: `#${color}`, label });
      }
      sections.push({ title: 'Fiber Colors', items: fiberItems });
    }

    return sections;
  }

  // -------------------------------------------------------------------
  // Layout helpers
  // -------------------------------------------------------------------

  private layoutColumn(cables: CableGroupData[], visibleTubeIds: Set<number> | null = null, visibleLooseStrandIds: Set<number> | null = null): LayoutNode[] {
    const nodes: LayoutNode[] = [];
    let y = TOP_PAD;
    const trayFilter = this.activeTrayFilter;

    for (const cg of cables) {
      // When a tray filter is active, skip cables that have no visible content
      if (trayFilter !== null && visibleTubeIds !== null) {
        const hasVisibleTube = cg.tubes.some((t) => visibleTubeIds.has(t.id));
        const hasVisibleLoose = visibleLooseStrandIds !== null &&
          cg.loose_strands.some((s) => visibleLooseStrandIds.has(s.id));
        if (!hasVisibleTube && !hasVisibleLoose) continue;
      }

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
        // When a tray filter is active, skip tubes not in the visible set
        if (trayFilter !== null && visibleTubeIds !== null) {
          if (!visibleTubeIds.has(tube.id)) continue;
        }

        const tubeNode: LayoutNode = {
          type: 'tube',
          label: tube.name,
          color: tube.color,
          markerCount: tube.marker_count,
          markerColor: tube.marker_color,
          markerType: tube.marker_type,
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

      // Loose strands: shown when no tray filter, or when they are splice partners
      const showAllLoose = trayFilter === null;
      for (const s of cg.loose_strands) {
        if (!showAllLoose && (visibleLooseStrandIds === null || !visibleLooseStrandIds.has(s.id))) continue;
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
      y += GROUP_PAD;
    }

    return nodes;
  }

  private collectSpliceEntries(): void {
    this.spliceEntries = [];
    const entryMap = new Map<string, SpliceEntry>();

    for (const cg of this.cableGroups) {
      const allStrands: StrandData[] = [];
      for (const t of cg.tubes) allStrands.push(...t.strands);
      allStrands.push(...cg.loose_strands);

      for (const s of allStrands) {
        // Live splices
        if (s.live_spliced_to) {
          const key = this.spliceKey(s.id, s.live_spliced_to);
          const existing = entryMap.get(key);
          if (existing) {
            existing.isLive = true;
          } else {
            const entry: SpliceEntry = {
              sourceId: s.id,
              targetId: s.live_spliced_to,
              entryId: null,
              isLive: true,
              isPlan: false,
            };
            entryMap.set(key, entry);
          }
        }
        // Plan splices
        if (s.plan_entry_id && s.plan_spliced_to) {
          const key = this.spliceKey(s.id, s.plan_spliced_to);
          const existing = entryMap.get(key);
          if (existing) {
            existing.isPlan = true;
            if (!existing.entryId) existing.entryId = s.plan_entry_id;
          } else {
            const entry: SpliceEntry = {
              sourceId: s.id,
              targetId: s.plan_spliced_to,
              entryId: s.plan_entry_id,
              isLive: false,
              isPlan: true,
            };
            entryMap.set(key, entry);
          }
        }
      }
    }

    this.spliceEntries = Array.from(entryMap.values());
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
