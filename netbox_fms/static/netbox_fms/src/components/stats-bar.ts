import type { StatsData } from '../types';
import { createBadge } from './badge';

export class FmsStatsBar {
  private container: HTMLElement;
  private left: HTMLElement;
  private right: HTMLElement;
  private messageEl: HTMLSpanElement;
  private planSection: HTMLSpanElement;
  private messageTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(parent: HTMLElement) {
    this.container = document.createElement('div');
    this.container.className = 'fms-stats-bar';

    this.left = document.createElement('div');
    this.left.className = 'fms-stats-bar__left';

    this.right = document.createElement('div');
    this.right.className = 'fms-stats-bar__right';

    // Message element sits in the right section, before the plan badge
    this.messageEl = document.createElement('span');
    this.messageEl.className = 'fms-stats-bar__message';
    this.messageEl.style.marginRight = '6px';

    // Plan section holds badge + plan name
    this.planSection = document.createElement('span');
    this.planSection.style.display = 'inline-flex';
    this.planSection.style.alignItems = 'center';
    this.planSection.style.gap = '6px';

    this.right.appendChild(this.messageEl);
    this.right.appendChild(this.planSection);

    this.container.appendChild(this.left);
    this.container.appendChild(this.right);
    parent.appendChild(this.container);
  }

  update(stats: StatsData): void {
    // Clear left
    while (this.left.firstChild) {
      this.left.removeChild(this.left.firstChild);
    }

    const statItems: Array<{ label: string; value: string; color?: string; essential?: boolean }> = [
      { label: 'Cables:', value: String(stats.cableCount) },
      { label: 'Strands:', value: String(stats.strandCount) },
      { label: 'Splices:', value: `${stats.liveSpliceCount} live`, color: '#28a745', essential: true },
      { label: '', value: `${stats.plannedSpliceCount} planned`, color: '#17a2b8' },
      { label: 'Pending:', value: `${stats.pendingCount} changes`, color: stats.pendingCount > 0 ? '#ffc107' : undefined, essential: true },
    ];

    statItems.forEach((item, index) => {
      if (index > 0) {
        const sep = document.createElement('span');
        sep.textContent = '\u00B7'; // middot
        this.left.appendChild(sep);
      }

      const stat = document.createElement('span');
      stat.className = 'fms-stat';
      if (item.essential) {
        stat.classList.add('fms-stat--essential');
      }

      const label = document.createElement('span');
      label.className = 'fms-stat__label';
      label.textContent = item.label;
      stat.appendChild(label);

      const value = document.createElement('span');
      value.className = 'fms-stat__value';
      value.textContent = item.value;
      if (item.color) {
        value.style.color = item.color;
      }
      stat.appendChild(value);

      this.left.appendChild(stat);
    });

    // Plan section in right side
    while (this.planSection.firstChild) {
      this.planSection.removeChild(this.planSection.firstChild);
    }
    if (stats.planStatus) {
      this.planSection.appendChild(createBadge(stats.planStatus, stats.planStatus));
    }
    if (stats.planName) {
      const name = document.createElement('span');
      name.textContent = stats.planName;
      this.planSection.appendChild(name);
    }
  }

  /** Show a message on the right side of the stats bar (e.g. selection info).
   *  Pass null to clear. Optionally auto-clear after durationMs. */
  setMessage(message: string | null, durationMs?: number): void {
    if (this.messageTimer !== null) {
      clearTimeout(this.messageTimer);
      this.messageTimer = null;
    }
    this.messageEl.textContent = message || '';
    if (message && durationMs) {
      this.messageTimer = setTimeout(() => {
        this.messageEl.textContent = '';
        this.messageTimer = null;
      }, durationMs);
    }
  }

  /** @deprecated Use setMessage() instead. Temporarily replaces left content. */
  flash(message: string, durationMs = 2000): void {
    this.setMessage(message, durationMs);
  }

  destroy(): void {
    if (this.messageTimer !== null) {
      clearTimeout(this.messageTimer);
    }
    this.container.parentNode?.removeChild(this.container);
  }
}
