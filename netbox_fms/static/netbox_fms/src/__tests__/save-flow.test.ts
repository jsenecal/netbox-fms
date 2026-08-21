import { describe, it, expect } from 'vitest';
import { needsPlanQuickCreate, bulkUpdateUrlFor } from '../save-flow';

// ---------------------------------------------------------------------------
// needsPlanQuickCreate — both Save and Save & Submit must route through the
// quick-create modal when the closure has no plan yet, instead of dying at
// bulkUpdatePlan with "No bulk update URL".
// ---------------------------------------------------------------------------

describe('needsPlanQuickCreate', () => {
  it('is true in view context with no plan', () => {
    expect(needsPlanQuickCreate({ contextMode: 'view', planId: null })).toBe(true);
  });

  it('is false in view context once a plan exists', () => {
    expect(needsPlanQuickCreate({ contextMode: 'view', planId: 42 })).toBe(false);
  });

  it('is false in edit context', () => {
    expect(needsPlanQuickCreate({ contextMode: 'edit', planId: null })).toBe(false);
    expect(needsPlanQuickCreate({ contextMode: 'edit', planId: 42 })).toBe(false);
  });

  it('is false in plan-edit context', () => {
    expect(needsPlanQuickCreate({ contextMode: 'plan-edit', planId: 42 })).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// bulkUpdateUrlFor — derive the bulk-update endpoint for a quick-created plan
// ---------------------------------------------------------------------------

describe('bulkUpdateUrlFor', () => {
  it('replaces the quick-add suffix with the plan bulk-update path', () => {
    expect(bulkUpdateUrlFor('/api/plugins/fms/splice-plans/quick-add/', 7)).toBe(
      '/api/plugins/fms/splice-plans/7/bulk-update/',
    );
  });
});
