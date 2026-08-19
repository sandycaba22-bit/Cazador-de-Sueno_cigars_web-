/**
 * Logging estructurado para el flujo de pago.
 *
 * Regla PCI DSS 3.3/3.4: ningún dato de titular de tarjeta puede quedar escrito
 * en disco ni en journald. Toda la salida pasa obligatoriamente por redact().
 */

const crypto = require('crypto');

/** Claves cuyo valor jamás debe imprimirse, en cualquier nivel de anidamiento. */
const FORBIDDEN_KEYS = new Set(
  [
    'card-number',
    'cardnumber',
    'card',
    'pan',
    'cvv',
    'cvc',
    'cvv2',
    'cid',
    'expiration-date',
    'expirationdate',
    'expiry',
    'track1',
    'track2',
    'pin',
    'pinblock',
    'privateaccountkey',
    'publicaccountkey',
    'commercekey',
    'authorization',
    'password',
    'secret',
    'clientsecret',
    'client_secret',
    'apikey',
    'api_key',
  ].map((k) => k.toLowerCase())
);

/** Claves que sí queremos ver, pero solo enmascaradas. */
const MASKED_KEYS = new Set(
  ['trxtoken', 'pwtoken', 'token', 'txtoken', 'idempotency-key', 'email', 'phone'].map((k) =>
    k.toLowerCase()
  )
);

const PAN_PATTERN = /\b(?:\d[ -]*?){13,19}\b/g;

function maskValue(value) {
  const str = String(value);
  if (str.length <= 8) return '***';
  return `${str.slice(0, 4)}…${str.slice(-4)}`;
}

function maskEmail(value) {
  const str = String(value);
  const at = str.indexOf('@');
  if (at < 1) return '***';
  return `${str[0]}***${str.slice(at)}`;
}

/**
 * Elimina cualquier rastro de PAN de una cadena libre (mensajes de error de
 * terceros, cuerpos de respuesta, stack traces).
 */
function scrubText(text) {
  return String(text).replace(PAN_PATTERN, (match) => {
    const digits = match.replace(/\D/g, '');
    if (digits.length < 13 || digits.length > 19) return match;
    return `[PAN_REDACTADO:${digits.length}d]`;
  });
}

function redact(value, depth = 0) {
  if (depth > 8) return '[profundidad_máxima]';
  if (value === null || value === undefined) return value;

  if (typeof value === 'string') return scrubText(value);
  if (typeof value === 'number' || typeof value === 'boolean') return value;

  if (value instanceof Error) {
    return { name: value.name, message: scrubText(value.message) };
  }

  if (Array.isArray(value)) return value.map((entry) => redact(entry, depth + 1));

  if (typeof value === 'object') {
    const out = {};
    for (const [key, entry] of Object.entries(value)) {
      const normalized = key.toLowerCase();
      if (FORBIDDEN_KEYS.has(normalized)) {
        out[key] = '[REDACTADO]';
      } else if (MASKED_KEYS.has(normalized) && entry) {
        out[key] = normalized === 'email' ? maskEmail(entry) : maskValue(entry);
      } else {
        out[key] = redact(entry, depth + 1);
      }
    }
    return out;
  }

  return '[no_serializable]';
}

function newCorrelationId() {
  return `cds_${crypto.randomBytes(8).toString('hex')}`;
}

/**
 * Logger con contexto acumulable. Cada petición de checkout arrastra su
 * correlationId para poder reconstruir una transacción completa con
 * `journalctl -u cds-commerce | grep <id>`.
 */
function createLogger(baseContext = {}, sink = console) {
  function emit(level, message, extra) {
    const record = {
      ts: new Date().toISOString(),
      level,
      msg: message,
      ...redact(baseContext),
      ...(extra ? { data: redact(extra) } : {}),
    };
    const line = JSON.stringify(record);
    if (level === 'error') sink.error(line);
    else if (level === 'warn') sink.warn(line);
    else sink.log(line);
  }

  return {
    correlationId: baseContext.correlationId,
    child(context) {
      return createLogger({ ...baseContext, ...context }, sink);
    },
    debug: (m, e) => emit('debug', m, e),
    info: (m, e) => emit('info', m, e),
    warn: (m, e) => emit('warn', m, e),
    error: (m, e) => emit('error', m, e),
  };
}

module.exports = { createLogger, redact, scrubText, newCorrelationId, FORBIDDEN_KEYS, MASKED_KEYS };
