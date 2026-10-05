import { describe, it, expect } from 'vitest';
import { isDarkTheme } from '../theme';

function el(theme: string | null): Pick<Element, 'getAttribute'> {
  return { getAttribute: () => theme };
}

describe('isDarkTheme', () => {
  it('reads the <html> attribute when <body> carries none (NetBox 4.6+)', () => {
    expect(isDarkTheme(el('dark'), el(null))).toBe(true);
    expect(isDarkTheme(el('light'), el(null))).toBe(false);
  });

  it('prefers <body> over a stale <html> attribute (NetBox 4.5 toggle)', () => {
    expect(isDarkTheme(el('dark'), el('light'))).toBe(false);
    expect(isDarkTheme(el('light'), el('dark'))).toBe(true);
  });

  it('defaults to light when neither element is themed', () => {
    expect(isDarkTheme(el(null), el(null))).toBe(false);
  });
});
