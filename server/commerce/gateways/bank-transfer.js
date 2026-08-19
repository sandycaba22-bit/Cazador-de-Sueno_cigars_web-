/**
 * Transferencia bancaria (Banreservas / BHD).
 *
 * No mueve dinero: reserva el pedido y devuelve las instrucciones. La
 * conciliación es manual, contra el comprobante que envía el cliente. Aun así
 * implementa el mismo contrato que CardNET para que el checkout no tenga que
 * distinguir casos especiales.
 */

const { CheckoutError, ERROR_CODES } = require('../errors');

/**
 * @param {object} appConfig APP_CONFIG compartido con el frontend (js/config.js).
 */
function createBankTransferGateway(appConfig, enabled = true) {
  const id = 'bank_transfer';
  const bank = appConfig.bankTransfer || {};

  function accounts() {
    return Array.isArray(bank.accounts) ? bank.accounts : [];
  }

  function isConfigured() {
    return Boolean(enabled && accounts().length > 0);
  }

  return {
    id,
    label: 'Transferencia bancaria',
    requiresCardData: false,
    isConfigured,

    describe() {
      return {
        id,
        label: 'Transferencia bancaria',
        available: isConfigured(),
        client: {
          currency: bank.currency || 'USD',
          email: bank.email || '',
          proofDeadlineHours: bank.proofDeadlineHours || 48,
          instructions: bank.instructions || '',
          beneficiary: bank.beneficiary || {},
          accounts: accounts().map((account) => ({
            bankName: account.bankName,
            accountHolder: account.accountHolder,
            accountType: account.accountType,
            accountNumber: account.accountNumber,
            currency: account.currency,
            note: account.note || '',
          })),
        },
      };
    },

    validatePayload() {
      if (!isConfigured()) {
        throw new CheckoutError(
          ERROR_CODES.GATEWAY_NOT_CONFIGURED,
          'La transferencia bancaria no está disponible en este momento.',
          { httpStatus: 503 }
        );
      }
    },

    async charge(ctx) {
      const detail = this.describe().client;

      ctx.log.info('bank_transfer.reservado', {
        order: ctx.orderReference,
        amountCents: ctx.amountCents,
        currency: ctx.currency,
        accounts: detail.accounts.length,
      });

      return {
        status: 'pending_transfer',
        gateway: id,
        transactionId: null,
        authorizationCode: null,
        customerMessage: `Pedido reservado. Transfiere el monto exacto indicando la referencia ${ctx.orderReference} en el concepto y envía el comprobante dentro de ${detail.proofDeadlineHours} horas.`,
        diagnostics: { accounts: detail.accounts.length },
        instructions: detail,
      };
    },
  };
}

module.exports = { createBankTransferGateway };
