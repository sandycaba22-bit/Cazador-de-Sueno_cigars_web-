/**
 * Pasarela PayPal (Checkout con Smart Payment Buttons).
 *
 * DECISIÓN DE ALCANCE PCI DSS
 * ---------------------------
 * El cobro ocurre dentro de los servidores de PayPal. El navegador carga el
 * SDK oficial con el Client ID público; el comprador autentica en PayPal y
 * aquí solo llega un identificador de orden (`paypalOrderId`). Este servidor
 * captura esa orden con la Orders API v2. Jamás viaja un PAN, CVV ni cuenta
 * bancaria por nuestro código, lo que nos mantiene en SAQ A-EP.
 *
 * Activación: con PAYPAL_CLIENT_ID + PAYPAL_CLIENT_SECRET (y
 * PAYPAL_ENABLED distinto de false) el checkout monta los Smart Payment
 * Buttons oficiales. Sin credenciales, PayPal no aparece como método.
 *
 * En producción el modo por defecto es `live` (USD reales).
 *
 * Documentación: https://developer.paypal.com/docs/checkout/standard/integrate/
 */

const { CheckoutError, ERROR_CODES } = require('../errors');
const { fetchWithTimeout, formatAmount } = require('./base');

const HOSTS = {
  sandbox: 'https://api-m.sandbox.paypal.com',
  live: 'https://api-m.paypal.com',
};

const SDK_HOSTS = {
  sandbox: 'https://www.sandbox.paypal.com/sdk/js',
  live: 'https://www.paypal.com/sdk/js',
};

function createPaypalGateway(paypalConfig = {}) {
  const id = 'paypal';
  const mode = paypalConfig.mode === 'live' ? 'live' : 'sandbox';
  const apiBase = HOSTS[mode];
  const timeoutMs = Number(paypalConfig.timeoutMs) || 30_000;

  function isConfigured() {
    return Boolean(
      paypalConfig.enabled && paypalConfig.clientId && paypalConfig.clientSecret
    );
  }

  async function parseJson(response) {
    const text = await response.text();
    try {
      return text ? JSON.parse(text) : {};
    } catch {
      throw new CheckoutError(
        ERROR_CODES.GATEWAY_BAD_RESPONSE,
        'PayPal devolvió una respuesta inesperada. Verifica tu estado de cuenta antes de reintentar.',
        { httpStatus: 502, diagnostics: { gatewayId: id, status: response.status } }
      );
    }
  }

  async function getAccessToken(log) {
    const auth = Buffer.from(`${paypalConfig.clientId}:${paypalConfig.clientSecret}`).toString(
      'base64'
    );

    const { response, elapsedMs } = await fetchWithTimeout(
      `${apiBase}/v1/oauth2/token`,
      {
        method: 'POST',
        headers: {
          Authorization: `Basic ${auth}`,
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: 'grant_type=client_credentials',
      },
      timeoutMs,
      id
    );

    const body = await parseJson(response);
    if (!response.ok || !body.access_token) {
      log.error('paypal.oauth.fallido', {
        status: response.status,
        elapsedMs,
        name: body.error,
      });
      throw new CheckoutError(
        ERROR_CODES.GATEWAY_UNREACHABLE,
        'No pudimos conectar con PayPal. Inténtalo en unos minutos o usa transferencia bancaria.',
        { httpStatus: 502, retryable: true, diagnostics: { status: response.status, elapsedMs } }
      );
    }

    return body.access_token;
  }

  function assertConfigured() {
    if (!isConfigured()) {
      throw new CheckoutError(
        ERROR_CODES.GATEWAY_NOT_CONFIGURED,
        'PayPal aún no está disponible. Elige tarjeta o transferencia bancaria.',
        { httpStatus: 503 }
      );
    }
  }

  return {
    id,
    label: 'PayPal',
    requiresCardData: false,
    isConfigured,

    /**
     * PayPal siempre aparece en el checkout. `ready` indica si el servidor puede
     * cobrar (Client ID + Secret). El Client ID público se expone en cuanto existe
     * para que el SDK monte el botón real de inmediato.
     */
    describe() {
      const ready = isConfigured();
      const clientId = paypalConfig.clientId || '';
      const hasClient = Boolean(clientId);
      return {
        id,
        label: 'PayPal',
        available: true,
        ready,
        client: {
          clientId: hasClient ? clientId : '',
          currency: paypalConfig.currency || 'USD',
          intent: 'capture',
          mode,
          scriptUrl: hasClient
            ? `${SDK_HOSTS[mode]}?client-id=${encodeURIComponent(clientId)}&currency=${encodeURIComponent(paypalConfig.currency || 'USD')}&intent=capture&components=buttons`
            : '',
        },
      };
    },

    validatePayload(payload) {
      assertConfigured();
      const orderId = String(payload?.paypalOrderId || '').trim();
      if (!orderId) {
        throw new CheckoutError(
          ERROR_CODES.PAYPAL_ORDER_MISSING,
          'Confirma el pago en la ventana de PayPal antes de continuar.'
        );
      }
    },

    /**
     * Crea la orden en PayPal con el importe autoritativo de la cotización.
     * El SDK del navegador solo recibe el id: no decide cuánto se cobra.
     */
    async createCheckoutOrder({ amountCents, currency, quoteId, log }) {
      assertConfigured();

      const token = await getAccessToken(log);
      const value = formatAmount(amountCents);

      log.info('paypal.order.create', { quoteId, amountCents, currency, mode });

      const { response, elapsedMs } = await fetchWithTimeout(
        `${apiBase}/v2/checkout/orders`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
            'PayPal-Request-Id': String(quoteId || '').slice(0, 64),
          },
          body: JSON.stringify({
            intent: 'CAPTURE',
            purchase_units: [
              {
                custom_id: String(quoteId || '').slice(0, 127),
                amount: { currency_code: currency, value },
              },
            ],
          }),
        },
        timeoutMs,
        id
      );

      const body = await parseJson(response);
      if (!response.ok || !body.id) {
        log.error('paypal.order.create.fallido', {
          status: response.status,
          elapsedMs,
          name: body.name,
        });
        throw new CheckoutError(
          ERROR_CODES.GATEWAY_BAD_RESPONSE,
          'No pudimos iniciar el pago con PayPal. Inténtalo de nuevo o usa transferencia bancaria.',
          {
            httpStatus: 502,
            retryable: true,
            diagnostics: { status: response.status, name: body.name, elapsedMs },
          }
        );
      }

      return { paypalOrderId: body.id, status: body.status };
    },

    async charge(ctx) {
      assertConfigured();

      const paypalOrderId = String(ctx.payload?.paypalOrderId || '').trim();
      const token = await getAccessToken(ctx.log);

      ctx.log.info('paypal.capture.request', {
        order: ctx.orderReference,
        paypalOrderId,
        amountCents: ctx.amountCents,
        currency: ctx.currency,
      });

      const { response, elapsedMs } = await fetchWithTimeout(
        `${apiBase}/v2/checkout/orders/${encodeURIComponent(paypalOrderId)}/capture`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
            'PayPal-Request-Id': ctx.idempotencyKey,
          },
          body: '{}',
        },
        timeoutMs,
        id
      );

      const body = await parseJson(response);
      const capture = body?.purchase_units?.[0]?.payments?.captures?.[0] || null;
      const captureStatus = capture?.status || body.status;
      const capturedValue = capture?.amount?.value;
      const capturedCurrency = capture?.amount?.currency_code;

      ctx.log.info('paypal.capture.response', {
        status: response.status,
        captureStatus,
        captureId: capture?.id,
        elapsedMs,
      });

      if (!response.ok || (captureStatus && captureStatus !== 'COMPLETED')) {
        throw new CheckoutError(
          ERROR_CODES.CARD_DECLINED,
          'PayPal no pudo completar el cobro. Prueba con otra cuenta o usa transferencia bancaria.',
          {
            httpStatus: 402,
            diagnostics: {
              status: response.status,
              captureStatus,
              name: body.name,
              elapsedMs,
            },
          }
        );
      }

      if (capturedValue != null) {
        const capturedCents = Math.round(Number(capturedValue) * 100);
        if (capturedCents !== ctx.amountCents || capturedCurrency !== ctx.currency) {
          ctx.log.error('paypal.capture.importe_distinto', {
            capturedCents,
            capturedCurrency,
            expectedCents: ctx.amountCents,
            expectedCurrency: ctx.currency,
          });
          throw new CheckoutError(
            ERROR_CODES.GATEWAY_BAD_RESPONSE,
            'El importe cobrado no coincide con el pedido. Escríbenos por WhatsApp con tu referencia.',
            {
              httpStatus: 502,
              diagnostics: { capturedCents, capturedCurrency },
            }
          );
        }
      }

      return {
        status: 'paid',
        gateway: id,
        transactionId: String(capture?.id || body.id || paypalOrderId),
        authorizationCode: String(capture?.id || ''),
        customerMessage: 'Pago con PayPal confirmado.',
        diagnostics: { paypalOrderId, captureStatus, elapsedMs, mode },
      };
    },
  };
}

module.exports = { createPaypalGateway, HOSTS, SDK_HOSTS };
