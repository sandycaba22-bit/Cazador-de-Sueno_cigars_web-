/**
 * CAZADOR DE SUEÑOS CIGARS - Sistema de Carrito de Compras Premium
 * Carrito funcional estilo PedidosYa con bloqueo post-pago y persistencia localStorage
 */

const ShoppingCart = (function() {
  const CART_STORAGE_KEY = 'cds-shopping-cart';
  const PRODUCTS_CONFIG_PATH = '/config/products.json';
  const SHIPPING_CONFIG_PATH = '/config/shipping-zones.json';
  
  let cart = {
    items: [],
    subtotal: 0,
    shipping: 0,
    total: 0,
    currency: 'USD',
    shippingCountry: 'US',
    isPaid: false, // Estado de bloqueo post-pago
    orderDate: null, // Fecha de la orden procesada
    orderId: null // ID de la orden procesada
  };
  
  let products = [];
  let shippingZones = [];
  
  // Cargar configuración de productos
  async function loadProducts() {
    try {
      const response = await fetch(PRODUCTS_CONFIG_PATH);
      const data = await response.json();
      products = data.products.filter(p => p.active);
      return products;
    } catch (error) {
      console.error('Error loading products:', error);
      return [];
    }
  }
  
  // Cargar configuración de envíos
  async function loadShippingZones() {
    try {
      const response = await fetch(SHIPPING_CONFIG_PATH);
      const data = await response.json();
      shippingZones = data.zones;
      return shippingZones;
    } catch (error) {
      console.error('Error loading shipping zones:', error);
      return [];
    }
  }
  
  // Guardar carrito en localStorage
  function saveCart() {
    localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(cart));
    updateCartDisplay();
    updateCartLockState();
  }
  
  // Cargar carrito desde localStorage
  function loadCart() {
    const savedCart = localStorage.getItem(CART_STORAGE_KEY);
    if (savedCart) {
      cart = JSON.parse(savedCart);
      // Asegurar compatibilidad con versiones anteriores
      if (typeof cart.isPaid === 'undefined') cart.isPaid = false;
      if (typeof cart.orderDate === 'undefined') cart.orderDate = null;
      if (typeof cart.orderId === 'undefined') cart.orderId = null;
    }
  }
  
  // Obtener producto por ID
  function getProduct(productId) {
    return products.find(p => p.id === productId);
  }
  
  // FILTRO DE SEGURIDAD: Verificar si el carrito está bloqueado
  function isCartLocked() {
    return cart.isPaid === true;
  }
  
  // Agregar producto al carrito (Estilo PedidosYa - acumulación inteligente)
  function addToCart(productId, quantity = 1) {
    // Filtro de seguridad post-pago
    if (isCartLocked()) {
      console.warn('Cart is locked after payment. Cannot add items.');
      showLockNotification();
      return false;
    }
    
    const product = getProduct(productId);
    if (!product) {
      console.error('Product not found:', productId);
      return false;
    }
    
    const existingItem = cart.items.find(item => item.productId === productId);
    
    if (existingItem) {
      // Acumular cantidad si ya existe (estilo PedidosYa)
      existingItem.quantity += quantity;
    } else {
      // Agregar como nueva línea si es nuevo
      cart.items.push({
        productId: productId,
        name: product.name,
        name_en: product.name_en,
        price: product.price_usd,
        image: product.image,
        quantity: quantity,
        weight: product.weight_grams,
        category: product.category,
        boxSize: product.box_size
      });
    }
    
    calculateTotals();
    saveCart();
    
    // Emitir evento
    window.dispatchEvent(new CustomEvent('cds:cart-updated', { detail: cart }));
    
    return true;
  }
  
  // Remover producto del carrito
  function removeFromCart(productId) {
    // Filtro de seguridad post-pago
    if (isCartLocked()) {
      console.warn('Cart is locked after payment. Cannot remove items.');
      showLockNotification();
      return false;
    }
    
    cart.items = cart.items.filter(item => item.productId !== productId);
    calculateTotals();
    saveCart();
    
    window.dispatchEvent(new CustomEvent('cds:cart-updated', { detail: cart }));
    
    return true;
  }
  
  // Actualizar cantidad de producto
  function updateQuantity(productId, quantity) {
    // Filtro de seguridad post-pago
    if (isCartLocked()) {
      console.warn('Cart is locked after payment. Cannot modify quantities.');
      showLockNotification();
      return false;
    }
    
    if (quantity <= 0) {
      return removeFromCart(productId);
    }
    
    const item = cart.items.find(item => item.productId === productId);
    if (item) {
      item.quantity = quantity;
      calculateTotals();
      saveCart();
      
      window.dispatchEvent(new CustomEvent('cds:cart-updated', { detail: cart }));
    }
    
    return true;
  }
  
  // Disminuir cantidad de producto (botón -)
  function decreaseQuantity(productId) {
    // Filtro de seguridad post-pago
    if (isCartLocked()) {
      console.warn('Cart is locked after payment. Cannot decrease quantities.');
      showLockNotification();
      return false;
    }
    
    const item = cart.items.find(item => item.productId === productId);
    if (item) {
      if (item.quantity > 1) {
        item.quantity -= 1;
        calculateTotals();
        saveCart();
        window.dispatchEvent(new CustomEvent('cds:cart-updated', { detail: cart }));
      } else {
        return removeFromCart(productId);
      }
    }
    
    return true;
  }
  
  // Calcular subtotal
  function calculateSubtotal() {
    return cart.items.reduce((sum, item) => sum + (item.price * item.quantity), 0);
  }
  
  // Calcular envío según zona
  function calculateShipping() {
    if (cart.items.length === 0) return 0;
    
    const zone = getShippingZone(cart.shippingCountry);
    if (!zone) return 0;
    
    const totalWeight = cart.items.reduce((sum, item) => sum + (item.weight * item.quantity), 0);
    const totalItems = cart.items.reduce((sum, item) => sum + item.quantity, 0);
    
    let shipping = zone.base_rate_usd;
    shipping += (totalItems * zone.rate_per_item_usd);
    shipping += (totalWeight * zone.rate_per_gram_usd);
    
    // Envío gratis si supera el umbral
    if (cart.subtotal >= zone.free_shipping_threshold_usd) {
      shipping = 0;
    }
    
    return Math.round(shipping * 100) / 100;
  }
  
  // Obtener zona de envío por país
  function getShippingZone(countryCode) {
    return shippingZones.find(zone => 
      zone.countries.includes(countryCode) || zone.id === 'zone3'
    );
  }
  
  // Establecer país de envío
  function setShippingCountry(countryCode) {
    // Filtro de seguridad post-pago
    if (isCartLocked()) {
      console.warn('Cart is locked after payment. Cannot change shipping country.');
      showLockNotification();
      return false;
    }
    
    cart.shippingCountry = countryCode;
    calculateTotals();
    saveCart();
    
    window.dispatchEvent(new CustomEvent('cds:cart-updated', { detail: cart }));
    
    return true;
  }
  
  // Calcular totales
  function calculateTotals() {
    cart.subtotal = calculateSubtotal();
    cart.shipping = calculateShipping();
    cart.total = cart.subtotal + cart.shipping;
  }
  
  // SISTEMA DE BLOQUEO POST-PAGO: Congelar carrito después del pago
  function lockCartAfterPayment(orderId) {
    cart.isPaid = true;
    cart.orderDate = new Date().toISOString();
    cart.orderId = orderId;
    saveCart();
    
    // Emitir evento especial de bloqueo
    window.dispatchEvent(new CustomEvent('cds:cart-locked', { detail: cart }));
    
    console.log('Cart locked after payment. Order ID:', orderId);
  }
  
  // Liberar carrito para nueva orden (función administrativa)
  function unlockCartForNewOrder() {
    cart.isPaid = false;
    cart.orderDate = null;
    cart.orderId = null;
    saveCart();
    
    // Emitir evento de desbloqueo
    window.dispatchEvent(new CustomEvent('cds:cart-unlocked', { detail: cart }));
    
    console.log('Cart unlocked for new order.');
  }
  
  // Limpiar carrito completamente
  function clearCart() {
    // Filtro de seguridad post-pago
    if (isCartLocked()) {
      console.warn('Cart is locked after payment. Cannot clear cart directly.');
      showLockNotification();
      return false;
    }
    
    cart = {
      items: [],
      subtotal: 0,
      shipping: 0,
      total: 0,
      currency: 'USD',
      shippingCountry: 'US',
      isPaid: false,
      orderDate: null,
      orderId: null
    };
    saveCart();
    
    window.dispatchEvent(new CustomEvent('cds:cart-updated', { detail: cart }));
    
    return true;
  }
  
  // Obtener cantidad de items en carrito
  function getItemCount() {
    return cart.items.reduce((sum, item) => sum + item.quantity, 0);
  }
  
  // Mostrar notificación de bloqueo
  function showLockNotification() {
    const notification = document.createElement('div');
    notification.className = 'cart-lock-notification';
    notification.innerHTML = `
      <div class="cart-lock-banner">
        <span class="cart-lock-icon">🔒</span>
        <span class="cart-lock-message">Este carrito está bloqueado tras procesar el pago. No admite modificaciones.</span>
      </div>
    `;
    document.body.appendChild(notification);
    
    setTimeout(() => {
      notification.remove();
    }, 3000);
  }
  
  // Actualizar display del carrito (badge)
  function updateCartDisplay() {
    const badge = document.querySelector('.cart-badge');
    if (badge) {
      const count = getItemCount();
      badge.textContent = count;
      badge.style.display = count > 0 ? 'flex' : 'none';
    }
  }
  
  // Actualizar estado visual de bloqueo en toda la interfaz
  function updateCartLockState() {
    const cartElements = document.querySelectorAll('[data-cart-action]');
    cartElements.forEach(element => {
      if (isCartLocked()) {
        element.classList.add('cart-locked');
        element.setAttribute('disabled', 'true');
        element.setAttribute('data-disabled', 'true');
      } else {
        element.classList.remove('cart-locked');
        element.removeAttribute('disabled');
        element.removeAttribute('data-disabled');
      }
    });
    
    // Mostrar/ocultar banner de bloqueo global
    let lockBanner = document.querySelector('.cart-lock-banner-global');
    if (isCartLocked()) {
      if (!lockBanner) {
        lockBanner = document.createElement('div');
        lockBanner.className = 'cart-lock-banner-global';
        lockBanner.innerHTML = `
          <div class="cart-lock-content">
            <span class="cart-lock-icon-global">🔒</span>
            <div class="cart-lock-text">
              <strong>Orden Procesada</strong>
              <span>Carrito bloqueado - ID: ${cart.orderId || 'N/A'}</span>
            </div>
          </div>
        `;
        document.body.insertBefore(lockBanner, document.body.firstChild);
      }
    } else {
      if (lockBanner) {
        lockBanner.remove();
      }
    }
  }
  
  // Inicializar
  async function init() {
    await loadProducts();
    await loadShippingZones();
    loadCart();
    calculateTotals();
    updateCartDisplay();
    updateCartLockState();
    
    console.log('Shopping Cart initialized:', cart);
    
    // Emitir evento global indicando que ShoppingCart está listo
    window.dispatchEvent(new CustomEvent('cds:shopping-cart-ready', { detail: cart }));
  }
  
  return {
    init,
    addToCart,
    removeFromCart,
    updateQuantity,
    decreaseQuantity,
    setShippingCountry,
    clearCart,
    lockCartAfterPayment,
    unlockCartForNewOrder,
    isCartLocked,
    getItemCount,
    getCart: () => cart,
    getProducts: () => products,
    getShippingZones: () => shippingZones
  };
})();

// Auto-inicialización
document.addEventListener('DOMContentLoaded', () => {
  console.log('DOMContentLoaded - Initializing ShoppingCart');
  ShoppingCart.init();
});

// Auto-inicialización
document.addEventListener('DOMContentLoaded', () => {
  ShoppingCart.init();
});
