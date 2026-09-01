/**
 * Pruebas de integración contra el servidor HTTP real.
 *
 * Levantan el servicio en un puerto efímero con un directorio de datos
 * temporal, de modo que ejercitan el mismo camino que recorre un comprador.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { createCommerceApp } = require('../app');
const { createLogger } = require('../logger');
const { createOrdersStore } = require('../orders-store');
const { CheckoutError, ERROR_CODES } = require('../errors');
const { getProductById } = require('../../../js/catalog');
const { calculateShipping } = require('../../../js/shipping');

const silentLog = createLogger({}, { log() {}, warn() {}, error() {} });

/** Registro de pasarelas con una sola implementación, para forzar escenarios. */
function registroConPasarela(gateway) {
  const full = {
    label: 'Pasarela de prueba',
    isConfigured: () => true,
    validatePayload() {},
    describe: () => ({ id: gateway.id, label: 'Pasarela de prueba', available: true, ready: true, client: null }),
    ...gateway,
  };
  return {
    get(id) {
      if (id !== full.id) {
        throw new CheckoutError(ERROR_CODES.GATEWAY_NOT_CONFIGURED, 'No disponible.', {
          httpStatus: 503,
        });
      }
      return full;
    },
    list: () => [full],
    describeAvailable: () => [full.describe()],
  };
}

/** Pasarela de prueba que aprueba el cobro (sustituye al sandbox retirado). */
function pasarelaAprobada(id = 'test_pay') {
  return registroConPasarela({
    id,
    async charge(ctx) {
      return {
        status: 'paid',
        gateway: id,
        transactionId: `test_${ctx.idempotencyKey.slice(0, 12)}`,
        authorizationCode: '000000',
        customerMessage: 'Pago de prueba aprobado.',
        diagnostics: { simulated: true },
      };
    },
  });
}

/** Registro de PayPal de prueba para cubrir setup, cancelación lógica y captura. */
function registroPaypalPrueba() {
  const gateway = {
    id: 'paypal',
    label: 'PayPal',
    requiresCardData: false,
    isConfigured: () => true,
    describe: () => ({
      id: 'paypal',
      label: 'PayPal',
      available: true,
      ready: true,
      client: {
        clientId: 'PAYPAL-SANDBOX-ID',
        currency: 'USD',
        intent: 'capture',
        mode: 'sandbox',
        scriptUrl: 'https://www.sandbox.paypal.com/sdk/js?client-id=PAYPAL-SANDBOX-ID',
      },
    }),
    validatePayload(payload) {
      if (!payload || !payload.paypalOrderId) {
        throw new CheckoutError(
          ERROR_CODES.PAYPAL_ORDER_MISSING,
          'Confirma el pago en la ventana de PayPal antes de continuar.'
        );
      }
    },
    async createCheckoutOrder({ amountCents, currency, quoteId }) {
      return {
        paypalOrderId: `PAYPAL-ORDER-${quoteId}`,
        status: 'CREATED',
        amountCents,
        currency,
      };
    },
    async charge(ctx) {
      return {
        status: 'paid',
        gateway: 'paypal',
        transactionId: `CAP-${ctx.payload.paypalOrderId}`,
        authorizationCode: `CAP-${ctx.payload.paypalOrderId}`,
        customerMessage: 'Pago con PayPal confirmado.',
        diagnostics: {
          paypalOrderId: ctx.payload.paypalOrderId,
          captureStatus: 'COMPLETED',
          mode: 'sandbox',
        },
      };
    },
  };

  return {
    get(id) {
      if (id !== 'paypal') {
        throw new CheckoutError(ERROR_CODES.GATEWAY_NOT_CONFIGURED, 'No disponible.', {
          httpStatus: 503,
        });
      }
      return gateway;
    },
    list: () => [gateway],
    describeAvailable: () => [gateway.describe()],
  };
}

function testConfig(overrides = {}) {
  return {
    nodeEnv: 'test',
    isProduction: false,
    port: 0,
    host: '127.0.0.1',
    corsOrigins: ['https://www.cazadordesuenocigars.com'],
    dataDir: fs.mkdtempSync(path.join(os.tmpdir(), 'cds-app-')),
    quoteSecret: 'secreto-de-prueba',
    quoteSecretProvided: true,
    quoteTtlSeconds: 900,
    idempotencyTtlSeconds: 3600,
    rateLimit: { windowMs: 60_000, maxQuotes: 500, maxPayments: 500 },
    sandbox: { enabled: false },
    cardnet: {
      enabled: false,
      baseUrl: 'https://example.invalid',
      publicAccountKey: '',
      privateAccountKey: '',
      currency: 'DOP',
      usdToDopRate: 0,
      timeoutMs: 5000,
      captureImmediately: true,
    },
    bankTransfer: { enabled: true },
    paypal: {
      enabled: false,
      clientId: '',
      clientSecret: '',
      mode: 'live',
      currency: 'USD',
      timeoutMs: 5000,
    },
    contact: { whatsapp: '18094645016', email: 'ventas@ejemplo.com' },
    ...overrides,
  };
}

/** Arranca el servicio y devuelve un cliente HTTP sencillo. */
async function startServer(config = testConfig(), overrides = {}) {
  const store = createOrdersStore(config.dataDir, silentLog);
  const app = createCommerceApp({ config, logger: silentLog, store, ...overrides });

  const server = http.createServer(async (req, res) => {
    const attended = await app(req, res);
    if (!attended) {
      res.writeHead(404).end();
    }
  });

  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;

  return {
    config,
    store,
    base,
    async request(method, routePath, { body, headers } = {}) {
      const response = await fetch(`${base}${routePath}`, {
        method,
        headers: { 'Content-Type': 'application/json', ...headers },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const text = await response.text();
      let json = null;
      try {
        json = text ? JSON.parse(text) : null;
      } catch {
        json = null;
      }
      return { status: response.status, body: json, text, headers: response.headers };
    },
    async close() {
      await new Promise((resolve) => server.close(resolve));
    },
  };
}

const CARRITO = [{ productId: 'emperador', unitType: 'box', quantity: 2 }];

function datosCliente(overrides = {}) {
  return {
    customer: { fullName: 'Ana Pérez', email: 'ana@ejemplo.com', phone: '8095551234' },
    shipping: {
      address: 'Calle El Conde 102',
      city: 'Miami',
      state: '',
      postalCode: '',
      country: 'US',
    },
    notes: '',
    acceptances: { finalSale: true, customs: true },
    ...overrides,
  };
}

async function cotizar(api, items = CARRITO, country = 'US') {
  const response = await api.request('POST', '/api/commerce/quote', { body: { items, country } });
  assert.equal(response.status, 200, `cotización falló: ${response.text}`);
  return response.body;
}

// ------------------------------------------------------------------ salud

test('el endpoint de salud informa qué pasarelas están configuradas', async () => {
  const api = await startServer();
  try {
    const { status, body } = await api.request('GET', '/api/commerce/health');
    assert.equal(status, 200);
    assert.equal(body.ok, true);

    const sandbox = body.gateways.find((g) => g.id === 'sandbox');
    const cardnet = body.gateways.find((g) => g.id === 'cardnet');
    const paypal = body.gateways.find((g) => g.id === 'paypal');
    const bank = body.gateways.find((g) => g.id === 'bank_transfer');
    assert.equal(sandbox, undefined, 'sandbox no debe existir en el registro');
    assert.equal(cardnet.configured, false);
    assert.equal(paypal.configured, false);
    assert.equal(bank.configured, true);
  } finally {
    await api.close();
  }
});

test('la configuración pública no incluye ninguna clave privada', async () => {
  const api = await startServer(
    testConfig({
      cardnet: {
        ...testConfig().cardnet,
        enabled: true,
        publicAccountKey: 'PUBLICA-123',
        privateAccountKey: 'PRIVADA-SECRETA-456',
        usdToDopRate: 60,
      },
      paypal: {
        ...testConfig().paypal,
        enabled: true,
        clientId: 'PAYPAL-CLIENT-ID',
        clientSecret: 'PAYPAL-SECRET-NUNCA-SALE',
      },
    })
  );
  try {
    const { status, text, body } = await api.request('GET', '/api/commerce/config');
    assert.equal(status, 200);
    assert.match(text, /PUBLICA-123/);
    assert.doesNotMatch(text, /PRIVADA-SECRETA-456/);
    assert.match(text, /PAYPAL-CLIENT-ID/);
    assert.doesNotMatch(text, /PAYPAL-SECRET-NUNCA-SALE/);

    const paypal = body.paymentMethods.find((m) => m.id === 'paypal');
    assert.equal(paypal.ready, true);
    assert.ok(paypal.client.scriptUrl.includes('PAYPAL-CLIENT-ID'));
  } finally {
    await api.close();
  }
});

test('el checkout solo ve los métodos que el servidor puede procesar', async () => {
  const api = await startServer();
  try {
    const { body } = await api.request('GET', '/api/commerce/config');
    const ids = body.paymentMethods.map((m) => m.id);

    assert.ok(ids.includes('bank_transfer'));
    assert.equal(ids.includes('sandbox'), false);
    assert.ok(ids.includes('paypal'), 'PayPal aparece aunque aún no cobre');
    assert.equal(ids.includes('cardnet'), false, 'CardNET está deshabilitada en esta config');
    const paypal = body.paymentMethods.find((m) => m.id === 'paypal');
    assert.equal(paypal.ready, false);
  } finally {
    await api.close();
  }
});

// -------------------------------------------------------------- cotización

test('la cotización devuelve el total calculado por el servidor', async () => {
  const api = await startServer();
  try {
    const data = await cotizar(api);
    const product = getProductById('emperador');
    const esperadoSubtotal = Math.round(product.pricePerBox * 100) * 2;
    const esperadoEnvio = Math.round(calculateShipping('US', 2).cost * 100);

    assert.equal(data.quote.subtotalCents, esperadoSubtotal);
    assert.equal(data.quote.totalCents, esperadoSubtotal + esperadoEnvio);
    assert.ok(data.quoteToken.includes('.'));
  } finally {
    await api.close();
  }
});

// -------------------------------------------------------------------- pago

test('un pedido completo se confirma y se puede consultar', async () => {
  const api = await startServer(testConfig(), { gateways: pasarelaAprobada() });
  try {
    const { quoteToken, quote } = await cotizar(api);

    const created = await api.request('POST', '/api/commerce/orders', {
      headers: { 'Idempotency-Key': 'clave-de-prueba-0001' },
      body: { quoteToken, paymentMethod: 'test_pay', paymentPayload: {}, ...datosCliente() },
    });

    assert.equal(created.status, 201, created.text);
    assert.equal(created.body.paymentStatus, 'paid');
    assert.equal(created.body.status, 'confirmed');
    assert.ok(created.body.accessToken);

    const consulta = await api.request(
      'GET',
      `/api/commerce/orders/${created.body.reference}?t=${encodeURIComponent(created.body.accessToken)}`
    );

    assert.equal(consulta.status, 200);
    assert.equal(consulta.body.totalCents, quote.totalCents);
    assert.equal(consulta.body.customer.email, 'ana@ejemplo.com');
  } finally {
    await api.close();
  }
});

test('ATAQUE: manipular el total del carrito no cambia lo que se cobra', async () => {
  const api = await startServer(testConfig(), { gateways: pasarelaAprobada() });
  try {
    const { quoteToken, quote } = await cotizar(api);

    // El atacante reenvía la cotización legítima pero añade importes propios.
    const created = await api.request('POST', '/api/commerce/orders', {
      body: {
        quoteToken,
        paymentMethod: 'test_pay',
        paymentPayload: {},
        total: 1,
        totalCents: 1,
        amount: 1,
        subtotalCents: 1,
        ...datosCliente(),
      },
    });

    assert.equal(created.status, 201);

    const order = await api.request(
      'GET',
      `/api/commerce/orders/${created.body.reference}?t=${encodeURIComponent(created.body.accessToken)}`
    );
    assert.equal(order.body.totalCents, quote.totalCents, 'el total debe ser el del servidor');
    assert.notEqual(order.body.totalCents, 1);
  } finally {
    await api.close();
  }
});

test('ATAQUE: una cotización con la firma alterada se rechaza', async () => {
  const api = await startServer(testConfig(), { gateways: pasarelaAprobada() });
  try {
    const { quoteToken } = await cotizar(api);

    const [payload, signature] = quoteToken.split('.');
    const decoded = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
    decoded.quote.totalCents = 100;
    const forjada = `${Buffer.from(JSON.stringify(decoded)).toString('base64url')}.${signature}`;

    const response = await api.request('POST', '/api/commerce/orders', {
      body: { quoteToken: forjada, paymentMethod: 'test_pay', ...datosCliente() },
    });

    assert.equal(response.status, 400);
    assert.equal(response.body.code, 'QUOTE_TAMPERED');
  } finally {
    await api.close();
  }
});

test('IDEMPOTENCIA: dos envíos con la misma clave producen un solo pedido', async () => {
  const api = await startServer(testConfig(), { gateways: pasarelaAprobada() });
  try {
    const { quoteToken } = await cotizar(api);
    const payload = {
      body: { quoteToken, paymentMethod: 'test_pay', paymentPayload: {}, ...datosCliente() },
      headers: { 'Idempotency-Key': 'doble-clic-del-cliente' },
    };

    const primero = await api.request('POST', '/api/commerce/orders', payload);
    const segundo = await api.request('POST', '/api/commerce/orders', payload);

    assert.equal(primero.status, 201);
    assert.equal(segundo.status, 200, 'el segundo debe devolver el resultado guardado');
    assert.equal(primero.body.reference, segundo.body.reference);

    const ficheros = fs.readdirSync(path.join(api.config.dataDir, 'orders'));
    assert.equal(ficheros.length, 1, 'solo puede existir un pedido en disco');
  } finally {
    await api.close();
  }
});

test('un pago rechazado deja el pedido como fallido, nunca como confirmado', async () => {
  const api = await startServer(testConfig(), {
    gateways: registroConPasarela({
      id: 'test_pay',
      async charge() {
        throw new CheckoutError(ERROR_CODES.CARD_DECLINED, 'Fondos insuficientes.', {
          httpStatus: 402,
        });
      },
    }),
  });
  try {
    const { quoteToken } = await cotizar(api);

    const response = await api.request('POST', '/api/commerce/orders', {
      body: { quoteToken, paymentMethod: 'test_pay', ...datosCliente() },
    });

    assert.equal(response.status, 402);
    assert.equal(response.body.code, ERROR_CODES.CARD_DECLINED);
    assert.equal(response.body.success, undefined, 'un rechazo no puede parecer un éxito');

    // El pedido quedó registrado como fallido: hay rastro del intento.
    const ficheros = fs.readdirSync(path.join(api.config.dataDir, 'orders'));
    assert.equal(ficheros.length, 1);
    const order = JSON.parse(
      fs.readFileSync(path.join(api.config.dataDir, 'orders', ficheros[0]), 'utf8')
    );
    assert.equal(order.status, 'payment_failed');
    assert.equal(order.paymentStatus, 'failed');
  } finally {
    await api.close();
  }
});

test('si la pasarela se cae, el fallo no se disfraza de pago aprobado', async () => {
  const api = await startServer(testConfig(), {
    gateways: registroConPasarela({
      id: 'test_pay',
      async charge() {
        throw new Error('ECONNRESET contra el procesador');
      },
    }),
  });
  try {
    const { quoteToken } = await cotizar(api);

    const response = await api.request('POST', '/api/commerce/orders', {
      body: { quoteToken, paymentMethod: 'test_pay', ...datosCliente() },
    });

    assert.equal(response.status, 500);
    assert.equal(response.body.code, ERROR_CODES.INTERNAL);
    assert.ok(response.body.correlationId, 'el cliente puede citar el identificador al soporte');
    assert.doesNotMatch(response.text, /ECONNRESET/, 'el detalle interno no sale al cliente');
  } finally {
    await api.close();
  }
});

test('la transferencia bancaria queda pendiente y devuelve las cuentas', async () => {
  const api = await startServer();
  try {
    const { quoteToken } = await cotizar(api);

    const response = await api.request('POST', '/api/commerce/orders', {
      body: { quoteToken, paymentMethod: 'bank_transfer', ...datosCliente() },
    });

    assert.equal(response.status, 201);
    assert.equal(response.body.paymentStatus, 'pending_transfer');
    assert.equal(response.body.status, 'awaiting_payment');
    assert.ok(response.body.bankTransfer.accounts.length >= 1);
    assert.match(response.body.message, /CS-/);
  } finally {
    await api.close();
  }
});

test('no se puede pagar con una pasarela deshabilitada', async () => {
  const api = await startServer();
  try {
    const { quoteToken } = await cotizar(api);
    const response = await api.request('POST', '/api/commerce/orders', {
      body: { quoteToken, paymentMethod: 'cardnet', paymentPayload: { trxToken: 'x' }, ...datosCliente() },
    });

    assert.equal(response.status, 503);
    assert.equal(response.body.code, 'GATEWAY_NOT_CONFIGURED');
  } finally {
    await api.close();
  }
});

test('PayPal aparece en el checkout pero no cobra sin credenciales', async () => {
  const api = await startServer();
  try {
    const config = await api.request('GET', '/api/commerce/config');
    const paypal = config.body.paymentMethods.find((m) => m.id === 'paypal');
    assert.ok(paypal);
    assert.equal(paypal.ready, false);

    const { quoteToken } = await cotizar(api);

    const setup = await api.request('POST', '/api/commerce/paypal/orders', {
      body: { quoteToken },
    });
    assert.equal(setup.status, 503);

    const cobro = await api.request('POST', '/api/commerce/orders', {
      body: {
        quoteToken,
        paymentMethod: 'paypal',
        paymentPayload: { paypalOrderId: 'PAYPAL-ORDER-1' },
        ...datosCliente(),
      },
    });
    assert.equal(cobro.status, 503);
    assert.equal(cobro.body.code, 'GATEWAY_NOT_CONFIGURED');
  } finally {
    await api.close();
  }
});

test('PayPal configurado crea una orden de checkout sin registrar todavía el pedido', async () => {
  const api = await startServer(testConfig(), { gateways: registroPaypalPrueba() });
  try {
    const { quoteToken, quote } = await cotizar(api);

    const setup = await api.request('POST', '/api/commerce/paypal/orders', {
      body: { quoteToken },
    });

    assert.equal(setup.status, 200, setup.text);
    assert.match(setup.body.paypalOrderId, /^PAYPAL-ORDER-/);
    assert.equal(setup.body.status, 'CREATED');

    const ficheros = fs.readdirSync(path.join(api.config.dataDir, 'orders'));
    assert.equal(
      ficheros.length,
      0,
      'crear la orden PayPal no debe registrar un pedido si el comprador cancela'
    );

    assert.equal(quote.totalCents > 0, true);
  } finally {
    await api.close();
  }
});

test('PayPal configurado captura el pago y confirma el pedido', async () => {
  const api = await startServer(testConfig(), { gateways: registroPaypalPrueba() });
  try {
    const { quoteToken, quote } = await cotizar(api, [
      { productId: 'emperador', unitType: 'box', quantity: 1 },
      { productId: 'sultan', unitType: 'unit', quantity: 3 },
    ]);

    const setup = await api.request('POST', '/api/commerce/paypal/orders', {
      body: { quoteToken },
    });
    assert.equal(setup.status, 200, setup.text);

    const created = await api.request('POST', '/api/commerce/orders', {
      headers: { 'Idempotency-Key': 'paypal-prueba-0001' },
      body: {
        quoteToken,
        paymentMethod: 'paypal',
        paymentPayload: { paypalOrderId: setup.body.paypalOrderId },
        ...datosCliente(),
      },
    });

    assert.equal(created.status, 201, created.text);
    assert.equal(created.body.paymentStatus, 'paid');
    assert.equal(created.body.status, 'confirmed');
    assert.ok(created.body.accessToken);

    const order = await api.store.get(created.body.reference);
    assert.equal(order.totalCents, quote.totalCents);
    assert.equal(order.payment.gateway, 'paypal');
    assert.equal(order.payment.transactionId, `CAP-${setup.body.paypalOrderId}`);
    assert.equal(order.payment.diagnostics.paypalOrderId, setup.body.paypalOrderId);
  } finally {
    await api.close();
  }
});

test('PayPal configurado rechaza confirmar el pedido si falta paypalOrderId', async () => {
  const api = await startServer(testConfig(), { gateways: registroPaypalPrueba() });
  try {
    const { quoteToken } = await cotizar(api);

    const response = await api.request('POST', '/api/commerce/orders', {
      body: {
        quoteToken,
        paymentMethod: 'paypal',
        paymentPayload: {},
        ...datosCliente(),
      },
    });

    assert.equal(response.status, 400);
    assert.equal(response.body.code, ERROR_CODES.PAYPAL_ORDER_MISSING);
  } finally {
    await api.close();
  }
});

test('cambiar el país después de cotizar invalida el pedido', async () => {
  const api = await startServer(testConfig(), { gateways: pasarelaAprobada() });
  try {
    const { quoteToken } = await cotizar(api, CARRITO, 'US');

    const response = await api.request('POST', '/api/commerce/orders', {
      body: {
        quoteToken,
        paymentMethod: 'test_pay',
        ...datosCliente({
          shipping: { address: 'Calle 1', city: 'Tokio', state: '', postalCode: '', country: 'JP' },
        }),
      },
    });

    assert.equal(response.status, 409, 'el flete de Japón no es el de Estados Unidos');
    assert.equal(response.body.code, 'QUOTE_INVALID');
  } finally {
    await api.close();
  }
});

test('sin aceptar las políticas no hay pedido', async () => {
  const api = await startServer();
  try {
    const { quoteToken } = await cotizar(api);

    const response = await api.request('POST', '/api/commerce/orders', {
      body: {
        quoteToken,
        paymentMethod: 'bank_transfer',
        ...datosCliente({ acceptances: { finalSale: true, customs: false } }),
      },
    });

    assert.equal(response.status, 400);
    assert.match(response.body.error, /condiciones de venta/i);
  } finally {
    await api.close();
  }
});

// -------------------------------------------------------------- seguridad

test('un pedido no se puede consultar sin el token de acceso', async () => {
  const api = await startServer(testConfig(), { gateways: pasarelaAprobada() });
  try {
    const { quoteToken } = await cotizar(api);
    const created = await api.request('POST', '/api/commerce/orders', {
      body: { quoteToken, paymentMethod: 'test_pay', ...datosCliente() },
    });

    const sinToken = await api.request('GET', `/api/commerce/orders/${created.body.reference}`);
    const tokenFalso = await api.request(
      'GET',
      `/api/commerce/orders/${created.body.reference}?t=inventado`
    );

    assert.equal(sinToken.status, 404);
    assert.equal(tokenFalso.status, 404);
    assert.doesNotMatch(sinToken.text, /ana@ejemplo\.com/);
  } finally {
    await api.close();
  }
});

test('un origen no autorizado recibe 403', async () => {
  const api = await startServer();
  try {
    const response = await api.request('POST', '/api/commerce/quote', {
      headers: { Origin: 'https://sitio-malicioso.example' },
      body: { items: CARRITO, country: 'US' },
    });

    assert.equal(response.status, 403);
    assert.equal(response.body.code, 'CORS_DENIED');
  } finally {
    await api.close();
  }
});

test('el origen canónico sí recibe las cabeceras CORS', async () => {
  const api = await startServer();
  try {
    const response = await api.request('POST', '/api/commerce/quote', {
      headers: { Origin: 'https://www.cazadordesuenocigars.com' },
      body: { items: CARRITO, country: 'US' },
    });

    assert.equal(response.status, 200);
    assert.equal(
      response.headers.get('access-control-allow-origin'),
      'https://www.cazadordesuenocigars.com'
    );
  } finally {
    await api.close();
  }
});

test('una ruta inexistente bajo /api responde JSON, no HTML', async () => {
  const api = await startServer();
  try {
    const response = await api.request('GET', '/api/commerce/no-existe');
    assert.equal(response.status, 404);
    assert.equal(response.body.code, 'NOT_FOUND');
    assert.doesNotMatch(response.text, /<html/i);
  } finally {
    await api.close();
  }
});

test('cada respuesta lleva un correlationId para rastrear la transacción', async () => {
  const api = await startServer();
  try {
    const response = await api.request('GET', '/api/commerce/health');
    assert.match(response.headers.get('x-correlation-id') || '', /^cds_[0-9a-f]{16}$/);
  } finally {
    await api.close();
  }
});

test('el webhook de CardNET rechaza notificaciones sin autenticación válida', async () => {
  const api = await startServer(
    testConfig({
      cardnet: { ...testConfig().cardnet, privateAccountKey: 'PRIVADA-456' },
    })
  );
  try {
    const sinAuth = await api.request('POST', '/api/commerce/webhooks/cardnet', {
      body: { ResourceType: 1, ResourceObject: { Order: 'CS-1', Status: 1 } },
    });
    assert.equal(sinAuth.status, 401);

    const authMala = await api.request('POST', '/api/commerce/webhooks/cardnet', {
      headers: { Authorization: `Basic ${Buffer.from('otra-clave:').toString('base64')}` },
      body: { ResourceType: 1, ResourceObject: { Order: 'CS-1', Status: 1 } },
    });
    assert.equal(authMala.status, 401);
  } finally {
    await api.close();
  }
});

test('el webhook autenticado confirma un pedido pendiente', async () => {
  const config = testConfig({
    cardnet: { ...testConfig().cardnet, privateAccountKey: 'PRIVADA-456' },
  });
  const api = await startServer(config);
  try {
    const { quoteToken } = await cotizar(api);
    const created = await api.request('POST', '/api/commerce/orders', {
      body: { quoteToken, paymentMethod: 'bank_transfer', ...datosCliente() },
    });
    assert.equal(created.body.paymentStatus, 'pending_transfer');

    const webhook = await api.request('POST', '/api/commerce/webhooks/cardnet', {
      headers: { Authorization: `Basic ${Buffer.from('PRIVADA-456:').toString('base64')}` },
      body: {
        ResourceType: 1,
        ResourceObject: { Order: created.body.reference, Status: 1, PurchaseId: 90210 },
      },
    });
    assert.equal(webhook.status, 200);

    const order = await api.store.get(created.body.reference);
    assert.equal(order.paymentStatus, 'paid');
    assert.equal(order.status, 'confirmed');
  } finally {
    await api.close();
  }
});

test('el límite de intentos de pago protege contra pruebas de tarjetas robadas', async () => {
  const api = await startServer(
    testConfig({ rateLimit: { windowMs: 60_000, maxQuotes: 500, maxPayments: 3 } })
  );
  try {
    const { quoteToken } = await cotizar(api);
    const cuerpo = { quoteToken, paymentMethod: 'bank_transfer', ...datosCliente() };

    const codigos = [];
    for (let i = 0; i < 5; i += 1) {
      const response = await api.request('POST', '/api/commerce/orders', { body: cuerpo });
      codigos.push(response.status);
    }

    assert.ok(codigos.includes(429), `se esperaba un 429 entre ${codigos.join(', ')}`);
  } finally {
    await api.close();
  }
});

test('un cuerpo que no es JSON válido no derriba el servicio', async () => {
  const api = await startServer();
  try {
    const response = await fetch(`${api.base}/api/commerce/quote`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{ esto no es json',
    });
    assert.equal(response.status, 400);

    const salud = await api.request('GET', '/api/commerce/health');
    assert.equal(salud.status, 200, 'el servicio sigue en pie');
  } finally {
    await api.close();
  }
});
