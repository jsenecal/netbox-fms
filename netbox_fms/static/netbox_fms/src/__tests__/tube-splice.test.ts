import { describe, it, expect } from 'vitest';
import { pairTubeFibers } from '../tube-splice';
import type { TubeFiberInfo } from '../tube-splice';

// Bulk tube-to-tube pairing logic (issue #116).

function makeFiber(overrides: Partial<TubeFiberInfo> & { id: number }): TubeFiberInfo {
  return {
    frontPortId: overrides.id * 100,
    spliced: false,
    pendingAdd: false,
    isProtected: false,
    label: `Fiber ${overrides.id}`,
    ...overrides,
  };
}

function makeFibers(ids: number[], overrides: Partial<TubeFiberInfo> = {}): TubeFiberInfo[] {
  return ids.map((id) => makeFiber({ id, ...overrides }));
}

describe('pairTubeFibers', () => {
  it('pairs equal-count tubes 1:1 in positional order', () => {
    const left = makeFibers([1, 2, 3]);
    const right = makeFibers([11, 12, 13]);

    const result = pairTubeFibers(left, right);

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.pairs.map((p) => [p.a.id, p.b.id])).toEqual([
        [1, 11],
        [2, 12],
        [3, 13],
      ]);
    }
  });

  it('pairs only the unspliced remainder of partially spliced tubes', () => {
    const left = [
      makeFiber({ id: 1, spliced: true }),
      makeFiber({ id: 2 }),
      makeFiber({ id: 3 }),
    ];
    const right = [
      makeFiber({ id: 11 }),
      makeFiber({ id: 12, spliced: true }),
      makeFiber({ id: 13 }),
    ];

    const result = pairTubeFibers(left, right);

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.pairs.map((p) => [p.a.id, p.b.id])).toEqual([
        [2, 11],
        [3, 13],
      ]);
    }
  });

  it('rejects mismatched unspliced counts with both counts in the reason', () => {
    const left = makeFibers([1, 2, 3]);
    const right = makeFibers([11, 12]);

    const result = pairTubeFibers(left, right);

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reason).toContain('3');
      expect(result.reason).toContain('2');
      expect(result.reason).toContain('do not match');
    }
  });

  it('rejects when both tubes are fully spliced', () => {
    const left = makeFibers([1, 2], { spliced: true });
    const right = makeFibers([11, 12], { spliced: true });

    const result = pairTubeFibers(left, right);

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reason).toContain('already spliced');
    }
  });

  it('rejects when one side has no spliceable fibers', () => {
    const left = makeFibers([1, 2], { spliced: true });
    const right = makeFibers([11, 12]);

    const result = pairTubeFibers(left, right);

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reason).toContain('Left tube');
    }
  });

  it('excludes protected fibers from pairing', () => {
    const left = [
      makeFiber({ id: 1, isProtected: true }),
      makeFiber({ id: 2 }),
    ];
    const right = makeFibers([11]);

    const result = pairTubeFibers(left, right);

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.pairs).toEqual([
        expect.objectContaining({ a: expect.objectContaining({ id: 2 }), b: expect.objectContaining({ id: 11 }) }),
      ]);
    }
  });

  it('treats pending-add fibers as unavailable', () => {
    const left = [
      makeFiber({ id: 1, pendingAdd: true }),
      makeFiber({ id: 2 }),
    ];
    const right = makeFibers([11, 12]);

    const result = pairTubeFibers(left, right);

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reason).toContain('1');
      expect(result.reason).toContain('2');
    }
  });

  it('treats fibers without a front port as unavailable', () => {
    const left = [
      makeFiber({ id: 1, frontPortId: null }),
      makeFiber({ id: 2 }),
    ];
    const right = makeFibers([11]);

    const result = pairTubeFibers(left, right);

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.pairs.map((p) => [p.a.id, p.b.id])).toEqual([[2, 11]]);
    }
  });
});
