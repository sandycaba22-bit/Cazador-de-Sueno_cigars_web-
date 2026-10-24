const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');

// Minimal DOM surface for checkout state transitions; no third-party runtime dependencies.
function fixture({ permanentHost = true, fetchImpl } = {}) {
  const nodes = new Map();
  class Element {
    constructor(id = '') {
      this.id = id;
      this.hidden = false;
      this.disabled = false;
      this.dataset = {};
      this.children = [];
      this.listeners = {};
      this.attributes = {};
      this.textContent = '';
      if (id) nodes.set(id, this);
    }
    set innerHTML(value) {
      for (const child of [...this.children]) child.remove();
      this.html = value;
      for (const match of value.matchAll(/\bid="([^"]+)"/g)) {
        this.appendChild(new Element(match[1]));
      }
    }
    get innerHTML() {
      return this.html || this.textContent.replace(/&/g, '&amp;').replace(/</g, '&lt;');
    }
    appendChild(child) {
      child.parentElement = this;
      this.children.push(child);
      return child;
    }
    remove() {
      for (const child of [...this.children]) child.remove();
      if (this.id) nodes.delete(this.id);
      if (this.parentElement) {
        this.parentElement.children = this.parentElement.children.filter((child) => child !== this);
      }
    }
    contains(child) {
      return this.children.some((entry) => entry === child || entry.contains(child));
    }
    querySelector() { return null; }
    querySelectorAll() { return []; }
    addEventListener(name, handler) { this.listeners[name] = handler; }
    setAttribute(name, value) { this.attributes[name] = value; }
    scrollIntoView() {}
  }
  for (const id of [
    'co-form', 'co-alert', 'co-empty', 'co-layout', 'co-method-detail',
    'co-methods', 'co-submit', 'co-shipping', 'co-items', 'co-subtotal',
    'co-total', 'co-zone', 'co-units', 'co-boxes', 'co-eta', 'co-boxes-warning',
    'co-paypal-mode',
  ]) new Element(id);
  nodes.get('co-alert').hidden = true;
  if (permanentHost) new Element('paypal-button-container');
  const form = nodes.get('co-form');
  for (const [key, value] of Object.entries({
    fullName: 'Checkout Test', email: 'checkout-test@example.com', phone: '8095550100',
    address: 'Calle Prueba 123', city: 'Santo Domingo', country: 'DO',
    state: '', postalCode: '', notes: '',
  })) form[key] = { value };
  form.acceptTerms = { checked: true };
  form.elements = { namedItem: (name) => form[name] };
  const quote = (country) => ({
    currency: 'USD', country, lines: [], subtotalCents: 24000, shippingCents: 500,
    totalCents: 24500, totalUnits: 20, shippingBoxes: 1,
    shipping: { zone: country, maxBoxes: 10, estimatedDays: '2-4' },
  });
  const requests = [];
  const paypalClient = { clientId: 'TEST-PUBLIC-ID', mode: 'sandbox', currency: 'USD' };
  const document = {
    head: new Element(), createElement: () => new Element(),
    getElementById: (id) => nodes.get(id) || null,
    querySelector: () => null, querySelectorAll: () => [],
    addEventListener() {},
  };
  const window = {
    location: { href: 'http://localhost:3000/checkout.html', assign() {} },
    addEventListener() {}, dispatchEvent() {},
  };
  const context = vm.createContext({
    document, window, crypto: webcrypto, URL, AbortController, Intl,
    BankTransferLinks: require('../../../js/bank-transfer-links'),
    setTimeout, clearTimeout, console, CustomEvent: class {},
    getCartItems: () => [{ productId: 'emperador', unitType: 'box', quantity: 1 }],
    fetch: async (url, options) => {
      requests.push({ url, options });
      if (fetchImpl) return fetchImpl(url, options, quote);
      return { ok: true, text: async () => JSON.stringify({ success: true }) };
    },
  });
  const file = path.join(__dirname, '../../../js/checkout.js');
  const source = fs.readFileSync(file, 'utf8').replace(/\}\)\(\);\s*$/, `
    window.__checkoutTest = {
      state, apiFetch, refreshQuote, renderMethodDetail, mountPaypal, renderPaypalButtons,
      readForm, localErrors, setBusy, syncSubmitVisibility, bindEvents, renderAccountCard
    };
  })();`);
  vm.runInContext(source, context, { filename: file });
  const api = window.__checkoutTest;
  api.state.config = {
    paymentMethods: [
      { id: 'bank_transfer', client: { accounts: [] } },
      { id: 'paypal', ready: true, client: paypalClient },
    ],
  };
  api.state.method = 'paypal';
  api.state.quoteToken = 'signed-quote';
  api.state.quote = quote('DO');
  const settle = async () => {
    for (let i = 0; i < 5; i++) await new Promise((resolve) => setImmediate(resolve));
  };
  return { api, nodes, document, window, form, requests, paypalClient, settle };
}

test('PayPal conserva su contenedor al repetir la seleccion dentro del panel', async () => {
  const f = fixture({ permanentHost: false });
  f.api.state.config.paymentMethods[1].client = {};
  f.api.renderMethodDetail();
  f.api.renderMethodDetail();
  assert.ok(f.nodes.get('paypal-button-container'));
  assert.equal(f.nodes.get('co-method-detail').hidden, false);
});

test('PayPal sin credenciales muestra un error accionable, no carga infinita', async () => {
  const f = fixture();
  f.api.state.config.paymentMethods[1].ready = false;
  f.api.state.config.paymentMethods[1].client = {};
  f.api.renderMethodDetail();
  await f.settle();
  assert.equal(f.nodes.get('co-alert').hidden, false);
  assert.match(f.nodes.get('co-alert').textContent, /transferencia|disponible/i);
});

test('fallo de carga del SDK muestra aviso y permite reintentar', async () => {
  const f = fixture();
  f.api.renderMethodDetail();
  f.document.head.children.find((script) => script.src).onerror();
  await f.settle();
  assert.equal(f.nodes.get('co-alert').hidden, false);
  assert.ok(f.nodes.get('co-paypal-retry'));
});

test('una respuesta vieja no sustituye la cotizacion del nuevo pais', async () => {
  const pending = [];
  const f = fixture({
    fetchImpl: (url, options, quote) => new Promise((resolve) => {
      const country = JSON.parse(options.body).country;
      pending.push(() => resolve({
        ok: true, text: async () => JSON.stringify({ quote: quote(country), quoteToken: country }),
      }));
    }),
  });
  const first = f.api.refreshQuote();
  f.form.country.value = 'US';
  const second = f.api.refreshQuote();
  pending[1]();
  await second;
  pending[0]();
  await first;
  assert.equal(f.api.state.quoteToken, 'US');
});

test('el boton se bloquea mientras se actualiza la cotizacion', async () => {
  let resolve;
  const f = fixture({ fetchImpl: () => new Promise((done) => { resolve = done; }) });
  const pending = f.api.refreshQuote();
  assert.equal(f.api.state.quoteToken, null);
  assert.equal(f.nodes.get('co-submit').disabled, true);
  resolve({ ok: false, status: 503, text: async () => '{"error":"Servicio no disponible"}' });
  await pending;
});

test('POST de pedido conserva Content-Type junto a Idempotency-Key', async () => {
  const f = fixture();
  await f.api.apiFetch('/orders', {
    method: 'POST', headers: { 'Idempotency-Key': 'test-key-123' }, body: '{}',
  });
  assert.equal(f.requests[0].options.headers['Content-Type'], 'application/json');
  assert.equal(f.requests[0].options.headers['Idempotency-Key'], 'test-key-123');
});

test('PayPal exige condiciones antes de abrir la orden, no despues de aprobarla', async () => {
  const f = fixture();
  let callbacks;
  f.window.paypal = { Buttons(options) { callbacks = options; return { render: async () => {} }; } };
  f.api.renderPaypalButtons();
  f.form.acceptTerms.checked = false;
  await assert.rejects(callbacks.createOrder());
  assert.equal(f.requests.length, 0);
});

test('respuesta HTML de la API genera error explicito', async () => {
  const f = fixture({ fetchImpl: async () => ({ ok: true, text: async () => '<html></html>' }) });
  await assert.rejects(f.api.apiFetch('/orders', { method: 'POST' }), /servicio de pagos/i);
});

test('error HTTP conserva codigo y status para informar al comprador', async () => {
  const f = fixture({
    fetchImpl: async () => ({
      ok: false, status: 409, text: async () => '{"error":"Cotizacion caducada","code":"QUOTE_EXPIRED"}',
    }),
  });
  await assert.rejects(f.api.apiFetch('/orders'), (error) =>
    error.status === 409 && error.code === 'QUOTE_EXPIRED');
});

test('PayPal crea la orden, envia captura al backend y navega a confirmacion', async () => {
  const f = fixture({
    fetchImpl: async (url) => ({
      ok: true,
      text: async () => JSON.stringify(url.endsWith('/paypal/orders')
        ? { paypalOrderId: 'PAYPAL-TEST-ORDER' }
        : { success: true, reference: 'CS-TEST', accessToken: 'TEST-ACCESS' }),
    }),
  });
  let callbacks;
  let destination;
  f.window.location.assign = (url) => { destination = new URL(url); };
  f.window.paypal = { Buttons(options) { callbacks = options; return { render: async () => {} }; } };
  f.api.renderPaypalButtons();
  assert.equal(await callbacks.createOrder(), 'PAYPAL-TEST-ORDER');
  assert.equal(f.api.state.submitting, true);
  await callbacks.onApprove({ orderID: 'PAYPAL-TEST-ORDER' });
  assert.equal(f.requests[1].url, '/api/commerce/orders');
  const payload = JSON.parse(f.requests[1].options.body);
  assert.equal(payload.paymentMethod, 'paypal');
  assert.equal(payload.paymentPayload.paypalOrderId, 'PAYPAL-TEST-ORDER');
  assert.equal(payload.acceptances.finalSale, true);
  assert.equal(destination.pathname, '/order-confirmation.html');
  assert.equal(destination.searchParams.get('ref'), 'CS-TEST');
});

test('cancelar PayPal restaura el estado y no envia una captura', async () => {
  const f = fixture();
  let callbacks;
  f.window.paypal = { Buttons(options) { callbacks = options; return { render: async () => {} }; } };
  f.api.renderPaypalButtons();
  f.api.setBusy(true);
  callbacks.onCancel();
  assert.equal(f.api.state.submitting, false);
  assert.equal(f.requests.length, 0);
  assert.equal(f.nodes.get('co-alert').hidden, false);
});

test('un SDK que termina despues de cambiar a transferencia no monta PayPal', async () => {
  const f = fixture();
  let rendered = 0;
  f.api.renderMethodDetail();
  f.api.state.method = 'bank_transfer';
  f.api.renderMethodDetail();
  f.window.paypal = { Buttons() { rendered++; return { render: async () => {} }; } };
  f.document.head.children.find((script) => script.src).onload();
  await f.settle();
  assert.equal(rendered, 0);
  assert.equal(f.nodes.get('paypal-button-container').hidden, true);
  assert.equal(f.nodes.get('co-submit').hidden, false);
});

test('PayPal en sandbox avisa que no se cobra dinero real y el aviso se va al cambiar de metodo', () => {
  const f = fixture();
  f.api.renderMethodDetail();
  const note = f.nodes.get('co-paypal-mode');
  assert.equal(note.hidden, false);
  assert.match(note.textContent, /prueba/i);
  f.api.state.method = 'bank_transfer';
  f.api.renderMethodDetail();
  assert.equal(note.hidden, true);
});

test('PayPal en live no muestra aviso de pruebas', () => {
  const f = fixture();
  f.api.state.config.paymentMethods[1].client = { ...f.paypalClient, mode: 'live' };
  f.api.renderMethodDetail();
  assert.equal(f.nodes.get('co-paypal-mode').hidden, true);
});

test('cada cuenta del checkout trae boton para copiar el numero', () => {
  const f = fixture();
  const html = f.api.renderAccountCard({
    bankName: 'Banco BHD', accountHolder: 'Titular', accountType: 'Ahorros', accountNumber: '15705310035',
  });
  assert.ok(html.includes('data-copy="15705310035"'));
});

test('cada cuenta del checkout incluye el enlace oficial del banco sin cambiar sus datos', () => {
  const f = fixture();
  for (const [bankName, url] of [
    ['Banco de Reservas', 'https://www.banreservas.com'],
    ['Banco BHD', 'https://www.bhd.com.do'],
  ]) {
    const html = f.api.renderAccountCard({
      bankName, accountHolder: 'Titular Prueba', accountType: 'Ahorros', accountNumber: '123456',
    });
    assert.ok(html.includes(`href="${url}" target="_blank" rel="noopener noreferrer"`));
    assert.ok(html.includes('123456'));
    assert.ok(html.includes('Titular Prueba'));
  }
});
