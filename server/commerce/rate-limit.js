/**
 * Limitador de peticiones en memoria.
 *
 * El intento de pago tiene un límite mucho más bajo que la cotización: un
 * atacante que prueba tarjetas robadas contra el endpoint de pago (card
 * testing) es un riesgo real para la cuenta de comercio, y el adquiriente
 * penaliza el ratio de rechazos.
 */

const { CheckoutError, ERROR_CODES } = require('./errors');

function createRateLimiter({ windowMs, max, name }) {
  /** @type {Map<string, { count: number, resetAt: number }>} */
  const buckets = new Map();

  function prune(now) {
    for (const [key, bucket] of buckets) {
      if (bucket.resetAt <= now) buckets.delete(key);
    }
  }

  return function enforce(key) {
    const now = Date.now();
    if (buckets.size > 5000) prune(now);

    const bucket = buckets.get(key);
    if (!bucket || bucket.resetAt <= now) {
      buckets.set(key, { count: 1, resetAt: now + windowMs });
      return;
    }

    bucket.count += 1;
    if (bucket.count > max) {
      throw new CheckoutError(
        ERROR_CODES.RATE_LIMITED,
        'Demasiados intentos seguidos. Espera un minuto antes de volver a intentarlo.',
        {
          httpStatus: 429,
          retryable: true,
          diagnostics: { limiter: name, count: bucket.count, max },
        }
      );
    }
  };
}

module.exports = { createRateLimiter };
