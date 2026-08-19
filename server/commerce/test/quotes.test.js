const test = require('node:test');
const assert = require('node:assert/strict');

const { issueQuoteToken, verifyQuoteToken } = require('../quotes');
const { buildQuote } = require('../pricing');
const { ERROR_CODES } = require('../errors');

const SECRET = 'secreto-de-prueba-no-usar-en-produccion';

function quoteDeEjemplo() {
  return buildQuote({
    items: [{ productId: 'emperador', unitType: 'box', quantity: 2 }],
    country: 'US',
  });
}

function expectCheckoutError(fn, code) {
  try {
    fn();
  } catch (error) {
    assert.equal(error.code, code);
    return error;
  }
  assert.fail(`se esperaba un error ${code}`);
}

test('una cotización firmada se verifica y conserva el total', () => {
  const quote = quoteDeEjemplo();
  const { token } = issueQuoteToken(quote, SECRET, 900);
  const verified = verifyQuoteToken(token, SECRET);

  assert.equal(verified.quote.totalCents, quote.totalCents);
  assert.equal(verified.quote.country, 'US');
});

test('manipular el total invalida la firma', () => {
  const quote = quoteDeEjemplo();
  const { token } = issueQuoteToken(quote, SECRET, 900);

  const [payloadB64, signature] = token.split('.');
  const payload = JSON.parse(Buffer.from(payloadB64, 'base64url').toString('utf8'));
  payload.quote.totalCents = 100;
  const forged = `${Buffer.from(JSON.stringify(payload)).toString('base64url')}.${signature}`;

  expectCheckoutError(() => verifyQuoteToken(forged, SECRET), ERROR_CODES.QUOTE_TAMPERED);
});

test('una firma hecha con otra clave se rechaza', () => {
  const { token } = issueQuoteToken(quoteDeEjemplo(), 'otra-clave', 900);
  expectCheckoutError(() => verifyQuoteToken(token, SECRET), ERROR_CODES.QUOTE_TAMPERED);
});

test('una cotización caducada se rechaza y es reintentable', () => {
  const { token } = issueQuoteToken(quoteDeEjemplo(), SECRET, -1);
  const error = expectCheckoutError(() => verifyQuoteToken(token, SECRET), ERROR_CODES.QUOTE_EXPIRED);
  assert.equal(error.retryable, true);
  assert.equal(error.httpStatus, 409);
});

test('un token con forma inválida se rechaza sin lanzar excepciones internas', () => {
  for (const invalid of ['', 'sin-punto', null, undefined, 42, {}]) {
    expectCheckoutError(() => verifyQuoteToken(invalid, SECRET), ERROR_CODES.QUOTE_INVALID);
  }
});

test('el mensaje al cliente nunca revela por qué falló la firma', () => {
  const { token } = issueQuoteToken(quoteDeEjemplo(), 'otra-clave', 900);
  const error = expectCheckoutError(() => verifyQuoteToken(token, SECRET), ERROR_CODES.QUOTE_TAMPERED);

  assert.match(error.customerMessage, /Recarga el checkout/);
  assert.doesNotMatch(error.customerMessage, /firma|hmac|secret/i);
});
