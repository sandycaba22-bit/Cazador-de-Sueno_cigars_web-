/**
 * Contrato que debe cumplir toda pasarela de pago.
 *
 * Añadir una pasarela nueva significa crear un módulo con esta forma y
 * registrarlo en gateways/index.js. Ni el checkout ni el carrito necesitan
 * enterarse.
 *
 * @typedef {object} PaymentContext
 * @property {string} orderReference   Referencia visible para el cliente.
 * @property {number} amountCents      Importe autoritativo, en centavos.
 * @property {string} currency         Moneda del catálogo (USD).
 * @property {object} customer         { fullName, email, phone }
 * @property {string} clientIp
 * @property {string} idempotencyKey   Estable por intento de pedido.
 * @property {object} payload          Datos específicos de la pasarela.
 * @property {object} log              Logger con correlationId.
 *
 * @typedef {object} PaymentResult
 * @property {'paid'|'pending_transfer'|'failed'} status
 * @property {string} gateway
 * @property {string|null} transactionId
 * @property {string|null} authorizationCode
 * @property {string} customerMessage  Texto seguro para mostrar al comprador.
 * @property {object} diagnostics      Solo para el log del servidor.
 *
 * @typedef {object} PaymentGateway
 * @property {string} id
 * @property {string} label
 * @property {boolean} requiresCardData
 * @property {() => boolean} isConfigured
 * @property {() => object} describe          Datos públicos para el frontend.
 * @property {(payload: object) => void} validatePayload
 * @property {(ctx: PaymentContext) => Promise<PaymentResult>} charge
 */

const { CheckoutError, ERROR_CODES } = require('../errors');

/**
 * fetch con límite de tiempo. Sin esto, una pasarela lenta deja peticiones
 * colgadas y el comprador se queda mirando un spinner sin desenlace.
 *
 * @param {string} url
 * @param {RequestInit} options
 * @param {number} timeoutMs
 * @param {string} gatewayId
 */
async function fetchWithTimeout(url, options, timeoutMs, gatewayId) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const startedAt = Date.now();

  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    return { response, elapsedMs: Date.now() - startedAt };
  } catch (cause) {
    const elapsedMs = Date.now() - startedAt;
    if (cause?.name === 'AbortError') {
      throw new CheckoutError(
        ERROR_CODES.GATEWAY_TIMEOUT,
        'El procesador de pagos tardó demasiado en responder. Revisa tu estado de cuenta antes de reintentar.',
        {
          httpStatus: 504,
          retryable: false,
          diagnostics: { gatewayId, elapsedMs, timeoutMs },
          cause,
        }
      );
    }
    throw new CheckoutError(
      ERROR_CODES.GATEWAY_UNREACHABLE,
      'No pudimos conectar con el procesador de pagos. Inténtalo en unos minutos o usa transferencia bancaria.',
      { httpStatus: 502, retryable: true, diagnostics: { gatewayId, elapsedMs }, cause }
    );
  } finally {
    clearTimeout(timer);
  }
}

function formatAmount(amountCents) {
  return (amountCents / 100).toFixed(2);
}

module.exports = { fetchWithTimeout, formatAmount };
