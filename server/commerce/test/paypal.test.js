const test = require('node:test');
const assert = require('node:assert/strict');

const { createPaypalGateway, HOSTS, SDK_HOSTS } = require('../gateways/paypal');
const { ERROR_CODES } = require('../errors');
const { createLogger } = require('../logger');

const silentLog = createLogger({}, { log() {}, warn() {}, error() {} });

function baseConfig(overrides = {}) {
  return {
    enabled: true,
    clientId: 'CLIENT-ID-PUBLICO',
    clientSecret: 'CLIENT-SECRET-PRIVADO',
    mode: 'sandbox',
    currency: 'USD',
    timeoutMs: 5000,
    ...overrides,
  };
}

function contexto(overrides = {}) {
  return {
    orderReference: 'CS-TEST-PP',
    amountCents: 27_700,
    currency: 'USD',
    customer: { fullName: 'Ana Pérez', email: 'ana@ejemplo.com', phone: '8095551234' },
    clientIp: '190.80.1.2',
    userAgent: 'Mozilla/5.0',
    idempotencyKey: 'paypal-idem-0001',
    payload: { paypalOrderId: 'PAYPAL-ORDER-1' },
    log: silentLog,
    ...overrides,
  };
}

function stubFetch(responder) {
  const calls = [];
  const original = global.fetch;
  global.fetch = async (url, options) => {
    calls.push({
      url,
      method: options.method,
      headers: options.headers,
      body: options.body,
    });
    return responder(url, options);
  };
  return {
    calls,
    restore() {
      global.fetch = original;
    },
  };
}

function jsonResponse(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, text: async () => JSON.stringify(body) };
}

async function expectRejection(promise, code) {
  try {
    await promise;
  } catch (error) {
    assert.equal(error.code, code, `se esperaba ${code} y llegó ${error.code}`);
    return error;
  }
  assert.fail(`se esperaba un error ${code}`);
}

test('solo está lista para cobrar si hay Client ID, secret y el interruptor', () => {
  assert.equal(createPaypalGateway(baseConfig({ clientId: '' })).isConfigured(), false);
  assert.equal(createPaypalGateway(baseConfig({ clientSecret: '' })).isConfigured(), false);
  assert.equal(createPaypalGateway(baseConfig({ enabled: false })).isConfigured(), false);
  assert.equal(createPaypalGateway(baseConfig()).isConfigured(), true);
});

test('describe() siempre expone el botón, aunque las credenciales aún no existan', () => {
  const preview = createPaypalGateway(
    baseConfig({ enabled: false, clientId: '', clientSecret: '' })
  ).describe();
  assert.equal(preview.available, true, 'el checkout debe pintar PayPal ya');
  assert.equal(preview.ready, false);
  assert.equal(preview.client.clientId, '');
  assert.equal(preview.client.scriptUrl, '');
});

test('describe() expone el Client ID público y jamás el secret', () => {
  const description = createPaypalGateway(baseConfig()).describe();
  const serialized = JSON.stringify(description);

  assert.equal(description.ready, true);
  assert.match(serialized, /CLIENT-ID-PUBLICO/);
  assert.doesNotMatch(serialized, /CLIENT-SECRET-PRIVADO/);
  assert.match(description.client.scriptUrl, /client-id=CLIENT-ID-PUBLICO/);
  assert.match(description.client.scriptUrl, new RegExp(SDK_HOSTS.sandbox.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
});

test('exige el identificador de orden de PayPal antes de capturar', () => {
  const gateway = createPaypalGateway(baseConfig());
  assert.throws(
    () => gateway.validatePayload({}),
    (e) => e.code === ERROR_CODES.PAYPAL_ORDER_MISSING
  );
});

test('si no está configurada, validatePayload lo impide antes de tocar la red', () => {
  const gateway = createPaypalGateway(baseConfig({ enabled: false }));
  assert.throws(
    () => gateway.validatePayload({ paypalOrderId: 'x' }),
    (e) => e.code === ERROR_CODES.GATEWAY_NOT_CONFIGURED
  );
});

test('crea la orden en PayPal con el importe autoritativo, no con uno del cliente', async () => {
  const stub = stubFetch((url) => {
    if (String(url).includes('/v1/oauth2/token')) {
      return jsonResponse({ access_token: 'token-oauth' });
    }
    return jsonResponse({ id: 'PAYPAL-ORDER-1', status: 'CREATED' });
  });

  try {
    const created = await createPaypalGateway(baseConfig()).createCheckoutOrder({
      amountCents: 27_700,
      currency: 'USD',
      quoteId: 'q_abc123',
      log: silentLog,
    });

    assert.equal(created.paypalOrderId, 'PAYPAL-ORDER-1');

    const createCall = stub.calls.find((c) => String(c.url).includes('/v2/checkout/orders'));
    const body = JSON.parse(createCall.body);
    assert.equal(body.purchase_units[0].amount.value, '277.00');
    assert.equal(body.purchase_units[0].amount.currency_code, 'USD');
    assert.equal(body.intent, 'CAPTURE');
    assert.equal(createCall.headers['PayPal-Request-Id'], 'q_abc123');
  } finally {
    stub.restore();
  }
});

test('CUMPLIMIENTO PCI: la petición a PayPal no contiene ningún dato de tarjeta', async () => {
  const stub = stubFetch((url) => {
    if (String(url).includes('/oauth2/token')) return jsonResponse({ access_token: 'token-oauth' });
    return jsonResponse({
      id: 'PAYPAL-ORDER-1',
      status: 'COMPLETED',
      purchase_units: [
        {
          payments: {
            captures: [
              { id: 'CAP-1', status: 'COMPLETED', amount: { value: '277.00', currency_code: 'USD' } },
            ],
          },
        },
      ],
    });
  });

  try {
    await createPaypalGateway(baseConfig()).charge(contexto());
    const dumped = JSON.stringify(stub.calls);
    assert.doesNotMatch(dumped, /card/i);
    assert.doesNotMatch(dumped, /cvv/i);
    assert.doesNotMatch(dumped, /4111/);
    assert.doesNotMatch(dumped, /CLIENT-SECRET-PRIVADO/);
  } finally {
    stub.restore();
  }
});

test('un cobro completado devuelve el identificador de captura', async () => {
  const stub = stubFetch((url) => {
    if (String(url).includes('/oauth2/token')) return jsonResponse({ access_token: 'token-oauth' });
    return jsonResponse({
      id: 'PAYPAL-ORDER-1',
      status: 'COMPLETED',
      purchase_units: [
        {
          payments: {
            captures: [
              { id: 'CAP-99', status: 'COMPLETED', amount: { value: '277.00', currency_code: 'USD' } },
            ],
          },
        },
      ],
    });
  });

  try {
    const result = await createPaypalGateway(baseConfig()).charge(contexto());
    assert.equal(result.status, 'paid');
    assert.equal(result.gateway, 'paypal');
    assert.equal(result.transactionId, 'CAP-99');

    const captureCall = stub.calls.find((c) => String(c.url).includes('/capture'));
    assert.match(captureCall.url, new RegExp(`${HOSTS.sandbox.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}/v2/checkout/orders/PAYPAL-ORDER-1/capture`));
    assert.equal(captureCall.headers['PayPal-Request-Id'], 'paypal-idem-0001');
  } finally {
    stub.restore();
  }
});

test('un importe capturado distinto al de la cotización se rechaza', async () => {
  const stub = stubFetch((url) => {
    if (String(url).includes('/oauth2/token')) return jsonResponse({ access_token: 'token-oauth' });
    return jsonResponse({
      status: 'COMPLETED',
      purchase_units: [
        {
          payments: {
            captures: [
              { id: 'CAP-1', status: 'COMPLETED', amount: { value: '1.00', currency_code: 'USD' } },
            ],
          },
        },
      ],
    });
  });

  try {
    await expectRejection(
      createPaypalGateway(baseConfig()).charge(contexto()),
      ERROR_CODES.GATEWAY_BAD_RESPONSE
    );
  } finally {
    stub.restore();
  }
});

test('un rechazo de PayPal no se disfraza de pago aprobado', async () => {
  const stub = stubFetch((url) => {
    if (String(url).includes('/oauth2/token')) return jsonResponse({ access_token: 'token-oauth' });
    return jsonResponse({ name: 'UNPROCESSABLE_ENTITY', status: 'DECLINED' }, 422);
  });

  try {
    await expectRejection(createPaypalGateway(baseConfig()).charge(contexto()), ERROR_CODES.CARD_DECLINED);
  } finally {
    stub.restore();
  }
});

test('autentica el secret solo en el intercambio de token, nunca en el SDK público', async () => {
  const stub = stubFetch((url) => {
    if (String(url).includes('/oauth2/token')) return jsonResponse({ access_token: 'token-oauth' });
    return jsonResponse({ id: 'PAYPAL-ORDER-1', status: 'CREATED' });
  });

  try {
    await createPaypalGateway(baseConfig()).createCheckoutOrder({
      amountCents: 1000,
      currency: 'USD',
      quoteId: 'q_1',
      log: silentLog,
    });

    const oauth = stub.calls.find((c) => String(c.url).includes('/oauth2/token'));
    const expected = `Basic ${Buffer.from('CLIENT-ID-PUBLICO:CLIENT-SECRET-PRIVADO').toString('base64')}`;
    assert.equal(oauth.headers.Authorization, expected);

    const sdk = createPaypalGateway(baseConfig()).describe().client.scriptUrl;
    assert.doesNotMatch(sdk, /CLIENT-SECRET-PRIVADO/);
  } finally {
    stub.restore();
  }
});
