import type { TraceConfig, TraceResponse } from './trace-types';
import { TraceRenderer } from './trace-renderer';

declare const d3: typeof import('d3');
declare const htmx: any;

const config = (window as unknown as { TRACE_VIEW_CONFIG?: TraceConfig }).TRACE_VIEW_CONFIG;
console.log('[trace-view] config:', config);
if (config) {
  initTraceView(config);
}

let activeRenderer: TraceRenderer | null = null;

async function initTraceView(config: TraceConfig): Promise<void> {
  const container = document.getElementById('trace-canvas-container');
  if (!container) return;

  // Wait for tab activation before initializing
  const tabBtn = document.getElementById('trace-tab-btn');
  console.log('[trace-view] tabBtn:', tabBtn, 'hash:', window.location.hash);
  if (tabBtn) {
    tabBtn.addEventListener('shown.bs.tab', () => {
      console.log('[trace-view] shown.bs.tab fired, calling loadAndRender');
      loadAndRender();
    }, { once: true });
    // If trace tab is directly activated via URL hash
    if (window.location.hash === '#trace') {
      console.log('[trace-view] clicking tab for #trace hash');
      tabBtn.click();
    }
  } else {
    console.log('[trace-view] no tabBtn, calling loadAndRender directly');
    await loadAndRender();
  }

  async function loadAndRender(): Promise<void> {
    console.log('[trace-view] loadAndRender called, fetching:', config.traceUrl);
    try {
      const resp = await fetch(config.traceUrl, {
        headers: { 'Accept': 'application/json' },
      });
      console.log('[trace-view] fetch response:', resp.status);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data: TraceResponse = await resp.json();
      console.log('[trace-view] data:', data.hops.length, 'hops, container width:', container.clientWidth);

      // Clear loading spinner safely
      while (container.firstChild) {
        container.removeChild(container.firstChild);
      }

      if (data.hops.length === 0) {
        const msg = document.createElement('div');
        msg.className = 'trace-loading';
        const p = document.createElement('p');
        p.className = 'text-muted';
        p.textContent = 'No trace data available';
        msg.appendChild(p);
        container.appendChild(msg);
        return;
      }

      activeRenderer = new TraceRenderer(container, data, config);
      activeRenderer.render();
    } catch (err) {
      while (container.firstChild) {
        container.removeChild(container.firstChild);
      }
      const msg = document.createElement('div');
      msg.className = 'trace-loading';
      const p = document.createElement('p');
      p.className = 'text-danger';
      p.textContent = 'Error: ' + (err as Error).message;
      msg.appendChild(p);
      container.appendChild(msg);
    }
  }
}

/** Called from HTMX back button in sidebar templates. */
export function deselectNode(): void {
  const panel = document.getElementById('trace-detail-panel');
  if (panel) {
    const wrapper = document.createElement('div');
    wrapper.className = 'trace-sidebar-empty';
    const p = document.createElement('p');
    p.textContent = 'Click a node to view details';
    wrapper.appendChild(p);
    while (panel.firstChild) {
      panel.removeChild(panel.firstChild);
    }
    panel.appendChild(wrapper);
  }
  document.dispatchEvent(new CustomEvent('trace:deselect'));
}
