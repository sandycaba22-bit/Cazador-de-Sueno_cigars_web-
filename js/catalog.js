/**
 * Catálogo de puros — fuente autoritativa de precios.
 *
 * Este fichero es el que consulta el servidor para calcular cuánto se cobra
 * (server/commerce/pricing.js), así que debe describir EXACTAMENTE las mismas
 * vitolas que las páginas de producto añaden al carrito.
 *
 * Los datos replican config/products.json, que es lo que cargan las páginas de
 * vitolas a través de js/shopping-cart.js. La prueba
 * server/commerce/test/catalog-sync.test.js falla si ambos ficheros divergen:
 * cuando se cambie un precio, hay que cambiarlo en los dos.
 *
 * Reglas de empaque:
 * - Vitolas estándar: 20 unidades por caja
 * - El Rango (doble perfecto): 10 unidades por caja
 * Venta por caja o por puro suelto.
 */

const PACKAGING = {
  STANDARD_UNITS: 20,
  RANGO_UNITS: 10,
};

const UNIT_TYPES = {
  BOX: 'box',
  UNIT: 'unit',
};

function getCartLineId(productId, unitType) {
  return `${productId}::${unitType || UNIT_TYPES.BOX}`;
}

const PRODUCT_LINES = {
  CLASSIC: 'classic',
  RESERVA: 'reserva',
  RANGO: 'rango',
};

function getUnitsPerBox(line) {
  return line === PRODUCT_LINES.RANGO ? PACKAGING.RANGO_UNITS : PACKAGING.STANDARD_UNITS;
}

function isRangoLine(line) {
  return line === PRODUCT_LINES.RANGO;
}

const CATALOG = [
  {
    id: 'emperador',
    name: 'El Emperador',
    nameEn: 'The Emperor',
    line: PRODUCT_LINES.CLASSIC,
    description: 'Gran Toro 58×6 — El Primer Sueño',
    pricePerUnit: 12.0,
    unitsPerBox: PACKAGING.STANDARD_UNITS,
    stockUnits: 100,
    image: 'img/el-emperador-cigarro.jpg',
    strength: 'Media-Full',
    origin: 'República Dominicana',
  },
  {
    id: 'puro-habano',
    name: 'Puro Habano',
    nameEn: 'Puro Habano',
    line: PRODUCT_LINES.CLASSIC,
    description: 'Churchill 48×7 — Raíces Cubanas',
    pricePerUnit: 14.0,
    unitsPerBox: PACKAGING.STANDARD_UNITS,
    stockUnits: 100,
    image: 'img/puro-habano-cigarro.jpg',
    strength: 'Media-Full',
    origin: 'República Dominicana',
  },
  {
    id: 'exquisito',
    name: 'El Exquisito',
    nameEn: 'The Exquisite',
    line: PRODUCT_LINES.RESERVA,
    description: 'Gran Toro 58×6 — Edición de Autor',
    pricePerUnit: 13.5,
    unitsPerBox: PACKAGING.STANDARD_UNITS,
    stockUnits: 50,
    image: 'img/el-exquisito-cigarro.jpg',
    strength: 'Media-Full',
    origin: 'República Dominicana',
  },
  {
    id: 'rango',
    name: 'El Rango',
    nameEn: 'The Range',
    line: PRODUCT_LINES.RANGO,
    description: 'Doble Perfecto 60×4½ — Formato Figurado',
    pricePerUnit: 16.0,
    unitsPerBox: PACKAGING.RANGO_UNITS,
    stockUnits: 100,
    image: 'img/el-rango-cigarro.jpg',
    strength: 'Full',
    origin: 'República Dominicana',
  },
  {
    id: 'ligero',
    name: 'Ligero 007',
    nameEn: 'Ligero 007',
    line: PRODUCT_LINES.RESERVA,
    description: 'Robusto 5×50 — Obra Maestra',
    pricePerUnit: 11.0,
    unitsPerBox: PACKAGING.STANDARD_UNITS,
    stockUnits: 50,
    image: 'images/ligero-007/cigarro.jpg',
    strength: 'Media',
    origin: 'República Dominicana',
  },
  {
    id: 'sultan',
    name: 'El Sultán',
    nameEn: 'The Sultan',
    line: PRODUCT_LINES.CLASSIC,
    description: 'Robusto 5×50 — Valle del Cibao',
    pricePerUnit: 15.0,
    unitsPerBox: PACKAGING.STANDARD_UNITS,
    stockUnits: 100,
    image: 'img/el-sultan-cigarro.jpg',
    strength: 'Media-Full',
    origin: 'República Dominicana',
  },
];

/**
 * El precio por caja se deriva del precio unitario, nunca al revés: así una
 * caja siempre cuesta exactamente lo que cuestan sus puros y no hay redondeos
 * que hagan divergir el total del cliente y el del servidor.
 */
function enrichProduct(product) {
  const unitsPerBox = product.unitsPerBox || getUnitsPerBox(product.line);
  const stockUnits = product.stockUnits;
  return {
    ...product,
    unitsPerBox,
    stockUnits,
    stockBoxes: Math.floor(stockUnits / unitsPerBox),
    packagingLabel:
      unitsPerBox === PACKAGING.RANGO_UNITS
        ? `Caja Rango (${PACKAGING.RANGO_UNITS} uds.)`
        : `Caja estándar (${PACKAGING.STANDARD_UNITS} uds.)`,
    pricePerBox: Math.round(product.pricePerUnit * unitsPerBox * 100) / 100,
    inStock: stockUnits > 0,
  };
}

function getCatalog() {
  return CATALOG.map(enrichProduct);
}

function getProductById(id) {
  const raw = CATALOG.find((p) => p.id === id);
  return raw ? enrichProduct(raw) : null;
}

/**
 * Calcula unidades totales ya reservadas en el carrito para un producto.
 * @param {Array} cartEntries
 * @param {string} productId
 * @param {string|null} excludeLineId
 */
function getReservedUnits(cartEntries, productId, excludeLineId = null) {
  return cartEntries.reduce((sum, entry) => {
    if (entry.productId !== productId) return sum;
    const lineId = getCartLineId(entry.productId, entry.unitType);
    if (excludeLineId && lineId === excludeLineId) return sum;
    const product = getProductById(entry.productId);
    if (!product) return sum;
    return sum + (entry.unitType === UNIT_TYPES.BOX ? entry.quantity * product.unitsPerBox : entry.quantity);
  }, 0);
}

function getAvailableUnits(productId, cartEntries = [], excludeLineId = null) {
  const product = getProductById(productId);
  if (!product) return 0;
  const reserved = getReservedUnits(cartEntries, productId, excludeLineId);
  return Math.max(0, product.stockUnits - reserved);
}

/**
 * @param {string} productId
 * @param {number} quantity
 * @param {'box'|'unit'} unitType
 * @param {Array} [cartEntries]
 * @param {string|null} [excludeLineId]
 */
function validateCartQuantity(productId, quantity, unitType = UNIT_TYPES.BOX, cartEntries = [], excludeLineId = null) {
  const product = getProductById(productId);
  if (!product) {
    return { valid: false, error: 'Producto no encontrado.' };
  }

  const qty = Math.floor(Number(quantity));
  if (!Number.isFinite(qty) || qty < 1) {
    return { valid: false, error: 'Cantidad inválida. Mínimo 1.' };
  }

  if (unitType !== UNIT_TYPES.BOX && unitType !== UNIT_TYPES.UNIT) {
    return { valid: false, error: 'Tipo de unidad no válido.' };
  }

  const requestedUnits = unitType === UNIT_TYPES.BOX ? qty * product.unitsPerBox : qty;
  const availableUnits = getAvailableUnits(productId, cartEntries, excludeLineId);

  if (requestedUnits > availableUnits) {
    const label = unitType === UNIT_TYPES.BOX ? 'caja(s)' : 'puro(s) sueltos';
    const maxDisplay =
      unitType === UNIT_TYPES.BOX
        ? Math.floor(availableUnits / product.unitsPerBox)
        : availableUnits;
    return {
      valid: false,
      error: `Stock insuficiente. Máximo ${maxDisplay} ${label} disponibles.`,
    };
  }

  const lineTotal =
    unitType === UNIT_TYPES.BOX ? qty * product.pricePerBox : qty * product.pricePerUnit;

  const displayLabel =
    unitType === UNIT_TYPES.BOX
      ? `${qty} caja(s) · ${requestedUnits} uds.`
      : `${qty} puro(s) suelto(s)`;

  return {
    valid: true,
    product,
    quantity: qty,
    unitType,
    totalUnits: requestedUnits,
    lineTotal: Math.round(lineTotal * 100) / 100,
    displayLabel,
    shippingBoxes: Math.ceil(requestedUnits / product.unitsPerBox),
  };
}

/** Compatibilidad con código anterior */
function validateBoxQuantity(productId, boxQty) {
  return validateCartQuantity(productId, boxQty, UNIT_TYPES.BOX);
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    PACKAGING,
    UNIT_TYPES,
    PRODUCT_LINES,
    CATALOG,
    getUnitsPerBox,
    isRangoLine,
    getCatalog,
    getProductById,
    validateCartQuantity,
    validateBoxQuantity,
    enrichProduct,
    getAvailableUnits,
    getReservedUnits,
    getCartLineId,
  };
}
