/**
 * Checkout de una sola página.
 *
 * Cambios de fondo respecto a la versión anterior:
 *
 *  - Los importes los calcula y firma el servidor. Esta página muestra lo que
 *    el servidor dice, y reenvía la cotización firmada al pagar. Antes el
 *    navegador enviaba el importe a cobrar, lo que permitía pagar un dólar por
 *    un pedido de dos mil.
 *  - Los métodos de pago se piden al servidor. Antes la web decidía sola si
 *    mostrar "tarjeta" mirando una clave que era un texto de relleno.
 *  - No hay modo de emergencia silencioso. Si el pedido no llega al servidor,
 *    el comprador lo sabe. Antes se guardaba en localStorage y se le decía que
 *    todo había ido bien.
 */

(function () {
  'use strict';

  const API = '/api/commerce';
  const QUOTE_DEBOUNCE_MS = 350;

  /** @type {{ config: object|null, quote: object|null, quoteToken: string|null, method: string|null, idempotencyKey: string|null, submitting: boolean }} */
  const state = {
    config: null,
    quote: null,
    quoteToken: null,
    method: null,
    idempotencyKey: null,
    submitting: false,
  };

  const el = (id) => document.getElementById(id);

  function money(cents, currency) {
    return new Intl.NumberFormat('es-DO', {
      style: 'currency',
      currency: currency || 'USD',
      minimumFractionDigits: 2,
    }).format((Number(cents) || 0) / 100);
  }

  function safe(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
  }

  function showAlert(message, tone) {
    const box = el('co-alert');
    if (!box) return;
    box.hidden = false;
    box.textContent = message;
    box.className = `co__alert co__alert--${tone || 'error'}`;
    box.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function clearAlert() {
    const box = el('co-alert');
    if (box) box.hidden = true;
  }

  function newIdempotencyKey() {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    return [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
  }

  // ------------------------------------------------------------- carrito

  /** Convierte el carrito local al formato mínimo que espera el servidor. */
  function cartPayload() {
    if (typeof getCartItems !== 'function') return [];
    return getCartItems().map((item) => ({
      productId: item.productId,
      unitType: item.unitType,
      quantity: item.quantity,
    }));
  }

  // -------------------------------------------------------------- red

  async function apiFetch(path, options) {
    const response = await fetch(`${API}${path}`, {
      headers: { 'Content-Type': 'application/json', ...(options && options.headers) },
      ...options,
    });

    const text = await response.text();
    let body = {};
    try {
      body = text ? JSON.parse(text) : {};
    } catch {
      // Una respuesta que no es JSON casi siempre significa que Nginx no está
      // enrutando /api/commerce al servicio. Merece un mensaje explícito.
      throw new Error(
        'El servicio de pagos no está respondiendo. Escríbenos por WhatsApp y completamos tu pedido.'
      );
    }

    if (!response.ok) {
      const error = new Error(body.error || 'No pudimos completar la operación.');
      error.code = body.code;
      error.retryable = body.retryable;
      error.status = response.status;
      throw error;
    }

    return body;
  }

  // ------------------------------------------------------------ resumen

  function renderItems() {
    const container = el('co-items');
    if (!container || !state.quote) return;

    container.innerHTML = state.quote.lines
      .map(
        (line) => `
        <article class="co-item" data-product="${safe(line.productId)}" data-unit="${safe(line.unitType)}">
          <div class="co-item__body">
            <p class="co-item__name">${safe(line.name)}</p>
            <p class="co-item__meta">${safe(line.packagingLabel)} · ${safe(line.displayLabel)}</p>
            <div class="co-item__qty">
              <button type="button" data-action="dec" aria-label="Quitar uno">−</button>
              <span>${line.quantity}</span>
              <button type="button" data-action="inc" aria-label="Añadir uno">+</button>
              <button type="button" class="co-item__remove" data-action="remove">Eliminar</button>
            </div>
          </div>
          <div class="co-item__price">${money(line.lineTotalCents, state.quote.currency)}</div>
        </article>`
      )
      .join('');
  }

  function renderTotals() {
    const q = state.quote;
    if (!q) return;

    el('co-subtotal').textContent = money(q.subtotalCents, q.currency);
    el('co-shipping').textContent = money(q.shippingCents, q.currency);
    el('co-total').textContent = money(q.totalCents, q.currency);
    el('co-zone').textContent = q.shipping.zone ? `(${q.shipping.zone})` : '';
    el('co-units').textContent = String(q.totalUnits);
    el('co-boxes').textContent = `${q.shippingBoxes} / ${q.shipping.maxBoxes}`;
    el('co-eta').textContent = `${q.shipping.estimatedDays} días`;
  }

  function setBusy(busy) {
    const button = el('co-submit');
    if (!button) return;
    state.submitting = busy;
    button.disabled = busy || !state.quoteToken;
    button.textContent = busy ? 'Procesando…' : 'Confirmar pedido';
  }

  // ---------------------------------------------------------- cotización

  let quoteTimer = null;

  function scheduleQuote() {
    clearTimeout(quoteTimer);
    quoteTimer = setTimeout(refreshQuote, QUOTE_DEBOUNCE_MS);
  }

  async function refreshQuote() {
    const items = cartPayload();
    const country = el('co-form').country.value;

    if (!items.length) {
      el('co-empty').hidden = false;
      el('co-layout').hidden = true;
      return;
    }

    try {
      const data = await apiFetch('/quote', {
        method: 'POST',
        body: JSON.stringify({ items, country }),
      });

      state.quote = data.quote;
      state.quoteToken = data.quoteToken;
      // Una cotización nueva es un intento nuevo: la clave de idempotencia
      // solo debe reutilizarse para reintentar exactamente el mismo pago.
      state.idempotencyKey = newIdempotencyKey();

      el('co-boxes-warning').hidden = true;
      renderItems();
      renderTotals();
      clearAlert();
      setBusy(false);
    } catch (error) {
      state.quote = null;
      state.quoteToken = null;
      setBusy(false);

      if (error.code === 'DHL_BOX_LIMIT') {
        const warning = el('co-boxes-warning');
        warning.hidden = false;
        warning.textContent = error.message;
      }
      showAlert(error.message);
    }
  }

  // ----------------------------------------------------- métodos de pago

  function renderPaymentMethods() {
    const container = el('co-methods');
    const methods = (state.config && state.config.paymentMethods) || [];

    if (!methods.length) {
      container.innerHTML =
        '<p class="co-methods__empty">No hay métodos de pago disponibles ahora mismo. Escríbenos por WhatsApp y completamos tu pedido.</p>';
      return;
    }

    container.innerHTML = methods
      .map(
        (method, index) => `
        <label class="co-method${method.id === 'paypal' ? ' co-method--paypal' : ''}">
          <input type="radio" name="paymentMethod" value="${safe(method.id)}" ${index === 0 ? 'checked' : ''} />
          <span class="co-method__body">
            <strong>${method.id === 'paypal' ? paypalWordmark() : safe(method.label)}</strong>
            <small>${safe(methodHint(method.id, method.ready))}</small>
          </span>
        </label>`
      )
      .join('');

    state.method = methods[0].id;

    container.querySelectorAll('input[name="paymentMethod"]').forEach((input) => {
      input.addEventListener('change', () => {
        state.method = input.value;
        renderMethodDetail();
      });
    });

    renderMethodDetail();
  }

  function paypalWordmark() {
    return `<span class="co-paypal-wordmark" aria-label="PayPal"><span>Pay</span><span>Pal</span></span>`;
  }

  function methodHint(id, ready) {
    if (id === 'cardnet') return 'Visa, Mastercard — procesado por CardNET con 3D Secure';
    if (id === 'bank_transfer') return 'Banreservas o BHD, con referencia única de pedido';
    if (id === 'paypal') {
      return ready
        ? 'Paga con tu cuenta PayPal, sin compartir datos de tarjeta con este sitio'
        : 'Paga con tu cuenta PayPal — disponible en breve';
    }
    if (id === 'sandbox') return 'Simula una compra completa sin cargo real';
    return '';
  }

  function currentMethod() {
    const methods = (state.config && state.config.paymentMethods) || [];
    return methods.find((m) => m.id === state.method) || null;
  }

  function renderMethodDetail() {
    const panel = el('co-method-detail');
    const method = currentMethod();
    if (!panel || !method) return;

    if (method.id === 'bank_transfer') {
      panel.hidden = false;
      panel.innerHTML = renderBankDetails(method.client);
      syncSubmitVisibility();
      return;
    }

    if (method.id === 'cardnet') {
      panel.hidden = false;
      panel.innerHTML = `
        <p class="co-note">
          Al confirmar se abrirá la ventana segura de CardNET para introducir tu tarjeta.
          Los datos viajan directamente al banco: este sitio nunca los recibe ni los guarda.
        </p>
        <button type="button" id="co-card-trigger" class="co-hidden-trigger" aria-hidden="true" tabindex="-1"></button>`;
      loadCardnet(method.client);
      syncSubmitVisibility();
      return;
    }

    if (method.id === 'paypal') {
      panel.hidden = false;
      panel.innerHTML = renderPaypalDetail(method);
      mountPaypal(method);
      syncSubmitVisibility();
      return;
    }

    panel.hidden = false;
    panel.innerHTML = '<p class="co-note">Modo de prueba: no se realizará ningún cargo real.</p>';
    syncSubmitVisibility();
  }

  function syncSubmitVisibility() {
    const button = el('co-submit');
    if (!button) return;
    const paypal = state.method === 'paypal';
    button.hidden = paypal;
    button.setAttribute('aria-hidden', paypal ? 'true' : 'false');
  }

  function renderPaypalDetail(method) {
    const ready = Boolean(method.ready && method.client && method.client.clientId);
    const hint = ready
      ? 'Al pulsar el botón se abrirá la ventana segura de PayPal. Este sitio nunca recibe los datos de tu tarjeta ni de tu cuenta.'
      : 'El botón de PayPal ya está en el checkout. El cobro se habilitará en breve; mientras tanto puede pagar con tarjeta o transferencia.';

    return `
      <div class="co-paypal">
        <p class="co-note">${hint}</p>
        <div id="co-paypal-buttons" class="co-paypal-buttons">
          <button type="button" class="co-paypal-btn" id="co-paypal-static" ${ready ? '' : 'disabled'} aria-disabled="${ready ? 'false' : 'true'}">
            ${paypalWordmark()}
          </button>
        </div>
      </div>`;
  }

  function renderBankDetails(bank) {
    if (!bank) return '';
    const accounts = (bank.accounts || [])
      .map(
        (account) => `
        <div class="co-bank__account">
          <p class="co-bank__bank">${safe(account.bankName)}</p>
          <dl>
            <div><dt>Titular</dt><dd>${safe(account.accountHolder)}</dd></div>
            <div><dt>Tipo</dt><dd>${safe(account.accountType)}</dd></div>
            <div><dt>Cuenta</dt><dd><code>${safe(account.accountNumber)}</code></dd></div>
          </dl>
        </div>`
      )
      .join('');

    return `
      <div class="co-bank">
        <p class="co-note">
          Al confirmar recibirás una referencia única. Ponla en el concepto de la
          transferencia y envía el comprobante a
          <strong>${safe(bank.email)}</strong> dentro de ${safe(bank.proofDeadlineHours)} horas.
        </p>
        ${accounts}
      </div>`;
  }

  // ------------------------------------------------------ tarjeta CardNET

  let cardnetReady = null;

  /**
   * Carga la librería de CardNET solo cuando hace falta. Es la única forma de
   * que el iframe de captura viva en su dominio y el PAN no pase por aquí.
   */
  function loadCardnet(client) {
    if (!client || cardnetReady) return cardnetReady;

    cardnetReady = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = client.scriptUrl;
      script.async = true;
      script.onload = () => {
        try {
          window.PWCheckout.SetProperties({
            name: 'Cazador de Sueños Cigars',
            description: 'Compra de puros premium',
            currency: client.currency,
            lang: 'ESP',
            form_id: 'co-form',
            checkout_card: 1,
            autoSubmit: 'false',
            empty: 'true',
          });
          window.PWCheckout.Bind('tokenCreated', onCardTokenCreated);
          window.PWCheckout.AddActionButton('co-card-trigger');
          resolve(window.PWCheckout);
        } catch (error) {
          reject(error);
        }
      };
      script.onerror = () =>
        reject(new Error('No pudimos cargar el formulario de tarjeta. Usa transferencia bancaria.'));
      document.head.appendChild(script);
    });

    cardnetReady.catch((error) => {
      cardnetReady = null;
      showAlert(error.message);
    });

    return cardnetReady;
  }

  function onCardTokenCreated(token) {
    const trxToken = token && (token.TokenId || token.tokenId || token);
    if (!trxToken) {
      setBusy(false);
      showAlert('No recibimos los datos de la tarjeta. Inténtalo de nuevo.');
      return;
    }
    submitOrder({ trxToken });
  }

  // ----------------------------------------------------------- PayPal

  let paypalSdkReady = null;
  let paypalButtons = null;

  /**
   * Si hay Client ID, sustituye el botón estático por los Smart Payment Buttons
   * oficiales. Si no, el botón dorado permanece visible e inerte: el componente
   * ya está en su sitio para cuando lleguen las credenciales.
   */
  function mountPaypal(method) {
    const ready = Boolean(method && method.ready && method.client && method.client.clientId);
    if (!ready) return;

    loadPaypalSdk(method.client)
      .then(() => renderPaypalButtons())
      .catch((error) => showAlert(error.message));
  }

  function loadPaypalSdk(client) {
    if (window.paypal) return Promise.resolve(window.paypal);
    if (paypalSdkReady) return paypalSdkReady;

    paypalSdkReady = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = client.scriptUrl;
      script.async = true;
      script.onload = () => {
        if (!window.paypal) {
          reject(new Error('No pudimos cargar PayPal. Use transferencia bancaria.'));
          return;
        }
        resolve(window.paypal);
      };
      script.onerror = () => {
        paypalSdkReady = null;
        reject(new Error('No pudimos cargar PayPal. Use transferencia bancaria.'));
      };
      document.head.appendChild(script);
    });

    return paypalSdkReady;
  }

  function renderPaypalButtons() {
    const host = el('co-paypal-buttons');
    if (!host || !window.paypal) return;

    host.innerHTML = '';
    if (paypalButtons && typeof paypalButtons.close === 'function') {
      try {
        paypalButtons.close();
      } catch {
        /* el SDK a veces ya desmontó el botón */
      }
    }

    paypalButtons = window.paypal.Buttons({
      fundingSource: window.paypal.FUNDING.PAYPAL,
      style: { layout: 'vertical', color: 'gold', shape: 'rect', label: 'paypal', height: 45 },
      createOrder: async () => {
        const data = readForm();
        const errors = localErrors(data);
        if (errors.length) {
          showAlert(errors[0]);
          throw new Error('validacion');
        }
        if (!state.quoteToken) {
          showAlert('El precio del pedido caducó. Recargamos el resumen.');
          refreshQuote();
          throw new Error('cotizacion');
        }
        const created = await apiFetch('/paypal/orders', {
          method: 'POST',
          body: JSON.stringify({ quoteToken: state.quoteToken }),
        });
        return created.paypalOrderId;
      },
      onApprove: async (data) => {
        await submitOrder({ paypalOrderId: data.orderID });
      },
      onCancel: () => {
        setBusy(false);
        showAlert('Cancelaste el pago en PayPal. Puedes intentarlo de nuevo o elegir otro método.', 'info');
      },
      onError: () => {
        setBusy(false);
        showAlert('PayPal no pudo completar el pago. Prueba de nuevo o usa transferencia bancaria.');
      },
    });

    return paypalButtons.render(host);
  }

  // ------------------------------------------------------------- envío

  function readForm() {
    const form = el('co-form');
    return {
      customer: {
        fullName: form.fullName.value.trim(),
        email: form.email.value.trim(),
        phone: form.phone.value.trim(),
      },
      shipping: {
        address: form.address.value.trim(),
        city: form.city.value.trim(),
        state: form.state.value.trim(),
        postalCode: form.postalCode.value.trim(),
        country: form.country.value,
      },
      notes: form.notes.value.trim(),
      acceptances: {
        finalSale: form.acceptFinalSale.checked,
        customs: form.acceptCustoms.checked,
      },
    };
  }

  /** Validación local: solo para dar respuesta inmediata. El servidor revalida. */
  function localErrors(data) {
    const errors = [];
    if (data.customer.fullName.length < 3) errors.push('Escribe tu nombre completo.');
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(data.customer.email)) {
      errors.push('Escribe un correo electrónico válido.');
    }
    if (data.customer.phone.replace(/\D/g, '').length < 7) {
      errors.push('Escribe un teléfono de contacto para la entrega.');
    }
    if (data.shipping.address.length < 5) errors.push('Escribe la dirección de entrega.');
    if (data.shipping.city.length < 2) errors.push('Escribe la ciudad de entrega.');
    if (!data.shipping.country) errors.push('Selecciona el país de destino.');
    if (!data.acceptances.finalSale) errors.push('Debes aceptar la política de venta final.');
    if (!data.acceptances.customs) errors.push('Debes aceptar la responsabilidad aduanera.');
    return errors;
  }

  async function submitOrder(paymentPayload) {
    if (!state.quoteToken) {
      showAlert('El precio del pedido caducó. Recargamos el resumen, revísalo y confirma otra vez.');
      refreshQuote();
      return;
    }

    setBusy(true);
    clearAlert();

    const data = readForm();

    try {
      const result = await apiFetch('/orders', {
        method: 'POST',
        headers: { 'Idempotency-Key': state.idempotencyKey },
        body: JSON.stringify({
          quoteToken: state.quoteToken,
          paymentMethod: state.method,
          paymentPayload: paymentPayload || {},
          ...data,
        }),
      });

      if (typeof clearCart === 'function') clearCart();

      const url = new URL('order-confirmation.html', window.location.href);
      url.searchParams.set('ref', result.reference);
      url.searchParams.set('t', result.accessToken);
      window.location.assign(url.toString());
    } catch (error) {
      setBusy(false);

      // Una cotización caducada se puede rehacer sola; el resto necesita al
      // comprador. En ningún caso reintentamos un cobro automáticamente.
      if (error.code === 'QUOTE_EXPIRED' || error.code === 'QUOTE_INVALID') {
        showAlert('El precio se actualizó mientras completabas el formulario. Revísalo y confirma otra vez.');
        refreshQuote();
        return;
      }

      showAlert(error.message);
      window.dispatchEvent(
        new CustomEvent('checkout:error', {
          detail: { code: error.code, message: error.message, method: state.method },
        })
      );
    }
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (state.submitting) return;

    const data = readForm();
    const errors = localErrors(data);
    if (errors.length) {
      showAlert(errors[0]);
      return;
    }

    if (!state.method) {
      showAlert('Elige un método de pago.');
      return;
    }

    if (state.method === 'cardnet') {
      const method = currentMethod();
      setBusy(true);
      try {
        await loadCardnet(method.client);
        // Abre el iframe de CardNET. El pedido se envía en 'tokenCreated'.
        el('co-card-trigger').click();
      } catch {
        setBusy(false);
      }
      return;
    }

    if (state.method === 'paypal') {
      showAlert('Usa el botón de PayPal para completar el pago.');
      return;
    }

    submitOrder({});
  }

  // ----------------------------------------------------------- arranque

  function renderStaticCopy() {
    if (typeof SALES_POLICY !== 'undefined') {
      el('co-policy-sale').textContent = SALES_POLICY.checkoutText;
    }
    if (typeof CUSTOMS_DISCLAIMER !== 'undefined') {
      el('co-policy-customs').textContent = CUSTOMS_DISCLAIMER.checkoutText;
    }
    if (typeof APP_CONFIG !== 'undefined' && APP_CONFIG.trust) {
      el('co-trust-1').textContent = APP_CONFIG.trust.authenticity;
      el('co-trust-2').textContent = APP_CONFIG.trust.delivery;
      el('co-trust-3').textContent = APP_CONFIG.trust.policy;
    }
  }

  function fillCountries(countries) {
    const select = el('co-form').country;
    const preferred =
      typeof getPreferredShippingCountry === 'function' ? getPreferredShippingCountry() : 'US';

    select.innerHTML = countries
      .map(
        (country) =>
          `<option value="${safe(country.code)}"${country.code === preferred ? ' selected' : ''}>${safe(country.name)}</option>`
      )
      .join('');
  }

  function bindEvents() {
    const form = el('co-form');

    form.addEventListener('submit', onSubmit);
    form.country.addEventListener('change', scheduleQuote);

    el('co-items').addEventListener('click', (event) => {
      const button = event.target.closest('[data-action]');
      if (!button) return;
      const item = button.closest('.co-item');
      const lineId = `${item.dataset.product}::${item.dataset.unit}`;
      const action = button.dataset.action;

      if (action === 'remove') {
        removeFromCart(lineId);
      } else {
        const line = state.quote.lines.find(
          (l) => l.productId === item.dataset.product && l.unitType === item.dataset.unit
        );
        const next = line.quantity + (action === 'inc' ? 1 : -1);
        const result = updateCartQuantity(lineId, next);
        if (!result.success) {
          showAlert(result.error);
          return;
        }
      }
      refreshQuote();
    });

    el('co-whatsapp').addEventListener('click', () => {
      const phone = (state.config && state.config.contact && state.config.contact.whatsapp) || '';
      const lines = state.quote
        ? state.quote.lines.map((l) => `• ${l.name} — ${l.displayLabel}`).join('\n')
        : '';
      const total = state.quote ? money(state.quote.totalCents, state.quote.currency) : '';
      const message = `Hola, quiero completar este pedido:\n${lines}\n\nTotal estimado: ${total}`;
      window.open(`https://wa.me/${phone}?text=${encodeURIComponent(message)}`, '_blank', 'noopener');
    });

    window.addEventListener('cart:updated', scheduleQuote);
    window.addEventListener('cds:cart-updated', scheduleQuote);
  }

  async function init() {
    renderStaticCopy();

    if (typeof initCartPersistence === 'function') initCartPersistence();

    if (!cartPayload().length) {
      el('co-empty').hidden = false;
      return;
    }

    el('co-layout').hidden = false;

    try {
      state.config = await apiFetch('/config', { method: 'GET' });
    } catch (error) {
      el('co-layout').hidden = true;
      showAlert(error.message);
      return;
    }

    fillCountries(state.config.countries);
    renderPaymentMethods();
    bindEvents();
    await refreshQuote();
  }

  document.addEventListener('DOMContentLoaded', () => {
    init().catch((error) => {
      console.error('[checkout]', error);
      showAlert('No pudimos iniciar el checkout. Recarga la página o escríbenos por WhatsApp.');
    });
  });

  // Superficie mínima para el asistente de IA, que solo lee.
  window.CDS_CHECKOUT = {
    getState() {
      return {
        method: state.method,
        hasQuote: Boolean(state.quoteToken),
        totalCents: state.quote ? state.quote.totalCents : 0,
        currency: state.quote ? state.quote.currency : 'USD',
        country: state.quote ? state.quote.country : null,
        boxes: state.quote ? state.quote.shippingBoxes : 0,
        availableMethods: ((state.config && state.config.paymentMethods) || []).map((m) => m.id),
      };
    },
  };
})();
