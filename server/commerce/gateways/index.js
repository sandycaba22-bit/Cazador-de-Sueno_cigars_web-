/**
 * Registro de pasarelas.
 *
 * Es el único punto que conoce la lista completa. El resto del checkout pide
 * una pasarela por id y trabaja contra el contrato de gateways/base.js.
 */

const { CheckoutError, ERROR_CODES } = require('../errors');
const { createCardnetGateway } = require('./cardnet');
const { createBankTransferGateway } = require('./bank-transfer');
const { createPaypalGateway } = require('./paypal');

/**
 * @param {object} config    Configuración del servicio (server/commerce/config.js).
 * @param {object} appConfig APP_CONFIG compartido con el frontend (js/config.js).
 */
function createGatewayRegistry(config, appConfig) {
  const gateways = new Map();

  const register = (gateway) => gateways.set(gateway.id, gateway);

  register(createCardnetGateway(config.cardnet));
  register(createBankTransferGateway(appConfig, config.bankTransfer.enabled));
  register(createPaypalGateway(config.paypal));
  // Sandbox eliminado del checkout: nunca se registra ni se ofrece al comprador.

  return {
    /** @returns {import('./base').PaymentGateway} */
    get(gatewayId) {
      const gateway = gateways.get(String(gatewayId || ''));
      if (!gateway) {
        throw new CheckoutError(
          ERROR_CODES.GATEWAY_UNKNOWN,
          'Ese método de pago no existe. Elige otro.',
          { diagnostics: { requested: gatewayId } }
        );
      }
      if (!gateway.isConfigured()) {
        throw new CheckoutError(
          ERROR_CODES.GATEWAY_NOT_CONFIGURED,
          'Ese método de pago no está disponible en este momento. Elige otro.',
          { httpStatus: 503, diagnostics: { requested: gatewayId } }
        );
      }
      return gateway;
    },

    list() {
      return [...gateways.values()];
    },

    /** Catálogo público que consume el checkout para pintar las opciones. */
    describeAvailable() {
      return [...gateways.values()]
        .map((gateway) => gateway.describe())
        .filter((description) => description.available);
    },
  };
}

module.exports = { createGatewayRegistry };
