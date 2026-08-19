/**
 * Cotizaciones firmadas.
 *
 * El servidor calcula el total, lo firma con HMAC-SHA256 y lo devuelve al
 * navegador como un token opaco. Al pagar, el navegador reenvía ese token: el
 * importe que se cobra sale de la firma, no de lo que diga el cliente. Así el
 * checkout sigue siendo sin estado (no hace falta sesión ni base de datos) y a
 * la vez es imposible manipular el precio desde la consola del navegador.
 */

const crypto = require('crypto');
const { CheckoutError, ERROR_CODES } = require('./errors');

function b64url(buffer) {
  return Buffer.from(buffer).toString('base64url');
}

function sign(payloadB64, secret) {
  return crypto.createHmac('sha256', secret).update(payloadB64).digest('base64url');
}

/**
 * @param {object} quote        Cotización producida por pricing.buildQuote.
 * @param {string} secret
 * @param {number} ttlSeconds
 * @returns {{ token: string, expiresAt: string }}
 */
function issueQuoteToken(quote, secret, ttlSeconds) {
  const expiresAt = Date.now() + ttlSeconds * 1000;
  const payload = {
    v: 1,
    id: `q_${crypto.randomBytes(9).toString('hex')}`,
    exp: expiresAt,
    quote,
  };

  const payloadB64 = b64url(JSON.stringify(payload));
  return {
    token: `${payloadB64}.${sign(payloadB64, secret)}`,
    quoteId: payload.id,
    expiresAt: new Date(expiresAt).toISOString(),
  };
}

/**
 * @param {string} token
 * @param {string} secret
 * @returns {{ quoteId: string, quote: object, expiresAt: number }}
 */
function verifyQuoteToken(token, secret) {
  if (typeof token !== 'string' || !token.includes('.')) {
    throw new CheckoutError(
      ERROR_CODES.QUOTE_INVALID,
      'La cotización del pedido no es válida. Recarga el checkout.',
      { httpStatus: 400 }
    );
  }

  const separator = token.lastIndexOf('.');
  const payloadB64 = token.slice(0, separator);
  const providedSignature = token.slice(separator + 1);
  const expectedSignature = sign(payloadB64, secret);

  const provided = Buffer.from(providedSignature);
  const expected = Buffer.from(expectedSignature);

  if (provided.length !== expected.length || !crypto.timingSafeEqual(provided, expected)) {
    throw new CheckoutError(
      ERROR_CODES.QUOTE_TAMPERED,
      'La cotización del pedido no es válida. Recarga el checkout.',
      { httpStatus: 400, diagnostics: { reason: 'firma_no_coincide' } }
    );
  }

  let payload;
  try {
    payload = JSON.parse(Buffer.from(payloadB64, 'base64url').toString('utf8'));
  } catch (cause) {
    throw new CheckoutError(
      ERROR_CODES.QUOTE_INVALID,
      'La cotización del pedido no es válida. Recarga el checkout.',
      { httpStatus: 400, cause }
    );
  }

  if (payload.v !== 1 || !payload.quote) {
    throw new CheckoutError(
      ERROR_CODES.QUOTE_INVALID,
      'La cotización del pedido no es válida. Recarga el checkout.',
      { httpStatus: 400 }
    );
  }

  if (Date.now() > payload.exp) {
    throw new CheckoutError(
      ERROR_CODES.QUOTE_EXPIRED,
      'El precio del pedido caducó. Recarga el checkout para actualizarlo.',
      { httpStatus: 409, retryable: true }
    );
  }

  return { quoteId: payload.id, quote: payload.quote, expiresAt: payload.exp };
}

module.exports = { issueQuoteToken, verifyQuoteToken };
