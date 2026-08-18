/**
 * Catálogo de puros — reglas de empaque:
 * - Línea estándar (Classic / Reserva): 20 unidades por caja
 * - Línea Rango: 10 unidades por caja
 * Venta por caja o por puro suelto (precio unitario derivado).
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
    id: 'cs-classic-robusto',
    name: 'Classic Robusto',
    line: PRODUCT_LINES.CLASSIC,
    description: 'Mezcla equilibrada con notas de cedro y cacao. Caja estándar de 20 unidades.',
    pricePerBox: 189.0,
    stockBoxes: 48,
    image: 'assets/products/classic-robusto.svg',
    strength: 'Media',
    origin: 'República Dominicana',
  },
  {
    id: 'cs-classic-toro',
    name: 'Classic Toro',
    line: PRODUCT_LINES.CLASSIC,
    description: 'Formato toro, humo cremoso y final prolongado. Caja de 20 puros.',
    pricePerBox: 199.0,
    stockBoxes: 36,
    image: 'assets/products/classic-toro.svg',
    strength: 'Media',
    origin: 'República Dominicana',
  },
  {
    id: 'cs-reserva-churchill',
    name: 'Reserva Churchill',
    line: PRODUCT_LINES.RESERVA,
    description: 'Tabaco añejado 5 años. Presentación premium de 20 unidades.',
    pricePerBox: 289.0,
    stockBoxes: 24,
    image: 'assets/products/reserva-churchill.svg',
    strength: 'Media-Full',
    origin: 'Nicaragua',
  },
  {
    id: 'cs-reserva-lancero',
    name: 'Reserva Lancero',
    line: PRODUCT_LINES.RESERVA,
    description: 'Edición limitada. Caja estándar con 20 lanceros.',
    pricePerBox: 319.0,
    stockBoxes: 18,
    image: 'assets/products/reserva-lancero.svg',
    strength: 'Full',
    origin: 'Nicaragua',
  },
  {
    id: 'cs-rango-petit',
    name: 'Rango Petit Corona',
    line: PRODUCT_LINES.RANGO,
    description: 'Línea Rango — empaque exclusivo de 10 unidades por caja.',
    pricePerBox: 149.0,
    stockBoxes: 30,
    image: 'assets/products/rango-petit.svg',
    strength: 'Media-Full',
    origin: 'Honduras',
  },
  {
    id: 'cs-rango-corona',
    name: 'Rango Corona Gorda',
    line: PRODUCT_LINES.RANGO,
    description: 'Selección artesanal Rango. Cada caja contiene 10 puros.',
    pricePerBox: 169.0,
    stockBoxes: 22,
    image: 'assets/products/rango-corona.svg',
    strength: 'Full',
    origin: 'Honduras',
  },
];

function enrichProduct(product) {
  const unitsPerBox = getUnitsPerBox(product.line);
  const stockUnits = product.stockBoxes * unitsPerBox;
  return {
    ...product,
    unitsPerBox,
    stockUnits,
    packagingLabel:
      unitsPerBox === PACKAGING.RANGO_UNITS
        ? `Caja Rango (${PACKAGING.RANGO_UNITS} uds.)`
        : `Caja estándar (${PACKAGING.STANDARD_UNITS} uds.)`,
    pricePerUnit: Math.round((product.pricePerBox / unitsPerBox) * 100) / 100,
    inStock: product.stockBoxes > 0,
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
