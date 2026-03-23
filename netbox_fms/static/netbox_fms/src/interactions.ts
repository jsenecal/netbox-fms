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
  private saveBtn: HTMLButtonElement | null = null;
  private deleteBtn: HTMLButtonElement | null = null;
  private undoBtn: HTMLButtonElement | null = null;
  private redoBtn: HTMLButtonElement | null = null;
  private countContainer: HTMLElement | null = null;
  private _statusMessage = '';

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

    this.setupToolbar();
    this.setupBeforeUnload();
  }

  private setupToolbar(): void {
    // Save button (created by splice-editor.ts)
    this.saveBtn = document.getElementById('splice-save-btn') as HTMLButtonElement | null;
    if (this.saveBtn) {
      this.saveBtn.addEventListener('click', () => this.onSave());
    }

    // Undo / Redo buttons (created by splice-editor.ts)
    this.undoBtn = document.getElementById('splice-undo-btn') as HTMLButtonElement | null;
    this.redoBtn = document.getElementById('splice-redo-btn') as HTMLButtonElement | null;
    if (this.undoBtn) {
      this.undoBtn.addEventListener('click', () => {
        this.state.undo();
        this.updateToolbarState();
        this.renderer.render();
        this.setStatus('Undone.');
      });
    }
    if (this.redoBtn) {
      this.redoBtn.addEventListener('click', () => {
        this.state.redo();
        this.updateToolbarState();
        this.renderer.render();
        this.setStatus('Redone.');
      });
    }

    // Delete button (deletes selected splices)
    this.deleteBtn = document.getElementById('splice-delete-btn') as HTMLButtonElement | null;
    if (this.deleteBtn) {
      this.deleteBtn.addEventListener('click', () => {
        const count = this.state.deleteSelectedSplices();
        if (count > 0) {
          this.updateToolbarState();
          this.renderer.render();
          this.setStatus(`${count} splice(s) marked for deletion. Save to apply.`);
        }
      });
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault();
        this.undoBtn?.click();
      } else if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
        e.preventDefault();
        this.redoBtn?.click();
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        if (this.state.selectedSpliceKeys.size > 0) {
          e.preventDefault();
          this.deleteBtn?.click();
        }
      } else if (e.key === 'Escape') {
        this.state.clearSpliceSelection();
        this.clearSelection();
        this.updateToolbarState();
        this.renderer.render();
        this.setStatus('Selection cleared.');
      }
    });

    // Sequential count selector (injected dynamically next to delete button)
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

    // Insert after the delete button so they don't overlap
    const deleteEl = document.getElementById('splice-delete-btn');
    if (deleteEl && deleteEl.parentNode) {
      deleteEl.parentNode.insertBefore(this.countContainer, deleteEl.nextSibling);
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

  /** Set the splice mode (called from pill group in splice-editor.ts). */
  setMode(mode: ActionMode): void {
    this.mode = mode;
    this.clearSelection();
    this.setStatus(`Mode: ${this.mode}`);
    this.updateCountSelector();
  }

  handleStrandClick(node: LayoutNode, side: 'left' | 'right'): void {
    if (!node.id || !node.frontPortId) return;

    // Block interaction with protected strands
    if (node.isProtected) {
      this.setStatus(`${node.label} is protected by circuit "${node.circuitName}" and cannot be modified.`);
      return;
    }

    // If strand is in a pending-add, only block it as a target (second click).
    // As a first click (no selection yet), allow it — user is replacing.
    if (this.state.isStrandPendingAdd(node.id) && this.selected) {
      this.setStatus(`${node.label} is already in a pending splice.`);
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
      // If this strand is in a pending-add, undo it first (user is re-splicing)
      if (this.state.isStrandPendingAdd(node.id!)) {
        this.state.undoPendingAddForStrand(node.id!);
        this.updateSaveButton();
      }
      this.selected = { id: node.id!, side, portId: node.frontPortId! };
      this.state.selectedStrandId = node.id!;
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
      this.state.selectedStrandId = node.id!;
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

      let skipped = 0;
      for (let i = 0; i < count; i++) {
        const a = startStrands[i];
        const b = endStrands[i];
        if (a.id && b.id && a.frontPortId && b.frontPortId) {
          if (this.state.isStrandPendingAdd(a.id) || this.state.isStrandPendingAdd(b.id)) {
            skipped++;
            continue;
          }
          this.state.addPendingSplice(a.id, b.id, a.frontPortId, b.frontPortId);
          created++;
        }
      }

      this.clearSelection();
      this.updateSaveButton();
      this.renderer.render();

      if (skipped > 0) {
        this.setStatus(`${created} splices added, ${skipped} skipped (already pending).`);
      } else if (created < this.sequentialCount) {
        this.setStatus(`Spliced ${created} of ${this.sequentialCount} requested (not enough strands).`);
      } else {
        this.setStatus(`${created} sequential splices added. Click Save to commit.`);
      }
    }
  }

  handleSpliceClick(entry: SpliceEntry): void {
    // Toggle selection on the clicked line
    this.state.toggleSpliceSelection(entry.sourceId, entry.targetId);
    const selCount = this.state.selectedSpliceKeys.size;
    this.updateToolbarState();
    this.renderer.render();
    if (selCount > 0) {
      this.setStatus(`${selCount} splice(s) selected. Press Delete to remove.`);
    } else {
      this.setStatus('Selection cleared.');
    }
  }

  updateSaveButton(): void {
    this.updateToolbarState();
  }

  private updateToolbarState(): void {
    if (this.saveBtn) {
      if (this.state.hasPendingChanges()) {
        this.saveBtn.classList.remove('d-none');
      } else {
        this.saveBtn.classList.add('d-none');
      }
    }
    if (this.undoBtn) this.undoBtn.disabled = !this.state.canUndo();
    if (this.redoBtn) this.redoBtn.disabled = !this.state.canRedo();
    if (this.deleteBtn) this.deleteBtn.disabled = this.state.selectedSpliceKeys.size === 0;
  }

  setStatus(msg: string): void {
    this._statusMessage = msg;
    // The stats bar flash is handled by the splice-editor.ts override
  }

  clearSelection(): void {
    this.selected = null;
    this.state.selectedStrandId = null;
  }
}
