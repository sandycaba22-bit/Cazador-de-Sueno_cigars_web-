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
    orderReference: null,
    orderAccessToken: null,
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
    // El botón se habilita en cuanto hay cotización: la validación de campos
    // ocurre al confirmar, no bloquea la UI de pago.
    button.disabled = Boolean(busy) || !state.quoteToken;
    button.textContent = busy ? 'Procesando…' : 'Confirmar pedido';
  }

  function syncPaymentUi() {
    setBusy(state.submitting);
    syncSubmitVisibility();
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
    const methods = ((state.config && state.config.paymentMethods) || []).filter(
      (method) => method && method.id !== 'sandbox'
    );

    if (!methods.length) {
      container.innerHTML =
        '<p class="co-methods__empty">No hay métodos de pago disponibles ahora mismo.</p>';
      return;
    }

    container.innerHTML = methods
      .map(
        (method, index) => `
        <label class="co-method${method.id === 'paypal' ? ' co-method--paypal' : ''}">
          <input type="radio" name="paymentMethod" value="${safe(method.id)}" ${index === 0 ? 'checked' : ''} />
          <span class="co-method__body">
            <strong>${method.id === 'paypal' ? paypalWordmark() : safe(method.label)}</strong>
            <small>${safe(methodHint(method.id))}</small>
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

  function methodHint(id) {
    if (id === 'cardnet') return 'Visa / Mastercard';
    if (id === 'bank_transfer') return 'Banreservas · BHD';
    if (id === 'paypal') return 'USD';
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
      bindBankWhatsApp();
      syncSubmitVisibility();
      return;
    }

    if (method.id === 'cardnet') {
      panel.hidden = false;
      panel.innerHTML = `
        <p class="co-note">Ventana segura de CardNET al confirmar.</p>
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

    panel.hidden = true;
    panel.innerHTML = '';
    syncSubmitVisibility();
  }

  function syncSubmitVisibility() {
    const button = el('co-submit');
    if (!button) return;
    const paypal = state.method === 'paypal';
    button.hidden = paypal;
    button.setAttribute('aria-hidden', paypal ? 'true' : 'false');
  }

  function renderPaypalDetail(_method) {
    return `
      <div class="co-paypal">
        <div id="co-paypal-buttons" class="co-paypal-buttons" aria-label="Pagar con PayPal en USD">
          <p class="co-note co-paypal__loading">Cargando PayPal…</p>
        </div>
      </div>`;
  }

  function accountRegion(account) {
    const blob = `${account.bankName || ''} ${account.note || ''} ${account.currency || ''} ${account.accountType || ''}`.toLowerCase();
    if (/\b(usa|ee\.?uu|united states|ach|zelle|routing)\b/.test(blob)) return 'US';
    if (account.currency === 'USD' && /\b(chase|wells|bank of america|us bank)\b/.test(blob)) return 'US';
    return 'DO';
  }

  function renderAccountCard(account) {
    return `
        <div class="co-bank__account">
          <p class="co-bank__bank">${safe(account.bankName)}</p>
          <dl>
            <div><dt>Titular</dt><dd>${safe(account.accountHolder)}</dd></div>
            <div><dt>Tipo</dt><dd>${safe(account.accountType)}</dd></div>
            <div><dt>Cuenta</dt><dd><code>${safe(account.accountNumber)}</code></dd></div>
            ${account.currency ? `<div><dt>Moneda</dt><dd>${safe(account.currency)}</dd></div>` : ''}
          </dl>
        </div>`;
  }

  function houseWhatsApp() {
    const fromConfig =
      (state.config && state.config.contact && state.config.contact.whatsapp) ||
      (typeof APP_CONFIG !== 'undefined' && APP_CONFIG.whatsapp && APP_CONFIG.whatsapp.phone) ||
      '18094645016';
    return String(fromConfig).replace(/\D/g, '');
  }

  function orderRefLabel() {
    return state.orderReference || '';
  }

  function bankWhatsAppMessage(reference) {
    const q = state.quote;
    const total = q ? money(q.totalCents, q.currency) : '';
    const lines = q
      ? q.lines.map((l) => `• ${l.name} — ${l.displayLabel}`).join('\n')
      : '';
    const name = (el('co-form') && el('co-form').fullName && el('co-form').fullName.value.trim()) || '';
    const ref = reference || orderRefLabel();
    return [
      'Hola, envío el comprobante de mi transferencia bancaria.',
      ref ? `Referencia del pedido: ${ref}` : '',
      name ? `Nombre: ${name}` : '',
      total ? `Total: ${total}` : '',
      lines ? `Pedido:\n${lines}` : '',
    ]
      .filter(Boolean)
      .join('\n');
  }

  function openBankWhatsApp(reference) {
    const phone = houseWhatsApp();
    if (!phone) {
      showAlert('No hay número de WhatsApp configurado.');
      return;
    }
    window.open(
      `https://wa.me/${phone}?text=${encodeURIComponent(bankWhatsAppMessage(reference))}`,
      '_blank',
      'noopener'
    );
  }

  function bindBankWhatsApp() {
    const link = el('co-bank-whatsapp');
    if (!link) return;
    const phone = houseWhatsApp();
    link.href = `https://wa.me/${phone}?text=${encodeURIComponent(bankWhatsAppMessage(orderRefLabel()))}`;
    link.onclick = async (event) => {
      event.preventDefault();
      if (state.submitting) return;

      const data = readForm();
      const basics = localErrors(data, { requireTerms: false });
      if (basics.length) {
        showAlert(basics[0]);
        return;
      }
      if (!data.acceptances.finalSale) {
        showAlert('Marca la casilla de condiciones de venta para generar la referencia.');
        return;
      }

      // Abrir la pestaña en el gesto del click: tras el await el navegador
      // bloquea window.open() y el botón de WhatsApp parece “roto”.
      const waWindow = window.open('about:blank', '_blank');

      try {
        setBusy(true);
        state.method = 'bank_transfer';
        const result = await createOrderPayload({});
        if (!result) {
          if (waWindow && !waWindow.closed) waWindow.close();
          setBusy(false);
          return;
        }
        const waUrl = `https://wa.me/${houseWhatsApp()}?text=${encodeURIComponent(
          bankWhatsAppMessage(result.reference)
        )}`;
        if (waWindow && !waWindow.closed) {
          waWindow.location.replace(waUrl);
        } else {
          // Si el popup sigue bloqueado, el enlace de confirmación abre WhatsApp.
          window.open(waUrl, '_blank', 'noopener');
        }
        goToConfirmation(result);
      } catch (error) {
        if (waWindow && !waWindow.closed) waWindow.close();
        setBusy(false);
        showAlert(error.message || 'No pudimos preparar el pedido.');
      }
    };
  }

  function renderBankDetails(bank) {
    if (!bank) return '';
    const accounts = bank.accounts || [];
    const dominican = accounts.filter((account) => accountRegion(account) === 'DO');
    const american = accounts.filter((account) => accountRegion(account) === 'US');
    const beneficiary = bank.beneficiary || {};
    const email = bank.email || '';
    const ref = orderRefLabel();

    const doBlock = dominican.length
      ? `
      <div class="co-bank__region">
        <h3 class="co-bank__region-title">República Dominicana</h3>
        ${dominican.map(renderAccountCard).join('')}
      </div>`
      : '';

    const usBlock =
      american.length || beneficiary.name
        ? `
      <div class="co-bank__region">
        <h3 class="co-bank__region-title">Estados Unidos / internacional</h3>
        ${american.map(renderAccountCard).join('')}
        ${
          beneficiary.name
            ? `<div class="co-bank__account">
                <p class="co-bank__bank">Beneficiario</p>
                <dl>
                  <div><dt>Nombre</dt><dd>${safe(beneficiary.name)}</dd></div>
                  ${beneficiary.taxId ? `<div><dt>RNC</dt><dd>${safe(beneficiary.taxId)}</dd></div>` : ''}
                </dl>
              </div>`
            : ''
        }
      </div>`
        : '';

    return `
      <div class="co-bank">
        <p class="co-note">
          ${ref ? `Referencia: <strong>${safe(ref)}</strong> · ` : ''}Usa la referencia en el concepto${email ? ` y envía el comprobante a <strong>${safe(email)}</strong>` : ''}.
        </p>
        ${doBlock}
        ${usBlock}
        <a
          id="co-bank-whatsapp"
          class="co-btn co-btn--whatsapp co-btn--block"
          href="#"
          target="_blank"
          rel="noopener noreferrer"
        >Enviar comprobante por WhatsApp</a>
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
   * Monta los Smart Payment Buttons oficiales en cuanto hay Client ID del servidor.
   * No bloquea la UI con mensajes de "no disponible".
   */
  function mountPaypal(method) {
    const client = method && method.client;
    const canLoad = Boolean(client && (client.scriptUrl || client.clientId));
    if (!canLoad) {
      // Reintenta con lo que venga de /config tras un refresh.
      const fromConfig = ((state.config && state.config.paymentMethods) || []).find((m) => m.id === 'paypal');
      if (fromConfig && fromConfig.client && (fromConfig.client.scriptUrl || fromConfig.client.clientId)) {
        return mountPaypal(fromConfig);
      }
      const host = el('co-paypal-buttons');
      if (host) {
        host.innerHTML =
          '<p class="co-note">Conectando con PayPal… Si tarda, recarga la página.</p>';
      }
      return;
    }

    const sdkClient = {
      ...client,
      scriptUrl:
        client.scriptUrl ||
        `https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(client.clientId)}&currency=${encodeURIComponent(client.currency || 'USD')}&intent=capture&components=buttons`,
    };

    loadPaypalSdk(sdkClient)
      .then(() => renderPaypalButtons())
      .catch((error) => {
        const host = el('co-paypal-buttons');
        if (host) host.innerHTML = `<p class="co-note">${safe(error.message)}</p>`;
      });
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
          reject(new Error('No pudimos cargar PayPal. Prueba de nuevo o usa transferencia.'));
          return;
        }
        resolve(window.paypal);
      };
      script.onerror = () => {
        paypalSdkReady = null;
        reject(new Error('No pudimos cargar PayPal. Prueba de nuevo o usa transferencia.'));
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
        // Solo datos de contacto/envío: las condiciones se piden al capturar.
        const data = readForm();
        const errors = localErrors(data, { requireTerms: false });
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
        const formData = readForm();
        if (!formData.acceptances.finalSale) {
          showAlert('Marca la casilla de condiciones de venta para completar el pago.');
          setBusy(false);
          return;
        }
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
        // Un solo checkbox en UI → ambas aceptaciones para el contrato del servidor.
        finalSale: form.acceptTerms.checked,
        customs: form.acceptTerms.checked,
      },
    };
  }

  /**
   * Validación local inmediata.
   * @param {object} data
   * @param {{ requireTerms?: boolean }} [opts]
   */
  function localErrors(data, opts = {}) {
    const requireTerms = opts.requireTerms !== false;
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
    if (requireTerms && !data.acceptances.finalSale) {
      errors.push('Debes aceptar las condiciones de venta.');
    }
    return errors;
  }

  function goToConfirmation(result) {
    if (typeof clearCart === 'function') clearCart();
    const url = new URL('order-confirmation.html', window.location.href);
    url.searchParams.set('ref', result.reference);
    url.searchParams.set('t', result.accessToken);
    window.location.assign(url.toString());
  }

  /** Crea el pedido en el servidor. Devuelve el cuerpo o null si falló con alerta. */
  async function createOrderPayload(paymentPayload) {
    if (!state.quoteToken) {
      showAlert('El precio del pedido caducó. Recargamos el resumen, revísalo y confirma otra vez.');
      refreshQuote();
      return null;
    }

    if (state.orderReference && state.orderAccessToken && state.method === 'bank_transfer') {
      return {
        reference: state.orderReference,
        accessToken: state.orderAccessToken,
      };
    }

    const data = readForm();
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

    state.orderReference = result.reference;
    state.orderAccessToken = result.accessToken;
    return result;
  }

  async function submitOrder(paymentPayload) {
    setBusy(true);
    clearAlert();

    try {
      const result = await createOrderPayload(paymentPayload);
      if (!result) {
        setBusy(false);
        return;
      }
      goToConfirmation(result);
    } catch (error) {
      setBusy(false);

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
    const terms = el('co-policy-terms');
    if (terms && typeof SALES_POLICY !== 'undefined') {
      terms.textContent = SALES_POLICY.checkoutText;
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

    // Al completar los datos básicos, el CTA de pago queda listo (con cotización).
    form.addEventListener('input', () => syncPaymentUi());
    form.addEventListener('change', () => syncPaymentUi());

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

    window.addEventListener('cart:updated', scheduleQuote);
    window.addEventListener('cds:cart-updated', scheduleQuote);
  }

  function prefetchPaypalSdk() {
    const paypal = ((state.config && state.config.paymentMethods) || []).find((m) => m.id === 'paypal');
    if (!paypal || !paypal.client) return;
    if (!paypal.client.scriptUrl && !paypal.client.clientId) return;
    loadPaypalSdk({
      scriptUrl:
        paypal.client.scriptUrl ||
        `https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(paypal.client.clientId)}&currency=${encodeURIComponent(paypal.client.currency || 'USD')}&intent=capture&components=buttons`,
    }).catch(() => {
      /* se reintenta al seleccionar PayPal */
    });
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
    prefetchPaypalSdk();
    bindEvents();
    await refreshQuote();
    syncPaymentUi();
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
