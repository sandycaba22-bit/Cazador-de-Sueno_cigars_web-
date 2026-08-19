/**
 * Taxonomía de errores del checkout.
 *
 * Separa dos audiencias que nunca deben mezclarse:
 *  - customerMessage: lo único que viaja al navegador. Sin detalles de la
 *    pasarela, sin nombres de host, sin códigos internos.
 *  - diagnostics: queda en el log del servidor para depurar la transacción.
 */

class CheckoutError extends Error {
  /**
   * @param {string} code        Código estable para métricas y grep en logs.
   * @param {string} customerMessage
   * @param {object} [options]
   * @param {number} [options.httpStatus]
   * @param {object} [options.diagnostics]
   * @param {boolean} [options.retryable]
   * @param {Error}  [options.cause]
   */
  constructor(code, customerMessage, options = {}) {
    super(options.internalMessage || customerMessage);
    this.name = 'CheckoutError';
    this.code = code;
    this.customerMessage = customerMessage;
    this.httpStatus = options.httpStatus || 400;
    this.diagnostics = options.diagnostics || {};
    this.retryable = options.retryable === true;
    if (options.cause) this.cause = options.cause;
  }

  toClientJSON() {
    return {
      error: this.customerMessage,
      code: this.code,
      retryable: this.retryable,
    };
  }
}

const ERROR_CODES = {
  VALIDATION_FAILED: 'VALIDATION_FAILED',
  CART_EMPTY: 'CART_EMPTY',
  UNKNOWN_PRODUCT: 'UNKNOWN_PRODUCT',
  DHL_BOX_LIMIT: 'DHL_BOX_LIMIT',
  QUOTE_INVALID: 'QUOTE_INVALID',
  QUOTE_EXPIRED: 'QUOTE_EXPIRED',
  QUOTE_TAMPERED: 'QUOTE_TAMPERED',
  GATEWAY_NOT_CONFIGURED: 'GATEWAY_NOT_CONFIGURED',
  GATEWAY_UNKNOWN: 'GATEWAY_UNKNOWN',
  GATEWAY_UNREACHABLE: 'GATEWAY_UNREACHABLE',
  GATEWAY_TIMEOUT: 'GATEWAY_TIMEOUT',
  GATEWAY_BAD_RESPONSE: 'GATEWAY_BAD_RESPONSE',
  CARD_DECLINED: 'CARD_DECLINED',
  CARD_TOKEN_MISSING: 'CARD_TOKEN_MISSING',
  CARD_TOKEN_EXPIRED: 'CARD_TOKEN_EXPIRED',
  PAYPAL_ORDER_MISSING: 'PAYPAL_ORDER_MISSING',
  DUPLICATE_ORDER: 'DUPLICATE_ORDER',
  ORDER_PERSIST_FAILED: 'ORDER_PERSIST_FAILED',
  RATE_LIMITED: 'RATE_LIMITED',
  INTERNAL: 'INTERNAL',
};

/**
 * Códigos del emisor devueltos por CardNET en `response-code`.
 * El texto es el que ve el comprador: explica qué hacer, no qué falló por dentro.
 */
const ISSUER_MESSAGES = {
  '00': 'Aprobada.',
  '01': 'Tu banco requiere autorización. Llámalos o prueba con otra tarjeta.',
  '02': 'Tu banco requiere autorización. Llámalos o prueba con otra tarjeta.',
  '05': 'Tu banco rechazó el cargo. Prueba con otra tarjeta o usa transferencia bancaria.',
  '06': 'No pudimos procesar la tarjeta. Revisa los datos e inténtalo de nuevo.',
  '07': 'La tarjeta fue rechazada por el emisor. Prueba con otra.',
  '08': 'Tu banco requiere autorización. Llámalos o prueba con otra tarjeta.',
  12: 'Operación no permitida con esta tarjeta. Prueba con otra.',
  13: 'El monto no es válido para esta tarjeta.',
  14: 'El número de tarjeta no es válido. Revísalo e inténtalo de nuevo.',
  51: 'Fondos insuficientes. Prueba con otra tarjeta o usa transferencia bancaria.',
  52: 'La cuenta asociada a la tarjeta no es válida.',
  53: 'La cuenta asociada a la tarjeta no es válida.',
  54: 'La tarjeta está vencida. Usa una tarjeta vigente.',
  62: 'La tarjeta tiene restricciones para compras internacionales. Consulta con tu banco.',
  89: 'No pudimos procesar el pago en este momento. Escríbenos por WhatsApp y lo resolvemos.',
  90: 'El sistema del banco está en cierre. Inténtalo en unos minutos.',
  91: 'El banco emisor no está disponible. Inténtalo en unos minutos.',
  96: 'Error del sistema de pagos. Inténtalo en unos minutos.',
  97: 'El banco emisor no está disponible. Inténtalo en unos minutos.',
  99: 'El código de seguridad (CVV) es incorrecto.',
  4901: 'La verificación 3D Secure de tu banco no se completó. Inténtalo de nuevo.',
};

const GENERIC_DECLINE =
  'No pudimos completar el pago con esa tarjeta. Prueba con otra o finaliza por transferencia bancaria.';

/**
 * @param {string} responseCode Código de 2-4 dígitos del emisor.
 * @returns {{ approved: boolean, customerMessage: string, known: boolean }}
 */
function describeIssuerCode(responseCode) {
  const key = String(responseCode ?? '').trim();
  const approved = key === '00' || key === '10' || key === '11';
  const message = ISSUER_MESSAGES[key] || ISSUER_MESSAGES[Number(key)];
  return {
    approved,
    known: Boolean(message),
    customerMessage: approved ? ISSUER_MESSAGES['00'] : message || GENERIC_DECLINE,
  };
}

module.exports = { CheckoutError, ERROR_CODES, ISSUER_MESSAGES, describeIssuerCode, GENERIC_DECLINE };
