import type { TraceConfig, TraceResponse } from './trace-types';
import { TraceRenderer } from './trace-renderer';

declare const d3: typeof import('d3');

const config = (window as unknown as { TRACE_VIEW_CONFIG?: TraceConfig }).TRACE_VIEW_CONFIG;
if (config) {
  initTraceView(config);
}

let activeRenderer: TraceRenderer | null = null;

async function initTraceView(config: TraceConfig): Promise<void> {
  const container = document.getElementById('trace-canvas-container');
  if (!container) return;

  // Wait for tab activation before initializing
  const tabBtn = document.getElementById('trace-tab-btn');
  if (tabBtn) {
    tabBtn.addEventListener('shown.bs.tab', () => {
      loadAndRender();
    }, { once: true });
    // If trace tab is directly activated via URL hash
    if (window.location.hash === '#trace') {
      tabBtn.click();
    }
  } else {
    await loadAndRender();
  }

  async function loadAndRender(): Promise<void> {
    const el = container!;
    try {
      const resp = await fetch(config.traceUrl, {
        headers: { 'Accept': 'application/json' },
      });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data: TraceResponse = await resp.json();

      // Clear loading spinner safely
      while (el.firstChild) {
        el.removeChild(el.firstChild);
      }

      if (data.hops.length === 0) {
        const msg = document.createElement('div');
        msg.className = 'trace-loading';
        const p = document.createElement('p');
        p.className = 'text-muted';
        p.textContent = 'No trace data available';
        msg.appendChild(p);
        el.appendChild(msg);
        return;
      }

      activeRenderer = new TraceRenderer(el, data, config);
      activeRenderer.render();
    } catch (err) {
      while (el.firstChild) {
        el.removeChild(el.firstChild);
      }
      const msg = document.createElement('div');
      msg.className = 'trace-loading';
      const p = document.createElement('p');
      p.className = 'text-danger';
      p.textContent = 'Error: ' + (err as Error).message;
      msg.appendChild(p);
      el.appendChild(msg);
    }
  }
}
