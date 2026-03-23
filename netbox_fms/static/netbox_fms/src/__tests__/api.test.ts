import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fetchStrands, quickAddPlan, bulkUpdatePlan, fetchQuickAddForm } from '../api';
import type { EditorConfig } from '../types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeConfig(overrides: Partial<EditorConfig> = {}): EditorConfig {
  return {
    deviceId: 1,
    planId: null,
    contextMode: 'edit',
    planStatus: 'draft',
    strandsUrl: '/api/fms/strands/1/',
    bulkUpdateUrl: '/api/fms/splice-plans/1/bulk-update/',
    quickAddFormUrl: '/api/fms/splice-plans/quick-add-form/',
    quickAddApiUrl: '/api/fms/splice-plans/quick-add/',
    csrfToken: 'test-token',
    ...overrides,
  };
}

function mockFetchOk(data: unknown, contentType = 'json') {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(data as string),
  });
}

function mockFetchError(status: number, detail?: string) {
  return vi.fn().mockResolvedValue({
    ok: false,
    status,
    json: () => Promise.resolve(detail ? { detail } : {}),
  });
}

beforeEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// fetchStrands
// ---------------------------------------------------------------------------

describe('fetchStrands', () => {
  it('fetches from strandsUrl', async () => {
    const data = { cables: [{ fiber_cable_id: 1 }], trays: [] };
    vi.stubGlobal('fetch', mockFetchOk(data));

    const result = await fetchStrands(makeConfig());
    expect(result).toEqual(data);
    expect(fetch).toHaveBeenCalledWith('/api/fms/strands/1/');
  });

  it('appends plan_id when set', async () => {
    vi.stubGlobal('fetch', mockFetchOk({ cables: [], trays: [] }));

    await fetchStrands(makeConfig({ planId: 42 }));
    expect(fetch).toHaveBeenCalledWith('/api/fms/strands/1/?plan_id=42');
  });

  it('uses & separator when URL already has query params', async () => {
    vi.stubGlobal('fetch', mockFetchOk({ cables: [], trays: [] }));

    await fetchStrands(makeConfig({
      strandsUrl: '/api/fms/strands/1/?foo=bar',
      planId: 42,
    }));
    expect(fetch).toHaveBeenCalledWith('/api/fms/strands/1/?foo=bar&plan_id=42');
  });

  it('throws on HTTP error', async () => {
    vi.stubGlobal('fetch', mockFetchError(500));
    await expect(fetchStrands(makeConfig())).rejects.toThrow('HTTP 500');
  });
});

// ---------------------------------------------------------------------------
// quickAddPlan
// ---------------------------------------------------------------------------

describe('quickAddPlan', () => {
  it('posts FormData with CSRF token', async () => {
    const response = { id: 1, name: 'Plan', url: '/plans/1/' };
    vi.stubGlobal('fetch', mockFetchOk(response));

    const formData = new FormData();
    formData.append('name', 'Plan');
    const result = await quickAddPlan(makeConfig(), formData);

    expect(result).toEqual(response);
    expect(fetch).toHaveBeenCalledWith('/api/fms/splice-plans/quick-add/', {
      method: 'POST',
      headers: { 'X-CSRFToken': 'test-token' },
      body: formData,
    });
  });

  it('throws with detail message on error', async () => {
    vi.stubGlobal('fetch', mockFetchError(400, 'Name required'));
    const formData = new FormData();
    await expect(quickAddPlan(makeConfig(), formData)).rejects.toThrow('Name required');
  });
});

// ---------------------------------------------------------------------------
// bulkUpdatePlan
// ---------------------------------------------------------------------------

describe('bulkUpdatePlan', () => {
  it('posts JSON payload with CSRF and Content-Type headers', async () => {
    vi.stubGlobal('fetch', mockFetchOk({ entries: [] }));
    const payload = { add: [{ fiber_a: 1, fiber_b: 2 }], remove: [] };

    await bulkUpdatePlan(makeConfig(), payload);

    expect(fetch).toHaveBeenCalledWith('/api/fms/splice-plans/1/bulk-update/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': 'test-token',
      },
      body: JSON.stringify(payload),
    });
  });

  it('throws when bulkUpdateUrl is null', async () => {
    const payload = { add: [], remove: [] };
    await expect(
      bulkUpdatePlan(makeConfig({ bulkUpdateUrl: null }), payload),
    ).rejects.toThrow('No bulk update URL');
  });

  it('throws with detail on error response', async () => {
    vi.stubGlobal('fetch', mockFetchError(409, 'Conflict'));
    const payload = { add: [], remove: [] };
    await expect(bulkUpdatePlan(makeConfig(), payload)).rejects.toThrow('Conflict');
  });
});

// ---------------------------------------------------------------------------
// fetchQuickAddForm
// ---------------------------------------------------------------------------

describe('fetchQuickAddForm', () => {
  it('fetches HTML as text', async () => {
    const html = '<form><input name="name"></form>';
    vi.stubGlobal('fetch', mockFetchOk(html));

    const result = await fetchQuickAddForm(makeConfig());
    expect(result).toBe(html);
  });

  it('throws on HTTP error', async () => {
    vi.stubGlobal('fetch', mockFetchError(404));
    await expect(fetchQuickAddForm(makeConfig())).rejects.toThrow('HTTP 404');
  });
});
