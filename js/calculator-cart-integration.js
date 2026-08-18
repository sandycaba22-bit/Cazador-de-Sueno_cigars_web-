/**
 * CAZADOR DE SUEÑOS CIGARS - Sistema Integrado Calculadora + Carrito Premium
 * Fusión de calculadora interactiva con sistema de carrito estilo PedidosYa
 * Precios reales de config/products.json con estética premium
 */

(function() {
  'use strict';

  const CALCULATOR_STORAGE_KEY = 'cds-calculator-state';
  const PRODUCTS_CONFIG_PATH = '/config/products.json';
  
  let products = [];
  let calculatorState = {
    currentVitola: null,
    currentType: 'individual',
    quantity: 1
  };

  // Cargar productos desde config/products.json
  async function loadProducts() {
    try {
      const response = await fetch(PRODUCTS_CONFIG_PATH);
      const data = await response.json();
      products = data.products.filter(p => p.active);
      console.log('Calculator products loaded:', products);
      return products;
    } catch (error) {
      console.error('Error loading products:', error);
      return [];
    }
  }

  // Obtener producto por ID
  function getProduct(productId) {
    return products.find(p => p.id === productId);
  }

  // Obtener precio según tipo (individual/caja)
  function getPriceByType(product, type) {
    return type === 'caja' ? product.price_box_usd : product.price_usd;
  }

  // Mostrar calculadora interactiva
  function showCalculator(vitolaId, type) {
    const product = getProduct(vitolaId);
    if (!product) {
      console.error('Product not found:', vitolaId);
      showToast('❌ Producto no encontrado', 'error');
      return;
    }

    calculatorState.currentVitola = product;
    calculatorState.currentType = type;
    calculatorState.quantity = 1;

    const price = getPriceByType(product, type);
    const contenedor = document.getElementById('cs-calculadora-contenedor');
    
    if (!contenedor) {
      console.error('Calculator container not found');
      return;
    }

    const typeName = type === 'caja' ? `Caja (${product.box_size} unidades)` : 'Unidad individual';
    
    contenedor.innerHTML = `
      <div class="cs-calc-overlay">
        <div class="cs-calc-header">
          <h4 class="cs-calc-title">Calculadora de Pedido</h4>
          <span class="cs-calc-product">${product.name}</span>
          <span class="cs-calc-type">${typeName}</span>
        </div>
        
        <div class="cs-controls-group">
          <button type="button" class="cs-btn-decrease" aria-label="Disminuir cantidad">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M19 12H5M12 19l-7-7 7-7"/>
            </svg>
          </button>
          <input type="number" id="cs-input-cantidad" value="1" min="1" max="100" 
                 aria-label="Cantidad" class="cs-input-quantity">
          <button type="button" class="cs-btn-increase" aria-label="Aumentar cantidad">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 5v14M5 12h14"/>
            </svg>
          </button>
        </div>
        
        <div class="cs-total-display">
          <span class="cs-total-label">Total:</span>
          <span class="cs-total-amount">$<span id="cs-span-total">${price.toFixed(2)}</span></span>
        </div>
        
        <button type="button" class="cs-btn-add-cart" id="cs-btn-add-cart">
          <svg class="cs-btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M9 20a1 1 0 1 0 0 2 1 1 0 0 0 0-2z"/>
            <path d="M20 20a1 1 0 1 0 0 2 1 1 0 0 0 0-2z"/>
            <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>
          </svg>
          <span>Añadir al Carrito</span>
        </button>
      </div>
    `;

    // Configurar eventos
    setupCalculatorEvents(product, price);
    
    // Scroll suave hacia la calculadora
    contenedor.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  // Configurar eventos de la calculadora
  function setupCalculatorEvents(product, price) {
    const decreaseBtn = document.querySelector('.cs-btn-decrease');
    const increaseBtn = document.querySelector('.cs-btn-increase');
    const quantityInput = document.getElementById('cs-input-cantidad');
    const addCartBtn = document.getElementById('cs-btn-add-cart');

    if (decreaseBtn) {
      decreaseBtn.addEventListener('click', () => modifyQuantity(-1, price));
    }

    if (increaseBtn) {
      increaseBtn.addEventListener('click', () => modifyQuantity(1, price));
    }

    if (quantityInput) {
      quantityInput.addEventListener('input', () => calculateTotal(price));
    }

    if (addCartBtn) {
      addCartBtn.addEventListener('click', () => addToCart(product));
    }
  }

  // Modificar cantidad
  function modifyQuantity(change, price) {
    const input = document.getElementById('cs-input-cantidad');
    let currentValue = parseInt(input.value) || 1;
    currentValue += change;
    
    if (currentValue < 1) currentValue = 1;
    if (currentValue > 100) currentValue = 100;
    
    input.value = currentValue;
    calculatorState.quantity = currentValue;
    calculateTotal(price);
  }

  // Calcular total
  function calculateTotal(price) {
    const input = document.getElementById('cs-input-cantidad');
    const quantity = parseInt(input.value) || 1;
    const total = quantity * price;
    
    const totalSpan = document.getElementById('cs-span-total');
    if (totalSpan) {
      totalSpan.textContent = total.toFixed(2);
    }
  }

  // Agregar al carrito usando sistema ShoppingCart premium
  async function addToCart(product) {
    console.log('addToCart called, ShoppingCart available:', !!window.ShoppingCart);
    
    // Verificación síncrona limpia
    if (!window.ShoppingCart) {
      console.error('ShoppingCart not available');
      showToast('❌ Sistema de carrito no disponible', 'error');
      return;
    }

    // Verificar bloqueo post-pago
    if (ShoppingCart.isCartLocked()) {
      showToast('🔒 Carrito bloqueado tras pago', 'error');
      return;
    }

    const quantity = calculatorState.quantity;
    const productId = product.id;
    
    try {
      const success = ShoppingCart.addToCart(productId, quantity);
      
      if (success) {
        showToast(`✅ ¡${quantity} x ${product.name} agregado al carrito!`, 'success');

        if (typeof window.revealCheckoutShortcut === 'function') {
          window.revealCheckoutShortcut();
        }
      } else {
        showToast('❌ Error al agregar al carrito', 'error');
      }
    } catch (error) {
      console.error('Error adding to cart:', error);
      showToast('❌ Error: ' + error.message, 'error');
    }
  }

  // Sistema de notificaciones visuales elegantes (toasts)
  function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = 'cs-toast cs-toast--' + type;
    toast.innerHTML = message;
    
    // Estilos premium manteniendo elegancia de marca
    toast.style.cssText = `
      position: fixed;
      top: 100px;
      right: 20px;
      background: ${type === 'success' ? 'linear-gradient(135deg, #2d5a3d 0%, #1a3d2a 100%)' : 'linear-gradient(135deg, #8B0000 0%, #A52A2A 100%)'};
      color: #f4efe2;
      padding: 1rem 1.5rem;
      border-radius: 8px;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
      z-index: 10000;
      font-family: 'Cormorant Garamond', Georgia, serif;
      font-size: 1rem;
      font-weight: 400;
      letter-spacing: 0.05em;
      border: 1px solid ${type === 'success' ? '#4caf50' : '#FFD700'};
      animation: slideIn 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94);
      max-width: 350px;
      backdrop-filter: blur(10px);
    `;
    
    // Animación CSS premium
    const style = document.createElement('style');
    style.textContent = `
      @keyframes slideIn {
        from {
          transform: translateX(100%);
          opacity: 0;
        }
        to {
          transform: translateX(0);
          opacity: 1;
        }
      }
      @keyframes slideOut {
        from {
          transform: translateX(0);
          opacity: 1;
        }
        to {
          transform: transform: translateX(100%);
          opacity: 0;
        }
      }
    `;
    document.head.appendChild(style);
    
    document.body.appendChild(toast);
    
    // Remover después de 4 segundos
    setTimeout(() => {
      toast.style.animation = 'slideOut 0.4s cubic-bezier(0.45, 0, 0.15, 1) forwards';
      setTimeout(() => {
        toast.remove();
        style.remove();
      }, 400);
    }, 4000);
  }

  // Estilos premium para la calculadora
  function injectCalculatorStyles() {
    if (document.getElementById('cs-calculator-styles')) return;
    
    const style = document.createElement('style');
    style.id = 'cs-calculator-styles';
    style.textContent = `
      .cs-calc-overlay {
        background: linear-gradient(135deg, rgba(15, 34, 56, 0.95) 0%, rgba(10, 24, 38, 0.98) 100%);
        border: 1px solid rgba(198, 162, 90, 0.3);
        padding: 2rem;
        margin-top: 2rem;
        color: #f4efe2;
        font-family: 'Cormorant Garamond', Georgia, serif;
        border-radius: 8px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
        backdrop-filter: blur(10px);
      }
      
      .cs-calc-header {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
        margin-bottom: 1.5rem;
        border-bottom: 1px solid rgba(198, 162, 90, 0.2);
        padding-bottom: 1rem;
      }
      
      .cs-calc-title {
        color: #e7d3a0;
        font-size: 1.4rem;
        font-weight: 400;
        letter-spacing: 0.08em;
        margin: 0;
      }
      
      .cs-calc-product {
        color: #f4efe2;
        font-size: 1.1rem;
        font-style: italic;
        opacity: 0.9;
      }
      
      .cs-calc-type {
        color: #c6a25a;
        font-size: 0.9rem;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        font-weight: 500;
      }
      
      .cs-controls-group {
        display: flex;
        align-items: center;
        gap: 1rem;
        margin-bottom: 1.5rem;
        justify-content: center;
      }
      
      .cs-btn-decrease,
      .cs-btn-increase {
        background: linear-gradient(135deg, #c6a25a 0%, #93763c 100%);
        color: #f4efe2;
        border: 1px solid rgba(198, 162, 90, 0.3);
        width: 40px;
        height: 40px;
        border-radius: 6px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.3s ease;
      }
      
      .cs-btn-decrease:hover,
      .cs-btn-increase:hover {
        background: linear-gradient(135deg, #d4b368 0%, #a3844a 100%);
        transform: scale(1.05);
      }
      
      .cs-btn-decrease svg,
      .cs-btn-increase svg {
        width: 20px;
        height: 20px;
      }
      
      .cs-input-quantity {
        background: rgba(15, 34, 56, 0.8);
        border: 1px solid rgba(198, 162, 90, 0.3);
        color: #f4efe2;
        width: 70px;
        text-align: center;
        padding: 0.75rem;
        font-size: 1.1rem;
        font-family: 'Cormorant Garamond', Georgia, serif;
        border-radius: 6px;
        outline: none;
      }
      
      .cs-input-quantity:focus {
        border-color: #c6a25a;
        box-shadow: 0 0 0 2px rgba(198, 162, 90, 0.3);
      }
      
      .cs-total-display {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 1rem 1.5rem;
        background: rgba(198, 162, 90, 0.1);
        border-radius: 6px;
        margin-bottom: 1.5rem;
      }
      
      .cs-total-label {
        color: #e7d3a0;
        font-size: 1rem;
        font-weight: 400;
        letter-spacing: 0.08em;
      }
      
      .cs-total-amount {
        color: #e7d3a0;
        font-family: 'Bodoni Moda', 'Didot', 'Bodoni MT', 'Times New Roman', serif;
        font-size: 1.8rem;
        font-weight: 400;
        letter-spacing: 0.06em;
      }
      
      .cs-btn-add-cart {
        background: linear-gradient(135deg, #c6a25a 0%, #93763c 100%);
        color: #f4efe2;
        border: 1px solid rgba(198, 162, 90, 0.3);
        padding: 1rem 2rem;
        width: 100%;
        cursor: pointer;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        font-family: 'Cormorant Garamond', Georgia, serif;
        font-size: 1rem;
        font-weight: 400;
        border-radius: 6px;
        transition: all 0.3s ease;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.75rem;
        box-shadow: 0 4px 12px rgba(198, 162, 90, 0.2);
      }
      
      .cs-btn-add-cart:hover {
        background: linear-gradient(135deg, #d4b368 0%, #a3844a 100%);
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(198, 162, 90, 0.3);
      }

      .cs-btn-icon {
        width: 20px;
        height: 20px;
      }
      
      /* Responsive */
      @media (max-width: 768px) {
        .cs-calc-overlay {
          padding: 1.5rem;
        }
        
        .cs-calc-title {
          font-size: 1.2rem;
        }
        
        .cs-total-amount {
          font-size: 1.5rem;
        }
        
        .cs-controls-group {
          gap: 0.75rem;
        }
      }
    `;
    document.head.appendChild(style);
  }

  // Carrito flotante indicador premium
  function createFloatingCart() {
    if (document.getElementById('cs-carrito-flotante')) return;
    // Un solo carrito flotante por página: si ya existe el de comercio, no duplicar.
    if (document.getElementById('cds-float-cart')) return;
    
    const floatingCart = document.createElement('div');
    floatingCart.id = 'cs-carrito-flotante';
    floatingCart.innerHTML = `
      <div class="cs-cart-content">
        <span class="cs-cart-icon">🛒</span>
        <span class="cs-cart-text"><span id="cs-contador-carrito">0</span> ítems</span>
        <a href="/checkout.html" class="cs-cart-link cs-cart-link--checkout">Ver carrito</a>
      </div>
    `;
    
    floatingCart.style.cssText = `
      position: fixed;
      bottom: 30px;
      right: 30px;
      background: linear-gradient(135deg, rgba(15, 34, 56, 0.98) 0%, rgba(10, 24, 38, 0.98) 100%);
      border: 2px solid rgba(198, 162, 90, 0.4);
      color: #f4efe2;
      padding: 1rem 1.5rem;
      z-index: 9999;
      display: none;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
      border-radius: 8px;
      backdrop-filter: blur(10px);
      animation: floatUp 0.5s cubic-bezier(0.25, 0.46, 0.45, 0.94);
    `;
    
    const style = document.createElement('style');
    style.textContent = `
      @keyframes floatUp {
        from {
          transform: translateY(20px);
          opacity: 0;
        }
        to {
          transform: translateY(0);
          opacity: 1;
        }
      }
      
      .cs-cart-content {
        display: flex;
        align-items: center;
        gap: 1rem;
      }
      
      .cs-cart-icon {
        font-size: 1.5rem;
      }
      
      .cs-cart-text {
        font-family: 'Cormorant Garamond', Georgia, serif;
        font-size: 0.95rem;
        letter-spacing: 0.05em;
      }
      
      .cs-cart-link {
        color: #e7d3a0;
        text-decoration: none;
        font-family: 'Cormorant Garamond', Georgia, serif;
        font-size: 0.85rem;
        letter-spacing: 0.08em;
        border-bottom: 1px solid rgba(198, 162, 90, 0.3);
        padding-bottom: 2px;
        transition: all 0.3s ease;
      }
      
      .cs-cart-link:hover {
        color: #c6a25a;
        border-color: #c6a25a;
      }
      
      #cs-carrito-flotante.activo {
        display: block;
      }
    `;
    document.head.appendChild(style);
    
    document.body.appendChild(floatingCart);

    const checkoutLink = floatingCart.querySelector('.cs-cart-link--checkout');
    if (checkoutLink) {
      if (typeof getCheckoutUrl === 'function') checkoutLink.href = getCheckoutUrl();
      checkoutLink.addEventListener('click', (e) => {
        if (window.CartModal && typeof window.CartModal.open === 'function') {
          e.preventDefault();
          window.CartModal.open();
        }
      });
    }
  }

  // Actualizar contador del carrito flotante
  function updateFloatingCart() {
    if (!window.ShoppingCart) return;
    
    const cart = ShoppingCart.getCart();
    const contador = document.getElementById('cs-contador-carrito');
    const floatingCart = document.getElementById('cs-carrito-flotante');
    
    if (contador && floatingCart) {
      const totalItems = cart.items.reduce((sum, item) => sum + item.quantity, 0);
      contador.textContent = totalItems;
      
      if (totalItems > 0) {
        floatingCart.classList.add('activo');
      } else {
        floatingCart.classList.remove('activo');
      }
    }
  }

  // Configurar eventos de botones de compra en páginas de vitolas
  function setupPurchaseButtons() {
    // Buscar botones con data-vitola y data-tipo-compra
    const purchaseButtons = document.querySelectorAll('[data-vitola], [data-tipo-compra]');
    
    purchaseButtons.forEach(button => {
      button.addEventListener('click', (e) => {
        e.preventDefault();
        const vitolaId = button.dataset.vitola || button.dataset.productId;
        const tipo = button.dataset.tipo || button.dataset.tipoCompra || 'individual';
        
        // Mapeo de IDs estándar
        const idMap = {
          'emperador': 'emperador',
          'puro-habano': 'puro-habano',
          'exquisito': 'exquisito',
          'rango': 'rango',
          'ligero': 'ligero',
          'sultan': 'sultan'
        };
        
        const mappedId = idMap[vitolaId] || vitolaId;
        
        showCalculator(mappedId, tipo);
      });
    });
  }

  // Escuchar eventos del carrito principal
  function setupCartListeners() {
    window.addEventListener('cds:cart-updated', updateFloatingCart);
    window.addEventListener('cds:cart-locked', updateFloatingCart);
    window.addEventListener('cds:cart-unlocked', updateFloatingCart);
  }

  // Inicialización
  async function init() {
    console.log('Calculator Cart Integration initializing...');
    
    // Cargar productos
    await loadProducts();
    
    // Inyectar estilos premium
    injectCalculatorStyles();
    
    // Crear carrito flotante
    createFloatingCart();
    
    // Configurar botones de compra
    setupPurchaseButtons();
    
    // Escuchar eventos del carrito
    setupCartListeners();
    
    // Actualizar estado inicial - ShoppingCart debe estar disponible
    if (window.ShoppingCart) {
      console.log('ShoppingCart available, updating floating cart');
      updateFloatingCart();
    } else {
      console.warn('ShoppingCart not available at initialization time');
    }
    
    console.log('Calculator Cart Integration initialized successfully');
  }

  // Exponer función pública para mostrar calculadora
  window.CalculatorCart = {
    showCalculator,
    show: showCalculator
  };

  // Auto-inicialización
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();