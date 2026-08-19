/**
 * Pasarela simulada para desarrollo y pruebas de extremo a extremo.
 *
 * A diferencia del sandbox anterior, este vive en el servidor y solo existe si
 * COMMERCE_SANDBOX_ENABLED está activo. Nunca es un plan B silencioso cuando
 * otra pasarela falla: si CardNET rechaza, el pedido se rechaza.
 *
 * Los importes terminados en ciertos centavos permiten forzar escenarios sin
 * depender del ambiente de certificación:
 *   .01 → rechazo por fondos insuficientes
 *   .02 → timeout de la pasarela
 *   .03 → respuesta ilegible
 */

const { CheckoutError, ERROR_CODES, describeIssuerCode } = require('../errors');

function createSandboxGateway(enabled) {
  const id = 'sandbox';

  return {
    id,
    label: 'Pago simulado (sandbox)',
    requiresCardData: false,
    isConfigured: () => Boolean(enabled),

    describe() {
      return {
        id,
        label: 'Pago simulado (sandbox — sin cargo real)',
        available: Boolean(enabled),
        client: null,
      };
    },

    validatePayload() {
      if (!enabled) {
        throw new CheckoutError(
          ERROR_CODES.GATEWAY_NOT_CONFIGURED,
          'El modo de prueba no está habilitado.',
          { httpStatus: 503 }
        );
      }
    },

    async charge(ctx) {
      const trigger = ctx.amountCents % 100;

      if (trigger === 1) {
        ctx.log.warn('sandbox.rechazo_forzado', { order: ctx.orderReference, code: '51' });
        throw new CheckoutError(ERROR_CODES.CARD_DECLINED, describeIssuerCode('51').customerMessage, {
          httpStatus: 402,
          diagnostics: { simulated: true, responseCode: '51' },
        });
      }

      if (trigger === 2) {
        throw new CheckoutError(
          ERROR_CODES.GATEWAY_TIMEOUT,
          'El procesador de pagos tardó demasiado en responder. Revisa tu estado de cuenta antes de reintentar.',
          { httpStatus: 504, diagnostics: { simulated: true } }
        );
      }

      if (trigger === 3) {
        throw new CheckoutError(
          ERROR_CODES.GATEWAY_BAD_RESPONSE,
          'El procesador de pagos devolvió una respuesta inesperada. Verifica tu estado de cuenta antes de reintentar.',
          { httpStatus: 502, diagnostics: { simulated: true } }
        );
      }

      ctx.log.info('sandbox.aprobado', {
        order: ctx.orderReference,
        amountCents: ctx.amountCents,
      });

      return {
        status: 'paid',
        gateway: id,
        transactionId: `sandbox_${ctx.idempotencyKey.slice(0, 12)}`,
        authorizationCode: '000000',
        customerMessage: 'Pago simulado aprobado. No se realizó ningún cargo real.',
        diagnostics: { simulated: true },
      };
    },
  };
}

module.exports = { createSandboxGateway };
