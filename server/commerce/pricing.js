/**
 * Cálculo autoritativo de precios.
 *
 * El navegador nunca decide cuánto se cobra. Envía qué quiere comprar y a
 * dónde; el importe sale siempre de aquí, del mismo catálogo y las mismas
 * tarifas DHL que usa la web (js/catalog.js y js/shipping.js), de modo que
 * cliente y servidor no puedan divergir.
 */

const { UNIT_TYPES, getProductById } = require('../../js/catalog');
const { calculateShipping, validateDhlBoxLimit, getCountryName } = require('../../js/shipping');
const { CheckoutError, ERROR_CODES } = require('./errors');

const CURRENCY = 'USD';
const MAX_LINES = 20;
const MAX_QUANTITY_PER_LINE = 200;

function toCents(amount) {
  return Math.round(Number(amount) * 100);
}

/**
 * Normaliza y valida lo que llega del navegador antes de tocar precios.
 * @param {unknown} rawItems
 * @returns {Array<{ productId: string, unitType: string, quantity: number }>}
 */
function normalizeItems(rawItems) {
  if (!Array.isArray(rawItems) || rawItems.length === 0) {
    throw new CheckoutError(ERROR_CODES.CART_EMPTY, 'Tu carrito está vacío.');
  }
  if (rawItems.length > MAX_LINES) {
    throw new CheckoutError(
      ERROR_CODES.VALIDATION_FAILED,
      `Un pedido admite como máximo ${MAX_LINES} líneas distintas.`
    );
  }

  const seen = new Set();

  return rawItems.map((raw) => {
    const productId = String(raw?.productId || '').trim();
    const unitType = raw?.unitType === UNIT_TYPES.UNIT ? UNIT_TYPES.UNIT : UNIT_TYPES.BOX;
    const quantity = Math.floor(Number(raw?.quantity));

    if (!productId) {
      throw new CheckoutError(ERROR_CODES.VALIDATION_FAILED, 'Hay una línea sin producto.');
    }
    if (!Number.isFinite(quantity) || quantity < 1 || quantity > MAX_QUANTITY_PER_LINE) {
      throw new CheckoutError(
        ERROR_CODES.VALIDATION_FAILED,
        `Cantidad inválida para ${productId}.`
      );
    }

    const key = `${productId}::${unitType}`;
    if (seen.has(key)) {
      throw new CheckoutError(
        ERROR_CODES.VALIDATION_FAILED,
        'El carrito tiene líneas duplicadas. Recárgalo e inténtalo de nuevo.'
      );
    }
    seen.add(key);

    return { productId, unitType, quantity };
  });
}

/**
 * @param {{ items: unknown, country: string }} input
 * @returns {object} Cotización con importes en centavos enteros.
 */
function buildQuote({ items, country }) {
  const normalized = normalizeItems(items);
  const destination = String(country || '').toUpperCase() || 'OTHER';

  let subtotalCents = 0;
  let totalUnits = 0;
  let shippingBoxes = 0;

  const lines = normalized.map(({ productId, unitType, quantity }) => {
    const product = getProductById(productId);
    if (!product) {
      throw new CheckoutError(
        ERROR_CODES.UNKNOWN_PRODUCT,
        'Uno de los productos ya no está disponible. Actualiza el carrito.',
        { diagnostics: { productId } }
      );
    }

    const isBox = unitType === UNIT_TYPES.BOX;
    const units = isBox ? quantity * product.unitsPerBox : quantity;

    if (units > product.stockUnits) {
      throw new CheckoutError(
        ERROR_CODES.VALIDATION_FAILED,
        `No queda suficiente stock de ${product.name}.`,
        { diagnostics: { productId, requested: units, available: product.stockUnits } }
      );
    }

    const unitPriceCents = isBox ? toCents(product.pricePerBox) : toCents(product.pricePerUnit);
    const lineTotalCents = unitPriceCents * quantity;
    const boxes = Math.ceil(units / product.unitsPerBox);

    subtotalCents += lineTotalCents;
    totalUnits += units;
    shippingBoxes += boxes;

    return {
      productId,
      name: product.name,
      line: product.line,
      unitType,
      quantity,
      unitsPerBox: product.unitsPerBox,
      totalUnits: units,
      unitPriceCents,
      lineTotalCents,
      packagingLabel: product.packagingLabel,
      displayLabel: isBox ? `${quantity} caja(s) · ${units} uds.` : `${quantity} puro(s) suelto(s)`,
    };
  });

  const boxLimit = validateDhlBoxLimit(shippingBoxes);
  if (!boxLimit.valid) {
    throw new CheckoutError(ERROR_CODES.DHL_BOX_LIMIT, boxLimit.error, {
      diagnostics: { shippingBoxes, maxBoxes: boxLimit.maxBoxes },
    });
  }

  const shipping = calculateShipping(destination, shippingBoxes);
  const shippingCents = toCents(shipping.cost);
  const totalCents = subtotalCents + shippingCents;

  if (totalCents <= 0) {
    throw new CheckoutError(ERROR_CODES.VALIDATION_FAILED, 'El total del pedido no es válido.');
  }

  return {
    currency: CURRENCY,
    country: destination,
    countryName: getCountryName(destination),
    lines,
    totalUnits,
    shippingBoxes,
    subtotalCents,
    shippingCents,
    totalCents,
    shipping: {
      carrier: shipping.carrier,
      zone: shipping.zone.name,
      zoneKey: shipping.zoneKey,
      estimatedDays: shipping.estimatedDays,
      maxBoxes: shipping.maxBoxes,
      originCountry: shipping.originCountry,
      originLabel: shipping.originLabel,
    },
  };
}

module.exports = { buildQuote, normalizeItems, toCents, CURRENCY, MAX_LINES, MAX_QUANTITY_PER_LINE };
