import type { ChannelData, EditorConfig, PortData } from './wavelength-editor-types';

interface Change {
  channelId: number;
  oldPortId: number | null;
  newPortId: number | null;
}

function getCsrfToken(): string {
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : '';
}

function clearElement(el: HTMLElement): void {
  while (el.firstChild) {
    el.removeChild(el.firstChild);
  }
}

class WavelengthEditor {
  private config: EditorConfig;
  private container: HTMLElement;
  /** Current port assignment per channel id */
  private currentMapping: Map<number, number | null>;
  /** Initial mapping snapshot for dirty detection */
  private initialMapping: Map<number, number | null>;
  private undoStack: Change[] = [];
  private redoStack: Change[] = [];
  private lastUpdated: string;

  // toolbar elements
  private undoBtn!: HTMLButtonElement;
  private redoBtn!: HTMLButtonElement;
  private saveBtn!: HTMLButtonElement;
  private dirtyBadge!: HTMLSpanElement;
  private messageArea!: HTMLDivElement;

  constructor(container: HTMLElement, config: EditorConfig) {
    this.container = container;
    this.config = config;
    this.lastUpdated = config.lastUpdated;

    this.currentMapping = new Map();
    this.initialMapping = new Map();
    for (const ch of config.channels) {
      this.currentMapping.set(ch.id, ch.front_port_id);
      this.initialMapping.set(ch.id, ch.front_port_id);
    }

    this.render();
    this.bindKeyboard();
    this.bindBeforeUnload();
  }

  private render(): void {
    clearElement(this.container);

    // Message area
    this.messageArea = document.createElement('div');
    this.container.appendChild(this.messageArea);

    // Toolbar
    const toolbar = document.createElement('div');
    toolbar.className = 'd-flex align-items-center gap-2 mb-3';

    this.undoBtn = this.makeButton('mdi mdi-undo', 'Undo', () => this.undo());
    this.redoBtn = this.makeButton('mdi mdi-redo', 'Redo', () => this.redo());
    this.saveBtn = this.makeButton('mdi mdi-content-save', 'Save', () => this.save());
    this.saveBtn.classList.replace('btn-outline-secondary', 'btn-primary');

    this.dirtyBadge = document.createElement('span');
    this.dirtyBadge.className = 'badge bg-warning text-dark ms-2 d-none';
    this.dirtyBadge.textContent = 'Unsaved changes';

    toolbar.appendChild(this.undoBtn);
    toolbar.appendChild(this.redoBtn);
    toolbar.appendChild(this.saveBtn);
    toolbar.appendChild(this.dirtyBadge);
    this.container.appendChild(toolbar);

    // Table
    const table = document.createElement('table');
    table.className = 'table table-sm table-hover';

    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    for (const h of ['Grid Pos', 'Label', 'Wavelength (nm)', 'Port Assignment', 'Status']) {
      const th = document.createElement('th');
      th.scope = 'col';
      th.textContent = h;
      headerRow.appendChild(th);
    }
    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    const sorted = [...this.config.channels].sort((a, b) => a.grid_position - b.grid_position);
    for (const ch of sorted) {
      const tr = document.createElement('tr');
      tr.dataset.channelId = String(ch.id);

      // Grid Position
      this.addCell(tr, String(ch.grid_position));
      // Label
      this.addCell(tr, ch.label);
      // Wavelength
      this.addCell(tr, String(ch.wavelength_nm));

      // Port Assignment
      const portTd = document.createElement('td');
      if (ch.status === 'available') {
        const select = this.buildPortSelect(ch);
        portTd.appendChild(select);
      } else {
        // Reserved or lit: show port name with lock icon
        const span = document.createElement('span');
        const lockIcon = document.createElement('i');
        lockIcon.className = 'mdi mdi-lock me-1';
        if (ch.service_name) {
          lockIcon.title = ch.service_name;
        }
        span.appendChild(lockIcon);
        span.appendChild(document.createTextNode(ch.front_port_name || 'Unassigned'));
        portTd.appendChild(span);
      }
      tr.appendChild(portTd);

      // Status
      const statusTd = document.createElement('td');
      const badge = document.createElement('span');
      if (ch.status === 'lit') {
        badge.className = 'badge bg-success';
        badge.textContent = 'Lit';
      } else if (ch.status === 'reserved') {
        badge.className = 'badge bg-warning';
        badge.textContent = 'Reserved';
      } else {
        badge.className = 'badge bg-secondary';
        badge.textContent = 'Available';
      }
      statusTd.appendChild(badge);
      tr.appendChild(statusTd);

      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    this.container.appendChild(table);

    this.updateToolbar();
  }

  private addCell(tr: HTMLTableRowElement, text: string): void {
    const td = document.createElement('td');
    td.textContent = text;
    tr.appendChild(td);
  }

  private buildPortSelect(ch: ChannelData): HTMLSelectElement {
    const select = document.createElement('select');
    select.className = 'form-select form-select-sm';
    select.dataset.channelId = String(ch.id);

    // "Unassigned" option
    const unassigned = document.createElement('option');
    unassigned.value = '';
    unassigned.textContent = '-- Unassigned --';
    select.appendChild(unassigned);

    // Current port (if assigned but might not be in available list)
    const currentPortId = this.currentMapping.get(ch.id);

    // Build set of all available port ids
    const availableIds = new Set(this.config.availablePorts.map(p => p.id));

    // If current channel has a port assigned, include it in options
    if (ch.front_port_id && !availableIds.has(ch.front_port_id)) {
      const opt = document.createElement('option');
      opt.value = String(ch.front_port_id);
      opt.textContent = ch.front_port_name || `Port ${ch.front_port_id}`;
      select.appendChild(opt);
    }

    // Also include ports currently assigned to OTHER available channels
    // (they might be reassigned)
    const otherAssigned = new Map<number, string>();
    for (const other of this.config.channels) {
      if (other.id !== ch.id && other.status === 'available' && other.front_port_id && !availableIds.has(other.front_port_id)) {
        otherAssigned.set(other.front_port_id, other.front_port_name || `Port ${other.front_port_id}`);
      }
    }

    for (const port of this.config.availablePorts) {
      const opt = document.createElement('option');
      opt.value = String(port.id);
      opt.textContent = port.name;
      select.appendChild(opt);
    }

    for (const [portId, portName] of otherAssigned) {
      const opt = document.createElement('option');
      opt.value = String(portId);
      opt.textContent = portName;
      select.appendChild(opt);
    }

    // Set current value
    select.value = currentPortId ? String(currentPortId) : '';

    select.addEventListener('change', () => {
      const newPortId = select.value ? Number(select.value) : null;
      const oldPortId = this.currentMapping.get(ch.id) ?? null;
      if (newPortId === oldPortId) return;

      this.currentMapping.set(ch.id, newPortId);
      this.undoStack.push({ channelId: ch.id, oldPortId, newPortId });
      this.redoStack = [];
      this.updateToolbar();
    });

    return select;
  }

  private makeButton(iconClass: string, label: string, onClick: () => void): HTMLButtonElement {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-sm btn-outline-secondary';
    btn.title = label;
    const icon = document.createElement('i');
    icon.className = iconClass;
    btn.appendChild(icon);
    btn.appendChild(document.createTextNode(' ' + label));
    btn.addEventListener('click', onClick);
    return btn;
  }

  private isDirty(): boolean {
    for (const [chId, portId] of this.currentMapping) {
      if (this.initialMapping.get(chId) !== portId) return true;
    }
    return false;
  }

  private updateToolbar(): void {
    this.undoBtn.disabled = this.undoStack.length === 0;
    this.redoBtn.disabled = this.redoStack.length === 0;
    const dirty = this.isDirty();
    this.saveBtn.disabled = !dirty;
    if (dirty) {
      this.dirtyBadge.classList.remove('d-none');
    } else {
      this.dirtyBadge.classList.add('d-none');
    }
  }

  private undo(): void {
    const change = this.undoStack.pop();
    if (!change) return;
    this.currentMapping.set(change.channelId, change.oldPortId);
    this.redoStack.push(change);
    this.syncSelect(change.channelId);
    this.updateToolbar();
  }

  private redo(): void {
    const change = this.redoStack.pop();
    if (!change) return;
    this.currentMapping.set(change.channelId, change.newPortId);
    this.undoStack.push(change);
    this.syncSelect(change.channelId);
    this.updateToolbar();
  }

  private syncSelect(channelId: number): void {
    const select = this.container.querySelector(
      `select[data-channel-id="${channelId}"]`
    ) as HTMLSelectElement | null;
    if (select) {
      const val = this.currentMapping.get(channelId);
      select.value = val ? String(val) : '';
    }
  }

  private async save(): Promise<void> {
    this.saveBtn.disabled = true;
    clearElement(this.saveBtn);
    this.saveBtn.textContent = 'Saving...';

    const mapping: Record<string, number | null> = {};
    for (const [chId, portId] of this.currentMapping) {
      mapping[String(chId)] = portId;
    }

    try {
      const resp = await fetch(this.config.applyUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken(),
        },
        body: JSON.stringify({
          mapping,
          last_updated: this.lastUpdated,
        }),
      });

      if (resp.status === 200) {
        const data = await resp.json() as { added: number; removed: number; changed: number; last_updated?: string };
        if (data.last_updated) {
          this.lastUpdated = data.last_updated;
        }
        // Reset initial mapping to current
        for (const [chId, portId] of this.currentMapping) {
          this.initialMapping.set(chId, portId);
        }
        this.undoStack = [];
        this.redoStack = [];
        this.showMessage(
          'success',
          `Saved: ${data.added} added, ${data.removed} removed, ${data.changed} changed.`
        );
      } else if (resp.status === 409) {
        this.showConflict();
      } else {
        const data = await resp.json() as { errors?: string[] };
        const msg = data.errors ? data.errors.join(', ') : 'Validation error';
        this.showMessage('danger', msg);
      }
    } catch (err) {
      this.showMessage('danger', 'Network error: ' + (err as Error).message);
    }

    // Restore button content
    clearElement(this.saveBtn);
    const icon = document.createElement('i');
    icon.className = 'mdi mdi-content-save';
    this.saveBtn.appendChild(icon);
    this.saveBtn.appendChild(document.createTextNode(' Save'));
    this.updateToolbar();
  }

  private showMessage(type: string, text: string): void {
    clearElement(this.messageArea);
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show`;
    alert.setAttribute('role', 'alert');
    alert.textContent = text;
    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'btn-close';
    closeBtn.setAttribute('data-bs-dismiss', 'alert');
    alert.appendChild(closeBtn);
    this.messageArea.appendChild(alert);
  }

  private showConflict(): void {
    clearElement(this.messageArea);
    const alert = document.createElement('div');
    alert.className = 'alert alert-warning';
    alert.setAttribute('role', 'alert');
    alert.textContent = 'This node was modified by another user. ';
    const reloadBtn = document.createElement('button');
    reloadBtn.type = 'button';
    reloadBtn.className = 'btn btn-sm btn-outline-warning ms-2';
    reloadBtn.textContent = 'Reload';
    reloadBtn.addEventListener('click', () => window.location.reload());
    alert.appendChild(reloadBtn);
    this.messageArea.appendChild(alert);
  }

  private bindKeyboard(): void {
    document.addEventListener('keydown', (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        if (e.shiftKey) {
          e.preventDefault();
          this.redo();
        } else {
          e.preventDefault();
          this.undo();
        }
      }
    });
  }

  private bindBeforeUnload(): void {
    window.addEventListener('beforeunload', (e: BeforeUnloadEvent) => {
      if (this.isDirty()) {
        e.preventDefault();
      }
    });
  }
}

// Entry point
const config = (window as unknown as { WAVELENGTH_EDITOR_CONFIG?: EditorConfig }).WAVELENGTH_EDITOR_CONFIG;
if (config) {
  const container = document.getElementById('wavelength-editor-container');
  if (container) {
    new WavelengthEditor(container, config);
  }
}
