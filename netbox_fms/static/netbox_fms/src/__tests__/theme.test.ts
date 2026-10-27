import { describe, it, expect } from 'vitest';
import { isDarkTheme } from '../theme';

function el(theme: string | null): Pick<Element, 'getAttribute'> {
  return { getAttribute: () => theme };
}

describe('isDarkTheme', () => {
  it('reads the <html> data-bs-theme attribute', () => {
    expect(isDarkTheme(el('dark'))).toBe(true);
    expect(isDarkTheme(el('light'))).toBe(false);
  });

  it('defaults to light when <html> is not themed', () => {
    expect(isDarkTheme(el(null))).toBe(false);
  });
});
