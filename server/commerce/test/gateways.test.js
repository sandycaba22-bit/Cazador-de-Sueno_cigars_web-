/**
 * Contrato del registro de pasarelas.
 *
 * El checkout no habla con CardNET, PayPal ni el banco a pelo: pide un id y
 * trabaja contra gateways/base.js. Estas pruebas clavan ese contrato y el
 * modo producción: sandbox apagado, precios del servidor, ninguna clave privada
 * en la descripción pública.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const { createGatewayRegistry } = require('../gateways');
const { ERROR_CODES } = require('../errors');
const { APP_CONFIG } = require('../../../js/config');
const { collectConfigWarnings, collectProductionBlocks, REPO_ROOT } = require('../config');

function productionLike(overrides = {}) {
  return {
    isProduction: true,
    nodeEnv: 'production',
    host: '127.0.0.1',
    dataDir: '/var/lib/cazador-de-suenos/commerce',
    corsOrigins: ['https://www.cazadordesuenocigars.com'],
    sandbox: { enabled: false },
    bankTransfer: { enabled: true },
    cardnet: {
      enabled: false,
      publicAccountKey: '',
      privateAccountKey: '',
      baseUrl: 'https://servicios.cardnet.com.do/servicios/tokens',
      currency: 'DOP',
      usdToDopRate: 0,
    },
    paypal: {
      enabled: false,
      clientId: '',
      clientSecret: '',
      mode: 'live',
      currency: 'USD',
    },
    quoteSecretProvided: true,
    ...overrides,
  };
}

test('el registro expone exactamente las cuatro pasarelas del contrato', () => {
  const registry = createGatewayRegistry(productionLike(), APP_CONFIG);
  const ids = registry.list().map((g) => g.id).sort();
  assert.deepEqual(ids, ['bank_transfer', 'cardnet', 'paypal', 'sandbox']);
});

test('en producción el checkout no ofrece sandbox ni CardNET sin claves', () => {
  const registry = createGatewayRegistry(productionLike(), APP_CONFIG);
  const ids = registry.describeAvailable().map((m) => m.id);

  assert.ok(ids.includes('bank_transfer'));
  assert.ok(ids.includes('paypal'), 'PayPal se pinta aunque aún no cobre');
  assert.equal(ids.includes('sandbox'), false);
  assert.equal(ids.includes('cardnet'), false);
});

test('CardNET aparece solo cuando las dos claves están y el interruptor está on', () => {
  const apagada = createGatewayRegistry(productionLike(), APP_CONFIG);
  assert.equal(
    apagada.describeAvailable().some((m) => m.id === 'cardnet'),
    false
  );

  const lista = createGatewayRegistry(
    productionLike({
      cardnet: {
        enabled: true,
        publicAccountKey: 'PUB',
        privateAccountKey: 'PRIV',
        baseUrl: 'https://servicios.cardnet.com.do/servicios/tokens',
        currency: 'USD',
        usdToDopRate: 0,
      },
    }),
    APP_CONFIG
  );
  const cardnet = lista.describeAvailable().find((m) => m.id === 'cardnet');
  assert.ok(cardnet);
  assert.equal(JSON.stringify(cardnet).includes('PRIV'), false);
});

test('cobrar con una pasarela no configurada se rechaza antes de tocar la red', () => {
  const registry = createGatewayRegistry(productionLike(), APP_CONFIG);
  assert.throws(
    () => registry.get('sandbox'),
    (error) => error.code === ERROR_CODES.GATEWAY_NOT_CONFIGURED
  );
  assert.throws(
    () => registry.get('cardnet'),
    (error) => error.code === ERROR_CODES.GATEWAY_NOT_CONFIGURED
  );
  assert.throws(
    () => registry.get('inventada'),
    (error) => error.code === ERROR_CODES.GATEWAY_UNKNOWN
  );
});

test('ninguna pasarela declara que necesita datos de tarjeta en este servidor', () => {
  const registry = createGatewayRegistry(
    productionLike({ sandbox: { enabled: true } }),
    APP_CONFIG
  );
  for (const gateway of registry.list()) {
    assert.equal(
      gateway.requiresCardData,
      false,
      `${gateway.id} no debe recibir PAN: eso nos sacaría de SAQ A-EP`
    );
  }
});

test('producción se niega a arrancar si los pedidos vivirían en el webroot', () => {
  const blocks = collectProductionBlocks(
    productionLike({ dataDir: path.join(REPO_ROOT, '.commerce-data') })
  );
  assert.ok(blocks.some((b) => /DATA_DIR/.test(b)));
});

test('producción se niega a arrancar si el servicio no escucha en loopback', () => {
  const blocks = collectProductionBlocks(productionLike({ host: '0.0.0.0' }));
  assert.ok(blocks.some((b) => /HOST/.test(b)));
});

test('producción bien configurada no bloquea el arranque', () => {
  assert.deepEqual(collectProductionBlocks(productionLike()), []);
});

test('sandbox activo en producción impide arrancar', () => {
  const warnings = collectConfigWarnings(productionLike({ sandbox: { enabled: true } }));
  assert.ok(warnings.some((w) => /SANDBOX/.test(w)));
  const blocks = collectProductionBlocks(productionLike({ sandbox: { enabled: true } }));
  assert.ok(blocks.some((b) => /SANDBOX/.test(b)));
});

test('producción se niega a arrancar sin clave de firma de cotizaciones', () => {
  const blocks = collectProductionBlocks(productionLike({ quoteSecretProvided: false }));
  assert.ok(blocks.some((b) => /QUOTE_SECRET/.test(b)));
});
