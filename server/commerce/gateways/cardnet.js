/**
 * Pasarela CardNET (plataforma SiemprePago / Ztrans).
 *
 * DECISIÓN DE ALCANCE PCI DSS
 * ---------------------------
 * CardNET ofrece dos caminos. Usamos deliberadamente el segundo:
 *
 *  1. "Integración sin pantalla" (REST /api/payment/transactions/sales): el
 *     comercio recibe el PAN, el CVV y la fecha de expiración y los reenvía.
 *     Eso mete a nuestro servidor dentro del entorno de datos de titulares y
 *     nos obliga a un SAQ D con escaneos ASV trimestrales.
 *
 *  2. Formulario de Checkout tokenizado (este módulo): la librería PWCheckout
 *     abre un iframe servido por CardNET, los datos de la tarjeta viajan del
 *     navegador directamente a sus sistemas de tokenización y aquí solo llega
 *     un "One Time Token" de un solo uso con 10 minutos de vigencia. Nuestro
 *     servidor jamás ve un número de tarjeta, lo que nos mantiene en SAQ A-EP.
 *
 * Por eso este archivo no tiene ni un solo campo de tarjeta: si algún día
 * aparece uno, es una regresión de cumplimiento.
 *
 * Documentación: https://developers.cardnet.com.do/guias/tokenizacion-autenticacion/
 */

const { CheckoutError, ERROR_CODES, describeIssuerCode, GENERIC_DECLINE } = require('../errors');
const { fetchWithTimeout } = require('./base');

/** Valores de TransactionStatus documentados por CardNET. */
const STATUS = { APPROVED: 1, PENDING: 2, PREAUTHORIZED: 3, REJECTED: 4 };

/**
 * Errores de la plataforma (no del emisor). Se traducen a lenguaje de comprador
 * porque un "PR001" en pantalla no ayuda a nadie.
 */
const PLATFORM_ERRORS = {
  PR001: 'La sesión de pago caducó. Vuelve a introducir los datos de la tarjeta.',
  PR002: 'Hubo un problema con la referencia del pedido. Recarga el checkout.',
  PR003: 'El importe del pedido no es válido. Recarga el checkout.',
  TR001: 'El banco adquiriente no respondió. Inténtalo en unos minutos.',
  TR002: 'Esta compra ya fue procesada. Revisa tu correo antes de reintentar.',
  TR003: 'Hay un problema con la cuenta de comercio. Escríbenos por WhatsApp.',
  TR004: 'El banco adquiriente no respondió. Inténtalo en unos minutos.',
  TR005: 'El banco adquiriente tuvo un error interno. Inténtalo en unos minutos.',
  TR006: 'Esta compra ya fue procesada. Revisa tu correo antes de reintentar.',
  TK001: 'La sesión de pago caducó. Vuelve a introducir los datos de la tarjeta.',
  TK014: 'Ese medio de pago no está habilitado. Prueba con otra tarjeta.',
};

function createCardnetGateway(cardnetConfig) {
  const id = 'cardnet';

  function isConfigured() {
    return Boolean(
      cardnetConfig.enabled && cardnetConfig.publicAccountKey && cardnetConfig.privateAccountKey
    );
  }

  /**
   * El catálogo está en USD, pero el afiliado puede estar habilitado a liquidar
   * solo en DOP. La conversión se hace aquí, una sola vez, y se registra en el
   * pedido para que la conciliación bancaria cuadre.
   */
  function convertAmount(amountCents, sourceCurrency) {
    const target = cardnetConfig.currency;
    if (target === sourceCurrency) {
      return { amountMinorUnits: amountCents, currency: target, rate: 1 };
    }

    const rate = Number(cardnetConfig.usdToDopRate);
    if (sourceCurrency !== 'USD' || target !== 'DOP' || !rate || rate <= 0) {
      throw new CheckoutError(
        ERROR_CODES.GATEWAY_NOT_CONFIGURED,
        'El pago con tarjeta no está disponible en este momento. Usa transferencia bancaria.',
        {
          httpStatus: 503,
          diagnostics: { reason: 'conversion_no_configurada', sourceCurrency, target, rate },
        }
      );
    }

    return { amountMinorUnits: Math.round(amountCents * rate), currency: target, rate };
  }

  /**
   * Traduce la respuesta de CardNET a nuestro resultado interno.
   * Se mantiene tolerante con la forma exacta del cuerpo porque la plataforma
   * anida el estado a veces en Purchase y a veces en Transaction.
   */
  function interpretResponse(body) {
    const transaction = body?.Transaction || {};
    const status = Number(body?.Status ?? transaction?.Status);
    const responseCode = transaction.ResponseCode ?? body?.ResponseCode ?? null;
    const authorizationCode = transaction.AuthorizationCode ?? body?.AuthorizationCode ?? null;
    const purchaseId = body?.PurchaseId ?? body?.PurchaseID ?? null;

    const errors = Array.isArray(body?.Errors) ? body.Errors : [];
    const platformCode = errors[0]?.Code || errors[0]?.code || null;

    return {
      status,
      responseCode,
      authorizationCode,
      purchaseId,
      platformCode,
      platformMessage: platformCode ? PLATFORM_ERRORS[platformCode] : null,
      errors,
    };
  }

  return {
    id,
    label: 'Tarjeta de crédito o débito',
    requiresCardData: false,
    isConfigured,

    /** Lo único que el frontend necesita saber. La clave privada nunca sale. */
    describe() {
      return {
        id,
        label: 'Tarjeta de crédito o débito',
        available: isConfigured(),
        client: isConfigured()
          ? {
              scriptUrl: `${cardnetConfig.baseUrl}/v1/Scripts/PWCheckout.js?key=${encodeURIComponent(cardnetConfig.publicAccountKey)}`,
              captureUrl: `${cardnetConfig.baseUrl}/v1/Capture/`,
              publicKey: cardnetConfig.publicAccountKey,
              currency: cardnetConfig.currency,
            }
          : null,
      };
    },

    validatePayload(payload) {
      const token = String(payload?.trxToken || '').trim();
      if (!token) {
        throw new CheckoutError(
          ERROR_CODES.CARD_TOKEN_MISSING,
          'Introduce los datos de tu tarjeta antes de confirmar el pedido.'
        );
      }
      if (token.length > 512) {
        throw new CheckoutError(
          ERROR_CODES.CARD_TOKEN_MISSING,
          'Los datos de la tarjeta no se recibieron correctamente. Inténtalo de nuevo.'
        );
      }
    },

    async charge(ctx) {
      if (!isConfigured()) {
        throw new CheckoutError(
          ERROR_CODES.GATEWAY_NOT_CONFIGURED,
          'El pago con tarjeta no está disponible en este momento. Usa transferencia bancaria.',
          { httpStatus: 503, diagnostics: { gateway: id } }
        );
      }

      const { amountMinorUnits, currency, rate } = convertAmount(ctx.amountCents, ctx.currency);

      const requestBody = {
        TrxToken: ctx.payload.trxToken,
        Order: ctx.orderReference,
        Amount: amountMinorUnits,
        Currency: currency,
        Capture: cardnetConfig.captureImmediately,
        Description: `Cazador de Sueño Cigars SRL ${ctx.orderReference}`.slice(0, 50),
        // Cierra la puerta a cobros duplicados si el cliente hace doble clic o
        // si la red corta la respuesta y el navegador reintenta.
        UniqueID: ctx.idempotencyKey,
        CustomerIP: ctx.clientIp,
        CustomerUserAgent: ctx.userAgent || 'unknown',
        DataDo: { Invoice: ctx.orderReference, Tax: 0 },
      };

      const url = `${cardnetConfig.baseUrl}/v1/api/purchase`;
      const auth = Buffer.from(`${cardnetConfig.privateAccountKey}:`).toString('base64');

      ctx.log.info('cardnet.purchase.request', {
        url,
        order: ctx.orderReference,
        amountMinorUnits,
        currency,
        conversionRate: rate,
        uniqueId: ctx.idempotencyKey,
      });

      const { response, elapsedMs } = await fetchWithTimeout(
        url,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
            Authorization: `Basic ${auth}`,
          },
          body: JSON.stringify(requestBody),
        },
        cardnetConfig.timeoutMs,
        id
      );

      const rawText = await response.text();
      let body;
      try {
        body = rawText ? JSON.parse(rawText) : {};
      } catch (cause) {
        ctx.log.error('cardnet.purchase.respuesta_no_json', {
          httpStatus: response.status,
          elapsedMs,
          // scrubText del logger elimina cualquier PAN que la pasarela devuelva.
          bodyPreview: rawText.slice(0, 500),
        });
        throw new CheckoutError(
          ERROR_CODES.GATEWAY_BAD_RESPONSE,
          'El procesador de pagos devolvió una respuesta inesperada. Verifica tu estado de cuenta antes de reintentar.',
          { httpStatus: 502, diagnostics: { httpStatus: response.status }, cause }
        );
      }

      const result = interpretResponse(body);

      ctx.log.info('cardnet.purchase.response', {
        httpStatus: response.status,
        elapsedMs,
        status: result.status,
        responseCode: result.responseCode,
        purchaseId: result.purchaseId,
        platformCode: result.platformCode,
        errors: result.errors,
      });

      if (result.status === STATUS.APPROVED || result.status === STATUS.PREAUTHORIZED) {
        return {
          status: 'paid',
          gateway: id,
          transactionId: result.purchaseId ? String(result.purchaseId) : null,
          authorizationCode: result.authorizationCode,
          customerMessage: 'Pago aprobado.',
          diagnostics: {
            responseCode: result.responseCode,
            elapsedMs,
            chargedAmountMinorUnits: amountMinorUnits,
            chargedCurrency: currency,
            conversionRate: rate,
            captured: cardnetConfig.captureImmediately,
          },
        };
      }

      if (result.status === STATUS.PENDING) {
        throw new CheckoutError(
          ERROR_CODES.CARD_DECLINED,
          'Tu banco dejó el pago en verificación. Espera unos minutos antes de reintentar para no duplicar el cargo.',
          {
            httpStatus: 402,
            diagnostics: { purchaseId: result.purchaseId, commerceAction: body?.CommerceAction },
          }
        );
      }

      // Rechazo: el código del emisor manda, y si no lo hay, el de plataforma.
      const issuer = result.responseCode ? describeIssuerCode(result.responseCode) : null;
      const customerMessage =
        (issuer && !issuer.approved && issuer.known ? issuer.customerMessage : null) ||
        result.platformMessage ||
        GENERIC_DECLINE;

      throw new CheckoutError(ERROR_CODES.CARD_DECLINED, customerMessage, {
        httpStatus: 402,
        diagnostics: {
          status: result.status,
          responseCode: result.responseCode,
          platformCode: result.platformCode,
          httpStatus: response.status,
          purchaseId: result.purchaseId,
          elapsedMs,
        },
      });
    },
  };
}

module.exports = { createCardnetGateway, STATUS, PLATFORM_ERRORS };
