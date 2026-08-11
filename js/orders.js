/**
 * Registro de pedidos en el backend con validación y datos bancarios integrados.
 */

function attachBankTransferDetails(order) {
  if (order.paymentMethod !== 'bank_transfer') return order;

  const bt = APP_CONFIG.bankTransfer;
  const accounts = typeof getAllBankAccounts === 'function' ? getAllBankAccounts() : bt.accounts || [];

  return {
    ...order,
    bankTransfer: {
      currency: bt.currency,
      email: bt.email,
      proofDeadlineHours: bt.proofDeadlineHours,
      instructions: bt.instructions,
      beneficiary: { ...(bt.beneficiary || {}) },
      accounts: accounts.map((account) => ({
        bankName: account.bankName,
        accountHolder: account.accountHolder,
        accountType: account.accountType,
        accountNumber: account.accountNumber,
        currency: account.currency,
        note: account.note || '',
      })),
    },
  };
}

/**
 * Validación previa al envío del pedido al servidor.
 * @param {object} order
 * @returns {string[]}
 */
function validateOrderForSubmission(order) {
  const errors = [];

  if (!order?.reference) errors.push('Referencia de pedido requerida.');
  if (!order?.customer?.email) errors.push('Correo del cliente requerido.');
  if (!Array.isArray(order?.items) || order.items.length === 0) {
    errors.push('El pedido debe incluir al menos un artículo.');
  }
  if (!order?.policy?.accepted || !order?.policy?.noRefunds) {
    errors.push(SALES_POLICY.filterBlockedReason);
  }
  if (!order?.customsDisclaimer?.accepted) {
    errors.push(CUSTOMS_DISCLAIMER.filterBlockedReason);
  }
  if (!Number.isFinite(order?.total) || order.total <= 0) {
    errors.push('Total de pedido inválido.');
  }

  const boxLimit = validateDhlBoxLimit(order.shippingBoxes);
  if (!boxLimit.valid) {
    errors.push(boxLimit.error);
  }

  if (order.paymentMethod === 'bank_transfer') {
    const accounts = order.bankTransfer?.accounts || [];
    if (!accounts.length) {
      errors.push('No hay cuentas bancarias configuradas para transferencia.');
    }
  }

  return errors;
}

function prepareOrderForRegistration(order) {
  const enriched = attachBankTransferDetails(order);
  const errors = validateOrderForSubmission(enriched);
  if (errors.length) {
    throw new Error(errors[0]);
  }
  return enriched;
}

async function registerOrder(order) {
  const payload = prepareOrderForRegistration(order);

  const response = await fetch(`${APP_CONFIG.stripe.apiBaseUrl}/orders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.error || 'No se pudo registrar el pedido. Intenta de nuevo.');
  }

  return data;
}

async function fetchOrderByReference(reference) {
  const response = await fetch(
    `${APP_CONFIG.stripe.apiBaseUrl}/orders/${encodeURIComponent(reference)}`
  );

  if (!response.ok) return null;
  return response.json();
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    attachBankTransferDetails,
    validateOrderForSubmission,
    prepareOrderForRegistration,
    registerOrder,
    fetchOrderByReference,
  };
}
