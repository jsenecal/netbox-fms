import { bulkUpdatePlan, fetchStrands } from './api';
import { Interactions } from './interactions';
import { showQuickAddModal } from './modal';
import { SpliceRenderer } from './renderer';
import { EditorState } from './state';
import type { EditorConfig, LayoutNode, SpliceEntry } from './types';

declare const d3: typeof import('d3');

const config = (window as unknown as { SPLICE_EDITOR_CONFIG: EditorConfig }).SPLICE_EDITOR_CONFIG;
if (config) {
  init(config);
}

async function init(config: EditorConfig): Promise<void> {
  const containerEl = document.getElementById('splice-canvas-container');
  if (!containerEl) return;

  const state = new EditorState();

  const renderer = new SpliceRenderer(
    state,
    containerEl,
    (node: LayoutNode, side: 'left' | 'right') => interactions.handleStrandClick(node, side),
    (entry: SpliceEntry) => interactions.handleSpliceClick(entry),
    (node: LayoutNode, nodes: LayoutNode[]) => {
      node.collapsed = !node.collapsed;
      state.recalcPositions(nodes);
      renderer.render();
    },
  );

  const interactions = new Interactions(state, renderer, config, handleSave);

  // Cable move callback with fade animation
  renderer.setOnCableMove((cableId: number) => {
    const svg = containerEl.querySelector('svg');
    if (svg) {
      d3.select(svg).transition().duration(150).style('opacity', 0.3)
        .on('end', () => {
          state.moveCable(cableId);
          renderer.render();
          d3.select(svg).transition().duration(200).style('opacity', 1);
        });
    } else {
      state.moveCable(cableId);
      renderer.render();
    }
  });

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
        break;
      }
    }
  });
  observer.observe(document.body, { attributes: true, attributeFilter: ['data-bs-theme'] });

  async function loadData(): Promise<void> {
    try {
      const groups = await fetchStrands(config);
      state.loadCableGroups(groups);
      renderer.render();
      interactions.setStatus(
        `Loaded ${groups.length} cable(s). Click strands to splice.`,
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
