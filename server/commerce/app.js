/**
 * API de comercio: cotización, pedido, pago y consulta.
 *
 * Corre como servicio propio (cds-commerce) detrás de Nginx, separado del
 * sommelier de IA a propósito: una caída o una saturación del modelo de
 * lenguaje no puede impedir que alguien pague.
 *
 * Exporta un manejador `(req, res)` compatible con http.createServer, para que
 * el servidor de desarrollo pueda montarlo junto a los ficheros estáticos.
 */

const crypto = require('crypto');

const { CheckoutError, ERROR_CODES } = require('./errors');
const { createLogger, newCorrelationId } = require('./logger');
const { readJsonBody, sendJson, sendStatus, createRouter } = require('./http');
const { buildQuote } = require('./pricing');
const { issueQuoteToken, verifyQuoteToken } = require('./quotes');
const { parseCheckoutInput } = require('./validation');
const { createGatewayRegistry } = require('./gateways');
const { createOrdersStore } = require('./orders-store');
const { createRateLimiter } = require('./rate-limit');

const { APP_CONFIG } = require('../../js/config');
const { getCountryList } = require('../../js/shipping');
const { getCatalog } = require('../../js/catalog');

const BASE = '/api/commerce';
const SAFE_KEY = /^[A-Za-z0-9_-]{8,64}$/;

function generateOrderReference() {
  const stamp = Date.now().toString(36).toUpperCase();
  const random = crypto.randomBytes(3).toString('hex').toUpperCase();
  return `CS-${stamp}-${random}`;
}

/** Token de lectura del pedido: la referencia por sí sola no expone los datos. */
function orderAccessToken(reference, secret) {
  return crypto.createHmac('sha256', secret).update(`order:${reference}`).digest('base64url');
}

function timingSafeEquals(a, b) {
  const bufA = Buffer.from(String(a));
  const bufB = Buffer.from(String(b));
  return bufA.length === bufB.length && crypto.timingSafeEqual(bufA, bufB);
}

function clientIpOf(req) {
  const forwarded = String(req.headers['x-forwarded-for'] || '')
    .split(',')[0]
    .trim();
  return forwarded || (req.socket && req.socket.remoteAddress) || 'desconocida';
}

/**
 * @param {object} options
 * @param {object} options.config
 * @param {object} [options.logger]
 * @param {object} [options.store]
 * @param {object} [options.gateways]
 * @returns {(req: import('http').IncomingMessage, res: import('http').ServerResponse) => Promise<boolean>}
 *          Devuelve true si atendió la petición.
 */
function createCommerceApp({ config, logger, store, gateways }) {
  const baseLog = logger || createLogger({ service: 'cds-commerce' });
  const ordersStore = store || createOrdersStore(config.dataDir, baseLog);
  const registry = gateways || createGatewayRegistry(config, APP_CONFIG);

  const limitQuotes = createRateLimiter({
    windowMs: config.rateLimit.windowMs,
    max: config.rateLimit.maxQuotes,
    name: 'quotes',
  });
  const limitPayments = createRateLimiter({
    windowMs: config.rateLimit.windowMs,
    max: config.rateLimit.maxPayments,
    name: 'payments',
  });

  const router = createRouter();

  // ---------------------------------------------------------------- salud

  router.get(`${BASE}/health`, async (ctx) => {
    sendJson(ctx.res, 200, {
      ok: true,
      service: 'cds-commerce',
      environment: config.nodeEnv,
      gateways: registry.list().map((g) => ({ id: g.id, configured: g.isConfigured() })),
      timestamp: new Date().toISOString(),
    });
  });

  // -------------------------------------------------------- configuración

  /** Todo lo que el checkout necesita para pintarse, en una sola petición. */
  router.get(`${BASE}/config`, async (ctx) => {
    sendJson(ctx.res, 200, {
      currency: 'USD',
      countries: getCountryList(),
      catalog: getCatalog().map((product) => ({
        id: product.id,
        name: product.name,
        line: product.line,
        pricePerBox: product.pricePerBox,
        pricePerUnit: product.pricePerUnit,
        unitsPerBox: product.unitsPerBox,
        packagingLabel: product.packagingLabel,
        image: product.image,
      })),
      paymentMethods: registry.describeAvailable(),
      maxBoxesPerShipment: 10,
      contact: { whatsapp: config.contact.whatsapp, email: config.contact.email },
    });
  });

  // ------------------------------------------------------------ cotización

  router.post(`${BASE}/quote`, async (ctx) => {
    limitQuotes(ctx.clientIp);

    const body = await readJsonBody(ctx.req);
    const quote = buildQuote({ items: body.items, country: body.country });
    const signed = issueQuoteToken(quote, config.quoteSecret, config.quoteTtlSeconds);

    ctx.log.info('quote.emitida', {
      quoteId: signed.quoteId,
      totalCents: quote.totalCents,
      country: quote.country,
      lines: quote.lines.length,
    });

    sendJson(ctx.res, 200, { quote, quoteToken: signed.token, expiresAt: signed.expiresAt });
  });

  // ---------------------------------------------------------- PayPal setup

  /**
   * Crea la orden en PayPal con el total de la cotización firmada. El SDK del
   * navegador llama aquí desde createOrder: así el importe no lo decide el
   * cliente. El cobro real ocurre después, en POST /orders, al capturar.
   */
  router.post(`${BASE}/paypal/orders`, async (ctx) => {
    limitPayments(ctx.clientIp);

    const gateway = registry.get('paypal');
    const body = await readJsonBody(ctx.req);
    const { quote, quoteId } = verifyQuoteToken(body.quoteToken, config.quoteSecret);

    const created = await gateway.createCheckoutOrder({
      amountCents: quote.totalCents,
      currency: quote.currency,
      quoteId,
      log: ctx.log.child({ gateway: 'paypal', quoteId }),
    });

    ctx.log.info('paypal.orden_lista', {
      paypalOrderId: created.paypalOrderId,
      totalCents: quote.totalCents,
    });

    sendJson(ctx.res, 200, created);
  });

  // ----------------------------------------------------------------- pago

  router.post(`${BASE}/orders`, async (ctx) => {
    limitPayments(ctx.clientIp);

    const headerKey = String(ctx.req.headers['idempotency-key'] || '');
    const idempotencyKey = SAFE_KEY.test(headerKey)
      ? headerKey
      : crypto.randomBytes(16).toString('hex');

    const log = ctx.log.child({ idempotencyKey });

    // Reintento del mismo intento: devolvemos el desenlace anterior sin volver
    // a llamar a la pasarela.
    const previous = await ordersStore.findAttempt(idempotencyKey);
    if (previous) {
      log.info('pago.reintento_idempotente', { reference: previous.reference });
      return sendJson(ctx.res, 200, previous.response);
    }

    const body = await readJsonBody(ctx.req);
    const { quote } = verifyQuoteToken(body.quoteToken, config.quoteSecret);
    const { customer, shipping, notes, acceptances } = parseCheckoutInput(body);

    // El país del envío debe coincidir con el usado para calcular el flete.
    if (shipping.country !== quote.country) {
      throw new CheckoutError(
        ERROR_CODES.QUOTE_INVALID,
        'Cambiaste el país de destino. Recarga el checkout para actualizar el envío.',
        { httpStatus: 409, retryable: true }
      );
    }

    const gateway = registry.get(body.paymentMethod);
    gateway.validatePayload(body.paymentPayload || {});

    const reference = generateOrderReference();
    const paymentLog = log.child({ reference, gateway: gateway.id });

    paymentLog.info('pago.inicio', {
      totalCents: quote.totalCents,
      currency: quote.currency,
      country: quote.country,
      boxes: quote.shippingBoxes,
      email: customer.email,
    });

    // El pedido se registra ANTES de cobrar. Si la pasarela responde y nosotros
    // nos caemos justo después, queda rastro del intento en lugar de un cobro
    // huérfano sin pedido asociado.
    await ordersStore.create({
      reference,
      status: 'processing',
      paymentStatus: 'processing',
      paymentMethod: gateway.id,
      correlationId: ctx.correlationId,
      idempotencyKey,
      customer,
      shipping: {
        ...shipping,
        countryName: quote.countryName,
        carrier: quote.shipping.carrier,
        zone: quote.shipping.zone,
        estimatedDays: quote.shipping.estimatedDays,
        boxes: quote.shippingBoxes,
        originCountry: quote.shipping.originCountry,
        originLabel: quote.shipping.originLabel,
      },
      items: quote.lines,
      currency: quote.currency,
      subtotalCents: quote.subtotalCents,
      shippingCents: quote.shippingCents,
      totalCents: quote.totalCents,
      totalUnits: quote.totalUnits,
      notes,
      acceptances,
      refundEligible: false,
      createdAt: new Date().toISOString(),
    });

    let result;
    try {
      result = await gateway.charge({
        orderReference: reference,
        amountCents: quote.totalCents,
        currency: quote.currency,
        customer,
        clientIp: ctx.clientIp,
        userAgent: String(ctx.req.headers['user-agent'] || '').slice(0, 200),
        idempotencyKey,
        payload: body.paymentPayload || {},
        log: paymentLog,
      });
    } catch (error) {
      const code = error instanceof CheckoutError ? error.code : ERROR_CODES.INTERNAL;
      paymentLog.error('pago.fallido', {
        code,
        diagnostics: error instanceof CheckoutError ? error.diagnostics : undefined,
        cause: error,
      });
      await ordersStore.update(reference, {
        status: 'payment_failed',
        paymentStatus: 'failed',
        failure: { code, at: new Date().toISOString() },
      });
      throw error;
    }

    const paid = result.status === 'paid';
    const finalOrder = await ordersStore.update(reference, {
      status: paid ? 'confirmed' : 'awaiting_payment',
      paymentStatus: result.status,
      payment: {
        gateway: result.gateway,
        transactionId: result.transactionId,
        authorizationCode: result.authorizationCode,
        diagnostics: result.diagnostics,
        completedAt: new Date().toISOString(),
      },
      ...(result.instructions ? { bankTransfer: result.instructions } : {}),
    });

    paymentLog.info('pago.completado', {
      status: result.status,
      transactionId: result.transactionId,
      totalCents: quote.totalCents,
    });

    const response = {
      success: true,
      reference,
      status: finalOrder.status,
      paymentStatus: result.status,
      message: result.customerMessage,
      accessToken: orderAccessToken(reference, config.quoteSecret),
      ...(result.instructions ? { bankTransfer: result.instructions } : {}),
    };

    await ordersStore.saveAttempt(idempotencyKey, { reference, response });

    return sendJson(ctx.res, 201, response);
  });

  // ------------------------------------------------------------- consulta

  router.get(`${BASE}/orders/:reference`, async (ctx) => {
    const { reference } = ctx.params;
    const provided = ctx.url.searchParams.get('t') || '';

    if (!timingSafeEquals(provided, orderAccessToken(reference, config.quoteSecret))) {
      ctx.log.warn('pedido.consulta_no_autorizada', { reference });
      return sendJson(ctx.res, 404, { error: 'Pedido no encontrado.', code: 'NOT_FOUND' });
    }

    const order = await ordersStore.get(reference);
    if (!order) {
      return sendJson(ctx.res, 404, { error: 'Pedido no encontrado.', code: 'NOT_FOUND' });
    }

    return sendJson(ctx.res, 200, order);
  });

  // -------------------------------------------------- webhook de CardNET

  /**
   * CardNET autentica sus notificaciones con la misma PrivateAccountKey por
   * Basic Auth. Responder algo distinto de 200 provoca que lo reintente, que es
   * justo lo que queremos si nuestro almacén falla.
   */
  router.post(`${BASE}/webhooks/cardnet`, async (ctx) => {
    if (!config.cardnet.privateAccountKey) {
      ctx.log.error('webhook.cardnet.sin_clave_configurada');
      return sendStatus(ctx.res, 503);
    }

    const expected = `Basic ${Buffer.from(`${config.cardnet.privateAccountKey}:`).toString('base64')}`;
    if (!timingSafeEquals(ctx.req.headers.authorization || '', expected)) {
      ctx.log.warn('webhook.cardnet.autenticacion_invalida');
      return sendStatus(ctx.res, 401);
    }

    const body = await readJsonBody(ctx.req);
    const resource = body.ResourceObject || {};
    const reference = resource.Order || null;
    const status = Number(resource.Status);

    ctx.log.info('webhook.cardnet.recibido', {
      resourceType: body.ResourceType,
      reference,
      status,
      purchaseId: resource.PurchaseId,
    });

    if (!reference) return sendStatus(ctx.res, 200);

    const order = await ordersStore.get(reference);
    if (!order) {
      ctx.log.warn('webhook.cardnet.pedido_desconocido', { reference });
      return sendStatus(ctx.res, 200);
    }

    // Solo avanzamos el estado: una notificación tardía no puede degradar un
    // pedido que ya se confirmó.
    if (status === 1 && order.paymentStatus !== 'paid') {
      await ordersStore.update(reference, {
        status: 'confirmed',
        paymentStatus: 'paid',
        payment: {
          ...(order.payment || {}),
          gateway: 'cardnet',
          transactionId: String(resource.PurchaseId || ''),
          confirmedByWebhookAt: new Date().toISOString(),
        },
      });
      ctx.log.info('webhook.cardnet.pedido_confirmado', { reference });
    } else if (status === 4 && order.paymentStatus === 'processing') {
      await ordersStore.update(reference, {
        status: 'payment_failed',
        paymentStatus: 'failed',
        failure: { code: ERROR_CODES.CARD_DECLINED, at: new Date().toISOString() },
      });
    }

    return sendStatus(ctx.res, 200);
  });

  // ------------------------------------------------------------ despacho

  async function handle(req, res) {
    const url = new URL(req.url || '/', `http://${req.headers.host || 'localhost'}`);
    const pathname = url.pathname.replace(/\/+$/, '') || '/';

    if (!pathname.startsWith(BASE)) return false;

    const correlationId = newCorrelationId();
    const clientIp = clientIpOf(req);
    const log = baseLog.child({ correlationId, ip: clientIp, route: pathname });

    // CORS: en producción solo responde al dominio canónico.
    const origin = req.headers.origin;
    if (origin) {
      if (!config.corsOrigins.includes(origin)) {
        log.warn('cors.origen_rechazado', { origin });
        sendJson(res, 403, { error: 'Origen no permitido.', code: 'CORS_DENIED' });
        return true;
      }
      res.setHeader('Access-Control-Allow-Origin', origin);
      res.setHeader('Vary', 'Origin');
      res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Idempotency-Key');
      res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    }

    res.setHeader('X-Correlation-Id', correlationId);

    if (req.method === 'OPTIONS') {
      sendStatus(res, 204);
      return true;
    }

    const route = router.match(req.method, pathname);
    if (!route) {
      sendJson(res, 404, { error: 'Recurso no encontrado.', code: 'NOT_FOUND' });
      return true;
    }

    try {
      await route.handler({ req, res, url, params: route.params, log, clientIp, correlationId });
    } catch (error) {
      if (error instanceof CheckoutError) {
        if (error.httpStatus >= 500) {
          log.error('checkout.error', { code: error.code, diagnostics: error.diagnostics });
        } else {
          log.warn('checkout.rechazo', { code: error.code, diagnostics: error.diagnostics });
        }
        sendJson(res, error.httpStatus, error.toClientJSON());
      } else {
        log.error('checkout.error_no_controlado', { cause: error });
        sendJson(res, 500, {
          error: 'Ocurrió un error inesperado. Escríbenos por WhatsApp si el problema persiste.',
          code: ERROR_CODES.INTERNAL,
          correlationId,
        });
      }
    }

    return true;
  }

  handle.ordersStore = ordersStore;
  handle.registry = registry;

  return handle;
}

module.exports = { createCommerceApp, generateOrderReference, orderAccessToken, BASE };
