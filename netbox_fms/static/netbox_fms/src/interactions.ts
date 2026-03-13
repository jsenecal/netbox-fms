import type { EditorConfig, LayoutNode, SpliceEntry, ActionMode } from './types';
import type { EditorState } from './state';
import type { SpliceRenderer } from './renderer';

export class Interactions {
  private state: EditorState;
  private renderer: SpliceRenderer;
  private config: EditorConfig;
  private onSave: () => void;
  private mode: ActionMode = 'single';
  private selected: { id: number; side: 'left' | 'right'; portId: number } | null = null;
  private sequentialCount = 12;
  private statusEl: HTMLElement | null;
  private saveBtn: HTMLButtonElement | null = null;
  private countContainer: HTMLElement | null = null;

  constructor(
    state: EditorState,
    renderer: SpliceRenderer,
    config: EditorConfig,
    onSave: () => void,
  ) {
    this.state = state;
    this.renderer = renderer;
    this.config = config;
    this.onSave = onSave;
    this.statusEl = document.getElementById('splice-status');

    this.setupToolbar();
    this.setupBeforeUnload();
  }

  private setupToolbar(): void {
    const toolbar = document.getElementById('splice-toolbar');
    if (!toolbar) return;

    // Mode buttons
    toolbar.querySelectorAll<HTMLButtonElement>('[data-mode]').forEach((btn) => {
      btn.addEventListener('click', () => {
        toolbar.querySelectorAll('[data-mode]').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        this.mode = btn.dataset.mode as ActionMode;
        this.clearSelection();
        this.setStatus(`Mode: ${this.mode}`);
        this.updateCountSelector();
      });
    });

    // Save button (dynamically injected)
    this.saveBtn = document.createElement('button');
    this.saveBtn.type = 'button';
    this.saveBtn.id = 'splice-save-btn';
    this.saveBtn.className = 'btn btn-sm btn-success ms-2 d-none';
    const saveIcon = document.createElement('i');
    saveIcon.className = 'mdi mdi-content-save';
    this.saveBtn.appendChild(saveIcon);
    this.saveBtn.appendChild(document.createTextNode(' Save'));
    this.saveBtn.addEventListener('click', () => this.onSave());
    // Insert after the btn-group
    const btnGroup = toolbar.querySelector('.btn-group');
    if (btnGroup && btnGroup.parentNode) {
      btnGroup.parentNode.insertBefore(this.saveBtn, btnGroup.nextSibling);
    }

    // Sequential count selector (hidden by default)
    this.countContainer = document.createElement('span');
    this.countContainer.id = 'sequential-count';
    this.countContainer.className = 'ms-2 d-none align-items-center';
    this.countContainer.style.display = 'none';

    const minusBtn = document.createElement('button');
    minusBtn.type = 'button';
    minusBtn.className = 'btn btn-sm btn-outline-secondary';
    minusBtn.textContent = '-';
    minusBtn.addEventListener('click', () => this.adjustCount(-1));

    const countInput = document.createElement('input');
    countInput.type = 'number';
    countInput.className = 'form-control form-control-sm mx-1';
    countInput.style.width = '50px';
    countInput.min = '1';
    countInput.max = '144';
    countInput.value = String(this.sequentialCount);
    countInput.addEventListener('change', () => {
      const val = parseInt(countInput.value, 10);
      if (val >= 1 && val <= 144) {
        this.sequentialCount = val;
      } else {
        countInput.value = String(this.sequentialCount);
      }
    });

    const plusBtn = document.createElement('button');
    plusBtn.type = 'button';
    plusBtn.className = 'btn btn-sm btn-outline-secondary';
    plusBtn.textContent = '+';
    plusBtn.addEventListener('click', () => this.adjustCount(1));

    this.countContainer.appendChild(minusBtn);
    this.countContainer.appendChild(countInput);
    this.countContainer.appendChild(plusBtn);

    if (this.saveBtn.parentNode) {
      this.saveBtn.parentNode.insertBefore(this.countContainer, this.saveBtn.nextSibling);
    }
  }

  private adjustCount(delta: number): void {
    const newVal = Math.max(1, Math.min(144, this.sequentialCount + delta));
    this.sequentialCount = newVal;
    const input = this.countContainer?.querySelector('input');
    if (input) (input as HTMLInputElement).value = String(newVal);
  }

  private updateCountSelector(): void {
    if (!this.countContainer) return;
    if (this.mode === 'sequential') {
      this.countContainer.classList.remove('d-none');
      this.countContainer.style.display = 'inline-flex';
    } else {
      this.countContainer.classList.add('d-none');
      this.countContainer.style.display = 'none';
    }
  }

  private setupBeforeUnload(): void {
    window.addEventListener('beforeunload', (e) => {
      if (this.state.hasPendingChanges()) {
        e.preventDefault();
      }
    });
  }

  handleStrandClick(node: LayoutNode, side: 'left' | 'right'): void {
    if (!node.id || !node.frontPortId) return;

    if (this.mode === 'delete') {
      this.handleDeleteClick(node);
      return;
    }

    if (this.mode === 'single') {
      this.handleSingleClick(node, side);
      return;
    }

    if (this.mode === 'sequential') {
      this.handleSequentialClick(node, side);
    }
  }

  private handleSingleClick(node: LayoutNode, side: 'left' | 'right'): void {
    if (!this.selected) {
      this.selected = { id: node.id!, side, portId: node.frontPortId! };
      this.setStatus(`Selected ${node.label}. Click another strand to splice.`);
      this.renderer.render();
    } else if (this.selected.id === node.id) {
      this.clearSelection();
      this.setStatus('Selection cleared.');
    } else {
      this.state.addPendingSplice(
        this.selected.id, node.id!,
        this.selected.portId, node.frontPortId!,
      );
      this.clearSelection();
      this.updateSaveButton();
      this.renderer.render();
      this.setStatus('Pending splice added. Click Save to commit.');
    }
  }

  private handleSequentialClick(node: LayoutNode, side: 'left' | 'right'): void {
    if (!this.selected) {
      this.selected = { id: node.id!, side, portId: node.frontPortId! };
      this.setStatus(`Sequential start: ${node.label}. Click another strand.`);
      this.renderer.render();
    } else if (this.selected.id === node.id) {
      this.clearSelection();
      this.setStatus('Selection cleared.');
    } else {
      const startStrands = this.state.getVisibleStrandsInTubeFrom(this.selected.side, this.selected.id);
      const endStrands = this.state.getVisibleStrandsInTubeFrom(side, node.id!);
      const count = Math.min(this.sequentialCount, startStrands.length, endStrands.length);
      let created = 0;

      for (let i = 0; i < count; i++) {
        const a = startStrands[i];
        const b = endStrands[i];
        if (a.id && b.id && a.frontPortId && b.frontPortId) {
          this.state.addPendingSplice(a.id, b.id, a.frontPortId, b.frontPortId);
          created++;
        }
      }

      this.clearSelection();
      this.updateSaveButton();
      this.renderer.render();

      if (created < this.sequentialCount) {
        this.setStatus(`Spliced ${created} of ${this.sequentialCount} requested (not enough strands).`);
      } else {
        this.setStatus(`${created} sequential splices added. Click Save to commit.`);
      }
    }
  }

  private handleDeleteClick(node: LayoutNode): void {
    // Find existing splice involving this strand
    const entry = this.state.spliceEntries.find(
      (e) => e.sourceId === node.id || e.targetId === node.id,
    );
    if (entry) {
      // Need front port IDs for the pending change
      const sourceNode = this.findStrandNode(entry.sourceId);
      const targetNode = this.findStrandNode(entry.targetId);
      if (sourceNode?.frontPortId && targetNode?.frontPortId) {
        this.state.removePendingSplice(
          entry.sourceId, entry.targetId,
          sourceNode.frontPortId, targetNode.frontPortId,
        );
        this.updateSaveButton();
        this.renderer.render();
        this.setStatus('Pending delete added. Click Save to commit.');
      }
    }
  }

  handleSpliceClick(entry: SpliceEntry): void {
    if (this.mode !== 'delete') return;
    const sourceNode = this.findStrandNode(entry.sourceId);
    const targetNode = this.findStrandNode(entry.targetId);
    if (sourceNode?.frontPortId && targetNode?.frontPortId) {
      this.state.removePendingSplice(
        entry.sourceId, entry.targetId,
        sourceNode.frontPortId, targetNode.frontPortId,
      );
      this.updateSaveButton();
      this.renderer.render();
      this.setStatus('Pending delete added. Click Save to commit.');
    }
  }

  private findStrandNode(strandId: number): LayoutNode | undefined {
    return [...this.state.leftNodes, ...this.state.rightNodes].find(
      (n) => n.type === 'strand' && n.id === strandId,
    );
  }

  updateSaveButton(): void {
    if (!this.saveBtn) return;
    if (this.state.hasPendingChanges()) {
      this.saveBtn.classList.remove('d-none');
    } else {
      this.saveBtn.classList.add('d-none');
    }
  }

  setStatus(msg: string): void {
    if (this.statusEl) this.statusEl.textContent = msg;
  }

  clearSelection(): void {
    this.selected = null;
  }
}
