/**
 * CAZADOR DE SUEÑOS CIGARS - Modal del Carrito de Compras
 * UI del carrito lateral con diseño premium
 */

const CartModal = (function() {
  let modal = null;
  let overlay = null;
  let isOpen = false;
  
  // Crear estructura del modal
  function createModal() {
    // Overlay
    overlay = document.createElement('div');
    overlay.className = 'cart-overlay';
    overlay.style.cssText = `
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.7);
      z-index: 1000;
      opacity: 0;
      visibility: hidden;
      transition: opacity 0.3s ease, visibility 0.3s ease;
    `;
    
    // Modal
    modal = document.createElement('div');
    modal.className = 'cart-modal';
    modal.style.cssText = `
      position: fixed;
      top: 0;
      right: 0;
      width: min(100%, 450px);
      height: 100vh;
      background: linear-gradient(180deg, #0a1826 0%, #050505 100%);
      border-left: 1px solid rgba(198, 162, 90, 0.3);
      z-index: 1001;
      transform: translateX(100%);
      transition: transform 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94);
      display: flex;
      flex-direction: column;
    `;
    
    modal.innerHTML = `
      <div class="cart-modal__header" style="
        padding: 1.5rem;
        border-bottom: 1px solid rgba(198, 162, 90, 0.2);
        display: flex;
        justify-content: space-between;
        align-items: center;
      ">
        <h2 style="
          font-family: 'Cormorant Garamond', serif;
          font-size: 1.5rem;
          color: #f4efe2;
          margin: 0;
          letter-spacing: 0.1em;
        ">Carrito</h2>
        <button class="cart-modal__close" style="
          background: transparent;
          border: none;
          color: #f4efe2;
          font-size: 1.5rem;
          cursor: pointer;
          padding: 0.5rem;
          transition: color 0.3s ease;
        ">&times;</button>
      </div>
      
      <div class="cart-modal__items" style="
        flex: 1;
        overflow-y: auto;
        padding: 1.5rem;
      ">
        <!-- Items del carrito -->
      </div>
      
      <div class="cart-modal__footer" style="
        padding: 1.5rem;
        border-top: 1px solid rgba(198, 162, 90, 0.2);
        background: rgba(198, 162, 90, 0.05);
      ">
        <div class="cart-modal__totals" style="
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
          margin-bottom: 1.5rem;
        ">
          <div style="
            display: flex;
            justify-content: space-between;
            color: #aeb9c6;
            font-size: 0.9rem;
          ">
            <span>Subtotal</span>
            <span class="cart-subtotal">$0.00</span>
          </div>
          <div style="
            display: flex;
            justify-content: space-between;
            color: #aeb9c6;
            font-size: 0.9rem;
          ">
            <span>Envío</span>
            <span class="cart-shipping">$0.00</span>
          </div>
          <div style="
            display: flex;
            justify-content: space-between;
            color: #f4efe2;
            font-family: 'Cormorant Garamond', serif;
            font-size: 1.25rem;
            font-weight: 600;
            padding-top: 0.5rem;
            border-top: 1px solid rgba(198, 162, 90, 0.2);
          ">
            <span>Total</span>
            <span class="cart-total">$0.00</span>
          </div>
        </div>
        
        <div class="cart-modal__country-select" style="
          margin-bottom: 1.5rem;
        ">
          <label style="
            display: block;
            color: #aeb9c6;
            font-size: 0.85rem;
            margin-bottom: 0.5rem;
            font-family: 'Cormorant Garamond', serif;
            letter-spacing: 0.1em;
          ">País de envío</label>
          <select class="cart-country" style="
            width: 100%;
            padding: 0.75rem;
            background: rgba(7, 17, 29, 0.8);
            border: 1px solid rgba(198, 162, 90, 0.3);
            color: #f4efe2;
            font-family: 'Libre Baskerville', serif;
            font-size: 0.9rem;
            cursor: pointer;
          ">
            <option value="US">Estados Unidos</option>
            <option value="CA">Canadá</option>
            <option value="DO">República Dominicana</option>
            <option value="OTHER">Resto del mundo</option>
          </select>
        </div>
        
        <button class="cart-modal__checkout" style="
          width: 100%;
          padding: 1rem;
          background: linear-gradient(135deg, #c6a25a 0%, #8b7355 100%);
          border: none;
          color: #050505;
          font-family: 'Cormorant Garamond', serif;
          font-size: 1rem;
          font-weight: 600;
          letter-spacing: 0.15em;
          text-transform: uppercase;
          cursor: pointer;
          transition: transform 0.3s ease, box-shadow 0.3s ease;
        ">Proceder al Pago</button>
      </div>
    `;
    
    document.body.appendChild(overlay);
    document.body.appendChild(modal);
    
    // Event listeners
    overlay.addEventListener('click', close);
    modal.querySelector('.cart-modal__close').addEventListener('click', close);
    modal.querySelector('.cart-modal__checkout').addEventListener('click', () => {
      window.location.href = '/checkout.html';
    });
    modal.querySelector('.cart-country').addEventListener('change', (e) => {
      ShoppingCart.setShippingCountry(e.target.value);
    });
    
    // Escuchar actualizaciones del carrito
    window.addEventListener('cds:cart-updated', renderCartItems);
  }
  
  // Renderizar items del carrito
  function renderCartItems() {
    const cart = ShoppingCart.getCart();
    const itemsContainer = modal.querySelector('.cart-modal__items');
    
    if (cart.items.length === 0) {
      itemsContainer.innerHTML = `
        <div style="
          text-align: center;
          padding: 2rem;
          color: #aeb9c6;
        ">
          <p style="
            font-family: 'Cormorant Garamond', serif;
            font-size: 1.25rem;
            margin-bottom: 1rem;
          ">Tu carrito está vacío</p>
          <p style="font-size: 0.9rem;">Explora nuestra colección premium</p>
        </div>
      `;
    } else {
      itemsContainer.innerHTML = cart.items.map(item => `
        <div class="cart-item" style="
          display: flex;
          gap: 1rem;
          padding: 1rem 0;
          border-bottom: 1px solid rgba(198, 162, 90, 0.1);
        ">
          <div class="cart-item__image" style="
            width: 80px;
            height: 80px;
            background: rgba(7, 17, 29, 0.5);
            border: 1px solid rgba(198, 162, 90, 0.2);
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
          ">
            <span style="color: rgba(198, 162, 90, 0.5); font-size: 2rem;">🚬</span>
          </div>
          
          <div class="cart-item__details" style="
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
          ">
            <h3 style="
              font-family: 'Cormorant Garamond', serif;
              font-size: 1rem;
              color: #f4efe2;
              margin: 0;
            ">${item.name}</h3>
            <p style="
              color: #c6a25a;
              font-size: 0.9rem;
              margin: 0;
            ">$${item.price.toFixed(2)}</p>
            
            <div class="cart-item__quantity" style="
              display: flex;
              align-items: center;
              gap: 0.5rem;
            ">
              <button class="qty-btn qty-minus" data-id="${item.productId}" style="
                width: 28px;
                height: 28px;
                background: rgba(198, 162, 90, 0.1);
                border: 1px solid rgba(198, 162, 90, 0.3);
                color: #f4efe2;
                cursor: pointer;
                font-size: 1rem;
              ">-</button>
              <span style="
                color: #f4efe2;
                min-width: 30px;
                text-align: center;
              ">${item.quantity}</span>
              <button class="qty-btn qty-plus" data-id="${item.productId}" style="
                width: 28px;
                height: 28px;
                background: rgba(198, 162, 90, 0.1);
                border: 1px solid rgba(198, 162, 90, 0.3);
                color: #f4efe2;
                cursor: pointer;
                font-size: 1rem;
              ">+</button>
            </div>
          </div>
          
          <button class="cart-item__remove" data-id="${item.productId}" style="
            background: transparent;
            border: none;
            color: #65717f;
            cursor: pointer;
            padding: 0.5rem;
            transition: color 0.3s ease;
          ">🗑</button>
        </div>
      `).join('');
      
      // Event listeners para quantity
      itemsContainer.querySelectorAll('.qty-minus').forEach(btn => {
        btn.addEventListener('click', () => {
          const id = btn.dataset.id;
          const item = cart.items.find(i => i.productId === id);
          if (item) {
            ShoppingCart.updateQuantity(id, item.quantity - 1);
          }
        });
      });
      
      itemsContainer.querySelectorAll('.qty-plus').forEach(btn => {
        btn.addEventListener('click', () => {
          const id = btn.dataset.id;
          const item = cart.items.find(i => i.productId === id);
          if (item) {
            ShoppingCart.updateQuantity(id, item.quantity + 1);
          }
        });
      });
      
      itemsContainer.querySelectorAll('.cart-item__remove').forEach(btn => {
        btn.addEventListener('click', () => {
          ShoppingCart.removeFromCart(btn.dataset.id);
        });
      });
    }
    
    // Actualizar totales
    modal.querySelector('.cart-subtotal').textContent = `$${cart.subtotal.toFixed(2)}`;
    modal.querySelector('.cart-shipping').textContent = `$${cart.shipping.toFixed(2)}`;
    modal.querySelector('.cart-total').textContent = `$${cart.total.toFixed(2)}`;
  }
  
  // Abrir modal
  function open() {
    if (!modal) createModal();
    
    isOpen = true;
    overlay.style.opacity = '1';
    overlay.style.visibility = 'visible';
    modal.style.transform = 'translateX(0)';
    
    renderCartItems();
    document.body.style.overflow = 'hidden';
  }
  
  // Cerrar modal
  function close() {
    isOpen = false;
    overlay.style.opacity = '0';
    overlay.style.visibility = 'hidden';
    modal.style.transform = 'translateX(100%)';
    
    document.body.style.overflow = '';
  }
  
  // Toggle modal
  function toggle() {
    isOpen ? close() : open();
  }
  
  return {
    open,
    close,
    toggle
  };
})();

// Hacer disponible globalmente
window.CartModal = CartModal;
