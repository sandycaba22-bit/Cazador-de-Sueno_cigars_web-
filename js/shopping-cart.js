/**
 * CAZADOR DE SUEÑOS CIGARS - Sistema de Carrito de Compras
 * Carrito funcional con persistencia localStorage
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
    shippingCountry: 'US'
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
  }
  
  // Cargar carrito desde localStorage
  function loadCart() {
    const savedCart = localStorage.getItem(CART_STORAGE_KEY);
    if (savedCart) {
      cart = JSON.parse(savedCart);
    }
  }
  
  // Obtener producto por ID
  function getProduct(productId) {
    return products.find(p => p.id === productId);
  }
  
  // Agregar producto al carrito
  function addToCart(productId, quantity = 1) {
    const product = getProduct(productId);
    if (!product) {
      console.error('Product not found:', productId);
      return false;
    }
    
    const existingItem = cart.items.find(item => item.productId === productId);
    
    if (existingItem) {
      existingItem.quantity += quantity;
    } else {
      cart.items.push({
        productId: productId,
        name: product.name,
        name_en: product.name_en,
        price: product.price_usd,
        image: product.image,
        quantity: quantity,
        weight: product.weight_grams
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
    cart.items = cart.items.filter(item => item.productId !== productId);
    calculateTotals();
    saveCart();
    
    window.dispatchEvent(new CustomEvent('cds:cart-updated', { detail: cart }));
    
    return true;
  }
  
  // Actualizar cantidad de producto
  function updateQuantity(productId, quantity) {
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
    cart.shippingCountry = countryCode;
    calculateTotals();
    saveCart();
    
    window.dispatchEvent(new CustomEvent('cds:cart-updated', { detail: cart }));
  }
  
  // Calcular totales
  function calculateTotals() {
    cart.subtotal = calculateSubtotal();
    cart.shipping = calculateShipping();
    cart.total = cart.subtotal + cart.shipping;
  }
  
  // Limpiar carrito
  function clearCart() {
    cart = {
      items: [],
      subtotal: 0,
      shipping: 0,
      total: 0,
      currency: 'USD',
      shippingCountry: 'US'
    };
    saveCart();
    
    window.dispatchEvent(new CustomEvent('cds:cart-updated', { detail: cart }));
  }
  
  // Obtener cantidad de items en carrito
  function getItemCount() {
    return cart.items.reduce((sum, item) => sum + item.quantity, 0);
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
  
  // Inicializar
  async function init() {
    await loadProducts();
    await loadShippingZones();
    loadCart();
    calculateTotals();
    updateCartDisplay();
    
    console.log('Shopping Cart initialized:', cart);
  }
  
  return {
    init,
    addToCart,
    removeFromCart,
    updateQuantity,
    setShippingCountry,
    clearCart,
    getItemCount,
    getCart: () => cart,
    getProducts: () => products,
    getShippingZones: () => shippingZones
  };
})();

// Auto-inicialización
document.addEventListener('DOMContentLoaded', () => {
  ShoppingCart.init();
});
