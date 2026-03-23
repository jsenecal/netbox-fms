import { bulkUpdatePlan, fetchStrands } from './api';
import { FmsLegend, FmsDetailPanel, FmsStatsBar, createPillGroup, createSeparator, createSpacer } from './components';
import { Interactions } from './interactions';
import { showQuickAddModal } from './modal';
import { SpliceRenderer } from './renderer';
import { EditorState } from './state';
import type { DetailCard, EditorConfig, LayoutNode, SpliceEntry } from './types';

declare const d3: typeof import('d3');

const config = (window as unknown as { SPLICE_EDITOR_CONFIG: EditorConfig }).SPLICE_EDITOR_CONFIG;
if (config) {
  init(config);
}

/** Create a button element with an MDI icon and optional label text. */
function createIconButton(id: string, iconClass: string, label: string, className: string): HTMLButtonElement {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.id = id;
  btn.className = className;
  const icon = document.createElement('i');
  icon.className = iconClass;
  btn.appendChild(icon);
  if (label) {
    btn.appendChild(document.createTextNode(` ${label}`));
  }
  return btn;
}

async function init(config: EditorConfig): Promise<void> {
  const canvasContainer = document.getElementById('splice-canvas-container');
  const toolbarEl = document.getElementById('fms-toolbar');
  const statsBarEl = document.getElementById('fms-stats-bar');
  if (!canvasContainer) return;

  const state = new EditorState();

  // -----------------------------------------------------------------------
  // Visual components
  // -----------------------------------------------------------------------
  const legend = new FmsLegend(canvasContainer);
  const detailPanel = new FmsDetailPanel(canvasContainer.parentElement!);
  const statsBar = statsBarEl ? new FmsStatsBar(statsBarEl) : null;

  // -----------------------------------------------------------------------
  // Build toolbar contents
  // -----------------------------------------------------------------------
  if (toolbarEl) {
    // Mode pill group
    const modePills = createPillGroup(
      [
        { id: 'single', label: 'Single', active: true },
        { id: 'sequential', label: 'Sequential' },
      ],
      (id) => {
        interactions.setMode(id as 'single' | 'sequential');
      },
    );
    // Insert at the beginning (before the back button if present)
    toolbarEl.insertBefore(modePills, toolbarEl.firstChild);

    toolbarEl.insertBefore(createSeparator(), modePills.nextSibling);

    // Action buttons — create with IDs that interactions.ts expects
    const backBtn = toolbarEl.querySelector('#splice-back-btn');

    const deleteBtn = createIconButton('splice-delete-btn', 'mdi mdi-delete', 'Delete', 'btn btn-sm btn-outline-danger');
    deleteBtn.disabled = true;
    deleteBtn.title = 'Delete selected splices';
    toolbarEl.insertBefore(deleteBtn, backBtn);

    // Spacer pushes right-side buttons
    const spacer = createSpacer();
    toolbarEl.insertBefore(spacer, backBtn);

    // Undo button
    const undoBtn = createIconButton('splice-undo-btn', 'mdi mdi-undo', '', 'btn btn-sm btn-outline-secondary');
    undoBtn.disabled = true;
    undoBtn.title = 'Undo (Ctrl+Z)';
    toolbarEl.insertBefore(undoBtn, backBtn);

    // Redo button
    const redoBtn = createIconButton('splice-redo-btn', 'mdi mdi-redo', '', 'btn btn-sm btn-outline-secondary');
    redoBtn.disabled = true;
    redoBtn.title = 'Redo (Ctrl+Y)';
    toolbarEl.insertBefore(redoBtn, backBtn);

    // Save button
    const saveBtn = createIconButton('splice-save-btn', 'mdi mdi-content-save', 'Save', 'btn btn-sm btn-success d-none');
    toolbarEl.insertBefore(saveBtn, backBtn);
  }

  // -----------------------------------------------------------------------
  // Renderer + interactions
  // -----------------------------------------------------------------------
  const renderer = new SpliceRenderer(
    state,
    canvasContainer,
    (node: LayoutNode, side: 'left' | 'right') => {
      interactions.handleStrandClick(node, side);
      showStrandDetail(node);
    },
    (entry: SpliceEntry) => {
      interactions.handleSpliceClick(entry);
      showSpliceDetail(entry);
    },
    (node: LayoutNode, nodes: LayoutNode[]) => {
      node.collapsed = !node.collapsed;
      state.recalcPositions(nodes);
      renderer.render();
      updateAfterRender();
    },
  );

  const interactions = new Interactions(state, renderer, config, handleSave);

  // Wire detail panel close to clear selection highlight
  detailPanel.setOnClose(() => {
    // No-op — selection is managed by interactions
  });

  // Cable move callback with fade animation
  renderer.setOnCableMove((cableId: number) => {
    const svg = canvasContainer.querySelector('svg');
    if (svg) {
      d3.select(svg).transition().duration(150).style('opacity', 0.3)
        .on('end', () => {
          state.moveCable(cableId);
          renderer.render();
          updateAfterRender();
          d3.select(svg).transition().duration(200).style('opacity', 1);
        });
    } else {
      state.moveCable(cableId);
      renderer.render();
      updateAfterRender();
    }
  });

  // Override interactions.setStatus to also flash the stats bar
  const origSetStatus = interactions.setStatus.bind(interactions);
  interactions.setStatus = (msg: string) => {
    origSetStatus(msg);
    statsBar?.flash(msg);
  };

  // Load initial data
  await loadData();

  // Resize handler
  let resizeTimer: ReturnType<typeof setTimeout>;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => renderer.handleResize(), 150);
  });

  // Theme change handler — re-render when dark/light mode toggles
  const observer = new MutationObserver((mutations) => {
    for (const m of mutations) {
      if (m.attributeName === 'data-bs-theme') {
        renderer.render();
        updateAfterRender();
        break;
      }
    }
  });
  observer.observe(document.body, { attributes: true, attributeFilter: ['data-bs-theme'] });

  // -----------------------------------------------------------------------
  // Helpers
  // -----------------------------------------------------------------------

  function updateAfterRender(): void {
    legend.update(state.buildLegendSections());
    if (statsBar) {
      const stats = state.computeStats();
      // Overlay plan info from config
      if (config.planId) {
        stats.planStatus = config.planStatus || null;
      }
      statsBar.update(stats);
    }
  }

  function showStrandDetail(node: LayoutNode): void {
    if (!node.id) return;
    const strand = state.getStrand(node.id);
    if (!strand) return;

    const cards: DetailCard[] = [];

    // Properties card
    const propRows: DetailCard['rows'] = [
      { label: 'Name', value: strand.name },
      { label: 'Tube', value: strand.tube_name || 'Loose', color: strand.tube_color ? `#${strand.tube_color}` : undefined },
      { label: 'Color', value: strand.color, color: `#${strand.color}` },
    ];
    if (strand.ribbon_name) {
      propRows.push({ label: 'Ribbon', value: strand.ribbon_name, color: strand.ribbon_color ? `#${strand.ribbon_color}` : undefined });
    }
    if (strand.front_port_a_id) {
      propRows.push({ label: 'Front Port', value: `FP-${strand.front_port_a_id}` });
    }
    cards.push({ heading: 'Properties', rows: propRows });

    // Splice info card
    const spliceRows: DetailCard['rows'] = [];
    if (strand.live_spliced_to) {
      const target = state.getStrand(strand.live_spliced_to);
      spliceRows.push({ label: 'Live splice', value: target?.name || `#${strand.live_spliced_to}`, badge: 'active' });
    }
    if (strand.plan_spliced_to) {
      const target = state.getStrand(strand.plan_spliced_to);
      spliceRows.push({ label: 'Planned splice', value: target?.name || `#${strand.plan_spliced_to}`, badge: 'info' });
    }
    const pendingState = state.getStrandPendingState(node.id);
    if (pendingState) {
      spliceRows.push({ label: 'Pending', value: pendingState, badge: pendingState === 'add' ? 'warning' : 'danger' });
    }
    if (spliceRows.length > 0) {
      cards.push({ heading: 'Splice Status', rows: spliceRows });
    }

    // Circuit info card
    if (strand.protected && strand.circuit_name) {
      const circuitRows: DetailCard['rows'] = [
        { label: 'Circuit', value: strand.circuit_name, link: strand.circuit_url || undefined },
        { label: 'Protected', value: 'Yes', badge: 'danger' },
      ];
      cards.push({ heading: 'Circuit', rows: circuitRows });
    }

    detailPanel.show('Strand Details', cards);
  }

  function showSpliceDetail(entry: SpliceEntry): void {
    const sourceStrand = state.getStrand(entry.sourceId);
    const targetStrand = state.getStrand(entry.targetId);
    if (!sourceStrand || !targetStrand) return;

    const cards: DetailCard[] = [];

    const infoRows: DetailCard['rows'] = [
      { label: 'Source', value: sourceStrand.name, color: `#${sourceStrand.color}` },
      { label: 'Target', value: targetStrand.name, color: `#${targetStrand.color}` },
    ];
    if (entry.isLive) {
      infoRows.push({ label: 'Status', value: 'Live', badge: 'active' });
    }
    if (entry.isPlan) {
      infoRows.push({ label: 'Status', value: 'Planned', badge: 'info' });
    }
    if (state.isSplicePendingDelete(entry.sourceId, entry.targetId)) {
      infoRows.push({ label: 'Pending', value: 'Delete', badge: 'danger' });
    }
    cards.push({ heading: 'Splice', rows: infoRows });

    detailPanel.show('Splice Details', cards);
  }

  async function loadData(): Promise<void> {
    try {
      const response = await fetchStrands(config);
      state.loadCableGroups(response.cables, response.trays);
      renderer.render();
      updateAfterRender();

      // Build tray filter pills in toolbar if trays exist
      if (toolbarEl && response.trays.length > 0) {
        // Remove existing tray filter if any
        const existingFilter = toolbarEl.querySelector('.fms-pill-filter');
        if (existingFilter) existingFilter.remove();

        const { createPillFilter } = await import('./components');
        const allItems = [
          { id: 'all', label: 'All Trays', color: '#6c757d', on: true },
          ...response.trays.map((t) => ({
            id: String(t.id),
            label: `${t.name}`,
            color: t.role === 'splice_tray' ? '#0d6efd' : '#6c757d',
            on: false,
          })),
        ];
        const trayPills = createPillFilter(allItems, (id, on) => {
          if (id === 'all') {
            state.setTrayFilter(null);
          } else if (on) {
            state.setTrayFilter(parseInt(id));
          } else {
            state.setTrayFilter(null);
          }
          renderer.render();
          updateAfterRender();
        });
        // Insert after the first separator
        const sep = toolbarEl.querySelector('.fms-separator');
        if (sep && sep.nextSibling) {
          toolbarEl.insertBefore(trayPills, sep.nextSibling);
        } else {
          toolbarEl.appendChild(trayPills);
        }
      }

      interactions.setStatus(
        `Loaded ${response.cables.length} cable(s). Click strands to splice.`,
      );
    } catch (err) {
      interactions.setStatus(`Error: ${(err as Error).message}`);
    }
  }

  async function handleSave(): Promise<void> {
    if (!state.hasPendingChanges()) return;

    if (config.contextMode === 'view' && !config.planId) {
      const result = await showQuickAddModal(config);
      if (!result) return;

      config.planId = result.id;
      config.contextMode = 'edit';
      config.bulkUpdateUrl = config.quickAddApiUrl.replace(
        'quick-add/',
        `${result.id}/bulk-update/`,
      );

      await savePendingChanges();
    } else {
      await savePendingChanges();
    }
  }

  async function savePendingChanges(): Promise<void> {
    try {
      const payload = state.getPendingPayload();
      await bulkUpdatePlan(config, payload);
      state.clearPending();
      interactions.updateSaveButton();
      interactions.setStatus('Changes saved successfully.');
      await loadData();
    } catch (err) {
      interactions.setStatus(`Save error: ${(err as Error).message}`);
    }
  }
}
