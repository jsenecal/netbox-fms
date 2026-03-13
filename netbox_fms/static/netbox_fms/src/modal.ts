import { fetchQuickAddForm, quickAddPlan } from './api';
import type { EditorConfig, QuickAddResponse } from './types';

/**
 * Show a Bootstrap 5 modal to create a new SplicePlan.
 * Fetches form HTML from Django, renders in modal, submits via API.
 * Returns the created plan response, or null if cancelled.
 */
export async function showQuickAddModal(
  config: EditorConfig,
): Promise<QuickAddResponse | null> {
  // Fetch form HTML from Django
  const formHtml = await fetchQuickAddForm(config);

  return new Promise((resolve) => {
    // Create modal structure
    const backdrop = document.createElement('div');
    backdrop.className = 'modal-backdrop fade show';

    const modal = document.createElement('div');
    modal.className = 'modal fade show d-block';
    modal.tabIndex = -1;
    modal.setAttribute('role', 'dialog');

    const dialog = document.createElement('div');
    dialog.className = 'modal-dialog modal-lg';

    const content = document.createElement('div');
    content.className = 'modal-content';

    // Header
    const header = document.createElement('div');
    header.className = 'modal-header';
    header.insertAdjacentHTML('beforeend', '<h5 class="modal-title">Create Splice Plan</h5>');
    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'btn-close';
    closeBtn.setAttribute('aria-label', 'Close');
    header.appendChild(closeBtn);

    // Body
    const body = document.createElement('div');
    body.className = 'modal-body';
    const formEl = document.createElement('form');
    formEl.id = 'quick-add-form';
    formEl.insertAdjacentHTML('beforeend', formHtml);
    body.appendChild(formEl);

    // Error alert (hidden by default)
    const errorAlert = document.createElement('div');
    errorAlert.className = 'alert alert-danger d-none mt-2';
    body.appendChild(errorAlert);

    // Footer
    const footer = document.createElement('div');
    footer.className = 'modal-footer';
    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'btn btn-secondary';
    cancelBtn.textContent = 'Cancel';
    const createBtn = document.createElement('button');
    createBtn.type = 'button';
    createBtn.className = 'btn btn-primary';
    createBtn.textContent = 'Create';
    footer.appendChild(cancelBtn);
    footer.appendChild(createBtn);

    // Assemble
    content.appendChild(header);
    content.appendChild(body);
    content.appendChild(footer);
    dialog.appendChild(content);
    modal.appendChild(dialog);

    document.body.appendChild(backdrop);
    document.body.appendChild(modal);

    function cleanup(): void {
      modal.remove();
      backdrop.remove();
    }

    function cancel(): void {
      cleanup();
      resolve(null);
    }

    closeBtn.addEventListener('click', cancel);
    cancelBtn.addEventListener('click', cancel);
    backdrop.addEventListener('click', cancel);

    // Prevent clicks inside modal from closing
    content.addEventListener('click', (e) => e.stopPropagation());

    createBtn.addEventListener('click', async () => {
      createBtn.disabled = true;
      createBtn.textContent = 'Creating...';
      errorAlert.classList.add('d-none');

      try {
        const formData = new FormData(formEl);
        const result = await quickAddPlan(config, formData);
        cleanup();
        resolve(result);
      } catch (err) {
        errorAlert.textContent = (err as Error).message;
        errorAlert.classList.remove('d-none');
        createBtn.disabled = false;
        createBtn.textContent = 'Create';
      }
    });
  });
}
