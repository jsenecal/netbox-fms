import type { EditorConfig } from './types';

/**
 * True when saving must first create a plan via the quick-create modal.
 * Every save path (plain Save and Save & Submit alike) must check this
 * before touching the bulk-update endpoint, which needs an existing plan.
 */
export function needsPlanQuickCreate(config: Pick<EditorConfig, 'contextMode' | 'planId'>): boolean {
  return config.contextMode === 'view' && !config.planId;
}

/** Derive the bulk-update endpoint for a freshly quick-created plan. */
export function bulkUpdateUrlFor(quickAddApiUrl: string, planId: number): string {
  return quickAddApiUrl.replace('quick-add/', `${planId}/bulk-update/`);
}
