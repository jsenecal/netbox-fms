import type { LegendSection } from '../types';

export class FmsLegend {
  private container: HTMLElement;
  private body: HTMLElement;
  private toggleBtn: HTMLButtonElement;

  constructor(parent: HTMLElement) {
    this.container = document.createElement('div');
    this.container.className = 'fms-legend';
    this.container.dataset.collapsed = 'false';

    const header = document.createElement('div');
    header.className = 'fms-legend__header';

    const title = document.createElement('span');
    title.textContent = 'Legend';
    header.appendChild(title);

    this.toggleBtn = document.createElement('button');
    this.toggleBtn.type = 'button';
    this.toggleBtn.textContent = '\u25BC'; // down arrow (click to collapse)
    header.appendChild(this.toggleBtn);

    header.addEventListener('click', () => this.toggle());

    this.body = document.createElement('div');
    this.body.className = 'fms-legend__body';

    this.container.appendChild(header);
    this.container.appendChild(this.body);
    parent.appendChild(this.container);
  }

  toggle(): void {
    const collapsed = this.container.dataset.collapsed === 'true';
    this.container.dataset.collapsed = collapsed ? 'false' : 'true';
    this.toggleBtn.textContent = collapsed ? '\u25BC' : '\u25B2';
  }

  update(sections: LegendSection[]): void {
    // Clear body using safe DOM methods
    while (this.body.firstChild) {
      this.body.removeChild(this.body.firstChild);
    }

    if (sections.length === 0) {
      this.container.style.display = 'none';
      return;
    }

    this.container.style.display = '';

    for (const section of sections) {
      const sectionTitle = document.createElement('div');
      sectionTitle.className = 'fms-legend__section-title';
      sectionTitle.textContent = section.title;
      this.body.appendChild(sectionTitle);

      for (const item of section.items) {
        const row = document.createElement('div');
        row.className = 'fms-legend__item';

        if (item.type === 'dot') {
          const dot = document.createElement('span');
          dot.className = 'fms-legend__dot';
          if (item.color) {
            dot.style.backgroundColor = item.color;
          }
          row.appendChild(dot);
        } else if (item.type === 'line') {
          const line = document.createElement('span');
          line.className = 'fms-legend__line';
          const lineColor = item.dashColor || item.color || '#000';
          line.style.borderBottomStyle = item.dashed ? 'dashed' : 'solid';
          line.style.borderBottomColor = lineColor;
          row.appendChild(line);
        } else if (item.type === 'icon') {
          const icon = document.createElement('span');
          icon.textContent = item.icon || '';
          row.appendChild(icon);
        }

        const label = document.createElement('span');
        label.textContent = item.label;
        row.appendChild(label);

        this.body.appendChild(row);
      }
    }
  }

  destroy(): void {
    this.container.parentNode?.removeChild(this.container);
  }
}
