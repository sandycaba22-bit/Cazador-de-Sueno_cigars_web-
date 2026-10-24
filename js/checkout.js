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
  const PAYPAL_SDK_HOST_LIVE = 'https://www.paypal.com/sdk/js';
  const PAYPAL_SDK_HOST_SANDBOX = 'https://www.sandbox.paypal.com/sdk/js';
  const PAYPAL_BLOCKED_ERROR = 'PAYPAL_CHECKOUT_BLOCKED';
  const BANK_TRANSFER_WHATSAPP = '18094645016';
  const PAYPAL_CONTAINER_ID = 'paypal-button-container';
  const REQUEST_TIMEOUT_MS = 45000;
  const SDK_TIMEOUT_MS = 15000;

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

  function tt(path, fallback) {
    try {
      if (typeof LanguageSwitcher !== 'undefined' && typeof LanguageSwitcher.t === 'function') {
        const value = LanguageSwitcher.t(path);
        if (typeof value === 'string' && value) return value;
      }
    } catch (_) {
      /* ignore */
    }
    return fallback;
  }

  function money(cents, currency) {
    const lang =
      typeof LanguageSwitcher !== 'undefined' && LanguageSwitcher.getCurrentLanguage
        ? LanguageSwitcher.getCurrentLanguage()
        : 'es';
    const locale = lang === 'en' ? 'en-US' : 'es-DO';
    return new Intl.NumberFormat(locale, {
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
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    let response;
    let text;
    try {
      response = await fetch(`${API}${path}`, {
        ...options,
        headers: { 'Content-Type': 'application/json', ...(options && options.headers) },
        signal: controller.signal,
      });
      text = await response.text();
    } catch (cause) {
      throw new Error(tt(
        'checkout.errors.network',
        'No pudimos recibir la respuesta del servicio de pagos. Verifica tu conexión y el estado del pedido antes de reintentar.'
      ));
    } finally {
      clearTimeout(timeout);
    }
    let body = {};
    try {
      body = text ? JSON.parse(text) : {};
    } catch {
      // Una respuesta que no es JSON casi siempre significa que Nginx no está
      // enrutando /api/commerce al servicio. Merece un mensaje explícito.
      throw new Error(
        tt(
          'checkout.errors.service_down',
          'El servicio de pagos no está respondiendo. Escríbenos por WhatsApp y completamos tu pedido.'
        )
      );
    }

    if (!response.ok) {
      const error = new Error(body.error || tt('checkout.errors.generic', 'No pudimos completar la operación.'));
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
              <button type="button" data-action="dec" aria-label="${safe(tt('checkout.dec_aria', 'Quitar uno'))}">−</button>
              <span>${line.quantity}</span>
              <button type="button" data-action="inc" aria-label="${safe(tt('checkout.inc_aria', 'Añadir uno'))}">+</button>
              <button type="button" class="co-item__remove" data-action="remove">${safe(tt('checkout.remove', 'Eliminar'))}</button>
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
    el('co-eta').textContent = `${q.shipping.estimatedDays} ${tt('checkout.days', 'días')}`;
  }

  function setBusy(busy) {
    const button = el('co-submit');
    if (!button) return;
    state.submitting = busy;
    // El botón se habilita en cuanto hay cotización: la validación de campos
    // ocurre al confirmar, no bloquea la UI de pago.
    button.disabled = Boolean(busy) || !state.quoteToken || !state.method;
    button.textContent = busy
      ? tt('checkout.processing', 'Procesando…')
      : tt('checkout.submit', 'Confirmar pedido');
  }

  function syncPaymentUi() {
    setBusy(state.submitting);
    syncSubmitVisibility();
  }

  // ---------------------------------------------------------- cotización

  let quoteTimer = null;
  let quoteRequestId = 0;

  function scheduleQuote() {
    if (state.submitting) return;
    state.quoteToken = null;
    quoteRequestId++;
    setBusy(false);
    clearTimeout(quoteTimer);
    quoteTimer = setTimeout(refreshQuote, QUOTE_DEBOUNCE_MS);
  }

  async function refreshQuote() {
    if (state.submitting) return;
    clearTimeout(quoteTimer);
    const requestId = ++quoteRequestId;
    state.quoteToken = null;
    setBusy(false);
    const items = cartPayload();
    const country = el('co-form').country.value;

    if (!items.length) {
      el('co-empty').hidden = false;
      el('co-layout').hidden = true;
      return;
    }

    const shippingEl = el('co-shipping');
    if (shippingEl) shippingEl.textContent = '…';

    try {
      const data = await apiFetch('/quote', {
        method: 'POST',
        body: JSON.stringify({ items, country }),
      });
      if (requestId !== quoteRequestId) return;

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
      if (requestId !== quoteRequestId) return;
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
      container.innerHTML = `<p class="co-methods__empty">${safe(
        tt('checkout.methods_empty', 'No hay métodos de pago disponibles ahora mismo.')
      )}</p>`;
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

    state.method = (methods.find((method) => method.ready !== false) || {}).id || null;

    container.querySelectorAll('input[name="paymentMethod"]').forEach((input) => {
      const method = methods.find((entry) => entry.id === input.value);
      input.disabled = method.ready === false;
      input.checked = input.value === state.method;
      input.addEventListener('change', () => {
        if (state.submitting) {
          input.checked = false;
          container.querySelector(`input[value="${state.method}"]`).checked = true;
          return;
        }
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
    const method = ((state.config && state.config.paymentMethods) || []).find((entry) => entry.id === id);
    if (method && method.ready === false) return tt('checkout.unavailable', 'No disponible ahora');
    if (id === 'cardnet') return tt('checkout.hints.cardnet', 'Visa / Mastercard');
    if (id === 'bank_transfer') return tt('checkout.hints.bank_transfer', 'Banreservas · BHD');
    if (id === 'paypal') return tt('checkout.hints.paypal', 'USD');
    return '';
  }

  function currentMethod() {
    const methods = (state.config && state.config.paymentMethods) || [];
    return methods.find((m) => m.id === state.method) || null;
  }

  function paypalHostEl() {
    return el(PAYPAL_CONTAINER_ID) || el('co-paypal-buttons');
  }

  function setPaypalHostVisible(visible) {
    const host = paypalHostEl();
    if (host) host.hidden = !visible;
    syncPaypalModeNote(visible);
  }

  /** El comprador debe saber si PayPal está en pruebas: ahí no se cobra dinero real. */
  function syncPaypalModeNote(visible) {
    const note = el('co-paypal-mode');
    if (!note) return;
    const method = currentMethod();
    const sandbox =
      visible && method && method.id === 'paypal' && resolvePaypalClient(method.client).mode === 'sandbox';
    note.hidden = !sandbox;
    note.textContent = sandbox
      ? tt(
          'checkout.paypal_sandbox',
          'PayPal está en modo de prueba: no se cobra dinero real. Usa transferencia bancaria para comprar ahora.'
        )
      : '';
  }

  function renderMethodDetail() {
    const panel = el('co-method-detail');
    const method = currentMethod();
    if (!method || method.id !== 'paypal') setPaypalHostVisible(false);
    if (!panel || !method) return;

    if (method.id === 'bank_transfer') {
      panel.hidden = false;
      // Usar datos del servidor o fallback a configuración local
      const bankData = method.client || {
        accounts: (typeof APP_CONFIG !== 'undefined' && APP_CONFIG.bankTransfer && APP_CONFIG.bankTransfer.accounts) || [],
        beneficiary: (typeof APP_CONFIG !== 'undefined' && APP_CONFIG.bankTransfer && APP_CONFIG.bankTransfer.beneficiary) || {},
        email: (typeof APP_CONFIG !== 'undefined' && APP_CONFIG.bankTransfer && APP_CONFIG.bankTransfer.email) || ''
      };
      panel.innerHTML = renderBankDetails(bankData);
      BankTransferLinks.bindCopy(panel, () => ({
        copied: tt('checkout.bank.copied', 'Copiado'),
        failed: tt('checkout.bank.copy_failed', 'Copia manualmente'),
      }));
      bindBankWhatsApp();
      syncSubmitVisibility();
      return;
    }

    if (method.id === 'cardnet') {
      panel.hidden = false;
      panel.innerHTML = `
        <p class="co-note">${safe(tt('checkout.cardnet_note', 'Ventana segura de CardNET al confirmar.'))}</p>
        <button type="button" id="co-card-trigger" class="co-hidden-trigger" aria-hidden="true" tabindex="-1"></button>`;
      loadCardnet(method.client);
      syncSubmitVisibility();
      return;
    }

    if (method.id === 'paypal') {
      const host = paypalHostEl();
      if (host) {
        // A legacy layout may place the PayPal host inside this panel.
        // Clearing that panel would remove the payment button itself.
        panel.hidden = !panel.contains(host);
        if (!panel.contains(host)) panel.innerHTML = '';
        setPaypalHostVisible(true);
        if (!host.querySelector('iframe, .paypal-buttons')) {
          host.innerHTML = `<p class="co-note co-paypal__loading">${safe(
            tt('checkout.paypal_loading', 'Cargando PayPal…')
          )}</p>`;
        }
      } else {
        panel.hidden = false;
        panel.innerHTML = renderPaypalDetail(method);
      }
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
        <div id="${PAYPAL_CONTAINER_ID}" class="co-paypal-buttons" aria-label="${safe(
          tt('checkout.paypal_aria', 'Pagar con PayPal en USD')
        )}">
          <p class="co-note co-paypal__loading">${safe(tt('checkout.paypal_loading', 'Cargando PayPal…'))}</p>
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
            <div><dt>${safe(tt('checkout.bank.holder', 'Titular'))}</dt><dd>${safe(account.accountHolder)}</dd></div>
            <div><dt>${safe(tt('checkout.bank.type', 'Tipo'))}</dt><dd>${safe(account.accountType)}</dd></div>
            <div><dt>${safe(tt('checkout.bank.account', 'Cuenta'))}</dt><dd><code>${safe(account.accountNumber)}</code>${BankTransferLinks.copyButton(account.accountNumber, tt('checkout.bank.copy', 'Copiar'))}</dd></div>
            ${
              account.currency
                ? `<div><dt>${safe(tt('checkout.bank.currency', 'Moneda'))}</dt><dd>${safe(account.currency)}</dd></div>`
                : ''
            }
          </dl>
          ${BankTransferLinks.render(account.bankName, tt('checkout.bank.online', 'Abrir banca en línea'))}
        </div>`;
  }

  function houseWhatsApp() {
    return BANK_TRANSFER_WHATSAPP;
  }

  function orderRefLabel() {
    return state.orderReference || '';
  }

  function bankWhatsAppMessage(reference) {
    const ref = String(reference || orderRefLabel() || '').trim();
    return `¡Hola! He realizado mi pedido #${ref}. Adjunto comprobante.`;
  }

  function bankWhatsAppUrl(reference) {
    return `https://wa.me/${houseWhatsApp()}?text=${encodeURIComponent(bankWhatsAppMessage(reference))}`;
  }

  function openBankWhatsApp(reference, waWindow) {
    const phone = houseWhatsApp();
    if (!phone) {
      showAlert(tt('checkout.errors.no_whatsapp', 'No hay número de WhatsApp configurado.'));
      return false;
    }
    const url = bankWhatsAppUrl(reference);
    if (waWindow && !waWindow.closed) {
      try {
        waWindow.location.replace(url);
        return true;
      } catch (_) {
        /* el navegador a veces bloquea replace; abrimos otra pestaña */
      }
    }
    window.open(url, '_blank', 'noopener,noreferrer');
    return true;
  }

  function validateForBankTransfer() {
    const data = readForm();
    const errors = localErrors(data);
    if (errors.length) {
      showAlert(errors[0]);
      return false;
    }
    return true;
  }

  async function submitBankTransferOrder(waWindow) {
    if (!validateForBankTransfer()) {
      if (waWindow && !waWindow.closed) waWindow.close();
      return;
    }

    setBusy(true);
    clearAlert();

    try {
      state.method = 'bank_transfer';
      const result = await createOrderPayload({});
      if (!result || !result.reference) {
        if (waWindow && !waWindow.closed) waWindow.close();
        setBusy(false);
        return;
      }
      openBankWhatsApp(result.reference, waWindow);
      goToConfirmation(result);
    } catch (error) {
      if (waWindow && !waWindow.closed) waWindow.close();
      setBusy(false);
      showAlert(error.message || tt('checkout.errors.prepare_order', 'No pudimos preparar el pedido.'));
    }
  }

  function bindBankWhatsApp() {
    const link = el('co-bank-whatsapp');
    if (!link) return;
    link.href = bankWhatsAppUrl(orderRefLabel() || 'CS-REFERENCIA');
    link.onclick = async (event) => {
      event.preventDefault();
      if (state.submitting) return;
      const waWindow = window.open('about:blank', '_blank');
      await submitBankTransferOrder(waWindow);
    };
  }

  function renderBankDetails(bank) {
    // Usar configuración local si no hay datos del servidor
    const accounts = (bank && bank.accounts) || 
      (typeof APP_CONFIG !== 'undefined' && APP_CONFIG.bankTransfer && APP_CONFIG.bankTransfer.accounts) || [];
    const beneficiary = (bank && bank.beneficiary) || 
      (typeof APP_CONFIG !== 'undefined' && APP_CONFIG.bankTransfer && APP_CONFIG.bankTransfer.beneficiary) || {};
    const email = (bank && bank.email) || 
      (typeof APP_CONFIG !== 'undefined' && APP_CONFIG.bankTransfer && APP_CONFIG.bankTransfer.email) || '';
    const ref = orderRefLabel();

    const dominican = accounts.filter((account) => accountRegion(account) === 'DO');
    const american = accounts.filter((account) => accountRegion(account) === 'US');

    const doBlock = dominican.length
      ? `
      <div class="co-bank__region">
        <h3 class="co-bank__region-title">${safe(tt('checkout.bank.do_title', 'República Dominicana'))}</h3>
        ${dominican.map(renderAccountCard).join('')}
      </div>`
      : '';

    const usBlock =
      american.length || beneficiary.name
        ? `
      <div class="co-bank__region">
        <h3 class="co-bank__region-title">${safe(
          tt('checkout.bank.us_title', 'Estados Unidos / internacional')
        )}</h3>
        ${american.map(renderAccountCard).join('')}
        ${
          beneficiary.name
            ? `<div class="co-bank__account">
                <p class="co-bank__bank">${safe(tt('checkout.bank.beneficiary', 'Beneficiario'))}</p>
                <dl>
                  <div><dt>${safe(tt('checkout.bank.name', 'Nombre'))}</dt><dd>${safe(beneficiary.name)}</dd></div>
                  ${
                    beneficiary.taxId
                      ? `<div><dt>${safe(tt('checkout.bank.tax_id', 'RNC'))}</dt><dd>${safe(beneficiary.taxId)}</dd></div>`
                      : ''
                  }
                </dl>
              </div>`
            : ''
        }
      </div>`
        : '';

    const refNote = ref
      ? `${safe(tt('checkout.bank.reference_prefix', 'Referencia:'))} <strong>${safe(ref)}</strong> · `
      : '';
    const emailNote = email
      ? `${safe(tt('checkout.bank.concept_and_email', ' y envía el comprobante a'))} <strong>${safe(email)}</strong>`
      : '';

    return `
      <div class="co-bank">
        <ol class="co-bank__steps">
          <li>${safe(tt('checkout.bank.step_copy', 'Copia el número de cuenta y abre tu banca en línea.'))}</li>
          <li>${safe(tt('checkout.bank.step_transfer', 'Transfiere el total exacto en DOP o USD, según tu cuenta.'))}</li>
          <li>${refNote}${safe(tt('checkout.bank.concept_use', 'Usa la referencia en el concepto'))}${emailNote}.</li>
        </ol>
        ${doBlock}
        ${usBlock}
        <a
          id="co-bank-whatsapp"
          class="co-btn co-btn--whatsapp co-btn--block"
          href="#"
          target="_blank"
          rel="noopener noreferrer"
        >${safe(tt('checkout.bank.whatsapp_cta', 'Enviar comprobante por WhatsApp'))}</a>
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
            name: 'Cazador de Sueño Cigars SRL',
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
        reject(
          new Error(
            tt(
              'checkout.errors.card_load',
              'No pudimos cargar el formulario de tarjeta. Usa transferencia bancaria.'
            )
          )
        );
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
      showAlert(tt('checkout.errors.card_token', 'No recibimos los datos de la tarjeta. Inténtalo de nuevo.'));
      return;
    }
    submitOrder({ trxToken });
  }

  // ----------------------------------------------------------- PayPal

  let paypalSdkReady = null;
  let paypalButtons = null;
  let paypalSdkSource = '';

  /**
   * Client ID limpio: sin comillas de .env, sin URL pegada y sin caracteres
   * que PayPal rechaza (eso es lo que dispara el HTTP 400 del SDK).
   */
  function sanitizePaypalClientId(raw) {
    let value = String(raw == null ? '' : raw).trim();
    if (!value) return '';
    if (
      (value.charAt(0) === '"' && value.charAt(value.length - 1) === '"') ||
      (value.charAt(0) === "'" && value.charAt(value.length - 1) === "'")
    ) {
      value = value.slice(1, -1).trim();
    }
    if (/^https?:\/\//i.test(value)) {
      try {
        value = new URL(value).searchParams.get('client-id') || '';
      } catch (_) {
        return '';
      }
    }
    return value.replace(/[^A-Za-z0-9_-]/g, '');
  }

  function resolvePaypalClient(client) {
    const source = client || {};
    let clientId = sanitizePaypalClientId(source.clientId);
    let mode = String(source.mode || '').toLowerCase();

    if (source.scriptUrl) {
      try {
        const url = new URL(source.scriptUrl);
        if (!clientId) clientId = sanitizePaypalClientId(url.searchParams.get('client-id'));
        if (!mode) mode = /sandbox/i.test(url.hostname) ? 'sandbox' : 'live';
      } catch (_) {
        /* scriptUrl malformada: se ignora */
      }
    }

    if (mode !== 'sandbox') mode = 'live';
    const currencyRaw = String(source.currency || 'USD').toUpperCase();
    const currency = /^[A-Z]{3}$/.test(currencyRaw) ? currencyRaw : 'USD';
    return { clientId, currency, mode, intent: 'capture' };
  }

  function paypalSdkHost(client) {
    return resolvePaypalClient(client).mode === 'sandbox'
      ? PAYPAL_SDK_HOST_SANDBOX
      : PAYPAL_SDK_HOST_LIVE;
  }

  /** Solo client-id + currency + intent. Ningún flag extra (components, buyer-country, …). */
  function buildPaypalSdkUrl(client) {
    const resolved = resolvePaypalClient(client);
    if (!resolved.clientId) return '';
    return (
      `${paypalSdkHost(resolved)}?client-id=${encodeURIComponent(resolved.clientId)}` +
      `&currency=${encodeURIComponent(resolved.currency)}` +
      `&intent=capture`
    );
  }

  function resetPaypalSdk() {
    paypalSdkReady = null;
    paypalSdkSource = '';
    document.querySelectorAll('script[data-paypal-sdk="true"], script[src*="paypal.com/sdk/js"]').forEach((script) => {
      script.remove();
    });
    try {
      delete window.paypal;
    } catch (_) {
      window.paypal = undefined;
    }
  }

  function paypalAbort(message) {
    showAlert(message);
    const error = new Error(PAYPAL_BLOCKED_ERROR);
    error.code = PAYPAL_BLOCKED_ERROR;
    return error;
  }

  function isPaypalAbort(error) {
    return Boolean(
      error &&
        (error.code === PAYPAL_BLOCKED_ERROR ||
          error.message === PAYPAL_BLOCKED_ERROR ||
          String(error).includes(PAYPAL_BLOCKED_ERROR))
    );
  }

  /**
   * Monta los Smart Payment Buttons oficiales en cuanto hay Client ID del servidor.
   * No bloquea la UI con mensajes de "no disponible".
   */
  function mountPaypal(method) {
    const client = method && method.client;
    const sdkUrl = buildPaypalSdkUrl(client);
    const canLoad = Boolean(method && method.ready !== false && client && sdkUrl);
    if (!canLoad) {
      showPaypalFailure(tt('checkout.errors.paypal_unavailable', 'PayPal no está disponible ahora. Usa transferencia bancaria.'));
      return;
    }

    loadPaypalSdk(client)
      .then(() => {
        if (state.method === 'paypal') return renderPaypalButtons();
      })
      .catch((error) => {
        if (state.method === 'paypal') showPaypalFailure(error.message);
      });
  }

  function showPaypalFailure(message) {
    setBusy(false);
    showAlert(message);
    const host = paypalHostEl();
    if (!host) return;
    host.hidden = false;
    host.innerHTML = `<p class="co-note">${safe(message)}</p>
      <button type="button" id="co-paypal-retry" class="co-btn co-btn--ghost">${safe(tt('checkout.retry', 'Reintentar PayPal'))}</button>`;
    el('co-paypal-retry').addEventListener('click', () => {
      clearAlert();
      mountPaypal(currentMethod());
    });
  }

  function loadPaypalSdk(client) {
    const scriptUrl = buildPaypalSdkUrl(client);
    const existingScript = document.querySelector('script[data-paypal-sdk="true"], script[src*="paypal.com/sdk/js"]');
    if (!paypalSdkSource && existingScript && existingScript.src) {
      paypalSdkSource = existingScript.src;
    }
    if (!scriptUrl) {
      return Promise.reject(
        new Error(
          tt('checkout.errors.paypal_load', 'No pudimos cargar PayPal. Prueba de nuevo o usa transferencia.')
        )
      );
    }
    if (window.paypal && paypalSdkSource === scriptUrl) return Promise.resolve(window.paypal);
    if (paypalSdkReady && paypalSdkSource === scriptUrl) return paypalSdkReady;
    if (window.paypal && paypalSdkSource && paypalSdkSource !== scriptUrl) {
      resetPaypalSdk();
    }
    if (paypalSdkSource && paypalSdkSource !== scriptUrl) {
      resetPaypalSdk();
    }

    paypalSdkReady = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      const fail = () => {
        clearTimeout(timeout);
        script.remove();
        resetPaypalSdk();
        reject(new Error(tt('checkout.errors.paypal_load', 'No pudimos cargar PayPal. Prueba de nuevo o usa transferencia.')));
      };
      const timeout = setTimeout(fail, SDK_TIMEOUT_MS);
      script.src = scriptUrl;
      script.async = true;
      script.dataset.paypalSdk = 'true';
      paypalSdkSource = scriptUrl;
      script.onload = () => {
        clearTimeout(timeout);
        if (!window.paypal) {
          fail();
          return;
        }
        resolve(window.paypal);
      };
      script.onerror = fail;
      document.head.appendChild(script);
    });

    return paypalSdkReady;
  }

  function renderPaypalButtons() {
    const host = paypalHostEl();
    if (!host || !window.paypal || typeof window.paypal.Buttons !== 'function') return;

    host.hidden = false;
    if (paypalButtons && host.querySelector('iframe, .paypal-buttons')) return;
    if (paypalButtons && typeof paypalButtons.close === 'function') {
      try {
        paypalButtons.close();
      } catch {
        /* el SDK a veces ya desmontó el botón */
      }
    }
    host.innerHTML = '';

    paypalButtons = window.paypal.Buttons({
      style: { layout: 'vertical', color: 'gold', shape: 'rect', label: 'paypal', height: 45 },
      createOrder: async () => {
        const data = readForm();
        if (state.submitting) throw paypalAbort(tt('checkout.processing', 'Procesando…'));
        const errors = localErrors(data);
        if (errors.length) {
          throw paypalAbort(errors[0]);
        }
        if (!state.quoteToken) {
          const message = tt(
            'checkout.errors.quote_expired_soft',
            'El precio del pedido caducó. Recargamos el resumen.'
          );
          refreshQuote();
          throw paypalAbort(message);
        }
        clearAlert();
        setBusy(true);
        let created;
        try {
          created = await apiFetch('/paypal/orders', {
            method: 'POST',
            body: JSON.stringify({ quoteToken: state.quoteToken }),
          });
        } catch (error) {
          setBusy(false);
          showAlert(error.message);
          throw paypalAbort(error.message);
        }
        if (!created || !created.paypalOrderId) {
          throw new Error(
            tt(
              'checkout.errors.paypal_create',
              'No pudimos iniciar la orden de PayPal. Intenta de nuevo en unos segundos.'
            )
          );
        }
        return created.paypalOrderId;
      },
      onApprove: async (data) => {
        const formData = readForm();
        if (!formData.acceptances.finalSale) {
          showAlert(
            tt(
              'checkout.errors.accept_terms_pay',
              'Marca la casilla de condiciones de venta para completar el pago.'
            )
          );
          setBusy(false);
          return;
        }
        const orderId = data && (data.orderID || data.orderId);
        if (!orderId) {
          showAlert(
            tt(
              'checkout.errors.paypal_create',
              'No pudimos iniciar la orden de PayPal. Intenta de nuevo en unos segundos.'
            )
          );
          return;
        }
        await submitOrder({ paypalOrderId: orderId });
      },
      onCancel: () => {
        setBusy(false);
        showAlert(
          tt(
            'checkout.errors.paypal_cancel',
            'Cancelaste el pago en PayPal. Puedes intentarlo de nuevo o elegir otro método.'
          ),
          'info'
        );
      },
      onError: (error) => {
        if (isPaypalAbort(error)) return;
        setBusy(false);
        showAlert(
          tt(
            'checkout.errors.paypal_fail',
            'PayPal no pudo completar el pago. Prueba de nuevo o usa transferencia bancaria.'
          )
        );
      },
    });

    return paypalButtons.render(`#${PAYPAL_CONTAINER_ID}`);
  }

  // ------------------------------------------------------------- envío

  function readForm() {
    const form = el('co-form');
    const field = (name) => form.elements.namedItem(name);
    return {
      customer: {
        fullName: field('fullName').value.trim(),
        email: field('email').value.trim(),
        phone: field('phone').value.trim(),
      },
      shipping: {
        address: field('address').value.trim(),
        city: field('city').value.trim(),
        state: field('state').value.trim(),
        postalCode: field('postalCode').value.trim(),
        country: field('country').value,
      },
      notes: field('notes').value.trim(),
      acceptances: {
        // Un solo checkbox en UI → ambas aceptaciones para el contrato del servidor.
        finalSale: field('acceptTerms').checked,
        customs: field('acceptTerms').checked,
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
    if (data.customer.fullName.length < 3) {
      errors.push(tt('checkout.errors.name', 'Escribe tu nombre completo.'));
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(data.customer.email)) {
      errors.push(tt('checkout.errors.email', 'Escribe un correo electrónico válido.'));
    }
    if (data.customer.phone.replace(/\D/g, '').length < 7) {
      errors.push(tt('checkout.errors.phone', 'Escribe un teléfono de contacto para la entrega.'));
    }
    if (data.shipping.address.length < 5) {
      errors.push(tt('checkout.errors.address', 'Escribe la dirección de entrega.'));
    }
    if (data.shipping.city.length < 2) {
      errors.push(tt('checkout.errors.city', 'Escribe la ciudad de entrega.'));
    }
    if (!data.shipping.country) {
      errors.push(tt('checkout.errors.country', 'Selecciona el país de destino.'));
    }
    if (requireTerms && !data.acceptances.finalSale) {
      errors.push(tt('checkout.errors.terms', 'Debes aceptar las condiciones de venta.'));
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
      setBusy(false);
      showAlert(
        tt(
          'checkout.errors.quote_expired',
          'El precio del pedido caducó. Recargamos el resumen, revísalo y confirma otra vez.'
        )
      );
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
        showAlert(
          tt(
            'checkout.errors.quote_updated',
            'El precio se actualizó mientras completabas el formulario. Revísalo y confirma otra vez.'
          )
        );
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

    const selected = document.querySelector('input[name="paymentMethod"]:checked');
    if (selected) state.method = selected.value;

    const data = readForm();
    const errors = localErrors(data);
    if (errors.length) {
      showAlert(errors[0]);
      return;
    }

    if (!state.method) {
      showAlert(tt('checkout.errors.choose_method', 'Elige un método de pago.'));
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
      showAlert(tt('checkout.errors.use_paypal_button', 'Usa el botón de PayPal para completar el pago.'));
      return;
    }

    if (state.method === 'bank_transfer') {
      // Abrir la pestaña en el click (síncrono) para que el popup no lo bloquee
      // después del POST. Tras el 200 se navega a WhatsApp y esta pestaña a confirmación.
      const waWindow = window.open('about:blank', '_blank');
      await submitBankTransferOrder(waWindow);
      return;
    }

    submitOrder({});
  }

  // ----------------------------------------------------------- arranque

  function renderStaticCopy() {
    const terms = el('co-policy-terms');
    if (!terms) return;
    terms.textContent = tt(
      'checkout.terms',
      typeof SALES_POLICY !== 'undefined'
        ? SALES_POLICY.checkoutText
        : 'Acepto venta final (sin devoluciones) y la responsabilidad aduanera en destino.'
    );
  }

  function reapplyLanguage() {
    if (state.submitting) return;
    renderStaticCopy();
    if (state.quote) {
      renderItems();
      renderTotals();
    }
    if (state.config) {
      const previous = state.method;
      renderPaymentMethods();
      if (previous) {
        const input = document.querySelector(`input[name="paymentMethod"][value="${previous}"]`);
        if (input) {
          input.checked = true;
          state.method = previous;
          renderMethodDetail();
        }
      }
    }
    setBusy(state.submitting);
  }

  function fillCountries(countries) {
    const select = el('co-form').country;
    const preferred =
      typeof getPreferredShippingCountry === 'function'
        ? getPreferredShippingCountry()
        : typeof detectPreferredShippingCountry === 'function'
          ? detectPreferredShippingCountry()
          : 'DO';

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
    form.country.addEventListener('change', () => {
      refreshQuote();
    });

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
    if (!paypal || paypal.ready === false || !paypal.client) return;
    if (!buildPaypalSdkUrl(paypal.client)) return;
    loadPaypalSdk(paypal.client).catch(() => {
      /* se reintenta al seleccionar PayPal */
    });
  }

  async function init() {
    renderStaticCopy();
    window.addEventListener('cds:language-changed', reapplyLanguage);

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
      showAlert(
        tt(
          'checkout.errors.init_fail',
          'No pudimos iniciar el checkout. Recarga la página o escríbenos por WhatsApp.'
        )
      );
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
