const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { createOrdersStore } = require('../orders-store');
const { createLogger } = require('../logger');
const { ERROR_CODES } = require('../errors');

const silentLog = createLogger({}, { log() {}, warn() {}, error() {} });

function tempStore() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cds-commerce-'));
  return { store: createOrdersStore(dir, silentLog), dir };
}

function pedido(reference = 'CS-TEST-01') {
  return {
    reference,
    status: 'processing',
    customer: { fullName: 'Ana', email: 'ana@ejemplo.com' },
    totalCents: 41_700,
  };
}

test('guarda y recupera un pedido', async () => {
  const { store } = tempStore();
  await store.create(pedido());

  const leido = await store.get('CS-TEST-01');
  assert.equal(leido.reference, 'CS-TEST-01');
  assert.equal(leido.totalCents, 41_700);
  assert.ok(Date.parse(leido.registeredAt));
});

test('una referencia repetida se rechaza: es la última barrera contra el doble cobro', async () => {
  const { store } = tempStore();
  await store.create(pedido());

  await assert.rejects(
    () => store.create(pedido()),
    (error) => error.code === ERROR_CODES.DUPLICATE_ORDER
  );
});

test('dos escrituras concurrentes de la misma referencia: solo una gana', async () => {
  const { store } = tempStore();

  const resultados = await Promise.allSettled([
    store.create(pedido('CS-CARRERA')),
    store.create(pedido('CS-CARRERA')),
    store.create(pedido('CS-CARRERA')),
  ]);

  const exitosas = resultados.filter((r) => r.status === 'fulfilled');
  assert.equal(exitosas.length, 1);
});

test('actualizar conserva los campos previos y añade updatedAt', async () => {
  const { store } = tempStore();
  await store.create(pedido());

  const actualizado = await store.update('CS-TEST-01', { status: 'confirmed' });
  assert.equal(actualizado.status, 'confirmed');
  assert.equal(actualizado.customer.email, 'ana@ejemplo.com');
  assert.ok(Date.parse(actualizado.updatedAt));
});

test('actualizar un pedido inexistente devuelve null en lugar de crearlo', async () => {
  const { store } = tempStore();
  assert.equal(await store.update('CS-NO-EXISTE', { status: 'confirmed' }), null);
});

test('rechaza referencias con salto de directorio', async () => {
  const { store } = tempStore();

  await assert.rejects(
    () => store.create({ ...pedido(), reference: '../../../etc/passwd' }),
    (error) => error.code === ERROR_CODES.VALIDATION_FAILED
  );
  assert.equal(await store.get('../../../etc/passwd'), null);
});

test('el reintento con la misma clave de idempotencia devuelve el resultado guardado', async () => {
  const { store } = tempStore();
  assert.equal(await store.findAttempt('clave123456789'), null);

  await store.saveAttempt('clave123456789', { reference: 'CS-1', response: { success: true } });

  const encontrado = await store.findAttempt('clave123456789');
  assert.equal(encontrado.reference, 'CS-1');
  assert.equal(encontrado.response.success, true);
});

test('los pedidos no se escriben dentro del árbol público del sitio', async () => {
  const { store, dir } = tempStore();
  await store.create(pedido());

  const repoRoot = path.join(__dirname, '..', '..', '..');
  assert.equal(
    path.resolve(dir).startsWith(path.resolve(repoRoot)),
    false,
    'el directorio de datos no puede estar bajo el webroot'
  );
});

test('purga las claves de idempotencia caducadas', async () => {
  const { store } = tempStore();
  await store.saveAttempt('claveantigua123', { reference: 'CS-1', response: {} });

  assert.equal(await store.pruneAttempts(3600), 0, 'una clave reciente no se toca');
  assert.equal(await store.pruneAttempts(-1), 1, 'una clave caducada se elimina');
  assert.equal(await store.findAttempt('claveantigua123'), null);
});
