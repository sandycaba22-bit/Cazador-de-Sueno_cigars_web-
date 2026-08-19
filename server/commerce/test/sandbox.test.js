const test = require('node:test');
const assert = require('node:assert/strict');

const { createSandboxGateway } = require('../gateways/sandbox');
const { ERROR_CODES } = require('../errors');
const { createLogger } = require('../logger');

const silentLog = createLogger({}, { log() {}, warn() {}, error() {} });

function contexto(amountCents) {
  return {
    orderReference: 'CS-TEST-03',
    amountCents,
    currency: 'USD',
    customer: { fullName: 'Ana', email: 'ana@ejemplo.com', phone: '8095551234' },
    clientIp: '127.0.0.1',
    idempotencyKey: 'abcdef0123456789',
    payload: {},
    log: silentLog,
  };
}

async function expectRejection(promise, code) {
  try {
    await promise;
  } catch (error) {
    assert.equal(error.code, code);
    return error;
  }
  assert.fail(`se esperaba un error ${code}`);
}

test('solo existe si se habilita explícitamente', () => {
  assert.equal(createSandboxGateway(false).isConfigured(), false);
  assert.equal(createSandboxGateway(true).isConfigured(), true);
});

test('deshabilitada, rechaza el pago en lugar de aprobarlo por defecto', () => {
  assert.throws(
    () => createSandboxGateway(false).validatePayload({}),
    (e) => e.code === ERROR_CODES.GATEWAY_NOT_CONFIGURED
  );
});

test('aprueba un importe normal', async () => {
  const result = await createSandboxGateway(true).charge(contexto(41_700));
  assert.equal(result.status, 'paid');
  assert.equal(result.diagnostics.simulated, true);
  assert.match(result.customerMessage, /ningún cargo real/i);
});

test('los centavos disparadores simulan cada modo de fallo', async () => {
  const gateway = createSandboxGateway(true);

  await expectRejection(gateway.charge(contexto(41_701)), ERROR_CODES.CARD_DECLINED);
  await expectRejection(gateway.charge(contexto(41_702)), ERROR_CODES.GATEWAY_TIMEOUT);
  await expectRejection(gateway.charge(contexto(41_703)), ERROR_CODES.GATEWAY_BAD_RESPONSE);
});

test('el rechazo simulado usa el mismo mensaje que un rechazo real por fondos', async () => {
  const error = await expectRejection(
    createSandboxGateway(true).charge(contexto(41_701)),
    ERROR_CODES.CARD_DECLINED
  );
  assert.match(error.customerMessage, /[Ff]ondos insuficientes/);
});
