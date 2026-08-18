/**
 * Puente entre el carrito legacy (vitolas / shopping-cart.js)
 * y el checkout unificado (cart.js).
 */

const LEGACY_CART_KEY = 'cds-shopping-cart';

const LEGACY_PRODUCT_IMAGES = {
  emperador: 'img/el-emperador-cigarro.jpg',
  'puro-habano': 'img/puro-habano-cigarro.jpg',
  exquisito: 'img/el-exquisito-cigarro.jpg',
  rango: 'img/el-rango-cigarro.jpg',
  ligero: 'img/ligero-007/cigarro.jpg',
  sultan: 'img/el-sultan-cigarro.jpg',
};

function normalizeCommerceAssetUrl(path) {
  if (!path) return path;
  if (/^https?:\/\//i.test(path) || path.startsWith('/')) return path;
  if (typeof resolveCommerceAssetUrl === 'function') return resolveCommerceAssetUrl(path);
  return `/${String(path).replace(/^\.\//, '')}`;
}

function getLegacyProductImage(productId, itemImage) {
  if (itemImage) return normalizeCommerceAssetUrl(itemImage);
  return normalizeCommerceAssetUrl(
    LEGACY_PRODUCT_IMAGES[productId] || 'img/hero-atmosphere.jpg'
  );
}

function loadLegacyCartRaw() {
  try {
    const raw = localStorage.getItem(LEGACY_CART_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return null;
    return parsed;
  } catch {
    return null;
  }
}

function legacyItemToCartEntry(item) {
  const boxSize = item.boxSize || PACKAGING.STANDARD_UNITS;
  const totalUnits = Math.max(1, Math.floor(Number(item.quantity) || 0));
  const unitPrice = Number(item.price) || 0;
  const line = boxSize === PACKAGING.RANGO_UNITS ? PRODUCT_LINES.RANGO : PRODUCT_LINES.CLASSIC;

  return {
    lineId: `legacy::${item.productId}`,
    productId: item.productId,
    unitType: UNIT_TYPES.UNIT,
    quantity: totalUnits,
    product: {
      name: item.name || item.productId,
      line,
      unitsPerBox: boxSize,
      pricePerUnit: unitPrice,
      pricePerBox: Math.round(unitPrice * boxSize * 100) / 100,
      packagingLabel:
        boxSize === PACKAGING.RANGO_UNITS
          ? `Caja Rango (${PACKAGING.RANGO_UNITS} uds.)`
          : `Caja estándar (${PACKAGING.STANDARD_UNITS} uds.)`,
      image: getLegacyProductImage(item.productId, item.image),
    },
    lineTotal: Math.round(unitPrice * totalUnits * 100) / 100,
    totalUnits,
    displayLabel: `${totalUnits} puro(s)`,
    shippingBoxes: Math.ceil(totalUnits / boxSize),
    pricePerUnit: unitPrice,
    pricePerBox: Math.round(unitPrice * boxSize * 100) / 100,
    isLegacy: true,
  };
}

function getLegacyCartItems() {
  const legacy = loadLegacyCartRaw();
  if (!legacy?.items?.length || legacy.isPaid) return [];
  return legacy.items.map(legacyItemToCartEntry).filter((item) => item.totalUnits > 0);
}

function getLegacyShippingCountry() {
  const legacy = loadLegacyCartRaw();
  return legacy?.shippingCountry || null;
}

function clearLegacyCart() {
  try {
    localStorage.removeItem(LEGACY_CART_KEY);
  } catch {
    /* ignore */
  }
}

function removeLegacyCartItem(productId) {
  const legacy = loadLegacyCartRaw();
  if (!legacy?.items) return false;

  legacy.items = legacy.items.filter((item) => item.productId !== productId);
  legacy.subtotal = legacy.items.reduce((sum, item) => sum + item.price * item.quantity, 0);

  try {
    localStorage.setItem(LEGACY_CART_KEY, JSON.stringify(legacy));
    window.dispatchEvent(new CustomEvent('cart:updated'));
    return true;
  } catch {
    return false;
  }
}

function updateLegacyCartQuantity(productId, totalUnits) {
  const legacy = loadLegacyCartRaw();
  if (!legacy?.items) return { success: false, error: 'Carrito legacy no encontrado.' };

  const idx = legacy.items.findIndex((item) => item.productId === productId);
  if (idx === -1) {
    return { success: false, error: 'Artículo no encontrado en el carrito.' };
  }

  const units = Math.floor(Number(totalUnits));
  if (units < 1) {
    removeLegacyCartItem(productId);
    return { success: true, cart: getLegacyCartItems() };
  }

  legacy.items[idx].quantity = units;
  legacy.subtotal = legacy.items.reduce((sum, item) => sum + item.price * item.quantity, 0);

  try {
    localStorage.setItem(LEGACY_CART_KEY, JSON.stringify(legacy));
    window.dispatchEvent(new CustomEvent('cart:updated'));
    return { success: true, cart: getLegacyCartItems() };
  } catch {
    return { success: false, error: 'No se pudo actualizar el carrito legacy.' };
  }
}

function isLegacyLineId(lineId) {
  return String(lineId || '').startsWith('legacy::');
}

function legacyProductIdFromLineId(lineId) {
  return String(lineId || '').replace(/^legacy::/, '');
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    LEGACY_CART_KEY,
    loadLegacyCartRaw,
    getLegacyCartItems,
    getLegacyShippingCountry,
    clearLegacyCart,
    removeLegacyCartItem,
    updateLegacyCartQuantity,
    isLegacyLineId,
    legacyProductIdFromLineId,
  };
}
