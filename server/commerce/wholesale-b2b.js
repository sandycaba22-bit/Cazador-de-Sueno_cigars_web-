/**
 * Solicitudes del portal mayorista: se guardan en Supabase y se avisan
 * por Telegram con botones de aprobar o rechazar.
 *
 * La clave de Supabase no sale al navegador. Si no está configurada, la
 * petición se acepta igual y el portal sigue mostrando los precios.
 */

const crypto = require('crypto');
const https = require('https');

const { CheckoutError, ERROR_CODES } = require('./errors');

const TIPOS = new Set(['acceso', 'cotizacion']);
const VITOLAS = new Set(['sultan', 'ligero', 'puro-habano', 'exquisito', 'emperador']);

function supabaseConfig() {
  const url = String(process.env.SUPABASE_URL || '').trim().replace(/\/$/, '');
  const key = String(
    process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_ANON_KEY || '',
  ).trim();
  return { url, key, listo: Boolean(url && key) };
}

function clip(value, max) {
  return String(value || '').trim().slice(0, max);
}

function correoValido(value) {
  if (!value) return true;
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value) && value.length <= 180;
}

function normalizarSolicitud(body) {
  const data = body && typeof body === 'object' ? body : {};
  const tipo = clip(data.tipo, 20);
  const empresa = clip(data.empresa, 160);
  const correo = clip(data.correo, 180);
  const telefono = clip(data.telefono, 40);
  if (!TIPOS.has(tipo) || empresa.length < 2 || !correoValido(correo)) {
    throw new CheckoutError(ERROR_CODES.VALIDATION_FAILED, 'La solicitud mayorista está incompleta.', {
      httpStatus: 400,
    });
  }
  const volumen = Number(data.volumen);
  const total = Number(data.totalUsd);
  const tier = Number(data.tier);
  const vitolas = Array.isArray(data.vitolas)
    ? data.vitolas
        .filter((line) => line && VITOLAS.has(String(line.id)))
        .slice(0, 8)
        .map((line) => ({
          id: String(line.id),
          qty: Math.max(0, Math.min(1000000, Math.floor(Number(line.qty) || 0))),
        }))
    : [];
  return {
    id: crypto.randomBytes(6).toString('hex'),
    tipo,
    empresa,
    pais: clip(data.pais, 80),
    correo,
    telefono,
    estado: 'pendiente',
    volumen: Number.isFinite(volumen) ? Math.max(0, Math.min(10000000, Math.floor(volumen))) : null,
    vitolas,
    total_usd: Number.isFinite(total) ? Math.round(total * 100) / 100 : null,
    tier: Number.isFinite(tier) ? Math.max(0, Math.min(9, Math.floor(tier))) : null,
  };
}

function postJson(url, headers, body) {
  return new Promise((resolve) => {
    const payload = Buffer.from(JSON.stringify(body));
    const target = new URL(url);
    const req = https.request(
      {
        protocol: target.protocol,
        hostname: target.hostname,
        port: target.port || 443,
        path: `${target.pathname}${target.search}`,
        method: 'POST',
        headers: {
          ...headers,
          'Content-Type': 'application/json',
          'Content-Length': payload.length,
        },
      },
      (res) => {
        res.resume();
        resolve(res.statusCode >= 200 && res.statusCode < 300);
      },
    );
    req.setTimeout(12000, () => {
      req.destroy();
      resolve(false);
    });
    req.on('error', () => resolve(false));
    req.end(payload);
  });
}

async function guardarSolicitud(fila) {
  const { url, key, listo } = supabaseConfig();
  if (!listo) return false;
  return postJson(`${url}/rest/v1/solicitudes_precios`, {
    apikey: key,
    Authorization: `Bearer ${key}`,
    Prefer: 'return=minimal',
  }, fila);
}

function textoTelegram(fila) {
  const lineas = (fila.vitolas || [])
    .filter((line) => line.qty > 0)
    .map((line) => `${line.id}: ${line.qty}`)
    .join(', ');
  const titulo = fila.tipo === 'cotizacion' ? 'Cotización mayorista' : 'Acceso a precios mayoristas';
  return [
    titulo,
    `Empresa: ${fila.empresa}`,
    fila.pais ? `País: ${fila.pais}` : '',
    fila.correo ? `Correo: ${fila.correo}` : '',
    fila.telefono ? `Teléfono: ${fila.telefono}` : '',
    fila.volumen ? `Volumen: ${fila.volumen}` : '',
    lineas ? `Vitolas: ${lineas}` : '',
    fila.total_usd != null ? `Total FOB: $${fila.total_usd}` : '',
    'Estado: pendiente',
  ].filter(Boolean).join('\n');
}

async function avisarTelegram(fila) {
  const token = String(process.env.TELEGRAM_BOT_TOKEN || '').trim();
  const chat = String(process.env.TELEGRAM_CHAT_ID || '').trim();
  if (!token || !chat) return false;
  return postJson(`https://api.telegram.org/bot${token}/sendMessage`, {}, {
    chat_id: chat,
    text: textoTelegram(fila),
    reply_markup: {
      inline_keyboard: [[
        { text: 'Aprobar', callback_data: `b2ba:${fila.id}` },
        { text: 'Rechazar', callback_data: `b2bx:${fila.id}` },
      ]],
    },
  });
}

module.exports = {
  normalizarSolicitud,
  guardarSolicitud,
  avisarTelegram,
  supabaseConfig,
};
