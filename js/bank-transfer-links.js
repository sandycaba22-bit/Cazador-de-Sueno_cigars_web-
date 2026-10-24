const BankTransferLinks = (() => {
  const banks = Object.freeze([
    { name: 'Banreservas', url: 'https://www.banreservas.com', pattern: /banreservas|banco\s+(?:de\s+)?reservas/i },
    { name: 'Banco BHD', url: 'https://www.bhd.com.do', pattern: /\bbhd\b/i },
  ]);

  const escape = (value) => String(value == null ? '' : value).replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);

  function resolve(bankName) {
    return banks.find((bank) => bank.pattern.test(String(bankName || ''))) || null;
  }

  function render(bankName, label = 'Abrir banca en l\u00ednea') {
    const bank = resolve(bankName);
    if (!bank) return '';
    // Only known official URLs are used, never a URL supplied by an order.
    return `<a class="co-bank__link" href="${bank.url}" target="_blank" rel="noopener noreferrer">${escape(label)} &middot; ${bank.name}</a>`;
  }

  function copyButton(value, label = 'Copiar') {
    const text = String(value == null ? '' : value).trim();
    if (!text) return '';
    return `<button type="button" class="co-bank__copy" data-copy="${escape(text)}" aria-label="${escape(label)} ${escape(text)}">${escape(label)}</button>`;
  }

  async function writeClipboard(text) {
    if (typeof navigator !== 'undefined' && navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text);
        return;
      } catch (_) {
        /* permiso denegado: se intenta el método clásico */
      }
    }
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand('copy');
    area.remove();
    if (!ok) throw new Error('copy failed');
  }

  /** Delegated so re-rendered panels keep working without rebinding. */
  function bindCopy(root, labels) {
    if (!root || root.dataset.copyBound === 'true') return;
    root.dataset.copyBound = 'true';
    root.addEventListener('click', async (event) => {
      const button = event.target.closest && event.target.closest('[data-copy]');
      if (!button) return;
      event.preventDefault();
      const { copied = 'Copiado', failed = 'Copia manualmente' } =
        (typeof labels === 'function' ? labels() : labels) || {};
      const original = button.textContent;
      try {
        await writeClipboard(button.dataset.copy);
        button.textContent = copied;
        button.classList.add('is-copied');
      } catch (_) {
        button.textContent = failed;
        const code = button.parentElement && button.parentElement.querySelector('code');
        if (code && window.getSelection) {
          const range = document.createRange();
          range.selectNodeContents(code);
          const selection = window.getSelection();
          selection.removeAllRanges();
          selection.addRange(range);
        }
      }
      setTimeout(() => {
        button.textContent = original;
        button.classList.remove('is-copied');
      }, 1800);
    });
  }

  return Object.freeze({ resolve, render, copyButton, bindCopy });
})();

if (typeof module !== 'undefined' && module.exports) module.exports = BankTransferLinks;
