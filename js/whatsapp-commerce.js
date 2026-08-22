/**
 * WhatsApp flotante y mensajes de pedido pre-armados.
 */

function getWhatsAppPhone() {
  return (APP_CONFIG.whatsapp?.phone || '18095550198').replace(/\D/g, '');
}

function buildWhatsAppOrderMessage(order, summary) {
  const lines = [
    '🛒 *Pedido — Cazador de Sueños*',
    '',
    order.reference ? `Referencia: ${order.reference}` : '',
    `Cliente: ${order.customer?.fullName || ''}`,
    `Email: ${order.customer?.email || ''}`,
    `Tel: ${order.customer?.phone || '—'}`,
    '',
    '📦 *Productos*',
  ];

  (summary?.items || order.items || []).forEach((item) => {
    lines.push(
      `• ${item.product?.name || item.name} — ${item.displayLabel || item.quantity + ' uds.'} — ${formatCurrency(item.lineTotal)}`
    );
  });

  lines.push(
    '',
    `Subtotal: ${formatCurrency(summary?.subtotal ?? order.subtotal)}`,
    `Envío DHL: ${formatCurrency(summary?.shippingCost ?? order.shippingCost)}`,
    `*Total: ${formatCurrency(summary?.total ?? order.total)}*`,
    '',
    `Destino: ${order.shipping?.countryName || order.shipping?.country || ''} — ${order.shipping?.city || ''}`,
    `Método de pago: ${order.paymentMethod || 'transferencia'}`,
    order.notes ? `Notas: ${order.notes}` : ''
  );

  return lines.filter(Boolean).join('\n');
}

function openWhatsAppWithMessage(text) {
  const phone = getWhatsAppPhone();
  const url = `https://wa.me/${phone}?text=${encodeURIComponent(text)}`;
  window.open(url, '_blank', 'noopener');
}

function buildCheckoutWhatsAppPreview(formData, summary) {
  const previewOrder = {
    reference: '(pendiente de confirmar)',
    customer: {
      fullName: formData.fullName,
      email: formData.email,
      phone: formData.phone,
    },
    shipping: {
      city: formData.city,
      country: formData.country,
      countryName: getCountryName(formData.country),
    },
    paymentMethod: formData.paymentMethod,
    notes: formData.notes,
  };
  return buildWhatsAppOrderMessage(previewOrder, summary);
}

function getUnifiedCartCount() {
  try {
    if (typeof getCartCount === 'function') return getCartCount();
    const legacy = JSON.parse(localStorage.getItem('cds-shopping-cart') || '{}');
    if (legacy?.items?.length) {
      return legacy.items.reduce((sum, item) => sum + (Number(item.quantity) || 0), 0);
    }
    const modern = JSON.parse(localStorage.getItem('cazador_sueno_cart') || '{}');
    const items = modern.items || [];
    return items.reduce((sum, entry) => {
      const product = typeof getProductById === 'function' ? getProductById(entry.productId) : null;
      const units =
        entry.unitType === 'unit'
          ? entry.quantity
          : (product?.unitsPerBox || 20) * entry.quantity;
      return sum + units;
    }, 0);
  } catch {
    return 0;
  }
}

function initFloatingCommerceWidgets() {
  // La portada solo usa el Carrito del header; sin FABs de WhatsApp/CS/carrito flotante.
  if (document.body && document.body.getAttribute('data-page') === 'home') return;
  if (!APP_CONFIG.whatsapp?.enabled) return;

  if (!document.getElementById('cds-float-whatsapp')) {
    const wa = document.createElement('a');
    wa.id = 'cds-float-whatsapp';
    wa.className = 'cds-float-whatsapp';
    wa.href = `https://wa.me/${getWhatsAppPhone()}`;
    wa.target = '_blank';
    wa.rel = 'noopener';
    wa.setAttribute('aria-label', APP_CONFIG.whatsapp.floatLabel || 'WhatsApp');
    wa.innerHTML = `<span class="cds-float-whatsapp__icon">💬</span><span class="cds-float-whatsapp__text">${escapeHtml(APP_CONFIG.whatsapp.floatLabel || 'WhatsApp')}</span>`;
    document.body.appendChild(wa);
  }

  if (!document.getElementById('cds-float-cart')) {
    const cart = document.createElement('a');
    cart.id = 'cds-float-cart';
    cart.className = 'cds-float-cart';
    cart.href = typeof getCheckoutUrl === 'function' ? getCheckoutUrl() : '/checkout.html';
    cart.setAttribute('aria-label', 'Ir al checkout');
    cart.innerHTML = `<span class="cds-float-cart__icon">🛒</span><span id="cds-float-cart-count" class="cds-float-cart__count">0</span>`;
    document.body.appendChild(cart);
  }

  function refreshCount() {
    const countEl = document.getElementById('cds-float-cart-count');
    const count = getUnifiedCartCount();
    if (countEl) countEl.textContent = String(count);
    const headerCount = document.getElementById('cart-count');
    if (headerCount) headerCount.textContent = String(count);
  }

  refreshCount();
  window.addEventListener('cart:updated', refreshCount);
  window.addEventListener('cds:cart-updated', refreshCount);
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    buildWhatsAppOrderMessage,
    openWhatsAppWithMessage,
    buildCheckoutWhatsAppPreview,
    initFloatingCommerceWidgets,
    getUnifiedCartCount,
  };
}
