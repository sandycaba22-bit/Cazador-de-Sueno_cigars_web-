const test = require('node:test');
const assert = require('node:assert/strict');

const { createBankTransferGateway } = require('../gateways/bank-transfer');
const { ERROR_CODES } = require('../errors');
const { createLogger } = require('../logger');
const { APP_CONFIG } = require('../../../js/config');

const silentLog = createLogger({}, { log() {}, warn() {}, error() {} });

function contexto() {
  return {
    orderReference: 'CS-TEST-02',
    amountCents: 41_700,
    currency: 'USD',
    customer: { fullName: 'Ana Pérez', email: 'ana@ejemplo.com', phone: '8095551234' },
    clientIp: '190.80.1.2',
    idempotencyKey: 'abcdef0123456789',
    payload: {},
    log: silentLog,
  };
}

test('está configurada cuando hay al menos una cuenta bancaria', () => {
  assert.equal(createBankTransferGateway(APP_CONFIG, true).isConfigured(), true);
  assert.equal(createBankTransferGateway(APP_CONFIG, false).isConfigured(), false);
  assert.equal(
    createBankTransferGateway({ bankTransfer: { accounts: [] } }, true).isConfigured(),
    false
  );
});

test('reserva el pedido en estado pendiente de transferencia, no como pagado', async () => {
  const result = await createBankTransferGateway(APP_CONFIG, true).charge(contexto());

  assert.equal(result.status, 'pending_transfer');
  assert.notEqual(result.status, 'paid');
  assert.equal(result.transactionId, null);
});

test('el mensaje al cliente incluye la referencia que debe poner en el concepto', async () => {
  const result = await createBankTransferGateway(APP_CONFIG, true).charge(contexto());
  assert.match(result.customerMessage, /CS-TEST-02/);
});

test('devuelve las cuentas de Banreservas y BHD para mostrarlas en la confirmación', async () => {
  const result = await createBankTransferGateway(APP_CONFIG, true).charge(contexto());
  const bancos = result.instructions.accounts.map((a) => a.bankName);

  assert.ok(bancos.some((b) => /Reservas/i.test(b)));
  assert.ok(bancos.some((b) => /BHD/i.test(b)));
});

test('describe() no filtra campos que no existan en la configuración', () => {
  const description = createBankTransferGateway(APP_CONFIG, true).describe();

  assert.equal(description.available, true);
  for (const account of description.client.accounts) {
    assert.ok(account.bankName);
    assert.ok(account.accountNumber);
  }
});

test('si está deshabilitada, validatePayload lo impide antes de reservar nada', () => {
  const gateway = createBankTransferGateway(APP_CONFIG, false);
  assert.throws(
    () => gateway.validatePayload({}),
    (e) => e.code === ERROR_CODES.GATEWAY_NOT_CONFIGURED
  );
});
