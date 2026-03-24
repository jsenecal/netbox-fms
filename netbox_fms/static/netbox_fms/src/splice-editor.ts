import { bulkUpdatePlan, fetchStrands } from './api';
import { FmsLegend, FmsDetailPanel, FmsStatsBar, createPillGroup, createPillFilter, createSeparator, createSpacer } from './components';
import { Interactions } from './interactions';
import { showQuickAddModal } from './modal';
import { SpliceRenderer } from './renderer';
import { EditorState } from './state';
import type { DetailCard, EditorConfig, LayoutNode, SpliceEntry } from './types';

declare const d3: typeof import('d3');

const config = (window as unknown as { SPLICE_EDITOR_CONFIG: EditorConfig }).SPLICE_EDITOR_CONFIG;

/** Debug logger — only logs when config.debug is true. */
function dbg(...args: unknown[]): void {
  if (config?.debug) {
    console.log('[SpliceEditor]', ...args);
  }
}

if (config) {
  dbg('Config loaded:', JSON.stringify(config, null, 2));
  init(config);
} else {
  console.error('[SpliceEditor] No SPLICE_EDITOR_CONFIG found on window');
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
  dbg('init() starting');
  const canvasContainer = document.getElementById('splice-canvas-container');
  const toolbarEl = document.getElementById('fms-toolbar');
  const statsBarEl = document.getElementById('fms-stats-bar');
  dbg('DOM elements:', { canvasContainer: !!canvasContainer, toolbarEl: !!toolbarEl, statsBarEl: !!statsBarEl });
  if (!canvasContainer) {
    dbg('ERROR: #splice-canvas-container not found, aborting');
    return;
  }

  // Track plan version for optimistic locking
  let planVersion: string | null = null;

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

    // Splice visibility filter pills
    const visFilterSep = createSeparator();
    toolbarEl.insertBefore(visFilterSep, backBtn);

    const visFilterPills = createPillFilter(
      [
        { id: 'live', label: 'Live', color: 'var(--fms-live)', on: true },
        { id: 'planned', label: 'Planned', color: 'var(--fms-planned)', on: true },
        { id: 'unspliced', label: 'Unspliced', color: 'var(--fms-muted)', on: true },
      ],
      (id, on) => {
        if (id === 'live') state.showLive = on;
        else if (id === 'planned') state.showPlanned = on;
        else if (id === 'unspliced') state.showUnspliced = on;
        renderer.render();
        updateAfterRender();
      },
    );
    toolbarEl.insertBefore(visFilterPills, backBtn);

    const deleteSep = createSeparator();
    toolbarEl.insertBefore(deleteSep, backBtn);

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

    // Save split button (Save + dropdown with Save & Apply)
    const saveBtnGroup = document.createElement('div');
    saveBtnGroup.className = 'btn-group d-none';
    saveBtnGroup.id = 'splice-save-group';

    const saveBtn = document.createElement('button');
    saveBtn.type = 'button';
    saveBtn.id = 'splice-save-btn';
    saveBtn.className = 'btn btn-sm btn-success';
    saveBtn.innerHTML = '<i class="mdi mdi-content-save"></i> Save';
    saveBtnGroup.appendChild(saveBtn);

    const dropdownToggle = document.createElement('button');
    dropdownToggle.type = 'button';
    dropdownToggle.className = 'btn btn-sm btn-success dropdown-toggle dropdown-toggle-split';
    dropdownToggle.dataset.bsToggle = 'dropdown';
    dropdownToggle.setAttribute('aria-expanded', 'false');
    const srText = document.createElement('span');
    srText.className = 'visually-hidden';
    srText.textContent = 'Toggle Dropdown';
    dropdownToggle.appendChild(srText);
    saveBtnGroup.appendChild(dropdownToggle);

    const dropdownMenu = document.createElement('ul');
    dropdownMenu.className = 'dropdown-menu dropdown-menu-end';
    const applyItem = document.createElement('li');
    const applyLink = document.createElement('a');
    applyLink.className = 'dropdown-item';
    applyLink.href = '#';
    applyLink.id = 'splice-save-apply-btn';
    applyLink.innerHTML = '<i class="mdi mdi-check-circle"></i> Save &amp; Apply';
    applyItem.appendChild(applyLink);
    dropdownMenu.appendChild(applyItem);
    saveBtnGroup.appendChild(dropdownMenu);

    toolbarEl.insertBefore(saveBtnGroup, backBtn);
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
    (entry: SpliceEntry, event: MouseEvent) => {
      interactions.handleSpliceClick(entry, event);
      showSelectedSplicesDetail();
    },
    (node: LayoutNode, nodes: LayoutNode[]) => {
      node.collapsed = !node.collapsed;
      state.recalcPositions(nodes);
      renderer.render();
      updateAfterRender();
    },
  );

  const interactions = new Interactions(state, renderer, config, handleSave);

  // Wire detail panel close
  detailPanel.setOnClose(() => {
    // ResizeObserver handles the re-render
  });

  // Use ResizeObserver on the canvas container to smoothly re-render
  // when the detail panel opens/closes (animating via CSS transition).
  let resizeRafId: ReturnType<typeof requestAnimationFrame> | null = null;
  const resizeObserver = new ResizeObserver(() => {
    if (resizeRafId !== null) cancelAnimationFrame(resizeRafId);
    resizeRafId = requestAnimationFrame(() => {
      renderer.render();
      resizeRafId = null;
    });
  });
  resizeObserver.observe(canvasContainer);

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

  // Override interactions.setStatus to show messages in the stats bar right section
  const origSetStatus = interactions.setStatus.bind(interactions);
  interactions.setStatus = (msg: string) => {
    origSetStatus(msg);
    statsBar?.setMessage(msg, 3000);
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
      if (config.planId) {
        stats.planName = config.planId ? 'Splice Plan' : null;
        stats.planStatus = config.planStatus || null;
      }
      statsBar.update(stats);
    }
    // Set editor row height to match SVG canvas so detail panel scrolls within it
    const editorRow = document.getElementById('splice-editor-row');
    const svg = canvasContainer!.querySelector('svg');
    if (editorRow && svg) {
      const svgHeight = svg.getAttribute('height');
      if (svgHeight) {
        const h = parseInt(svgHeight, 10);
        if (h > 0) {
          editorRow.style.maxHeight = h + 'px';
          editorRow.style.minHeight = Math.min(h, 500) + 'px';
        }
      }
    }
  }

  function showStrandDetail(node: LayoutNode): void {
    if (!node.id) return;
    const strand = state.getStrand(node.id);
    if (!strand) return;

    const cards: DetailCard[] = [];
    const ctx = state.findStrandContext(node.id);

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

    // Cable info card
    if (ctx) {
      const cableRows: DetailCard['rows'] = [
        { label: 'Cable', value: ctx.cable.cable_label },
      ];
      if (ctx.cable.far_device_name) {
        cableRows.push({
          label: 'Far End',
          value: ctx.cable.far_device_name,
          link: ctx.cable.far_device_url || undefined,
        });
      }
      cards.push({ heading: 'Cable', rows: cableRows });
    }

    // Tray info card
    if (ctx?.tube?.tray_assignment) {
      const trayRows: DetailCard['rows'] = [
        { label: 'Tray', value: ctx.tube.tray_assignment.tray_name },
      ];
      cards.push({ heading: 'Tray', rows: trayRows });
    }

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
    if (strand.circuit_name) {
      const circuitRows: DetailCard['rows'] = [
        { label: 'Circuit', value: strand.circuit_name, link: strand.circuit_url || undefined },
      ];
      if (strand.protected) {
        circuitRows.push({ label: 'Protected', value: 'Yes', badge: 'danger' });
      }
      cards.push({ heading: 'Circuit', rows: circuitRows });
    }

    detailPanel.show('Strand Details', cards);
  }

  /** Build full detail cards for a single splice entry (splice info + source/target context with links). */
  function buildSpliceCards(entry: SpliceEntry): DetailCard[] {
    const sourceStrand = state.getStrand(entry.sourceId);
    const targetStrand = state.getStrand(entry.targetId);
    if (!sourceStrand || !targetStrand) return [];

    const cards: DetailCard[] = [];

    // Splice info card
    const infoRows: DetailCard['rows'] = [
      { label: 'Source', value: sourceStrand.name, color: `#${sourceStrand.color}` },
      { label: 'Target', value: targetStrand.name, color: `#${targetStrand.color}` },
    ];
    if (entry.isLive) infoRows.push({ label: 'Status', value: 'Live', badge: 'live' });
    if (entry.isPlan && !entry.isLive) infoRows.push({ label: 'Status', value: 'Planned', badge: 'planned' });
    if (entry.isLive && entry.isPlan) infoRows.push({ label: 'Status', value: 'Live + Planned', badge: 'live' });
    if (state.isSplicePendingDelete(entry.sourceId, entry.targetId)) {
      infoRows.push({ label: 'Pending', value: 'Delete', badge: 'protected' });
    }
    cards.push({ heading: 'Splice', rows: infoRows });

    // Source context card
    const srcCtx = state.findStrandContext(entry.sourceId);
    if (srcCtx) {
      const srcRows: DetailCard['rows'] = [
        { label: 'Cable', value: srcCtx.cable.cable_label, link: srcCtx.cable.cable_url },
      ];
      srcRows.push({ label: 'Tube', value: sourceStrand.tube_name || 'Loose', color: sourceStrand.tube_color ? `#${sourceStrand.tube_color}` : undefined });
      if (srcCtx.tube?.tray_assignment) {
        srcRows.push({ label: 'Tray', value: srcCtx.tube.tray_assignment.tray_name, link: srcCtx.tube.tray_assignment.tray_url });
      }
      if (sourceStrand.circuit_name) {
        srcRows.push({ label: 'Circuit', value: sourceStrand.circuit_name, link: sourceStrand.circuit_url || undefined });
      }
      if (srcCtx.cable.far_device_name) {
        srcRows.push({ label: 'Far end', value: srcCtx.cable.far_device_name, link: srcCtx.cable.far_device_url || undefined });
      }
      cards.push({ heading: `Source: ${sourceStrand.name}`, rows: srcRows });
    }

    // Target context card
    const tgtCtx = state.findStrandContext(entry.targetId);
    if (tgtCtx) {
      const tgtRows: DetailCard['rows'] = [
        { label: 'Cable', value: tgtCtx.cable.cable_label, link: tgtCtx.cable.cable_url },
      ];
      tgtRows.push({ label: 'Tube', value: targetStrand.tube_name || 'Loose', color: targetStrand.tube_color ? `#${targetStrand.tube_color}` : undefined });
      if (tgtCtx.tube?.tray_assignment) {
        tgtRows.push({ label: 'Tray', value: tgtCtx.tube.tray_assignment.tray_name, link: tgtCtx.tube.tray_assignment.tray_url });
      }
      if (targetStrand.circuit_name) {
        tgtRows.push({ label: 'Circuit', value: targetStrand.circuit_name, link: targetStrand.circuit_url || undefined });
      }
      if (tgtCtx.cable.far_device_name) {
        tgtRows.push({ label: 'Far end', value: tgtCtx.cable.far_device_name, link: tgtCtx.cable.far_device_url || undefined });
      }
      cards.push({ heading: `Target: ${targetStrand.name}`, rows: tgtRows });
    }

    return cards;
  }

  function showSelectedSplicesDetail(): void {
    const seenKeys = new Set<string>();
    const selectedEntries: SpliceEntry[] = [];
    for (const e of state.spliceEntries) {
      if (!state.isSpliceSelected(e.sourceId, e.targetId)) continue;
      const key = state.spliceKey(e.sourceId, e.targetId);
      if (seenKeys.has(key)) continue;
      seenKeys.add(key);
      selectedEntries.push(e);
    }

    if (selectedEntries.length === 0) {
      detailPanel.hide();
      return;
    }

    // Build full split detail cards for every selected splice, with separators between groups
    const allCards: DetailCard[] = [];
    for (let i = 0; i < selectedEntries.length; i++) {
      const cards = buildSpliceCards(selectedEntries[i]);
      if (i > 0 && cards.length > 0) {
        cards[0].separator = true;
      }
      allCards.push(...cards);
    }
    const title = selectedEntries.length === 1 ? 'Splice Details' : `${selectedEntries.length} Splices Selected`;
    detailPanel.show(title, allCards);
  }

  async function loadData(): Promise<void> {
    dbg('loadData() starting, url:', config.strandsUrl, 'planId:', config.planId);
    try {
      const response = await fetchStrands(config);
      dbg('loadData() response:', {
        cables: response.cables?.length ?? 'undefined',
        trays: response.trays?.length ?? 'undefined',
        plan_version: response.plan_version,
        responseKeys: Object.keys(response),
      });
      if (!response.cables) {
        dbg('ERROR: response.cables is falsy, full response:', response);
      }
      planVersion = response.plan_version;
      state.loadCableGroups(response.cables, response.trays);
      dbg('State after load:', {
        cableGroups: state.cableGroups.length,
        leftNodes: state.leftNodes.length,
        rightNodes: state.rightNodes.length,
        spliceEntries: state.spliceEntries.length,
      });
      renderer.render();
      updateAfterRender();

      // Build tray filter pills in toolbar if trays exist
      if (toolbarEl && response.trays.length > 0) {
        // Remove existing tray pill group if any
        const existingFilter = toolbarEl.querySelector('.fms-pill-group.fms-tray-pills');
        if (existingFilter) existingFilter.remove();

        const { createPillGroup: createTrayPillGroup } = await import('./components');
        const trayItems = [
          { id: 'all', label: 'All', active: true },
          ...response.trays.map((t) => {
            return { id: String(t.id), label: t.name };
          }),
        ];
        const trayPills = createTrayPillGroup(trayItems, (id) => {
          if (id === 'all') {
            state.setTrayFilter(null);
          } else {
            state.setTrayFilter(parseInt(id));
          }
          renderer.render();
          updateAfterRender();
        });
        trayPills.classList.add('fms-tray-pills');
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
      dbg('loadData() ERROR:', err);
      console.error('[SpliceEditor] loadData error:', err);
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

  async function savePendingChanges(andApply = false): Promise<void> {
    try {
      const payload = state.getPendingPayload();
      payload.plan_version = planVersion;
      const result = await bulkUpdatePlan(config, payload);
      planVersion = result.plan_version;
      state.clearPending();
      interactions.updateSaveButton();

      if (andApply && config.planId) {
        interactions.setStatus('Saved. Applying...');
        // POST to the apply endpoint (non-API URL)
        const applyUrl = `/plugins/fms/splice-plans/${config.planId}/apply/`;
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = applyUrl;
        const csrf = document.createElement('input');
        csrf.type = 'hidden';
        csrf.name = 'csrfmiddlewaretoken';
        csrf.value = config.csrfToken;
        form.appendChild(csrf);
        document.body.appendChild(form);
        form.submit();
        return;
      }

      interactions.setStatus('Changes saved successfully.');
      await loadData();
    } catch (err) {
      interactions.setStatus(`Save error: ${(err as Error).message}`);
    }
  }

  // Wire Save & Apply button
  const saveApplyBtn = document.getElementById('splice-save-apply-btn');
  if (saveApplyBtn) {
    saveApplyBtn.addEventListener('click', async (e) => {
      e.preventDefault();
      if (!state.hasPendingChanges()) return;
      await savePendingChanges(true);
    });
  }
}
