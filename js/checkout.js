/**
 * Lógica de checkout: Stripe, transferencia bancaria, sandbox y venta final.
 */

let stripeInstance = null;
let cardElement = null;

function initStripe() {
  if (!isStripeConfigured()) return null;
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
  if (!isStripeConfigured()) return;

  try {
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
  } catch (err) {
    console.error('[Checkout] Stripe mount error:', err);
    const errorEl = $('#card-errors');
    if (errorEl) {
      errorEl.textContent =
        'No se pudo cargar el formulario de tarjeta. Usa transferencia bancaria o modo sandbox.';
    }
  }
}

function destroyCardElement() {
  if (cardElement) {
    try {
      cardElement.destroy();
    } catch {
      /* ignore */
    }
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
    paymentProofFileName: form.paymentProof?.files?.[0]?.name || '',
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

  if (data.paymentMethod === 'card' && !isStripeConfigured()) {
    errors.push('Pagos con tarjeta no configurados. Usa transferencia o modo sandbox.');
  }

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
      isLegacy: Boolean(i.isLegacy),
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
    paymentProofFileName: formData.paymentProofFileName || '',
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

  const summary = safeGetCartSummary(formData.country);
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
    if (formData.paymentMethod === 'sandbox') {
      const saved = await finalizeOrder(order, 'paid_sandbox');
      window.location.href = `order-confirmation.html?ref=${encodeURIComponent(saved.reference)}&method=sandbox`;
      return;
    }

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
      const summaryAfter = safeGetCartSummary(formData.country);
      submitBtn.disabled = !summaryAfter.isEmpty && !summaryAfter.dhlValidation.valid;
      submitBtn.textContent = 'Confirmar pedido — venta final';
    }
  }
}

function renderCheckoutItem(item) {
  const lineClass = isRangoLine(item.product.line) ? 'is-rango' : 'is-standard';
  const imageSrc = item.product.image || 'img/hero-atmosphere.jpg';
  const unitLabel =
    item.unitType === UNIT_TYPES.BOX && !item.isLegacy
      ? `${formatCurrency(item.product.pricePerBox)}/caja`
      : `${formatCurrency(item.product.pricePerUnit)}/ud.`;

  return `
    <article class="checkout-line ${lineClass}" data-line-id="${escapeHtml(item.lineId)}">
      <img class="checkout-line__thumb" src="${escapeHtml(imageSrc)}" alt="${escapeHtml(item.product.name)}" loading="lazy" />
      <div class="checkout-line__body">
        <p class="checkout-line__name">${escapeHtml(item.product.name)}</p>
        <span class="checkout-line__meta">${escapeHtml(item.product.packagingLabel)} · ${escapeHtml(item.displayLabel)}</span>
        <div class="checkout-line__pricing">
          <span class="checkout-line__qty">
            <button type="button" class="checkout-qty-btn" data-action="decrease" aria-label="Reducir">−</button>
            <span>${item.quantity}</span>
            <button type="button" class="checkout-qty-btn" data-action="increase" aria-label="Aumentar">+</button>
          </span>
          <span>${unitLabel}</span>
        </div>
        <button type="button" class="checkout-line__remove" data-action="remove">Eliminar</button>
      </div>
      <div class="checkout-line__total">${formatCurrency(item.lineTotal)}</div>
    </article>`;
}

function bindCheckoutLineEvents(container, refreshSummary) {
  if (!container || container.dataset.bound === 'true') return;
  container.dataset.bound = 'true';

  container.addEventListener('click', (event) => {
    const line = event.target.closest('.checkout-line');
    if (!line) return;
    const lineId = line.dataset.lineId;
    const actionBtn = event.target.closest('[data-action]');
    if (!actionBtn) return;

    const action = actionBtn.dataset.action;
    const items = getCartItems();
    const current = items.find((i) => i.lineId === lineId);
    if (!current) return;

    if (action === 'remove') {
      removeFromCart(lineId);
      refreshSummary();
      showToast('Artículo eliminado.', 'info');
      return;
    }

    const delta = action === 'increase' ? qtyStepForItem(current) : -qtyStepForItem(current);
    const result = updateCartQuantity(lineId, current.quantity + delta);
    if (result.success) {
      refreshSummary();
    } else {
      showToast(result.error, 'error');
    }
  });
}

function qtyStepForItem(item) {
  if (item.isLegacy || item.unitType === UNIT_TYPES.UNIT) return 1;
  return 1;
}

function safeGetCartSummary(countryCode) {
  try {
    return getCartSummary(countryCode);
  } catch (err) {
    console.error('[Checkout] Error leyendo carrito:', err);
    showCheckoutFatalError(
      'No se pudo leer el carrito. Vacía el carrito del navegador o vuelve a añadir productos.'
    );
    return {
      items: [],
      subtotal: 0,
      totalUnits: 0,
      shippingBoxes: 0,
      shipping: calculateShipping(countryCode, 0),
      dhlValidation: validateDhlBoxLimit(0),
      shippingCost: 0,
      total: 0,
      isEmpty: true,
    };
  }
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
    submitBtn.disabled = summary.isEmpty || overLimit;
    submitBtn.title = overLimit ? summary.dhlValidation.error : '';
  }
}

function setCheckoutEmptyState(isEmpty) {
  const emptyEl = document.getElementById('checkout-empty');
  const mainEl = document.getElementById('checkout-main');
  const summaryEl = document.getElementById('checkout-summary-panel');

  if (emptyEl) emptyEl.hidden = !isEmpty;
  if (mainEl) mainEl.hidden = isEmpty;
  if (summaryEl) summaryEl.hidden = isEmpty;
}

function showCheckoutFatalError(message) {
  const banner = document.getElementById('checkout-error-banner');
  if (banner) {
    banner.hidden = false;
    banner.textContent = message;
  }
}

function setupPaymentMethods(form) {
  const cardOption = document.getElementById('payment-option-card');
  const cardInput = form.querySelector('input[name="paymentMethod"][value="card"]');
  const sandboxOption = document.getElementById('payment-option-sandbox');
  const sandboxInput = form.querySelector('input[name="paymentMethod"][value="sandbox"]');
  const stripeNotice = document.getElementById('stripe-unavailable-notice');

  if (!isStripeConfigured()) {
    if (cardOption) cardOption.hidden = true;
    if (cardInput) cardInput.disabled = true;
    if (stripeNotice) stripeNotice.hidden = false;
  }

  if (isSandboxCheckoutEnabled()) {
    if (sandboxOption) sandboxOption.hidden = false;
    if (sandboxInput) sandboxInput.disabled = false;
  } else {
    if (sandboxOption) sandboxOption.hidden = true;
    if (sandboxInput) sandboxInput.disabled = true;
  }

  const defaultMethod = isStripeConfigured()
    ? 'card'
    : 'bank_transfer';

  form.querySelectorAll('input[name="paymentMethod"]').forEach((input) => {
    input.checked = input.value === defaultMethod;
  });
}

function renderAlwaysVisibleBankDetails(container, summary) {
  if (!container || typeof renderBankTransferDetails !== 'function') return;

  const previewOrder = {
    reference: '(se generará al confirmar)',
    total: summary?.total || 0,
    customer: { fullName: '', email: '' },
  };

  renderBankTransferDetails(previewOrder, container, {
    showReference: false,
    showAmount: Boolean(summary && !summary.isEmpty),
  });
}

function initCheckoutPage() {
  try {
    const form = $('#checkout-form');
    if (!form) {
      showCheckoutFatalError('No se encontró el formulario de checkout.');
      return;
    }

    initGlobalCart();
    setupPaymentMethods(form);

    const countrySelect = form.country;
    const preferredCountry = getPreferredShippingCountry();

    getCountryList().forEach(({ code, name }) => {
      const opt = document.createElement('option');
      opt.value = code;
      opt.textContent = name;
      if (code === preferredCountry) opt.selected = true;
      countrySelect.appendChild(opt);
    });

    const bankAlways = document.getElementById('bank-transfer-always');

    function refreshSummary() {
      const country = countrySelect.value || preferredCountry || 'US';
      const summary = safeGetCartSummary(country);

      setCheckoutEmptyState(summary.isEmpty);

      if (summary.isEmpty) {
        updateCheckoutSubmitState(summary);
        if (bankAlways) renderAlwaysVisibleBankDetails(bankAlways, summary);
        return;
      }

      const listEl = $('#checkout-items');
      if (listEl) {
        listEl.innerHTML = summary.items.map(renderCheckoutItem).join('');
        bindCheckoutLineEvents(listEl, refreshSummary);
      }

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
      if (bankAlways) renderAlwaysVisibleBankDetails(bankAlways, summary);
    }

    function refreshBankPanels() {
      const country = countrySelect.value || preferredCountry || 'US';
      const summary = safeGetCartSummary(country);
      if (bankAlways) renderAlwaysVisibleBankDetails(bankAlways, summary);
    }

    countrySelect.addEventListener('change', refreshSummary);
    refreshSummary();
    refreshBankPanels();

    const paymentRadios = $$('input[name="paymentMethod"]');
    const cardSection = $('#card-payment-section');
    const bankSection = $('#bank-transfer-preview');
    const sandboxNotice = $('#sandbox-payment-notice');
    const proofArea = document.getElementById('proof-upload-area');
    const proofInput = document.getElementById('payment-proof');
    const proofName = document.getElementById('proof-file-name');

    if (proofArea && proofInput) {
      proofArea.addEventListener('click', () => proofInput.click());
      proofInput.addEventListener('change', () => {
        if (proofName) {
          proofName.textContent = proofInput.files?.[0]
            ? `Archivo: ${proofInput.files[0].name}`
            : '';
        }
      });
    }

    function togglePaymentUI() {
      const method = form.paymentMethod.value;
      if (cardSection) cardSection.hidden = method !== 'card';
      if (bankSection) bankSection.hidden = true;
      if (sandboxNotice) sandboxNotice.hidden = method !== 'sandbox';
      if (proofArea) proofArea.hidden = method === 'card';

      if (method === 'card') {
        mountCardElement();
      } else {
        destroyCardElement();
      }

      refreshBankPanels();
    }

    paymentRadios.forEach((radio) => radio.addEventListener('change', togglePaymentUI));
    countrySelect.addEventListener('change', () => {
      refreshSummary();
      refreshBankPanels();
    });

    togglePaymentUI();
    form.addEventListener('submit', submitCheckout);
    window.addEventListener('cart:updated', refreshSummary);
    window.addEventListener('cart:updated', refreshBankPanels);
    window.addEventListener('cds:cart-updated', () => {
      refreshSummary();
      refreshBankPanels();
    });

    const whatsappBtn = document.getElementById('whatsapp-checkout-btn');
    if (whatsappBtn) {
      whatsappBtn.addEventListener('click', () => {
        const formData = getCheckoutFormData();
        const summary = safeGetCartSummary(formData?.country || countrySelect.value || 'US');
        if (summary.isEmpty) {
          showToast('Tu carrito está vacío.', 'error');
          return;
        }
        const message = buildCheckoutWhatsAppPreview(formData || {}, summary);
        openWhatsAppWithMessage(message);
      });
    }
  } catch (err) {
    console.error('[Checkout] init error:', err);
    showCheckoutFatalError(
      err.message || 'Error al inicializar el checkout. Recarga la página e intenta de nuevo.'
    );
  }
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    initCheckoutPage,
    submitCheckout,
    buildOrderPayload,
    processStripePayment,
  };
}

