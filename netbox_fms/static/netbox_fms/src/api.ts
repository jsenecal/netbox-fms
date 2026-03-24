import type {
  BulkUpdatePayload,
  BulkUpdateResponse,
  EditorConfig,
  QuickAddResponse,
  StrandsApiResponse,
} from './types';

/** Fetch strand data for a device from ClosureStrandsAPIView. */
export async function fetchStrands(
  config: EditorConfig,
): Promise<StrandsApiResponse> {
  let url = config.strandsUrl;
  if (config.planId !== null) {
    const sep = url.includes('?') ? '&' : '?';
    url += `${sep}plan_id=${config.planId}`;
  }
  if (config.debug) console.log('[SpliceEditor:API] fetching:', url);
  const resp = await fetch(url);
  if (config.debug) console.log('[SpliceEditor:API] response status:', resp.status, 'content-type:', resp.headers.get('content-type'));
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  if (config.debug) console.log('[SpliceEditor:API] parsed JSON, type:', typeof data, 'isArray:', Array.isArray(data), 'keys:', data && typeof data === 'object' ? Object.keys(data) : 'N/A');
  return data;
}

/** Create a new splice plan via quick-add API. */
export async function quickAddPlan(
  config: EditorConfig,
  formData: FormData,
): Promise<QuickAddResponse> {
  const resp = await fetch(config.quickAddApiUrl, {
    method: 'POST',
    headers: { 'X-CSRFToken': config.csrfToken },
    body: formData,
  });
  if (!resp.ok) {
    const err = await resp.json();
    throw new Error(err.detail || err.error || `HTTP ${resp.status}`);
  }
  return resp.json();
}

/** Bulk-update splice plan entries (add/remove atomically). */
export async function bulkUpdatePlan(
  config: EditorConfig,
  payload: BulkUpdatePayload,
): Promise<BulkUpdateResponse> {
  if (!config.bulkUpdateUrl) {
    throw new Error('No bulk update URL — plan may not exist yet');
  }
  const resp = await fetch(config.bulkUpdateUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': config.csrfToken,
    },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const err = await resp.json();
    throw new Error(err.detail || err.error || `HTTP ${resp.status}`);
  }
  return resp.json();
}

/** Fetch quick-add form HTML from Django. */
export async function fetchQuickAddForm(
  config: EditorConfig,
): Promise<string> {
  const resp = await fetch(config.quickAddFormUrl);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.text();
}
