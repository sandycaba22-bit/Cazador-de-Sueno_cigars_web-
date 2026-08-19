const test = require('node:test');
const assert = require('node:assert/strict');

const { createCardnetGateway } = require('../gateways/cardnet');
const { ERROR_CODES } = require('../errors');
const { createLogger } = require('../logger');

const silentLog = createLogger({}, { log() {}, warn() {}, error() {} });

function baseConfig(overrides = {}) {
  return {
    enabled: true,
    baseUrl: 'https://labservicios.cardnet.com.do/servicios/tokens',
    publicAccountKey: 'clave-publica',
    privateAccountKey: 'clave-privada',
    currency: 'USD',
    usdToDopRate: 0,
    timeoutMs: 5000,
    captureImmediately: true,
    ...overrides,
  };
}

function contexto(overrides = {}) {
  return {
    orderReference: 'CS-TEST-01',
    amountCents: 41_700,
    currency: 'USD',
    customer: { fullName: 'Ana Pérez', email: 'ana@ejemplo.com', phone: '8095551234' },
    clientIp: '190.80.1.2',
    userAgent: 'Mozilla/5.0',
    idempotencyKey: 'abcdef0123456789',
    payload: { trxToken: 'OT_01_token_de_prueba' },
    log: silentLog,
    ...overrides,
  };
}

/** Sustituye fetch y devuelve las llamadas capturadas. */
function stubFetch(responder) {
  const calls = [];
  const original = global.fetch;
  global.fetch = async (url, options) => {
    calls.push({ url, options, body: JSON.parse(options.body) });
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
  return { status, text: async () => JSON.stringify(body) };
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

test('no está configurada si falta cualquiera de las dos claves', () => {
  assert.equal(createCardnetGateway(baseConfig({ privateAccountKey: '' })).isConfigured(), false);
  assert.equal(createCardnetGateway(baseConfig({ publicAccountKey: '' })).isConfigured(), false);
  assert.equal(createCardnetGateway(baseConfig({ enabled: false })).isConfigured(), false);
  assert.equal(createCardnetGateway(baseConfig()).isConfigured(), true);
});

test('describe() expone la clave pública pero nunca la privada', () => {
  const description = createCardnetGateway(baseConfig()).describe();
  const serialized = JSON.stringify(description);

  assert.match(serialized, /clave-publica/);
  assert.doesNotMatch(serialized, /clave-privada/);
  assert.match(description.client.scriptUrl, /PWCheckout\.js\?key=clave-publica/);
});

test('exige el token de tarjeta antes de intentar cobrar', () => {
  const gateway = createCardnetGateway(baseConfig());
  assert.throws(() => gateway.validatePayload({}), (e) => e.code === ERROR_CODES.CARD_TOKEN_MISSING);
  assert.throws(
    () => gateway.validatePayload({ trxToken: '   ' }),
    (e) => e.code === ERROR_CODES.CARD_TOKEN_MISSING
  );
  assert.doesNotThrow(() => gateway.validatePayload({ trxToken: 'OT_01_x' }));
});

test('un pago aprobado devuelve el identificador de compra y el código de autorización', async () => {
  const fetchStub = stubFetch(async () =>
    jsonResponse({
      PurchaseId: 987654,
      Status: 1,
      Transaction: { ResponseCode: '00', AuthorizationCode: '008766' },
    })
  );

  try {
    const result = await createCardnetGateway(baseConfig()).charge(contexto());

    assert.equal(result.status, 'paid');
    assert.equal(result.transactionId, '987654');
    assert.equal(result.authorizationCode, '008766');
    assert.equal(fetchStub.calls.length, 1);
    assert.match(fetchStub.calls[0].url, /\/v1\/api\/purchase$/);
  } finally {
    fetchStub.restore();
  }
});

test('CUMPLIMIENTO PCI: la petición no contiene ningún dato de tarjeta', async () => {
  const fetchStub = stubFetch(async () =>
    jsonResponse({ PurchaseId: 1, Status: 1, Transaction: { ResponseCode: '00' } })
  );

  try {
    await createCardnetGateway(baseConfig()).charge(contexto());

    const enviado = fetchStub.calls[0].body;
    const claves = Object.keys(enviado).map((k) => k.toLowerCase());

    for (const prohibida of ['card-number', 'cardnumber', 'cvv', 'cvc', 'expiration-date', 'pan']) {
      assert.equal(claves.includes(prohibida), false, `no debe enviarse ${prohibida}`);
    }
    assert.equal(enviado.TrxToken, 'OT_01_token_de_prueba');
  } finally {
    fetchStub.restore();
  }
});

test('envía la clave de idempotencia como UniqueID para no duplicar el cobro', async () => {
  const fetchStub = stubFetch(async () =>
    jsonResponse({ PurchaseId: 1, Status: 1, Transaction: { ResponseCode: '00' } })
  );

  try {
    await createCardnetGateway(baseConfig()).charge(contexto({ idempotencyKey: 'clave-unica-123' }));
    assert.equal(fetchStub.calls[0].body.UniqueID, 'clave-unica-123');
  } finally {
    fetchStub.restore();
  }
});

test('cobra exactamente el importe autoritativo, en unidades menores', async () => {
  const fetchStub = stubFetch(async () =>
    jsonResponse({ PurchaseId: 1, Status: 1, Transaction: { ResponseCode: '00' } })
  );

  try {
    await createCardnetGateway(baseConfig()).charge(contexto({ amountCents: 41_700 }));
    assert.equal(fetchStub.calls[0].body.Amount, 41_700);
    assert.equal(fetchStub.calls[0].body.Currency, 'USD');
  } finally {
    fetchStub.restore();
  }
});

test('convierte USD a DOP cuando el afiliado liquida en pesos', async () => {
  const fetchStub = stubFetch(async () =>
    jsonResponse({ PurchaseId: 1, Status: 1, Transaction: { ResponseCode: '00' } })
  );

  try {
    const gateway = createCardnetGateway(baseConfig({ currency: 'DOP', usdToDopRate: 60 }));
    const result = await gateway.charge(contexto({ amountCents: 10_000 }));

    assert.equal(fetchStub.calls[0].body.Amount, 600_000, '100 USD a tasa 60 son 6.000 DOP');
    assert.equal(fetchStub.calls[0].body.Currency, 'DOP');
    assert.equal(result.diagnostics.conversionRate, 60);
  } finally {
    fetchStub.restore();
  }
});

test('se niega a cobrar en DOP si no hay tasa configurada, en vez de adivinar', async () => {
  const gateway = createCardnetGateway(baseConfig({ currency: 'DOP', usdToDopRate: 0 }));
  await expectRejection(gateway.charge(contexto()), ERROR_CODES.GATEWAY_NOT_CONFIGURED);
});

test('traduce los códigos del emisor a instrucciones útiles para el comprador', async () => {
  const casos = [
    ['51', /[Ff]ondos insuficientes/],
    ['54', /vencida/],
    ['99', /CVV/],
    ['62', /restricciones/],
  ];

  for (const [responseCode, esperado] of casos) {
    const fetchStub = stubFetch(async () =>
      jsonResponse({ PurchaseId: 5, Status: 4, Transaction: { ResponseCode: responseCode } })
    );
    try {
      const error = await expectRejection(
        createCardnetGateway(baseConfig()).charge(contexto()),
        ERROR_CODES.CARD_DECLINED
      );
      assert.match(error.customerMessage, esperado);
      assert.equal(error.diagnostics.responseCode, responseCode);
    } finally {
      fetchStub.restore();
    }
  }
});

test('un código de emisor desconocido cae en el mensaje genérico, sin filtrarlo', async () => {
  const fetchStub = stubFetch(async () =>
    jsonResponse({ Status: 4, Transaction: { ResponseCode: 'ZZ' } })
  );

  try {
    const error = await expectRejection(
      createCardnetGateway(baseConfig()).charge(contexto()),
      ERROR_CODES.CARD_DECLINED
    );
    assert.doesNotMatch(error.customerMessage, /ZZ/);
    assert.equal(error.diagnostics.responseCode, 'ZZ', 'el código sí queda en el log interno');
  } finally {
    fetchStub.restore();
  }
});

test('traduce los errores de plataforma (PR/TR) sin exponer el código', async () => {
  const fetchStub = stubFetch(async () =>
    jsonResponse({ Status: 4, Errors: [{ Code: 'PR001' }] })
  );

  try {
    const error = await expectRejection(
      createCardnetGateway(baseConfig()).charge(contexto()),
      ERROR_CODES.CARD_DECLINED
    );
    assert.match(error.customerMessage, /sesión de pago caducó/i);
    assert.doesNotMatch(error.customerMessage, /PR001/);
    assert.equal(error.diagnostics.platformCode, 'PR001');
  } finally {
    fetchStub.restore();
  }
});

test('el estado Pending no se confunde con un pago aprobado', async () => {
  const fetchStub = stubFetch(async () => jsonResponse({ PurchaseId: 7, Status: 2 }));

  try {
    const error = await expectRejection(
      createCardnetGateway(baseConfig()).charge(contexto()),
      ERROR_CODES.CARD_DECLINED
    );
    assert.match(error.customerMessage, /verificación/i);
    assert.equal(error.retryable, false, 'no debe reintentarse solo: podría duplicar el cargo');
  } finally {
    fetchStub.restore();
  }
});

test('una respuesta que no es JSON se trata como fallo, no como aprobación', async () => {
  const fetchStub = stubFetch(async () => ({
    status: 502,
    text: async () => '<html>Bad Gateway</html>',
  }));

  try {
    await expectRejection(
      createCardnetGateway(baseConfig()).charge(contexto()),
      ERROR_CODES.GATEWAY_BAD_RESPONSE
    );
  } finally {
    fetchStub.restore();
  }
});

test('un timeout se marca como no reintentable para no cobrar dos veces', async () => {
  const original = global.fetch;
  global.fetch = async (_url, options) =>
    new Promise((_resolve, reject) => {
      options.signal.addEventListener('abort', () => {
        const error = new Error('abortado');
        error.name = 'AbortError';
        reject(error);
      });
    });

  try {
    const gateway = createCardnetGateway(baseConfig({ timeoutMs: 20 }));
    const error = await expectRejection(gateway.charge(contexto()), ERROR_CODES.GATEWAY_TIMEOUT);
    assert.equal(error.retryable, false);
    assert.match(error.customerMessage, /estado de cuenta/i);
  } finally {
    global.fetch = original;
  }
});

test('un fallo de red se reporta como pasarela inalcanzable y sí es reintentable', async () => {
  const fetchStub = stubFetch(async () => {
    throw new Error('ECONNREFUSED');
  });

  try {
    const error = await expectRejection(
      createCardnetGateway(baseConfig()).charge(contexto()),
      ERROR_CODES.GATEWAY_UNREACHABLE
    );
    assert.equal(error.retryable, true);
    assert.match(error.customerMessage, /transferencia bancaria/i);
  } finally {
    fetchStub.restore();
  }
});

test('una pasarela deshabilitada rechaza el cobro antes de tocar la red', async () => {
  const fetchStub = stubFetch(async () => {
    assert.fail('no debería llamarse a la red');
  });

  try {
    const gateway = createCardnetGateway(baseConfig({ enabled: false }));
    await expectRejection(gateway.charge(contexto()), ERROR_CODES.GATEWAY_NOT_CONFIGURED);
    assert.equal(fetchStub.calls.length, 0);
  } finally {
    fetchStub.restore();
  }
});

test('autentica con Basic usando la clave privada como usuario y sin contraseña', async () => {
  const fetchStub = stubFetch(async () =>
    jsonResponse({ PurchaseId: 1, Status: 1, Transaction: { ResponseCode: '00' } })
  );

  try {
    await createCardnetGateway(baseConfig()).charge(contexto());

    const auth = fetchStub.calls[0].options.headers.Authorization;
    assert.match(auth, /^Basic /);
    assert.equal(Buffer.from(auth.slice(6), 'base64').toString('utf8'), 'clave-privada:');
  } finally {
    fetchStub.restore();
  }
});

test('incluye DataDo.Invoice, obligatorio para República Dominicana', async () => {
  const fetchStub = stubFetch(async () =>
    jsonResponse({ PurchaseId: 1, Status: 1, Transaction: { ResponseCode: '00' } })
  );

  try {
    await createCardnetGateway(baseConfig()).charge(contexto());
    assert.equal(fetchStub.calls[0].body.DataDo.Invoice, 'CS-TEST-01');
    assert.equal(fetchStub.calls[0].body.Order, 'CS-TEST-01');
  } finally {
    fetchStub.restore();
  }
});
