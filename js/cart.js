/**
 * Carrito persistente — acumula cajas y puros sueltos entre páginas y sesiones.
 */

const CART_STORAGE_KEY = 'cazador_sueno_cart';
const CART_SCHEMA_VERSION = 2;

function parseCartLineId(lineId) {
  const [productId, unitType] = lineId.split('::');
  return { productId, unitType };
}

function loadRawCart() {
  try {
    const raw = localStorage.getItem(CART_STORAGE_KEY);
    if (!raw) return { version: CART_SCHEMA_VERSION, items: [] };
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return {
        version: CART_SCHEMA_VERSION,
        items: parsed.map((entry) => ({
          productId: entry.productId,
          unitType: UNIT_TYPES.BOX,
          quantity: entry.boxQty ?? entry.quantity ?? 1,
        })),
      };
    }
    return {
      version: parsed.version || CART_SCHEMA_VERSION,
      items: Array.isArray(parsed.items) ? parsed.items : [],
    };
  } catch {
    return { version: CART_SCHEMA_VERSION, items: [] };
  }
}

function loadCart() {
  return loadRawCart().items;
}

function saveCart(items) {
  const payload = { version: CART_SCHEMA_VERSION, items, updatedAt: Date.now() };
  localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(payload));
  window.dispatchEvent(new CustomEvent('cart:updated', { detail: { items } }));
}

/** Reconcilia el carrito con inventario actual — recorta cantidades excedidas */
function reconcileCart() {
  const cart = loadCart();
  let changed = false;

  const reconciled = cart
    .map((entry) => {
      const lineId = getCartLineId(entry.productId, entry.unitType || UNIT_TYPES.BOX);
      const unitType = entry.unitType || UNIT_TYPES.BOX;
      const validation = validateCartQuantity(
        entry.productId,
        entry.quantity,
        unitType,
        cart,
        lineId
      );

      if (!validation.valid) {
        const product = getProductById(entry.productId);
        if (!product) {
          changed = true;
          return null;
        }
        const available = getAvailableUnits(entry.productId, cart, lineId);
        const maxQty =
          unitType === UNIT_TYPES.BOX
            ? Math.floor(available / product.unitsPerBox)
            : available;
        if (maxQty < 1) {
          changed = true;
          return null;
        }
        changed = true;
        return { productId: entry.productId, unitType, quantity: maxQty };
      }

      if (validation.quantity !== entry.quantity) changed = true;
      return { productId: entry.productId, unitType, quantity: validation.quantity };
    })
    .filter(Boolean);

  if (changed) saveCart(reconciled);
  return reconciled;
}

function resolveCartItem(entry) {
  const unitType = entry.unitType || UNIT_TYPES.BOX;
  const lineId = getCartLineId(entry.productId, unitType);
  const cart = loadCart();
  const validation = validateCartQuantity(
    entry.productId,
    entry.quantity,
    unitType,
    cart,
    lineId
  );

  if (!validation.valid) return null;

  return {
    lineId,
    productId: entry.productId,
    unitType,
    quantity: validation.quantity,
    product: validation.product,
    lineTotal: validation.lineTotal,
    totalUnits: validation.totalUnits,
    displayLabel: validation.displayLabel,
    shippingBoxes: validation.shippingBoxes,
    pricePerUnit: validation.product.pricePerUnit,
    pricePerBox: validation.product.pricePerBox,
  };
}

function getCartItems() {
  reconcileCart();
  const modern = loadCart().map(resolveCartItem).filter(Boolean);
  if (modern.length) return modern;
  return typeof getLegacyCartItems === 'function' ? getLegacyCartItems() : [];
}

function addToCart(productId, quantity = 1, unitType = UNIT_TYPES.BOX) {
  const cart = loadCart();
  const lineId = getCartLineId(productId, unitType);
  const existing = cart.find((i) => getCartLineId(i.productId, i.unitType || UNIT_TYPES.BOX) === lineId);
  const newQty = (existing?.quantity || 0) + Math.floor(Number(quantity) || 0);

  const validation = validateCartQuantity(productId, newQty, unitType, cart, lineId);
  if (!validation.valid) {
    return { success: false, error: validation.error };
  }

  if (existing) {
    existing.quantity = validation.quantity;
    existing.unitType = unitType;
  } else {
    cart.push({ productId, unitType, quantity: validation.quantity });
  }

  saveCart(cart);
  return { success: true, cart: getCartItems() };
}

function updateCartQuantity(lineId, quantity) {
  if (typeof isLegacyLineId === 'function' && isLegacyLineId(lineId)) {
    const productId = legacyProductIdFromLineId(lineId);
    return updateLegacyCartQuantity(productId, quantity);
  }

  const { productId, unitType } = parseCartLineId(lineId);
  const cart = loadCart();
  const idx = cart.findIndex(
    (i) => getCartLineId(i.productId, i.unitType || UNIT_TYPES.BOX) === lineId
  );

  if (idx === -1) {
    return { success: false, error: 'Artículo no encontrado en el carrito.' };
  }

  const qty = Math.floor(Number(quantity));
  if (qty < 1) {
    cart.splice(idx, 1);
    saveCart(cart);
    return { success: true, cart: getCartItems() };
  }

  const validation = validateCartQuantity(productId, qty, unitType, cart, lineId);
  if (!validation.valid) {
    return { success: false, error: validation.error };
  }

  cart[idx].quantity = validation.quantity;
  saveCart(cart);
  return { success: true, cart: getCartItems() };
}

function removeFromCart(lineId) {
  if (typeof isLegacyLineId === 'function' && isLegacyLineId(lineId)) {
    removeLegacyCartItem(legacyProductIdFromLineId(lineId));
    return getCartItems();
  }

  const cart = loadCart().filter(
    (i) => getCartLineId(i.productId, i.unitType || UNIT_TYPES.BOX) !== lineId
  );
  saveCart(cart);
  return getCartItems();
}

function clearCart() {
  saveCart([]);
  if (typeof clearLegacyCart === 'function') clearLegacyCart();
}

function getPreferredShippingCountry() {
  const legacyCountry =
    typeof getLegacyShippingCountry === 'function' ? getLegacyShippingCountry() : null;
  if (legacyCountry) return legacyCountry;
  return 'US';
}

function getCartSummary(countryCode = 'MX') {
  const items = getCartItems();
  const subtotal = items.reduce((sum, i) => sum + i.lineTotal, 0);
  const totalUnits = items.reduce((sum, i) => sum + i.totalUnits, 0);
  const shippingBoxes = items.reduce((sum, i) => sum + i.shippingBoxes, 0);
  const shipping = calculateShipping(countryCode, shippingBoxes);
  const dhlValidation = validateDhlBoxLimit(shippingBoxes);

  return {
    items,
    subtotal: Math.round(subtotal * 100) / 100,
    totalUnits,
    shippingBoxes,
    shipping,
    dhlValidation,
    shippingCost: shipping.cost,
    total: Math.round((subtotal + shipping.cost) * 100) / 100,
    isEmpty: items.length === 0,
  };
}

function getCartCount() {
  return getCartItems().reduce((sum, i) => sum + i.totalUnits, 0);
}

function getCartLineCount() {
  return getCartItems().length;
}

function initCartPersistence() {
  reconcileCart();

  window.addEventListener('storage', (event) => {
    if (event.key === CART_STORAGE_KEY) {
      window.dispatchEvent(new CustomEvent('cart:updated'));
    }
  });
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    CART_STORAGE_KEY,
    CART_SCHEMA_VERSION,
    getCartLineId,
    loadCart,
    saveCart,
    reconcileCart,
    getCartItems,
    addToCart,
    updateCartQuantity,
    removeFromCart,
    clearCart,
    getCartSummary,
    getCartCount,
    getCartLineCount,
    initCartPersistence,
    getPreferredShippingCountry,
  };
}
