import type { DetailCard } from '../types';
import { createBadge } from './badge';

export class FmsDetailPanel {
  private container: HTMLElement;
  private titleEl: HTMLSpanElement;
  private body: HTMLElement;
  private onCloseFn: (() => void) | null = null;
  private keyHandler: (e: KeyboardEvent) => void;

  constructor(parent: HTMLElement) {
    this.container = document.createElement('div');
    this.container.className = 'fms-detail-panel';
    this.container.dataset.open = 'false';

    const header = document.createElement('div');
    header.className = 'fms-detail-panel__header';

    this.titleEl = document.createElement('span');
    this.titleEl.className = 'fms-detail-panel__title';
    header.appendChild(this.titleEl);

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'fms-detail-panel__close';
    closeBtn.textContent = '\u00D7'; // ×
    closeBtn.addEventListener('click', () => this.hide());
    header.appendChild(closeBtn);

    this.body = document.createElement('div');
    this.body.className = 'fms-detail-panel__body';

    this.container.appendChild(header);
    this.container.appendChild(this.body);
    parent.appendChild(this.container);

    this.keyHandler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && this.isOpen()) {
        this.hide();
      }
    };
    document.addEventListener('keydown', this.keyHandler);
  }

  setOnClose(fn: () => void): void {
    this.onCloseFn = fn;
  }

  show(title: string, cards: DetailCard[]): void {
    this.titleEl.textContent = title;

    // Clear body safely
    while (this.body.firstChild) {
      this.body.removeChild(this.body.firstChild);
    }

    for (const card of cards) {
      if (card.separator) {
        const sep = document.createElement('hr');
        sep.className = 'fms-detail-separator';
        this.body.appendChild(sep);
      }

      const cardEl = document.createElement('div');
      cardEl.className = 'fms-detail-card';

      if (card.heading) {
        const heading = document.createElement('div');
        heading.className = 'fms-detail-card__heading';
        heading.textContent = card.heading;
        cardEl.appendChild(heading);
      }

      for (const row of card.rows) {
        const rowEl = document.createElement('div');
        rowEl.className = 'fms-detail-card__row';

        const labelEl = document.createElement('span');
        labelEl.className = 'fms-detail-card__label';
        labelEl.textContent = row.label;
        rowEl.appendChild(labelEl);

        if (row.link) {
          const anchor = document.createElement('a');
          anchor.className = 'fms-link fms-detail-card__value';
          anchor.href = row.link;
          anchor.target = '_blank';
          anchor.textContent = `${row.value} \u2197`; // ↗
          rowEl.appendChild(anchor);
        } else if (row.badge) {
          rowEl.appendChild(createBadge(row.badge, row.value));
        } else if (row.color) {
          const valueWrap = document.createElement('span');
          valueWrap.className = 'fms-detail-card__value';
          valueWrap.style.display = 'inline-flex';
          valueWrap.style.alignItems = 'center';
          valueWrap.style.gap = '4px';

          const dot = document.createElement('span');
          dot.className = 'fms-legend__dot';
          dot.style.backgroundColor = row.color;
          valueWrap.appendChild(dot);

          const text = document.createElement('span');
          text.textContent = row.value;
          valueWrap.appendChild(text);

          rowEl.appendChild(valueWrap);
        } else {
          const text = document.createElement('span');
          text.className = 'fms-detail-card__value';
          text.textContent = row.value;
          rowEl.appendChild(text);
        }

        cardEl.appendChild(rowEl);
      }

      this.body.appendChild(cardEl);
    }

    this.container.dataset.open = 'true';
  }

  hide(): void {
    this.container.dataset.open = 'false';
    if (this.onCloseFn) {
      this.onCloseFn();
    }
  }

  isOpen(): boolean {
    return this.container.dataset.open === 'true';
  }

  destroy(): void {
    document.removeEventListener('keydown', this.keyHandler);
    this.container.parentNode?.removeChild(this.container);
  }
}
