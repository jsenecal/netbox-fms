/**
 * NetBox color-mode detection.
 *
 * NetBox 4.6+ sets `data-bs-theme` only on `<html>`. NetBox 4.5 also sets it
 * on `<html>` at page load, but its toggle writes to `<body>` and leaves the
 * `<html>` value stale. The nearest themed ancestor wins, so `<body>` is
 * consulted first. The splice editor stylesheet mirrors this rule.
 */

type Themed = Pick<Element, 'getAttribute'>;

export function isDarkTheme(
  root: Themed = document.documentElement,
  body: Themed = document.body,
): boolean {
  return (body.getAttribute('data-bs-theme') ?? root.getAttribute('data-bs-theme')) === 'dark';
}

/** Invoke `onChange` whenever NetBox toggles the color mode. */
export function observeThemeChange(onChange: () => void): MutationObserver {
  const observer = new MutationObserver(onChange);
  const options = { attributes: true, attributeFilter: ['data-bs-theme'] };
  observer.observe(document.documentElement, options);
  observer.observe(document.body, options);
  return observer;
}
