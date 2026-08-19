const test = require('node:test');
const assert = require('node:assert/strict');

const { createLogger, redact, scrubText } = require('../logger');

/** Recoge lo que el logger escribiría, para poder inspeccionarlo. */
function capturingSink() {
  const lines = [];
  const push = (line) => lines.push(line);
  return { lines, log: push, warn: push, error: push };
}

test('nunca escribe un número de tarjeta, venga como venga', () => {
  const salida = JSON.stringify(
    redact({
      'card-number': '4111111111111111',
      cvv: '123',
      'expiration-date': '12/28',
      anidado: { pan: '5555444433332222' },
    })
  );

  assert.doesNotMatch(salida, /4111111111111111/);
  assert.doesNotMatch(salida, /5555444433332222/);
  assert.doesNotMatch(salida, /"123"/);
  assert.match(salida, /REDACTADO/);
});

test('limpia PAN incrustados en texto libre de terceros', () => {
  const limpio = scrubText('Rechazo del emisor para la tarjeta 4111 1111 1111 1111 en la terminal');
  assert.doesNotMatch(limpio, /4111/);
  assert.match(limpio, /PAN_REDACTADO/);
});

test('enmascara tokens y correos en lugar de borrarlos, para poder correlacionar', () => {
  const salida = redact({
    trxToken: 'OT_01_kYv0qTHckRiZ4wjCz5NguZRuwFLSIrQc4jiYpVJ8SzQ_',
    email: 'cliente@ejemplo.com',
  });

  assert.notEqual(salida.trxToken, 'OT_01_kYv0qTHckRiZ4wjCz5NguZRuwFLSIrQc4jiYpVJ8SzQ_');
  assert.match(salida.trxToken, /…/);
  assert.equal(salida.email, 'c***@ejemplo.com');
});

test('redacta la cabecera Authorization y las claves de cuenta', () => {
  const salida = redact({
    Authorization: 'Basic bWlfY2xhdmVfcHJpdmFkYTo=',
    privateAccountKey: 'clave-secreta',
    publicAccountKey: 'clave-publica',
  });

  assert.equal(salida.Authorization, '[REDACTADO]');
  assert.equal(salida.privateAccountKey, '[REDACTADO]');
  assert.equal(salida.publicAccountKey, '[REDACTADO]');
});

test('cada línea es un JSON con marca de tiempo, nivel y correlationId', () => {
  const sink = capturingSink();
  const log = createLogger({ service: 'test', correlationId: 'cds_abc' }, sink);

  log.info('pago.inicio', { totalCents: 12345 });

  const record = JSON.parse(sink.lines[0]);
  assert.equal(record.level, 'info');
  assert.equal(record.msg, 'pago.inicio');
  assert.equal(record.correlationId, 'cds_abc');
  assert.equal(record.data.totalCents, 12345);
  assert.ok(Date.parse(record.ts));
});

test('el logger hijo hereda el contexto del padre', () => {
  const sink = capturingSink();
  const log = createLogger({ correlationId: 'cds_abc' }, sink).child({ reference: 'CS-1' });

  log.warn('pago.rechazo');

  const record = JSON.parse(sink.lines[0]);
  assert.equal(record.correlationId, 'cds_abc');
  assert.equal(record.reference, 'CS-1');
});

test('un Error se registra sin volcar el stack completo ni datos de tarjeta', () => {
  const sink = capturingSink();
  const log = createLogger({}, sink);

  log.error('fallo', { cause: new Error('Rechazo para 4111111111111111') });

  assert.doesNotMatch(sink.lines[0], /4111111111111111/);
  assert.match(sink.lines[0], /PAN_REDACTADO/);
});

test('resiste estructuras cíclicas sin desbordar la pila', () => {
  const ciclico = { nombre: 'raiz' };
  ciclico.self = ciclico;
  assert.doesNotThrow(() => JSON.stringify(redact(ciclico)));
});
