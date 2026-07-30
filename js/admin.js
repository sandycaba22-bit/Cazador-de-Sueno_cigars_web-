/**
 * CAZADOR DE SUEÑOS CIGARS - Panel Administrativo
 * Autenticación, calculadora de costos y gestión de pedidos
 */

const AdminPanel = (function() {
  const ADMIN_PASSWORD = 'cazador2024'; // Cambiar en producción
  const SESSION_KEY = 'cds-admin-session';
  
  // Verificar sesión
  function checkSession() {
    const session = localStorage.getItem(SESSION_KEY);
    if (session === 'active') {
      showAdminPanel();
    }
  }
  
  // Login
  function login(password) {
    if (password === ADMIN_PASSWORD) {
      localStorage.setItem(SESSION_KEY, 'active');
      showAdminPanel();
      return true;
    }
    return false;
  }
  
  // Logout
  function logout() {
    localStorage.removeItem(SESSION_KEY);
    showLoginScreen();
  }
  
  // Mostrar panel admin
  function showAdminPanel() {
    document.getElementById('loginScreen').style.display = 'none';
    document.getElementById('adminPanel').style.display = 'block';
    loadOrders();
    loadNotifications();
  }
  
  // Mostrar pantalla login
  function showLoginScreen() {
    document.getElementById('loginScreen').style.display = 'block';
    document.getElementById('adminPanel').style.display = 'none';
  }
  
  // Mostrar sección
  function showSection(sectionId) {
    // Ocultar todas las secciones
    document.querySelectorAll('.admin-section').forEach(section => {
      section.classList.remove('active');
    });
    
    // Remover active de botones
    document.querySelectorAll('.admin-nav button').forEach(btn => {
      btn.classList.remove('active');
    });
    
    // Mostrar sección seleccionada
    document.getElementById(sectionId + 'Section').classList.add('active');
    
    // Activar botón correspondiente
    event.target.classList.add('active');
  }
  
  // Calculadora de precios
  function calculatePrice() {
    const length = parseFloat(document.getElementById('length').value) || 0;
    const ringGauge = parseFloat(document.getElementById('ringGauge').value) || 0;
    const wrapperCost = parseFloat(document.getElementById('wrapperCost').value) || 0;
    const binderCost = parseFloat(document.getElementById('binderCost').value) || 0;
    const fillerCost = parseFloat(document.getElementById('fillerCost').value) || 0;
    const wastePercent = parseFloat(document.getElementById('wastePercent').value) || 0;
    const laborCost = parseFloat(document.getElementById('laborCost').value) || 0;
    const packagingCost = parseFloat(document.getElementById('packagingCost').value) || 0;
    const marginPercent = parseFloat(document.getElementById('marginPercent').value) || 0;
    
    // Validar campos requeridos
    if (wrapperCost === 0 && binderCost === 0 && fillerCost === 0) {
      alert('Por favor ingrese al menos un costo de material');
      return;
    }
    
    // Fórmulas
    const directCost = wrapperCost + binderCost + fillerCost;
    const adjustedCost = directCost * (1 + (wastePercent / 100));
    const totalCost = adjustedCost + laborCost + packagingCost;
    const salePrice = marginPercent > 0 ? totalCost / (1 - (marginPercent / 100)) : totalCost;
    
    // Mostrar resultados
    document.getElementById('results').style.display = 'block';
    document.getElementById('directCost').textContent = `$${directCost.toFixed(2)}`;
    document.getElementById('adjustedCost').textContent = `$${adjustedCost.toFixed(2)}`;
    document.getElementById('totalCost').textContent = `$${totalCost.toFixed(2)}`;
    document.getElementById('salePrice').textContent = `$${salePrice.toFixed(2)}`;
  }
  
  // Cargar pedidos
  function loadOrders() {
    const orders = JSON.parse(localStorage.getItem('cds-orders') || '[]');
    const ordersContent = document.getElementById('ordersContent');
    
    if (orders.length === 0) {
      ordersContent.innerHTML = '<p style="color: #aeb9c6;">No hay pedidos registrados.</p>';
      return;
    }
    
    // Ordenar por fecha (más reciente primero)
    orders.sort((a, b) => new Date(b.date) - new Date(a.date));
    
    const tableHTML = `
      <table class="orders-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Fecha</th>
            <th>Cliente</th>
            <th>Total</th>
            <th>Estado</th>
            <th>País</th>
          </tr>
        </thead>
        <tbody>
          ${orders.map(order => {
            const date = new Date(order.date).toLocaleDateString('es-ES');
            const customerName = `${order.shippingInfo.firstName} ${order.shippingInfo.lastName}`;
            const statusClass = `status-${order.status}`;
            const statusText = order.status === 'pending' ? 'Pendiente' : 
                               order.status === 'verified' ? 'Verificado' :
                               order.status === 'shipped' ? 'Enviado' :
                               order.status === 'completed' ? 'Completado' : order.status;
            
            return `
              <tr>
                <td>${order.id}</td>
                <td>${date}</td>
                <td>${customerName}</td>
                <td>$${order.total.toFixed(2)}</td>
                <td><span class="status-badge ${statusClass}">${statusText}</span></td>
                <td>${order.shippingInfo.country}</td>
              </tr>
            `;
          }).join('')}
        </tbody>
      </table>
    `;
    
    ordersContent.innerHTML = tableHTML;
  }
  
  // Cargar notificaciones
  function loadNotifications() {
    const notifications = JSON.parse(localStorage.getItem('cds-admin-notifications') || '[]');
    const notificationsContent = document.getElementById('notificationsContent');
    
    if (notifications.length === 0) {
      notificationsContent.innerHTML = '<p style="color: #aeb9c6;">No hay notificaciones.</p>';
      return;
    }
    
    // Ordenar por fecha (más reciente primero)
    notifications.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    
    const notificationsHTML = notifications.map(notif => {
      const date = new Date(notif.timestamp).toLocaleString('es-ES');
      return `
        <div style="padding: 1rem; border-bottom: 1px solid rgba(198, 162, 90, 0.1); margin-bottom: 1rem;">
          <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
            <span style="color: #c6a25a; font-weight: 600;">${notif.subject}</span>
            <span style="color: #65717f; font-size: 0.85rem;">${date}</span>
          </div>
          <p style="color: #aeb9c6; font-size: 0.9rem; margin: 0.5rem 0;">
            Pedido #${notif.orderId} - Total: $${notif.order.total.toFixed(2)} USD
          </p>
          <p style="color: #65717f; font-size: 0.85rem; margin: 0;">
            Cliente: ${notif.order.shippingInfo.email}
          </p>
          <div style="margin-top: 0.5rem;">
            <span style="color: ${notif.sent ? '#81c784' : '#e57373'}; font-size: 0.8rem;">
              ${notif.sent ? '✓ Enviado' : '⏳ Pendiente de envío'}
            </span>
          </div>
        </div>
      `;
    }).join('');
    
    notificationsContent.innerHTML = notificationsHTML;
  }
  
  // Inicializar
  function init() {
    checkSession();
    
    // Event listener para login
    document.getElementById('loginForm').addEventListener('submit', function(e) {
      e.preventDefault();
      const password = document.getElementById('adminPassword').value;
      
      if (!login(password)) {
        document.getElementById('loginError').textContent = 'Contraseña incorrecta';
      } else {
        document.getElementById('loginError').textContent = '';
        document.getElementById('adminPassword').value = '';
      }
    });
  }
  
  return {
    init,
    logout,
    showSection,
    calculatePrice
  };
})();

// Hacer funciones disponibles globalmente
window.logout = AdminPanel.logout;
window.showSection = AdminPanel.showSection;
window.calculatePrice = AdminPanel.calculatePrice;

// Auto-inicialización
document.addEventListener('DOMContentLoaded', () => {
  AdminPanel.init();
});
