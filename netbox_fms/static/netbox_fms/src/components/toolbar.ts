export function createPillGroup(
  items: Array<{ id: string; label: string; active?: boolean }>,
  onChange: (id: string) => void,
): HTMLElement {
  const container = document.createElement('div');
  container.className = 'fms-pill-group';

  for (const item of items) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'fms-pill';
    if (item.active) {
      btn.classList.add('fms-pill--active');
    }
    btn.dataset.id = item.id;
    btn.textContent = item.label;

    btn.addEventListener('click', () => {
      const pills = container.querySelectorAll('.fms-pill');
      pills.forEach((pill) => pill.classList.remove('fms-pill--active'));
      btn.classList.add('fms-pill--active');
      onChange(item.id);
    });

    container.appendChild(btn);
  }

  return container;
}

export function createPillFilter(
  items: Array<{ id: string; label: string; color: string; on?: boolean }>,
  onToggle: (id: string, on: boolean) => void,
): HTMLElement {
  const container = document.createElement('div');
  container.className = 'fms-pill-filter';

  for (const item of items) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'fms-pill';
    if (item.on) {
      btn.classList.add('fms-pill--active');
    }
    btn.dataset.id = item.id;
    btn.textContent = item.label;
    btn.style.setProperty('--pill-color', item.color);

    btn.addEventListener('click', () => {
      const isActive = btn.classList.toggle('fms-pill--active');
      onToggle(item.id, isActive);
    });

    container.appendChild(btn);
  }

  return container;
}

export function createSeparator(): HTMLElement {
  const el = document.createElement('div');
  el.className = 'fms-separator';
  return el;
}

export function createSearch(placeholder: string, onInput: (query: string) => void): HTMLInputElement {
  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'fms-search';
  input.placeholder = placeholder;
  input.addEventListener('input', () => {
    onInput(input.value);
  });
  return input;
}

export function createSpacer(): HTMLElement {
  const el = document.createElement('div');
  el.className = 'fms-toolbar__spacer';
  return el;
}
