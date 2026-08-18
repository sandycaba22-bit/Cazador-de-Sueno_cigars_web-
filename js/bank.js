/**
 * Renderizado y utilidades de transferencia bancaria internacional.
 */

function getPrimaryBankAccount() {
  const bt = APP_CONFIG.bankTransfer;
  return bt.accounts?.[0] || bt;
}

function getAllBankAccounts() {
  const bt = APP_CONFIG.bankTransfer;
  return bt.accounts?.length ? bt.accounts : [bt];
}

function formatBankField(label, value) {
  if (!value) return '';
  return `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd></div>`;
}

function renderBankAccountBlock(account, index, total) {
  const heading =
    total > 1
      ? `<h4 class="bank-account-heading">Cuenta ${index + 1} — ${escapeHtml(account.currency || APP_CONFIG.currency)}</h4>`
      : '';

  return `
    ${heading}
    ${formatBankField('Banco', account.bankName)}
    ${formatBankField('Dirección del banco', account.bankAddress)}
    ${formatBankField('Titular de la cuenta', account.accountHolder || APP_CONFIG.bankTransfer.beneficiary?.name)}
    ${formatBankField('Tipo de cuenta', account.accountType)}
    ${formatBankField('Número de cuenta', account.accountNumber)}
    ${formatBankField('CLABE', account.clabe)}
    ${formatBankField('Routing / ABA', account.routingNumber)}
    ${formatBankField('SWIFT / BIC', account.swiftBic)}
    ${formatBankField('IBAN', account.iban)}
    ${account.note ? `<p class="bank-account-note">${escapeHtml(account.note)}</p>` : ''}
  `;
}

/**
 * @param {object} order
 * @param {{ showAmount?: boolean, showReference?: boolean }} [options]
 */
function renderBankTransferDetails(order, container, options = {}) {
  const bt = APP_CONFIG.bankTransfer;
  const showAmount = options.showAmount !== false;
  const showReference = options.showReference !== false;
  const accounts = getAllBankAccounts();

  const accountsHtml = accounts
    .map((account, i) => renderBankAccountBlock(account, i, accounts.length))
    .join('');

  const beneficiary = bt.beneficiary || {};

  container.innerHTML = `
    <div class="bank-transfer-panel">
      <h3>Datos para transferencia bancaria</h3>
      ${
        showReference
          ? `<p class="bank-transfer-panel__ref">
              Referencia obligatoria en el concepto:
              <strong class="copyable" data-copy="${escapeHtml(order.reference)}">${escapeHtml(order.reference)}</strong>
              <button type="button" class="btn-copy" data-copy="${escapeHtml(order.reference)}" aria-label="Copiar referencia">Copiar</button>
            </p>`
          : `<p class="bank-transfer-panel__ref">La referencia única se generará al confirmar el pedido.</p>`
      }
      <dl class="bank-details">
        ${formatBankField('Beneficiario', beneficiary.name || bt.accountHolder)}
        ${formatBankField('Dirección del beneficiario', beneficiary.address)}
        ${formatBankField('RNC / Tax ID', beneficiary.taxId)}
        ${accountsHtml}
        ${formatBankField('Moneda de pago', bt.currency)}
        ${showAmount ? formatBankField('Monto exacto a transferir', formatCurrency(order.total)) : ''}
      </dl>
      <p class="bank-transfer-panel__instructions">${escapeHtml(bt.instructions)}</p>
      <p class="bank-transfer-panel__deadline">
        Plazo para enviar comprobante: <strong>${bt.proofDeadlineHours || 48} horas</strong>
      </p>
      <p class="bank-transfer-panel__email">
        Comprobante y consultas:
        <a href="${escapeHtml(getBankProofMailto(order))}">${escapeHtml(bt.email)}</a>
      </p>
      <button type="button" class="btn btn--secondary btn-copy-all" id="copy-bank-details">
        Copiar todos los datos bancarios
      </button>
    </div>
  `;

  bindCopyButtons(container);
}

function getBankProofMailto(order) {
  const bt = APP_CONFIG.bankTransfer;
  const subject = encodeURIComponent(`Comprobante de pago — ${order.reference}`);
  const body = encodeURIComponent(
    `Hola,\n\nAdjunto comprobante de transferencia.\n\nReferencia: ${order.reference}\nMonto: ${formatCurrency(order.total)}\nNombre: ${order.customer?.fullName || ''}\nEmail: ${order.customer?.email || ''}\n`
  );
  return `mailto:${bt.email}?subject=${subject}&body=${body}`;
}

function buildBankDetailsPlainText(order) {
  const bt = APP_CONFIG.bankTransfer;
  const beneficiary = bt.beneficiary || {};
  const lines = [
    `Referencia: ${order.reference}`,
    `Beneficiario: ${beneficiary.name || bt.accountHolder}`,
    beneficiary.address ? `Dirección: ${beneficiary.address}` : '',
    beneficiary.taxId ? `RNC/Tax ID: ${beneficiary.taxId}` : '',
  ];

  getAllBankAccounts().forEach((account, i) => {
    lines.push('');
    if (getAllBankAccounts().length > 1) lines.push(`--- Cuenta ${i + 1} (${account.currency}) ---`);
    lines.push(`Banco: ${account.bankName}`);
    if (account.bankAddress) lines.push(`Dirección banco: ${account.bankAddress}`);
    lines.push(`Cuenta: ${account.accountNumber}`);
    if (account.clabe) lines.push(`CLABE: ${account.clabe}`);
    if (account.routingNumber) lines.push(`Routing/ABA: ${account.routingNumber}`);
    if (account.swiftBic) lines.push(`SWIFT/BIC: ${account.swiftBic}`);
    if (account.iban) lines.push(`IBAN: ${account.iban}`);
  });

  lines.push('', `Monto: ${formatCurrency(order.total)}`, `Moneda: ${bt.currency}`);
  return lines.filter(Boolean).join('\n');
}

function bindCopyButtons(container) {
  container.querySelectorAll('[data-copy], .btn-copy').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const text = btn.dataset.copy || btn.closest('[data-copy]')?.dataset.copy;
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
        showToast('Copiado al portapapeles.', 'success');
      } catch {
        showToast('No se pudo copiar. Selecciona el texto manualmente.', 'error');
      }
    });
  });

  container.querySelector('#copy-bank-details')?.addEventListener('click', async () => {
    const ref = container.querySelector('[data-copy]')?.dataset.copy || '';
    const order = { reference: ref, total: 0, customer: {} };
    const totalEl = document.getElementById('summary-total');
    if (totalEl) {
      order.total = parseFloat(totalEl.textContent.replace(/[^0-9.]/g, '')) || 0;
    }
    try {
      await navigator.clipboard.writeText(buildBankDetailsPlainText(order));
      showToast('Datos bancarios copiados.', 'success');
    } catch {
      showToast('No se pudo copiar.', 'error');
    }
  });
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    getPrimaryBankAccount,
    getAllBankAccounts,
    renderBankTransferDetails,
    getBankProofMailto,
    buildBankDetailsPlainText,
  };
}
