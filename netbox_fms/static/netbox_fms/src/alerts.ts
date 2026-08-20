import type { CableGroupData, EditorConfig } from './types';

/** Severity of a status message. Info flashes briefly; warning/error persist. */
export type StatusLevel = 'info' | 'warning' | 'error';

/** Levels that are shown as persistent, dismissible alerts. */
export type AlertLevel = 'warning' | 'error';

/** Sinks a status message can be routed to. */
export interface StatusSinks {
  /** Transient display (stats bar flash). */
  flash: (msg: string) => void;
  /** Persistent, dismissible alert display. */
  alert: (msg: string, level: AlertLevel) => void;
}

/**
 * Route a status message to the right display: informational messages
 * flash briefly, while warnings and errors go to a persistent alert.
 */
export function routeStatusMessage(msg: string, level: StatusLevel, sinks: StatusSinks): void {
  if (level === 'info') {
    sinks.flash(msg);
  } else {
    sinks.alert(msg, level);
  }
}

/** Config fields relevant to preflight checks. */
export type PreflightConfig = Pick<EditorConfig, 'planId' | 'planStatus'> &
  Partial<Pick<EditorConfig, 'closurePlanCount' | 'closureDraftPlanCount'>>;

/**
 * Derive editor-load warnings from the loaded cable data and plan context:
 * buffer tubes without a tray assignment, no splice plan for the closure,
 * or only non-draft plans for the closure.
 *
 * The closure plan counts come from the page config and can be stale after
 * a plan is quick-added in the same session, so the current plan (planId /
 * planStatus) is folded in as a lower bound.
 */
export function derivePreflightWarnings(cables: CableGroupData[], config: PreflightConfig): string[] {
  const warnings: string[] = [];

  const planCount = Math.max(config.closurePlanCount ?? 0, config.planId !== null ? 1 : 0);
  const draftPlanCount = Math.max(
    config.closureDraftPlanCount ?? 0,
    config.planId !== null && config.planStatus === 'draft' ? 1 : 0,
  );

  if (planCount === 0) {
    warnings.push('No splice plan exists for this closure. A plan must be created before splices can be saved.');
  } else if (draftPlanCount === 0) {
    warnings.push(
      'Only non-draft splice plans exist for this closure. Changes cannot be saved until a draft plan exists.',
    );
  }

  let unassignedTubes = 0;
  for (const cable of cables) {
    for (const tube of cable.tubes) {
      if (!tube.tray_assignment) unassignedTubes++;
    }
  }
  if (unassignedTubes > 0) {
    warnings.push(
      `${unassignedTubes} buffer tube(s) are not assigned to a splice tray. ` +
        'Saving splices on their fibers may fail until the tubes are assigned.',
    );
  }

  return warnings;
}

/**
 * A stack of persistent, dismissible Bootstrap alerts shown above the
 * editor canvas. Duplicate messages are collapsed onto the existing alert.
 */
export class FmsAlertStack {
  private container: HTMLElement;
  private open = new Map<string, HTMLElement>();

  constructor(container: HTMLElement) {
    this.container = container;
  }

  /** Show a dismissible alert. Re-showing an identical message is a no-op. */
  show(msg: string, level: AlertLevel): void {
    if (this.open.has(msg)) return;

    const alert = document.createElement('div');
    alert.className = `alert alert-${level === 'error' ? 'danger' : 'warning'} d-flex align-items-center py-2 mb-2`;
    alert.setAttribute('role', 'alert');

    const icon = document.createElement('i');
    icon.className = `mdi ${level === 'error' ? 'mdi-alert-circle' : 'mdi-alert'} me-2`;
    alert.appendChild(icon);

    const text = document.createElement('span');
    text.className = 'me-auto';
    text.textContent = msg;
    alert.appendChild(text);

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'btn-close ms-2';
    closeBtn.setAttribute('aria-label', 'Close');
    closeBtn.addEventListener('click', () => {
      alert.remove();
      this.open.delete(msg);
    });
    alert.appendChild(closeBtn);

    this.container.appendChild(alert);
    this.open.set(msg, alert);
  }
}
