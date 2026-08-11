/**
 * Servidor Express — sitio estático, Stripe y registro inmediato de pedidos.
 */

require('dotenv').config();

const path = require('path');
const express = require('express');
const cors = require('cors');
const Stripe = require('stripe');
const { createOrder, getOrder } = require('./orders-store');

const PORT = process.env.PORT || 3000;
const ROOT = path.join(__dirname, '..');

const stripeSecret = process.env.STRIPE_SECRET_KEY;
const stripe = stripeSecret ? new Stripe(stripeSecret) : null;

const allowedOrigins = (process.env.CORS_ORIGINS || 'http://localhost:3000')
  .split(',')
  .map((o) => o.trim())
  .filter(Boolean);

const app = express();

app.use(
  cors({
    origin(origin, callback) {
      if (!origin || allowedOrigins.includes(origin)) {
        callback(null, true);
      } else {
        callback(new Error('Origen no permitido por CORS'));
      }
    },
  })
);

app.post(
  '/api/stripe-webhook',
  express.raw({ type: 'application/json' }),
  async (req, res) => {
    if (!stripe || !process.env.STRIPE_WEBHOOK_SECRET) {
      return res.status(503).send('Webhook no configurado');
    }

    const sig = req.headers['stripe-signature'];
    let event;

    try {
      event = stripe.webhooks.constructEvent(
        req.body,
        sig,
        process.env.STRIPE_WEBHOOK_SECRET
      );
    } catch (err) {
      return res.status(400).send(`Webhook Error: ${err.message}`);
    }

    if (event.type === 'payment_intent.succeeded') {
      const intent = event.data.object;
      console.log('[Webhook] Pago exitoso:', intent.metadata?.orderReference);
    }

    res.json({ received: true });
  }
);

app.use(express.json({ limit: '1mb' }));

/** Registro inmediato de pedidos — tarjeta y transferencia */
app.post('/api/orders', (req, res) => {
  const result = createOrder(req.body);

  if (!result.success) {
    return res.status(400).json({ error: result.errors.join(' ') });
  }

  res.status(201).json({
    success: true,
    order: result.order,
    message:
      result.order.paymentStatus === 'pending_transfer'
        ? 'Pedido registrado. Realiza la transferencia con la referencia indicada.'
        : 'Pedido confirmado y pagado.',
  });
});

app.get('/api/orders/:reference', (req, res) => {
  const order = getOrder(req.params.reference);
  if (!order) {
    return res.status(404).json({ error: 'Pedido no encontrado.' });
  }
  res.json(order);
});

app.post('/api/create-payment-intent', async (req, res) => {
  if (!stripe) {
    return res.status(503).json({
      error: 'Stripe no configurado. Define STRIPE_SECRET_KEY en .env',
    });
  }

  const { amount, currency = 'usd', metadata = {} } = req.body;

  if (!Number.isInteger(amount) || amount < 50) {
    return res.status(400).json({
      error: 'Monto inválido. Debe ser un entero en centavos (mínimo 50).',
    });
  }

  try {
    const paymentIntent = await stripe.paymentIntents.create({
      amount,
      currency: currency.toLowerCase(),
      automatic_payment_methods: { enabled: true },
      metadata: {
        ...metadata,
        finalSale: 'true',
        noRefunds: 'true',
      },
    });

    res.json({ clientSecret: paymentIntent.client_secret });
  } catch (err) {
    console.error('[Stripe]', err.message);
    res.status(500).json({ error: err.message });
  }
});

app.get('/api/health', (_req, res) => {
  res.json({
    ok: true,
    stripe: Boolean(stripe),
    orders: true,
    timestamp: new Date().toISOString(),
  });
});

app.use(express.static(ROOT));

app.get('*', (_req, res) => {
  res.sendFile(path.join(ROOT, 'index.html'));
});

app.listen(PORT, () => {
  console.log(`Cazador Sueño — http://localhost:${PORT}`);
  if (!stripe) {
    console.warn('⚠ STRIPE_SECRET_KEY no definida. Pagos con tarjeta deshabilitados.');
  }
});
