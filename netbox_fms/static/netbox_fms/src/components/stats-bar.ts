import type { StatsData } from '../types';
import { createBadge } from './badge';

export class FmsStatsBar {
  private container: HTMLElement;
  private left: HTMLElement;
  private right: HTMLElement;
  private flashTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(parent: HTMLElement) {
    this.container = document.createElement('div');
    this.container.className = 'fms-stats-bar';

    this.left = document.createElement('div');
    this.left.className = 'fms-stats-bar__left';

    this.right = document.createElement('div');
    this.right.className = 'fms-stats-bar__right';

    this.container.appendChild(this.left);
    this.container.appendChild(this.right);
    parent.appendChild(this.container);
  }

  update(stats: StatsData): void {
    // Clear left
    while (this.left.firstChild) {
      this.left.removeChild(this.left.firstChild);
    }
    // Clear right
    while (this.right.firstChild) {
      this.right.removeChild(this.right.firstChild);
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

    // Right side: plan status badge + plan name
    if (stats.planStatus) {
      this.right.appendChild(createBadge(stats.planStatus, stats.planStatus));
    }
    if (stats.planName) {
      const name = document.createElement('span');
      name.textContent = stats.planName;
      this.right.appendChild(name);
    }
  }

  flash(message: string, durationMs = 2000): void {
    // Save current left children
    const savedNodes: Node[] = [];
    while (this.left.firstChild) {
      savedNodes.push(this.left.removeChild(this.left.firstChild));
    }

    const msg = document.createElement('span');
    msg.className = 'fms-stats-bar__flash';
    msg.textContent = message;
    this.left.appendChild(msg);

    if (this.flashTimer !== null) {
      clearTimeout(this.flashTimer);
    }

    this.flashTimer = setTimeout(() => {
      while (this.left.firstChild) {
        this.left.removeChild(this.left.firstChild);
      }
      for (const node of savedNodes) {
        this.left.appendChild(node);
      }
      this.flashTimer = null;
    }, durationMs);
  }

  destroy(): void {
    if (this.flashTimer !== null) {
      clearTimeout(this.flashTimer);
    }
    this.container.parentNode?.removeChild(this.container);
  }
}
