import type {
  BulkUpdatePayload,
  BulkUpdateResponse,
  EditorConfig,
  FiberClaim,
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
  changelogMessage?: string,
): Promise<BulkUpdateResponse> {
  if (!config.bulkUpdateUrl) {
    throw new Error('No bulk update URL — plan may not exist yet');
  }
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-CSRFToken': config.csrfToken,
  };
  if (changelogMessage) {
    headers['X-Changelog-Message'] = changelogMessage;
  }
  const resp = await fetch(config.bulkUpdateUrl, {
    method: 'POST',
    headers,
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

/** Fetch fiber claims from other plans on this closure. */
export async function fetchFiberClaims(
  deviceId: number,
  excludePlanId: number | null,
): Promise<FiberClaim[]> {
  let url = `/api/plugins/fms/closures/${deviceId}/fiber-claims/`;
  if (excludePlanId !== null) {
    url += `?exclude_plan=${excludePlanId}`;
  }
  const resp = await fetch(url);
  if (!resp.ok) return [];
  return resp.json();
}
