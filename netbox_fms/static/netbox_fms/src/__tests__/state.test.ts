import { describe, it, expect, beforeEach } from 'vitest';
import {
  EditorState,
  CABLE_ROW_H,
  TUBE_ROW_H,
  STRAND_HEIGHT,
  GROUP_PAD,
  TOP_PAD,
  MIN_HEIGHT,
} from '../state';
import type { CableGroupData, StrandData } from '../types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeStrand(overrides: Partial<StrandData> & { id: number }): StrandData {
  return {
    name: `Strand ${overrides.id}`,
    position: overrides.id,
    color: 'ff0000',
    tube_color: null,
    tube_name: null,
    ribbon_name: null,
    ribbon_color: null,
    front_port_a_id: overrides.id * 100,
    live_spliced_to: null,
    plan_entry_id: null,
    plan_spliced_to: null,
    protected: false,
    circuit_name: null,
    circuit_url: null,
    ...overrides,
  };
}

function makeCableGroup(overrides: Partial<CableGroupData> & { fiber_cable_id: number }): CableGroupData {
  return {
    cable_label: `Cable ${overrides.fiber_cable_id}`,
    fiber_type: 'smf_os2',
    strand_count: 0,
    far_device_name: null,
    far_device_url: null,
    tubes: [],
    loose_strands: [],
    ...overrides,
  };
}

/** Two cables, each with a tube containing 2 strands. */
function twoTubeCables(): CableGroupData[] {
  return [
    makeCableGroup({
      fiber_cable_id: 1,
      strand_count: 2,
      tubes: [
        {
          id: 10, name: 'T1', color: '0000ff', stripe_color: null, strand_count: 2, tray_assignment: null,
          strands: [makeStrand({ id: 1 }), makeStrand({ id: 2 })],
        },
      ],
    }),
    makeCableGroup({
      fiber_cable_id: 2,
      strand_count: 2,
      tubes: [
        {
          id: 20, name: 'T1', color: 'ff0000', stripe_color: null, strand_count: 2, tray_assignment: null,
          strands: [makeStrand({ id: 3 }), makeStrand({ id: 4 })],
        },
      ],
    }),
  ];
}

// ---------------------------------------------------------------------------
// spliceKey
// ---------------------------------------------------------------------------

describe('spliceKey', () => {
  it('returns order-independent key', () => {
    const s = new EditorState();
    expect(s.spliceKey(5, 3)).toBe('3-5');
    expect(s.spliceKey(3, 5)).toBe('3-5');
  });

  it('handles equal IDs', () => {
    const s = new EditorState();
    expect(s.spliceKey(7, 7)).toBe('7-7');
  });
});

// ---------------------------------------------------------------------------
// Splice selection
// ---------------------------------------------------------------------------

describe('splice selection', () => {
  let s: EditorState;

  beforeEach(() => {
    s = new EditorState();
  });

  it('toggleSpliceSelection adds and removes', () => {
    s.toggleSpliceSelection(1, 2);
    expect(s.isSpliceSelected(1, 2)).toBe(true);
    expect(s.isSpliceSelected(2, 1)).toBe(true); // order-independent

    s.toggleSpliceSelection(1, 2);
    expect(s.isSpliceSelected(1, 2)).toBe(false);
  });

  it('clearSpliceSelection empties the set', () => {
    s.toggleSpliceSelection(1, 2);
    s.toggleSpliceSelection(3, 4);
    s.clearSpliceSelection();
    expect(s.isSpliceSelected(1, 2)).toBe(false);
    expect(s.isSpliceSelected(3, 4)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Pending changes
// ---------------------------------------------------------------------------

describe('pending changes', () => {
  let s: EditorState;

  beforeEach(() => {
    s = new EditorState();
  });

  it('addPendingSplice creates an add entry', () => {
    s.addPendingSplice(1, 2, 100, 200);
    expect(s.hasPendingChanges()).toBe(true);
    expect(s.pendingChanges).toHaveLength(1);
    expect(s.pendingChanges[0]).toMatchObject({
      action: 'add', fiberA: 1, fiberB: 2, portA: 100, portB: 200,
    });
  });

  it('addPendingSplice deduplicates', () => {
    s.addPendingSplice(1, 2, 100, 200);
    s.addPendingSplice(1, 2, 100, 200);
    expect(s.pendingChanges).toHaveLength(1);
  });

  it('addPendingSplice deduplicates reversed order', () => {
    s.addPendingSplice(1, 2, 100, 200);
    s.addPendingSplice(2, 1, 200, 100);
    expect(s.pendingChanges).toHaveLength(1);
  });

  it('removePendingSplice cancels a pending add', () => {
    s.addPendingSplice(1, 2, 100, 200);
    s.removePendingSplice(1, 2, 100, 200);
    // The add is removed, and no remove entry is created
    expect(s.pendingChanges).toHaveLength(0);
  });

  it('removePendingSplice creates a remove entry for existing splices', () => {
    s.removePendingSplice(1, 2, 100, 200);
    expect(s.pendingChanges).toHaveLength(1);
    expect(s.pendingChanges[0].action).toBe('remove');
  });

  it('removePendingSplice deduplicates remove entries', () => {
    s.removePendingSplice(1, 2, 100, 200);
    s.removePendingSplice(1, 2, 100, 200);
    expect(s.pendingChanges).toHaveLength(1);
  });

  it('clearPending resets everything', () => {
    s.addPendingSplice(1, 2, 100, 200);
    s.clearPending();
    expect(s.hasPendingChanges()).toBe(false);
    expect(s.canUndo()).toBe(false);
    expect(s.canRedo()).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Undo / redo
// ---------------------------------------------------------------------------

describe('undo/redo', () => {
  let s: EditorState;

  beforeEach(() => {
    s = new EditorState();
  });

  it('undo restores previous state', () => {
    s.addPendingSplice(1, 2, 100, 200);
    expect(s.pendingChanges).toHaveLength(1);
    s.undo();
    expect(s.pendingChanges).toHaveLength(0);
  });

  it('redo restores undone state', () => {
    s.addPendingSplice(1, 2, 100, 200);
    s.undo();
    s.redo();
    expect(s.pendingChanges).toHaveLength(1);
    expect(s.pendingChanges[0].fiberA).toBe(1);
  });

  it('canUndo/canRedo reflect stack state', () => {
    expect(s.canUndo()).toBe(false);
    expect(s.canRedo()).toBe(false);

    s.addPendingSplice(1, 2, 100, 200);
    expect(s.canUndo()).toBe(true);

    s.undo();
    expect(s.canUndo()).toBe(false);
    expect(s.canRedo()).toBe(true);
  });

  it('new action clears redo stack', () => {
    s.addPendingSplice(1, 2, 100, 200);
    s.undo();
    expect(s.canRedo()).toBe(true);

    s.addPendingSplice(3, 4, 300, 400);
    expect(s.canRedo()).toBe(false);
  });

  it('undo on empty stack is a no-op', () => {
    s.undo();
    expect(s.pendingChanges).toHaveLength(0);
  });

  it('redo on empty stack is a no-op', () => {
    s.redo();
    expect(s.pendingChanges).toHaveLength(0);
  });

  it('multiple undo steps', () => {
    s.addPendingSplice(1, 2, 100, 200);
    s.addPendingSplice(3, 4, 300, 400);
    expect(s.pendingChanges).toHaveLength(2);

    s.undo(); // undo add(3,4)
    expect(s.pendingChanges).toHaveLength(1);
    expect(s.pendingChanges[0].fiberA).toBe(1);

    s.undo(); // undo add(1,2)
    expect(s.pendingChanges).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Strand pending state queries
// ---------------------------------------------------------------------------

describe('strand pending state', () => {
  let s: EditorState;

  beforeEach(() => {
    s = new EditorState();
  });

  it('isStrandPendingAdd detects involved strands', () => {
    s.addPendingSplice(1, 2, 100, 200);
    expect(s.isStrandPendingAdd(1)).toBe(true);
    expect(s.isStrandPendingAdd(2)).toBe(true);
    expect(s.isStrandPendingAdd(3)).toBe(false);
  });

  it('getStrandPendingState returns correct action', () => {
    s.addPendingSplice(1, 2, 100, 200);
    s.removePendingSplice(5, 6, 500, 600);
    expect(s.getStrandPendingState(1)).toBe('add');
    expect(s.getStrandPendingState(5)).toBe('remove');
    expect(s.getStrandPendingState(99)).toBeNull();
  });

  it('isSplicePendingDelete checks specific splice', () => {
    s.removePendingSplice(1, 2, 100, 200);
    expect(s.isSplicePendingDelete(1, 2)).toBe(true);
    expect(s.isSplicePendingDelete(2, 1)).toBe(true); // reversed
    expect(s.isSplicePendingDelete(1, 3)).toBe(false);
  });

  it('undoPendingAddForStrand removes adds involving that strand', () => {
    s.addPendingSplice(1, 2, 100, 200);
    s.addPendingSplice(3, 4, 300, 400);
    s.undoPendingAddForStrand(1);
    expect(s.pendingChanges).toHaveLength(1);
    expect(s.pendingChanges[0].fiberA).toBe(3);
  });
});

// ---------------------------------------------------------------------------
// getReSplices
// ---------------------------------------------------------------------------

describe('getReSplices', () => {
  it('detects strand re-spliced from old to new target', () => {
    const s = new EditorState();
    // strand 1 was spliced to 2 (remove), now spliced to 3 (add)
    s.removePendingSplice(1, 2, 100, 200);
    s.addPendingSplice(1, 3, 100, 300);

    const reSplices = s.getReSplices();
    expect(reSplices.has(1)).toBe(true);
    expect(reSplices.get(1)).toEqual({ oldTarget: 2, newTarget: 3 });
  });

  it('returns empty map when no re-splices', () => {
    const s = new EditorState();
    s.addPendingSplice(1, 2, 100, 200);
    expect(s.getReSplices().size).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// getPendingPayload
// ---------------------------------------------------------------------------

describe('getPendingPayload', () => {
  it('separates adds and removes using port IDs', () => {
    const s = new EditorState();
    s.addPendingSplice(1, 2, 100, 200);
    s.removePendingSplice(3, 4, 300, 400);

    const payload = s.getPendingPayload();
    expect(payload.add).toEqual([{ fiber_a: 100, fiber_b: 200 }]);
    expect(payload.remove).toEqual([{ fiber_a: 300, fiber_b: 400 }]);
  });

  it('auto-removes superseded existing splices', () => {
    const s = new EditorState();
    // Load cables with strand 1 live-spliced to strand 3
    s.loadCableGroups([
      makeCableGroup({
        fiber_cable_id: 1,
        tubes: [{
          id: 10, name: 'T1', color: '0000ff', stripe_color: null, strand_count: 1, tray_assignment: null,
          strands: [makeStrand({ id: 1, live_spliced_to: 3 })],
        }],
      }),
      makeCableGroup({
        fiber_cable_id: 2,
        tubes: [{
          id: 20, name: 'T1', color: 'ff0000', stripe_color: null, strand_count: 1, tray_assignment: null,
          strands: [makeStrand({ id: 3, live_spliced_to: 1 })],
        }],
      }),
    ]);

    // Add a new splice for strand 1 -> strand 5 (supersedes 1->3)
    s.addPendingSplice(1, 5, 100, 500);

    const payload = s.getPendingPayload();
    expect(payload.add).toEqual([{ fiber_a: 100, fiber_b: 500 }]);
    // The existing 1-3 splice should be auto-removed
    expect(payload.remove).toHaveLength(1);
    expect(payload.remove[0]).toEqual({ fiber_a: 100, fiber_b: 300 });
  });
});

// ---------------------------------------------------------------------------
// Layout: loadCableGroups + rebuildLayout
// ---------------------------------------------------------------------------

describe('loadCableGroups', () => {
  it('splits cables into left and right columns', () => {
    const s = new EditorState();
    s.loadCableGroups(twoTubeCables());

    // 2 cables: first goes left, second goes right
    const leftCables = s.leftNodes.filter(n => n.type === 'cable');
    const rightCables = s.rightNodes.filter(n => n.type === 'cable');
    expect(leftCables).toHaveLength(1);
    expect(rightCables).toHaveLength(1);
  });

  it('creates correct node hierarchy: cable -> tube -> strands', () => {
    const s = new EditorState();
    s.loadCableGroups(twoTubeCables());

    // Left column: cable, tube, strand, strand
    expect(s.leftNodes).toHaveLength(4);
    expect(s.leftNodes[0].type).toBe('cable');
    expect(s.leftNodes[1].type).toBe('tube');
    expect(s.leftNodes[2].type).toBe('strand');
    expect(s.leftNodes[3].type).toBe('strand');
  });

  it('calculates correct y positions', () => {
    const s = new EditorState();
    s.loadCableGroups(twoTubeCables());

    expect(s.leftNodes[0].y).toBe(TOP_PAD);                         // cable
    expect(s.leftNodes[1].y).toBe(TOP_PAD + CABLE_ROW_H);           // tube
    expect(s.leftNodes[2].y).toBe(TOP_PAD + CABLE_ROW_H + TUBE_ROW_H); // strand 1
    expect(s.leftNodes[3].y).toBe(TOP_PAD + CABLE_ROW_H + TUBE_ROW_H + STRAND_HEIGHT); // strand 2
  });

  it('populates strandMap for getStrand lookups', () => {
    const s = new EditorState();
    s.loadCableGroups(twoTubeCables());
    expect(s.getStrand(1)?.name).toBe('Strand 1');
    expect(s.getStrand(99)).toBeUndefined();
  });

  it('handles loose strands (no tubes)', () => {
    const s = new EditorState();
    s.loadCableGroups([
      makeCableGroup({
        fiber_cable_id: 1,
        loose_strands: [makeStrand({ id: 1 }), makeStrand({ id: 2 })],
      }),
    ]);

    // cable + 2 loose strands (no tube node)
    expect(s.leftNodes).toHaveLength(3);
    expect(s.leftNodes[0].type).toBe('cable');
    expect(s.leftNodes[1].type).toBe('strand');
    expect(s.leftNodes[2].type).toBe('strand');
  });
});

// ---------------------------------------------------------------------------
// Splice entry collection
// ---------------------------------------------------------------------------

describe('splice entries', () => {
  it('collects live splices', () => {
    const s = new EditorState();
    s.loadCableGroups([
      makeCableGroup({
        fiber_cable_id: 1,
        tubes: [{
          id: 10, name: 'T1', color: '0000ff', stripe_color: null, strand_count: 1, tray_assignment: null,
          strands: [makeStrand({ id: 1, live_spliced_to: 3 })],
        }],
      }),
      makeCableGroup({
        fiber_cable_id: 2,
        tubes: [{
          id: 20, name: 'T1', color: 'ff0000', stripe_color: null, strand_count: 1, tray_assignment: null,
          strands: [makeStrand({ id: 3, live_spliced_to: 1 })],
        }],
      }),
    ]);

    // Should be deduplicated to 1 entry
    expect(s.spliceEntries).toHaveLength(1);
    expect(s.spliceEntries[0].isLive).toBe(true);
    expect(s.spliceEntries[0].isPlan).toBe(false);
  });

  it('collects plan splices', () => {
    const s = new EditorState();
    s.loadCableGroups([
      makeCableGroup({
        fiber_cable_id: 1,
        tubes: [{
          id: 10, name: 'T1', color: '0000ff', stripe_color: null, strand_count: 1, tray_assignment: null,
          strands: [makeStrand({ id: 1, plan_entry_id: 99, plan_spliced_to: 3 })],
        }],
      }),
      makeCableGroup({
        fiber_cable_id: 2,
        tubes: [{
          id: 20, name: 'T1', color: 'ff0000', stripe_color: null, strand_count: 1, tray_assignment: null,
          strands: [makeStrand({ id: 3, plan_entry_id: 99, plan_spliced_to: 1 })],
        }],
      }),
    ]);

    expect(s.spliceEntries).toHaveLength(1);
    expect(s.spliceEntries[0].isPlan).toBe(true);
    expect(s.spliceEntries[0].entryId).toBe(99);
  });
});

// ---------------------------------------------------------------------------
// moveCable
// ---------------------------------------------------------------------------

describe('moveCable', () => {
  it('moves a cable to the other side', () => {
    const s = new EditorState();
    s.loadCableGroups(twoTubeCables());

    const leftBefore = s.leftNodes.filter(n => n.type === 'cable').length;
    const rightBefore = s.rightNodes.filter(n => n.type === 'cable').length;

    // Move cable 1 from left to right
    s.moveCable(1);

    const leftAfter = s.leftNodes.filter(n => n.type === 'cable').length;
    const rightAfter = s.rightNodes.filter(n => n.type === 'cable').length;

    expect(leftAfter).toBe(leftBefore - 1);
    expect(rightAfter).toBe(rightBefore + 1);
  });
});

// ---------------------------------------------------------------------------
// recalcPositions (collapsed tubes)
// ---------------------------------------------------------------------------

describe('recalcPositions', () => {
  it('hides strands in collapsed tubes', () => {
    const s = new EditorState();
    s.loadCableGroups(twoTubeCables());

    // Collapse the tube
    const tubeNode = s.leftNodes.find(n => n.type === 'tube');
    tubeNode!.collapsed = true;
    s.recalcPositions(s.leftNodes);

    const strands = s.leftNodes.filter(n => n.type === 'strand');
    expect(strands.every(n => n.hidden)).toBe(true);
  });

  it('shows strands when tube is expanded', () => {
    const s = new EditorState();
    s.loadCableGroups(twoTubeCables());

    // Collapse then expand
    const tubeNode = s.leftNodes.find(n => n.type === 'tube');
    tubeNode!.collapsed = true;
    s.recalcPositions(s.leftNodes);
    tubeNode!.collapsed = false;
    s.recalcPositions(s.leftNodes);

    const strands = s.leftNodes.filter(n => n.type === 'strand');
    expect(strands.every(n => !n.hidden)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// getVisibleStrandsFrom / getVisibleStrandsInTubeFrom
// ---------------------------------------------------------------------------

describe('getVisibleStrandsFrom', () => {
  it('returns strands from start ID onwards', () => {
    const s = new EditorState();
    s.loadCableGroups(twoTubeCables());

    const strands = s.getVisibleStrandsFrom('left', 1);
    expect(strands).toHaveLength(2);
    expect(strands[0].id).toBe(1);
    expect(strands[1].id).toBe(2);
  });

  it('returns from second strand', () => {
    const s = new EditorState();
    s.loadCableGroups(twoTubeCables());

    const strands = s.getVisibleStrandsFrom('left', 2);
    expect(strands).toHaveLength(1);
    expect(strands[0].id).toBe(2);
  });

  it('returns empty for unknown ID', () => {
    const s = new EditorState();
    s.loadCableGroups(twoTubeCables());
    expect(s.getVisibleStrandsFrom('left', 999)).toHaveLength(0);
  });
});

describe('getVisibleStrandsInTubeFrom', () => {
  it('returns strands within same tube only', () => {
    const s = new EditorState();
    const cables = [
      makeCableGroup({
        fiber_cable_id: 1,
        tubes: [
          {
            id: 10, name: 'T1', color: '0000ff', stripe_color: null, strand_count: 2, tray_assignment: null,
            strands: [makeStrand({ id: 1 }), makeStrand({ id: 2 })],
          },
          {
            id: 11, name: 'T2', color: '00ff00', stripe_color: null, strand_count: 2, tray_assignment: null,
            strands: [makeStrand({ id: 3 }), makeStrand({ id: 4 })],
          },
        ],
      }),
    ];
    s.loadCableGroups(cables);

    const strands = s.getVisibleStrandsInTubeFrom('left', 1);
    expect(strands).toHaveLength(2);
    expect(strands.map(n => n.id)).toEqual([1, 2]);
  });
});

// ---------------------------------------------------------------------------
// columnHeight
// ---------------------------------------------------------------------------

describe('columnHeight', () => {
  it('returns MIN_HEIGHT for empty columns', () => {
    const s = new EditorState();
    expect(s.columnHeight([])).toBe(MIN_HEIGHT);
  });

  it('returns correct height based on last visible node', () => {
    const s = new EditorState();
    s.loadCableGroups(twoTubeCables());

    const height = s.columnHeight(s.leftNodes);
    const lastVisible = s.leftNodes.filter(n => !n.hidden).pop()!;
    expect(height).toBe(lastVisible.y + STRAND_HEIGHT + TOP_PAD);
  });
});

// ---------------------------------------------------------------------------
// deleteSelectedSplices
// ---------------------------------------------------------------------------

describe('deleteSelectedSplices', () => {
  it('creates remove entries for selected splices', () => {
    const s = new EditorState();
    s.loadCableGroups([
      makeCableGroup({
        fiber_cable_id: 1,
        tubes: [{
          id: 10, name: 'T1', color: '0000ff', stripe_color: null, strand_count: 1, tray_assignment: null,
          strands: [makeStrand({ id: 1, live_spliced_to: 3 })],
        }],
      }),
      makeCableGroup({
        fiber_cable_id: 2,
        tubes: [{
          id: 20, name: 'T1', color: 'ff0000', stripe_color: null, strand_count: 1, tray_assignment: null,
          strands: [makeStrand({ id: 3, live_spliced_to: 1 })],
        }],
      }),
    ]);

    s.toggleSpliceSelection(1, 3);
    const count = s.deleteSelectedSplices();

    expect(count).toBe(1);
    expect(s.pendingChanges).toHaveLength(1);
    expect(s.pendingChanges[0].action).toBe('remove');
    expect(s.selectedSpliceKeys.size).toBe(0);
  });
});
