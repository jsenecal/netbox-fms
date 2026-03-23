export function createBadge(variant: string, text: string): HTMLSpanElement {
  const el = document.createElement('span');
  el.className = `fms-badge fms-badge--${variant}`;
  el.textContent = text;
  return el;
}
