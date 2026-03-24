/**
 * Shared HTMX event listeners for FMS pages.
 * Loaded on pages that use HTMX modals (e.g. fiber overview).
 */

declare const bootstrap: {
  Modal: {
    getInstance(el: Element): { hide(): void } | null;
    getOrCreateInstance(el: Element): { hide(): void };
  };
};

/**
 * Close the HTMX modal and clear its content when the server sends
 * HX-Trigger: fmsCloseModal.  Uses Bootstrap's hidden.bs.modal event
 * to wipe content only after the fade-out animation completes.
 */
document.body.addEventListener('fmsCloseModal', () => {
  const el = document.getElementById('htmx-modal');
  if (!el) return;

  const modal = bootstrap.Modal.getInstance(el) ?? bootstrap.Modal.getOrCreateInstance(el);

  // Clear content after the fade-out finishes
  el.addEventListener('hidden.bs.modal', () => {
    const content = document.getElementById('htmx-modal-content');
    if (content) {
      while (content.firstChild) content.removeChild(content.firstChild);
    }
  }, { once: true });

  modal.hide();
});
