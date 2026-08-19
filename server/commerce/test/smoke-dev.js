/**
 * Sonda manual contra el servidor de desarrollo ya en marcha.
 *
 *   node server/server.js            (en una terminal)
 *   node server/commerce/test/smoke-dev.js
 *
 * No es una prueba automatizada: comprueba que el servidor real sirve lo que
 * debe y bloquea lo que no, incluido el fichero de pedidos.
 */

const BASE = process.env.SMOKE_BASE || 'http://localhost:3000';

const DEBE_BLOQUEARSE = [
  '/data/orders.json',
  '/data/',
  '/server/commerce/config.js',
  '/server/commerce/.env.example',
  '/.commerce-data/orders',
  '/.env',
  '/package.json',
  '/node_modules/',
];

const DEBE_SERVIRSE = [
  '/checkout.html',
  '/js/checkout.js',
  '/js/checkout-assistant.js',
  '/css/checkout-onepage.css',
  '/order-confirmation.html',
  '/api/commerce/health',
  '/api/commerce/config',
];

async function status(path) {
  try {
    const response = await fetch(`${BASE}${path}`, { redirect: 'manual' });
    return response.status;
  } catch (error) {
    return `sin respuesta (${error.message})`;
  }
}

async function main() {
  let fallos = 0;

  console.log('\n  Rutas que NO deben servirse');
  for (const path of DEBE_BLOQUEARSE) {
    const code = await status(path);
    const ok = code === 404 || code === 403;
    if (!ok) fallos += 1;
    console.log(`   ${ok ? 'OK  ' : 'FALLA'}  ${String(code).padEnd(6)} ${path}`);
  }

  console.log('\n  Rutas que sí deben servirse');
  for (const path of DEBE_SERVIRSE) {
    const code = await status(path);
    const ok = code === 200;
    if (!ok) fallos += 1;
    console.log(`   ${ok ? 'OK  ' : 'FALLA'}  ${String(code).padEnd(6)} ${path}`);
  }

  console.log('\n  Compra completa (sandbox)');
  const quote = await fetch(`${BASE}/api/commerce/quote`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      items: [{ productId: 'emperador', unitType: 'box', quantity: 2 }],
      country: 'US',
    }),
  }).then((r) => r.json());

  if (!quote.quoteToken) {
    console.log('   FALLA  no se pudo cotizar:', JSON.stringify(quote));
    process.exit(1);
  }
  console.log(`   OK     cotización: total ${(quote.quote.totalCents / 100).toFixed(2)} USD`);

  const order = await fetch(`${BASE}/api/commerce/orders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': `smoke-${Date.now()}` },
    body: JSON.stringify({
      quoteToken: quote.quoteToken,
      paymentMethod: 'sandbox',
      paymentPayload: {},
      customer: { fullName: 'Prueba Humo', email: 'humo@ejemplo.com', phone: '8095551234' },
      shipping: { address: 'Calle 1', city: 'Miami', country: 'US', state: 'FL', postalCode: '33101' },
      acceptances: { finalSale: true, customs: true },
    }),
  }).then((r) => r.json());

  if (order.paymentStatus !== 'paid') {
    console.log('   FALLA  el pedido no se confirmó:', JSON.stringify(order));
    fallos += 1;
  } else {
    console.log(`   OK     pedido ${order.reference} confirmado`);

    const consulta = await status(
      `/api/commerce/orders/${order.reference}?t=${encodeURIComponent(order.accessToken)}`
    );
    const sinToken = await status(`/api/commerce/orders/${order.reference}`);
    console.log(`   ${consulta === 200 ? 'OK  ' : 'FALLA'}  consulta con token: ${consulta}`);
    console.log(`   ${sinToken === 404 ? 'OK  ' : 'FALLA'}  consulta sin token: ${sinToken}`);
    if (consulta !== 200 || sinToken !== 404) fallos += 1;

    console.log(
      `\n  Confirmación: ${BASE}/order-confirmation.html?ref=${order.reference}` +
        `&t=${encodeURIComponent(order.accessToken)}`
    );
  }

  console.log(fallos === 0 ? '\n  Todo correcto.\n' : `\n  ${fallos} comprobaciones fallaron.\n`);
  process.exit(fallos === 0 ? 0 : 1);
}

main();
