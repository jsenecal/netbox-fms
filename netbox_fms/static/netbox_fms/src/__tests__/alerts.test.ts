import { describe, it, expect, vi } from 'vitest';
import { derivePreflightWarnings, routeStatusMessage } from '../alerts';
import type { CableGroupData, StrandData, TubeData } from '../types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeStrand(id: number): StrandData {
  return {
    id,
    name: `Strand ${id}`,
    position: id,
    color: 'ff0000',
    tube_color: null,
    tube_name: null,
    ribbon_name: null,
    ribbon_color: null,
    front_port_a_id: id * 100,
    live_spliced_to: null,
    plan_entry_id: null,
    plan_spliced_to: null,
    protected: false,
    circuit_name: null,
    circuit_url: null,
  };
}

function makeTube(id: number, assigned: boolean): TubeData {
  return {
    id,
    name: `Tube ${id}`,
    color: '0000ff',
    marker_count: 0,
    marker_color: null,
    marker_type: '',
    strand_count: 1,
    strands: [makeStrand(id * 10)],
    tray_assignment: assigned
      ? { tray_id: 1, tray_name: 'Tray 1', tray_url: '/trays/1/' }
      : null,
  };
}

function makeCable(id: number, tubes: TubeData[], looseStrands: StrandData[] = []): CableGroupData {
  return {
    fiber_cable_id: id,
    cable_label: `Cable ${id}`,
    cable_url: `/cables/${id}/`,
    fiber_type: 'smf_os2',
    strand_count: tubes.reduce((n, t) => n + t.strand_count, 0) + looseStrands.length,
    far_device_name: null,
    far_device_url: null,
    tubes,
    loose_strands: looseStrands,
  };
}

const draftEdit = {
  planId: 1,
  planStatus: 'draft',
  closurePlanCount: 1,
  closureDraftPlanCount: 1,
};

// ---------------------------------------------------------------------------
// routeStatusMessage
// ---------------------------------------------------------------------------

describe('routeStatusMessage', () => {
  it('sends info messages to the flash sink only', () => {
    const flash = vi.fn();
    const alert = vi.fn();
    routeStatusMessage('Loaded 2 cable(s).', 'info', { flash, alert });
    expect(flash).toHaveBeenCalledWith('Loaded 2 cable(s).');
    expect(alert).not.toHaveBeenCalled();
  });

  it('sends error messages to the persistent alert sink only', () => {
    const flash = vi.fn();
    const alert = vi.fn();
    routeStatusMessage('Save error: tube not assigned', 'error', { flash, alert });
    expect(alert).toHaveBeenCalledWith('Save error: tube not assigned', 'error');
    expect(flash).not.toHaveBeenCalled();
  });

  it('sends warning messages to the persistent alert sink only', () => {
    const flash = vi.fn();
    const alert = vi.fn();
    routeStatusMessage('Strand is protected.', 'warning', { flash, alert });
    expect(alert).toHaveBeenCalledWith('Strand is protected.', 'warning');
    expect(flash).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// derivePreflightWarnings
// ---------------------------------------------------------------------------

describe('derivePreflightWarnings', () => {
  it('returns no warnings for assigned tubes and a draft plan', () => {
    const cables = [makeCable(1, [makeTube(1, true), makeTube(2, true)])];
    expect(derivePreflightWarnings(cables, draftEdit)).toEqual([]);
  });

  it('warns when buffer tubes are not assigned to any tray', () => {
    const cables = [
      makeCable(1, [makeTube(1, true), makeTube(2, false)]),
      makeCable(2, [makeTube(3, false)]),
    ];
    const warnings = derivePreflightWarnings(cables, draftEdit);
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toContain('2 buffer tube(s)');
    expect(warnings[0]).toContain('not assigned');
  });

  it('does not warn about tubes for tight-buffer cables with loose strands only', () => {
    const cables = [makeCable(1, [], [makeStrand(1), makeStrand(2)])];
    expect(derivePreflightWarnings(cables, draftEdit)).toEqual([]);
  });

  it('warns when no splice plan exists for the closure', () => {
    const warnings = derivePreflightWarnings([], {
      planId: null,
      planStatus: '',
      closurePlanCount: 0,
      closureDraftPlanCount: 0,
    });
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toContain('No splice plan');
  });

  it('treats a quick-added plan as existing even if the count is stale', () => {
    const warnings = derivePreflightWarnings([], {
      planId: 42,
      planStatus: 'draft',
      closurePlanCount: 0,
      closureDraftPlanCount: 0,
    });
    expect(warnings).toEqual([]);
  });

  it('warns when only non-draft plans exist', () => {
    const warnings = derivePreflightWarnings([], {
      planId: 7,
      planStatus: 'archived',
      closurePlanCount: 2,
      closureDraftPlanCount: 0,
    });
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toContain('non-draft');
  });

  it('does not warn about plan status when the current plan is a draft', () => {
    const warnings = derivePreflightWarnings([], {
      planId: 7,
      planStatus: 'draft',
      closurePlanCount: 1,
      closureDraftPlanCount: 0,
    });
    expect(warnings).toEqual([]);
  });

  it('warns about a missing plan when the counts are not provided', () => {
    const warnings = derivePreflightWarnings([], {
      planId: null,
      planStatus: '',
    });
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toContain('No splice plan');
  });

  it('reports tube and plan warnings together', () => {
    const cables = [makeCable(1, [makeTube(1, false)])];
    const warnings = derivePreflightWarnings(cables, {
      planId: null,
      planStatus: '',
      closurePlanCount: 0,
      closureDraftPlanCount: 0,
    });
    expect(warnings).toHaveLength(2);
  });
});
