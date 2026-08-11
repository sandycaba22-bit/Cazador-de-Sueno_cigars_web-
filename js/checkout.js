/**
 * Lógica de checkout: Stripe, transferencia bancaria y venta final.
 */

let stripeInstance = null;
let cardElement = null;

function initStripe() {
  if (typeof Stripe === 'undefined') {
    console.warn('Stripe.js no cargado.');
    return null;
  }
  if (!stripeInstance) {
    stripeInstance = Stripe(APP_CONFIG.stripe.publishableKey);
  }
  return stripeInstance;
}

function mountCardElement() {
  const stripe = initStripe();
  const container = $('#card-element');
  if (!stripe || !container) return;

  if (cardElement) return;

  const elements = stripe.elements({ locale: APP_CONFIG.locale });
  cardElement = elements.create('card', {
    style: {
      base: {
        color: '#f5f0e8',
        fontFamily: '"Cormorant Garamond", Georgia, serif',
        fontSize: '16px',
        '::placeholder': { color: '#8a8278' },
      },
      invalid: { color: '#e07a5f' },
    },
  });

  cardElement.mount('#card-element');
  cardElement.on('change', (event) => {
    const errorEl = $('#card-errors');
    if (errorEl) errorEl.textContent = event.error ? event.error.message : '';
  });
}

function destroyCardElement() {
  if (cardElement) {
    cardElement.destroy();
    cardElement = null;
  }
}

function getCheckoutFormData() {
  const form = $('#checkout-form');
  if (!form) return null;

  return {
    fullName: form.fullName.value.trim(),
    email: form.email.value.trim(),
    phone: form.phone.value.trim(),
    address: form.address.value.trim(),
    city: form.city.value.trim(),
    state: form.state.value.trim(),
    postalCode: form.postalCode.value.trim(),
    country: form.country.value,
    paymentMethod: form.paymentMethod.value,
    notes: form.notes?.value?.trim() || '',
    acceptFinalSale: form.acceptFinalSale?.checked || false,
    acceptCustomsDisclaimer: form.acceptCustomsDisclaimer?.checked || false,
  };
}

function validateCheckoutForm(data) {
  const errors = [];
  if (!data.fullName) errors.push('Nombre completo requerido.');
  if (!data.email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email)) {
    errors.push('Correo electrónico válido requerido.');
  }
  if (!data.address) errors.push('Dirección requerida.');
  if (!data.city) errors.push('Ciudad requerida.');
  if (!data.country) errors.push('País de destino requerido.');
  if (!data.paymentMethod) errors.push('Selecciona un método de pago.');

  const policyCheck = validateFinalSaleAcceptance(data.acceptFinalSale);
  if (!policyCheck.valid) errors.push(policyCheck.error);

  const customsCheck = validateCustomsDisclaimer(data.acceptCustomsDisclaimer);
  if (!customsCheck.valid) errors.push(customsCheck.error);

  return errors;
}

function buildOrderPayload(formData, summary) {
  const destinationName = getCountryName(formData.country);

  return {
    reference: generateOrderReference(),
    customer: {
      fullName: formData.fullName,
      email: formData.email,
      phone: formData.phone,
    },
    shipping: {
      address: formData.address,
      city: formData.city,
      state: formData.state,
      postalCode: formData.postalCode,
      country: formData.country,
      countryName: destinationName,
      carrier: summary.shipping.carrier,
      boxes: summary.shippingBoxes,
      originCountry: summary.shipping.originCountry,
      originLabel: summary.shipping.originLabel,
      zone: summary.shipping.zone.name,
    },
    items: summary.items.map((i) => ({
      productId: i.productId,
      name: i.product.name,
      line: i.product.line,
      unitType: i.unitType,
      unitsPerBox: i.product.unitsPerBox,
      quantity: i.quantity,
      totalUnits: i.totalUnits,
      pricePerBox: i.product.pricePerBox,
      pricePerUnit: i.product.pricePerUnit,
      lineTotal: i.lineTotal,
      displayLabel: i.displayLabel,
      packagingLabel: i.product.packagingLabel,
    })),
    subtotal: summary.subtotal,
    shippingCost: summary.shippingCost,
    shippingBoxes: summary.shippingBoxes,
    shippingZone: summary.shipping.zone.name,
    estimatedDelivery: summary.shipping.estimatedDays,
    total: summary.total,
    currency: APP_CONFIG.currency,
    paymentMethod: formData.paymentMethod,
    notes: formData.notes,
    policy: {
      id: SALES_POLICY.id,
      accepted: true,
      acceptedAt: new Date().toISOString(),
      noRefunds: true,
    },
    customsDisclaimer: {
      id: CUSTOMS_DISCLAIMER.id,
      accepted: true,
      acceptedAt: new Date().toISOString(),
    },
    createdAt: new Date().toISOString(),
  };
}

async function createStripePaymentIntent(order) {
  const response = await fetch(`${APP_CONFIG.stripe.apiBaseUrl}/create-payment-intent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      amount: Math.round(order.total * 100),
      currency: order.currency.toLowerCase(),
      metadata: {
        orderReference: order.reference,
        customerEmail: order.customer.email,
        finalSale: 'true',
        noRefunds: 'true',
        customsDisclaimer: 'accepted',
      },
    }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error || 'No se pudo iniciar el pago con tarjeta.');
  }

  return response.json();
}

async function processStripePayment(order) {
  const stripe = initStripe();
  if (!stripe || !cardElement) {
    throw new Error('Stripe no está configurado correctamente.');
  }

  const { clientSecret } = await createStripePaymentIntent(order);

  const { error, paymentIntent } = await stripe.confirmCardPayment(clientSecret, {
    payment_method: {
      card: cardElement,
      billing_details: {
        name: order.customer.fullName,
        email: order.customer.email,
        phone: order.customer.phone,
        address: {
          line1: order.shipping.address,
          city: order.shipping.city,
          state: order.shipping.state,
          postal_code: order.shipping.postalCode,
          country: order.shipping.country === 'OTHER' ? undefined : order.shipping.country,
        },
      },
    },
  });

  if (error) throw new Error(error.message);
  return paymentIntent;
}

async function finalizeOrder(order, paymentStatus) {
  order.paymentStatus = paymentStatus;
  order.refundEligible = false;

  const registered = await registerOrder(order);
  sessionStorage.setItem('cazador_sueno_last_order', JSON.stringify(registered.order || order));
  clearCart();
  return registered.order || order;
}

async function submitCheckout(event) {
  event.preventDefault();

  const formData = getCheckoutFormData();
  const errors = validateCheckoutForm(formData);
  if (errors.length) {
    showToast(errors[0], 'error');
    return;
  }

  const summary = getCartSummary(formData.country);
  if (summary.isEmpty) {
    showToast('Tu carrito está vacío.', 'error');
    return;
  }

  if (!summary.dhlValidation.valid) {
    showToast(summary.dhlValidation.error, 'error');
    return;
  }

  const order = buildOrderPayload(formData, summary);
  const submitBtn = $('#submit-checkout');

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = 'Procesando…';
  }

  try {
    if (formData.paymentMethod === 'card') {
      const paymentIntent = await processStripePayment(order);
      order.stripePaymentIntentId = paymentIntent.id;
      const saved = await finalizeOrder(order, 'paid');
      window.location.href = `order-confirmation.html?ref=${encodeURIComponent(saved.reference)}&method=card`;
      return;
    }

    if (formData.paymentMethod === 'bank_transfer') {
      const saved = await finalizeOrder(order, 'pending_transfer');
      window.location.href = `order-confirmation.html?ref=${encodeURIComponent(saved.reference)}&method=bank`;
      return;
    }

    showToast('Método de pago no válido.', 'error');
  } catch (err) {
    showToast(err.message || 'Error al procesar el pedido.', 'error');
  } finally {
    if (submitBtn) {
      const summaryAfter = getCartSummary(formData.country);
      submitBtn.disabled = !summaryAfter.dhlValidation.valid;
      submitBtn.textContent = 'Confirmar pedido — venta final';
    }
  }
}

function renderCheckoutItem(item) {
  const lineClass = isRangoLine(item.product.line) ? 'is-rango' : 'is-standard';
  const packagingBadge = isRangoLine(item.product.line)
    ? `<span class="badge badge--rango badge--inline">Rango · ${PACKAGING.RANGO_UNITS} uds/caja</span>`
    : `<span class="badge badge--standard badge--inline">Estándar · ${PACKAGING.STANDARD_UNITS} uds/caja</span>`;

  return `
    <div class="checkout-item ${lineClass}">
      <div>
        <strong>${escapeHtml(item.product.name)}</strong>
        ${packagingBadge}
        <span class="checkout-item__meta">${escapeHtml(item.displayLabel)} · ${escapeHtml(item.product.packagingLabel)}</span>
      </div>
      <span>${formatCurrency(item.lineTotal)}</span>
    </div>`;
}

function updateCheckoutSubmitState(summary) {
  const submitBtn = $('#submit-checkout');
  const warnEl = document.getElementById('dhl-box-warning');
  const overLimit = !summary.dhlValidation.valid;

  if (warnEl) {
    warnEl.hidden = !overLimit;
    warnEl.textContent = overLimit ? summary.dhlValidation.error : '';
  }

  if (submitBtn) {
    submitBtn.disabled = overLimit;
    submitBtn.title = overLimit ? summary.dhlValidation.error : '';
  }
}

function initCheckoutPage() {
  const form = $('#checkout-form');
  if (!form) return;

  initGlobalCart();

  const countrySelect = form.country;
  getCountryList().forEach(({ code, name }) => {
    const opt = document.createElement('option');
    opt.value = code;
    opt.textContent = name;
    countrySelect.appendChild(opt);
  });

  function refreshSummary() {
    const country = countrySelect.value || 'MX';
    const summary = getCartSummary(country);

    if (summary.isEmpty) {
      window.location.href = 'index.html';
      return;
    }

    const listEl = $('#checkout-items');
    if (listEl) listEl.innerHTML = summary.items.map(renderCheckoutItem).join('');

    const set = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.textContent = val;
    };

    set('summary-subtotal', formatCurrency(summary.subtotal));
    set('summary-shipping', formatCurrency(summary.shippingCost));
    set('summary-total', formatCurrency(summary.total));
    set('summary-delivery', `${summary.shipping.estimatedDays} días hábiles`);
    set('summary-zone', summary.shipping.zone.name);
    set('summary-units', String(summary.totalUnits));
    set('summary-carrier', summary.shipping.carrier);
    set('summary-origin', summary.shipping.originLabel);
    set('summary-destination', getCountryName(country));
    set('summary-boxes', String(summary.shippingBoxes));
    set('summary-max-boxes', String(summary.shipping.maxBoxes));

    updateCheckoutSubmitState(summary);
  }

  countrySelect.addEventListener('change', refreshSummary);
  refreshSummary();

  const paymentRadios = $$('input[name="paymentMethod"]');
  const cardSection = $('#card-payment-section');
  const bankSection = $('#bank-transfer-preview');

  function togglePaymentUI() {
    const method = form.paymentMethod.value;
    if (cardSection) cardSection.hidden = method !== 'card';
    if (bankSection) bankSection.hidden = method !== 'bank_transfer';

    if (method === 'card') {
      mountCardElement();
    } else {
      destroyCardElement();
    }

    if (method === 'bank_transfer' && bankSection) {
      const summary = getCartSummary(countrySelect.value);
      const previewOrder = {
        reference: '(se generará al confirmar)',
        total: summary.total,
        customer: { fullName: form.fullName.value.trim(), email: form.email.value.trim() },
      };
      renderBankTransferDetails(previewOrder, bankSection, {
        showReference: false,
        showAmount: true,
      });
    }
  }

  paymentRadios.forEach((radio) => radio.addEventListener('change', togglePaymentUI));
  countrySelect.addEventListener('change', () => {
    refreshSummary();
    if (form.paymentMethod.value === 'bank_transfer') togglePaymentUI();
  });

  togglePaymentUI();
  form.addEventListener('submit', submitCheckout);
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    initCheckoutPage,
    submitCheckout,
    buildOrderPayload,
    processStripePayment,
  };
}
