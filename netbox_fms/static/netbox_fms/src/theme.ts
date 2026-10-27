/**
 * NetBox color-mode detection.
 *
 * NetBox sets `data-bs-theme` only on `<html>`, both at page load and when
 * the color-mode toggle is used. The FMS stylesheets key off the same
 * attribute.
 */

type Themed = Pick<Element, 'getAttribute'>;

export function isDarkTheme(root: Themed = document.documentElement): boolean {
  return root.getAttribute('data-bs-theme') === 'dark';
}

/** Invoke `onChange` whenever NetBox toggles the color mode. */
export function observeThemeChange(onChange: () => void): MutationObserver {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-bs-theme'] });
  return observer;
}
