'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const { CORE_SYSTEM_INSTRUCTION, buildSystemPrompt } = require('./system-prompt');
const { CHECKOUT_CORE_INSTRUCTION, buildCheckoutPrompt } = require('./checkout-prompt');

loadEnvFile(path.join(__dirname, '.env'));

const PORT = Number(process.env.PORT || 8787);
const HOST = process.env.HOST || '127.0.0.1';
const GEMINI_API_KEY = process.env.GEMINI_API_KEY || '';
const GEMINI_MODEL = process.env.GEMINI_MODEL || 'gemini-2.5-flash';
const FALLBACK_MODELS = (process.env.GEMINI_FALLBACK_MODELS || 'gemini-2.5-pro,gemini-2.0-flash,gemini-1.5-pro')
  .split(',')
  .map((item) => item.trim())
  .filter(Boolean);
const HOUSE_WHATSAPP_DISPLAY = process.env.HOUSE_WHATSAPP || '+1 809-464-5016';
const HOUSE_WHATSAPP_E164 =
  process.env.HOUSE_WHATSAPP_E164 ||
  String(HOUSE_WHATSAPP_DISPLAY).replace(/\D/g, '') ||
  '18094645016';
const HOUSE_EMAIL = process.env.HOUSE_EMAIL || 'cazadordesueno1@gmail.com';
const LOG_REPLIES = String(process.env.LOG_REPLIES || 'true').toLowerCase() !== 'false';

const MAX_MESSAGE_CHARS = 2000;
const MAX_HISTORY = 16;
const RATE_WINDOW_MS = 10 * 60 * 1000;
const RATE_MAX = 24;
const DATA_DIR = path.join(__dirname, 'data');
const LEADS_FILE = path.join(DATA_DIR, 'leads.jsonl');

const ALLOWED_ORIGINS = new Set([
  'https://www.cazadordesuenocigars.com',
  'https://cazadordesuenocigars.com',
  'https://www.cazadordesueno.com',
  'https://cazadordesueno.com',
  'http://localhost',
  'http://127.0.0.1'
]);

const rateBuckets = new Map();

function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return;
  const raw = fs.readFileSync(filePath, 'utf8');
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const idx = trimmed.indexOf('=');
    if (idx < 1) continue;
    const key = trimmed.slice(0, idx).trim();
    let value = trimmed.slice(idx + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (process.env[key] == null) process.env[key] = value;
  }
}

function ensureDataDir() {
  if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
}

function clientIp(req) {
  const forwarded = req.headers['x-forwarded-for'];
  if (typeof forwarded === 'string' && forwarded.trim()) {
    return forwarded.split(',')[0].trim();
  }
  return (req.socket && req.socket.remoteAddress) || 'unknown';
}

function originAllowed(req) {
  const origin = req.headers.origin;
  if (!origin) return true;
  try {
    const url = new URL(origin);
    if (url.hostname === 'localhost' || url.hostname === '127.0.0.1') return true;
    return ALLOWED_ORIGINS.has(`${url.protocol}//${url.host}`) || ALLOWED_ORIGINS.has(`${url.protocol}//${url.hostname}`);
  } catch {
    return false;
  }
}

function setCors(req, res) {
  const origin = req.headers.origin;
  if (origin && originAllowed(req)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Vary', 'Origin');
  }
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
}

function rateLimited(ip) {
  const now = Date.now();
  const hits = (rateBuckets.get(ip) || []).filter((ts) => now - ts < RATE_WINDOW_MS);
  if (hits.length >= RATE_MAX) {
    rateBuckets.set(ip, hits);
    return true;
  }
  hits.push(now);
  rateBuckets.set(ip, hits);
  return false;
}

function readJsonBody(req, limit = 80_000) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on('data', (chunk) => {
      size += chunk.length;
      if (size > limit) {
        reject(Object.assign(new Error('Payload too large'), { statusCode: 413 }));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => {
      if (!chunks.length) {
        resolve({});
        return;
      }
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')));
      } catch {
        reject(Object.assign(new Error('JSON inválido'), { statusCode: 400 }));
      }
    });
    req.on('error', reject);
  });
}

function sanitizeMessages(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .slice(-MAX_HISTORY)
    .map((item) => {
      const role = item && item.role === 'assistant' ? 'assistant' : 'user';
      const content = String((item && (item.content || item.text)) || '')
        .replace(/<<<CDS_LEAD[\s\S]*?>>>/g, '')
        .slice(0, MAX_MESSAGE_CHARS)
        .trim();
      return { role, content };
    })
    .filter((item) => item.content);
}

function toGeminiContents(messages) {
  return messages.map((msg) => ({
    role: msg.role === 'assistant' ? 'model' : 'user',
    parts: [{ text: msg.content }]
  }));
}

function extractLead(text) {
  const match = String(text || '').match(/<<<CDS_LEAD\s*(\{[\s\S]*?\})\s*>>>/);
  if (!match) return { clean: String(text || '').trim(), lead: null };
  let lead = null;
  try {
    lead = JSON.parse(match[1]);
  } catch {
    lead = null;
  }
  const clean = String(text)
    .replace(/<<<CDS_LEAD[\s\S]*?>>>/g, '')
    .replace(/[ \t]+\n/g, '\n')
    .trim();
  return { clean, lead };
}

function normalizeLead(lead, language, ip) {
  if (!lead || typeof lead !== 'object') return null;
  const pick = (key) => String(lead[key] || '').trim().slice(0, 240);
  const nombre = pick('nombre') || pick('name');
  const empresa = pick('empresa') || pick('company');
  const pais = pick('pais') || pick('country');
  if (!nombre && !empresa) return null;
  return {
    id: `lead_${Date.now()}`,
    created_at: new Date().toISOString(),
    language,
    nombre,
    empresa,
    pais,
    ciudad: pick('ciudad') || pick('city'),
    volumen: pick('volumen') || pick('volume'),
    email: pick('email'),
    telefono: pick('telefono') || pick('phone'),
    notas: pick('notas') || pick('notes'),
    ip,
    status: 'priority'
  };
}

function whatsappUrlForLead(lead) {
  const lines = [
    'Consulta B2B — Cazador de Sueño Cigars SRL',
    `Nombre: ${lead.nombre || '—'}`,
    `Empresa: ${lead.empresa || '—'}`,
    `País / ciudad: ${[lead.pais, lead.ciudad].filter(Boolean).join(', ') || '—'}`,
    `Volumen estimado: ${lead.volumen || '—'}`,
    lead.email ? `Correo: ${lead.email}` : '',
    lead.telefono ? `Teléfono: ${lead.telefono}` : '',
    lead.notas ? `Notas: ${lead.notas}` : ''
  ].filter(Boolean);
  return `https://wa.me/${HOUSE_WHATSAPP_E164}?text=${encodeURIComponent(lines.join('\n'))}`;
}

function logConversation({ language, page, ip, model, userText, reply, lead }) {
  if (!LOG_REPLIES) return;
  const stamp = new Date().toISOString();
  const blocks = [
    '',
    '========== SOMMELIER ==========',
    `[${stamp}] idioma=${language || 'es'} pagina=${page || '—'} ip=${ip} modelo=${model || '—'}`,
    '--- Cliente ---',
    userText || '(sin mensaje)',
    '--- Maestro Tabaquero ---',
    reply || '(respuesta vacía)'
  ];
  if (lead) {
    blocks.push('--- Lead B2B ---');
    blocks.push(
      `${lead.nombre || '—'} · ${lead.empresa || '—'} · ${[lead.pais, lead.ciudad].filter(Boolean).join(', ') || '—'} · ${lead.volumen || 'sin volumen'}`
    );
    blocks.push(`WhatsApp de derivación: ${HOUSE_WHATSAPP_DISPLAY} · ${HOUSE_EMAIL}`);
  }
  blocks.push('================================');
  blocks.push('');
  console.log(blocks.join('\n'));
}

function persistLead(lead) {
  ensureDataDir();
  fs.appendFileSync(LEADS_FILE, `${JSON.stringify(lead)}\n`, 'utf8');
}

class MarkerFilter {
  constructor() {
    this.hold = '';
    this.assembled = '';
  }

  push(chunk) {
    this.assembled += chunk;
    this.hold += chunk;
    return this.flush(false);
  }

  flush(final = false) {
    const start = this.hold.indexOf('<<<');
    if (start === -1) {
      const out = this.hold;
      this.hold = '';
      return out;
    }
    const before = this.hold.slice(0, start);
    const rest = this.hold.slice(start);
    const end = rest.indexOf('>>>');
    if (end === -1) {
      this.hold = rest;
      if (final) {
        this.hold = '';
        return before;
      }
      if (!'<<<CDS_LEAD'.startsWith(rest.slice(0, Math.min(rest.length, 12))) && !rest.startsWith('<<<')) {
        this.hold = '';
        return before + rest;
      }
      return before;
    }
    this.hold = rest.slice(end + 3);
    return before + this.flush(final);
  }

  finish() {
    const rest = this.flush(true);
    return rest;
  }
}

function sendSse(res, event, data) {
  res.write(`event: ${event}\n`);
  res.write(`data: ${JSON.stringify(data)}\n\n`);
}

function geminiUrl(model) {
  return `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:streamGenerateContent?alt=sse&key=${encodeURIComponent(GEMINI_API_KEY)}`;
}

/** Instrucciones de sistema del sommelier (comportamiento por defecto). */
function sommelierSystemParts(language) {
  return [
    { text: CORE_SYSTEM_INSTRUCTION },
    {
      text: buildSystemPrompt({
        language,
        whatsappDisplay: HOUSE_WHATSAPP_DISPLAY,
        email: HOUSE_EMAIL
      })
    }
  ];
}

function buildGeminiBody(messages, language, options = {}) {
  return {
    system_instruction: {
      parts: options.systemParts || sommelierSystemParts(language)
    },
    contents: toGeminiContents(messages),
    generationConfig: {
      temperature: options.temperature ?? 0.7,
      maxOutputTokens: options.maxOutputTokens ?? 1024,
      thinkingConfig: { thinkingBudget: 0 }
    },
    safetySettings: [
      { category: 'HARM_CATEGORY_HARASSMENT', threshold: 'BLOCK_ONLY_HIGH' },
      { category: 'HARM_CATEGORY_HATE_SPEECH', threshold: 'BLOCK_ONLY_HIGH' },
      { category: 'HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold: 'BLOCK_ONLY_HIGH' },
      { category: 'HARM_CATEGORY_DANGEROUS_CONTENT', threshold: 'BLOCK_ONLY_HIGH' }
    ]
  };
}

async function openGeminiStream(model, body) {
  const response = await fetch(geminiUrl(model), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  return response;
}

async function streamGeminiToSse(res, messages, language, ip, logMeta = {}, options = {}) {
  const models = [GEMINI_MODEL, ...FALLBACK_MODELS].filter(
    (model, index, list) => model && list.indexOf(model) === index
  );
  let lastError = 'No se pudo contactar al sommelier.';
  const body = buildGeminiBody(messages, language, options);
  // El asistente de checkout no capta leads B2B: solo desatasca la compra.
  const captureLeads = options.captureLeads !== false;

  for (const model of models) {
    let response;
    try {
      response = await openGeminiStream(model, body);
      if (response.status === 400) {
        const retryBody = JSON.parse(JSON.stringify(body));
        delete retryBody.generationConfig.thinkingConfig;
        response = await openGeminiStream(model, retryBody);
      }
    } catch (err) {
      lastError = err.message || lastError;
      continue;
    }

    if (!response.ok) {
      const errText = await response.text().catch(() => '');
      lastError = `Gemini ${response.status}: ${errText.slice(0, 280)}`;
      if (response.status === 404 || response.status === 400) continue;
      sendSse(res, 'error', { message: 'El sommelier no pudo responder en este momento.' });
      logConversation({
        language,
        page: logMeta.page,
        ip,
        model,
        userText: logMeta.userText,
        reply: `ERROR: ${lastError}`
      });
      return;
    }

    sendSse(res, 'meta', { model, whatsapp: HOUSE_WHATSAPP_DISPLAY });

    const filter = new MarkerFilter();
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let sseBuffer = '';

    const emitText = (text) => {
      if (!text) return;
      sendSse(res, 'token', { text });
    };

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        sseBuffer += decoder.decode(value, { stream: true });
        const lines = sseBuffer.split('\n');
        sseBuffer = lines.pop() || '';

        for (const rawLine of lines) {
          const line = rawLine.trim();
          if (!line.startsWith('data:')) continue;
          const payload = line.slice(5).trim();
          if (!payload || payload === '[DONE]') continue;
          let json;
          try {
            json = JSON.parse(payload);
          } catch {
            continue;
          }
          const parts =
            (json.candidates &&
              json.candidates[0] &&
              json.candidates[0].content &&
              json.candidates[0].content.parts) ||
            [];
          for (const part of parts) {
            if (part && typeof part.text === 'string') emitText(filter.push(part.text));
          }
        }
      }
    } finally {
      emitText(filter.finish());
    }

    const { clean, lead: rawLead } = extractLead(filter.assembled);
    const lead = captureLeads ? normalizeLead(rawLead, language, ip) : null;
    if (lead) {
      persistLead(lead);
      sendSse(res, 'lead', {
        lead,
        whatsappUrl: whatsappUrlForLead(lead),
        phone: HOUSE_WHATSAPP_DISPLAY
      });
    }

    logConversation({
      language,
      page: logMeta.page,
      ip,
      model,
      userText: logMeta.userText,
      reply: clean,
      lead
    });

    sendSse(res, 'done', { text: clean });
    return;
  }

  sendSse(res, 'error', { message: 'El sommelier no está disponible por ahora.' });
  console.error('[ai-sommelier]', lastError);
  logConversation({
    language,
    page: logMeta.page,
    ip,
    model: 'error',
    userText: logMeta.userText,
    reply: `ERROR: ${lastError}`
  });
}

async function handleChat(req, res) {
  setCors(req, res);
  if (!originAllowed(req)) {
    res.writeHead(403, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'Origen no permitido' }));
    return;
  }

  const ip = clientIp(req);
  if (rateLimited(ip)) {
    res.writeHead(429, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'Demasiadas consultas. Espere unos minutos en la cava.' }));
    return;
  }

  if (!GEMINI_API_KEY) {
    res.writeHead(503, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'Falta GEMINI_API_KEY en el servidor.' }));
    return;
  }

  let payload;
  try {
    payload = await readJsonBody(req);
  } catch (err) {
    res.writeHead(err.statusCode || 400, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: err.message || 'Solicitud inválida' }));
    return;
  }

  const messages = sanitizeMessages(payload.messages);
  if (!messages.length || messages[messages.length - 1].role !== 'user') {
    res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'Se requiere un mensaje del visitante.' }));
    return;
  }

  const language = String(payload.language || 'es').slice(0, 8);
  const page = String(payload.page || '').slice(0, 180);
  const visitorMessage = messages[messages.length - 1].content;
  if (page) {
    messages.unshift({
      role: 'user',
      content: `[Contexto de navegación: el visitante está en ${page}. Úsalo solo si ayuda a orientar la recomendación; no lo menciones de forma técnica.]`
    });
    messages.splice(1, 0, {
      role: 'assistant',
      content: 'Entendido. Atiendo desde la cava con ese contexto.'
    });
  }

  res.writeHead(200, {
    'Content-Type': 'text/event-stream; charset=utf-8',
    'Cache-Control': 'no-cache, no-transform',
    Connection: 'keep-alive',
    'X-Accel-Buffering': 'no'
  });

  try {
    await streamGeminiToSse(res, messages, language, ip, {
      userText: visitorMessage,
      page
    });
  } catch (err) {
    console.error('[ai-sommelier]', err);
    sendSse(res, 'error', { message: 'La cava está en silencio por un momento. Intente de nuevo.' });
  }
  res.end();
}

/**
 * Sanea el estado del checkout que envía el navegador.
 *
 * Es solo contexto para el modelo, nunca una fuente de verdad: el importe real
 * lo decide el servicio de comercio. Aun así se recorta y se normaliza para que
 * nadie pueda inyectar instrucciones al modelo a través de estos campos.
 */
function sanitizeCheckoutContext(raw) {
  if (!raw || typeof raw !== 'object') return {};
  const text = (value, max) => String(value == null ? '' : value).replace(/[\r\n]+/g, ' ').slice(0, max);
  const methods = Array.isArray(raw.availableMethods) ? raw.availableMethods : [];

  return {
    method: text(raw.method, 40),
    availableMethods: methods.slice(0, 6).map((m) => text(m, 40)),
    totalCents: Number.isFinite(Number(raw.totalCents)) ? Math.abs(Number(raw.totalCents)) : 0,
    currency: text(raw.currency, 8),
    country: text(raw.country, 8),
    boxes: Number.isFinite(Number(raw.boxes)) ? Math.abs(Math.floor(Number(raw.boxes))) : 0,
    lastError: text(raw.lastError, 200)
  };
}

/** Detecta un PAN escrito en el chat para cortarlo antes de enviarlo a Gemini. */
function containsCardNumber(text) {
  const digits = String(text || '').replace(/[\s-]/g, '');
  const match = digits.match(/\d{13,19}/);
  if (!match) return false;
  return luhnValid(match[0]);
}

function luhnValid(number) {
  let sum = 0;
  let double = false;
  for (let i = number.length - 1; i >= 0; i -= 1) {
    let digit = Number(number[i]);
    if (double) {
      digit *= 2;
      if (digit > 9) digit -= 9;
    }
    sum += digit;
    double = !double;
  }
  return sum % 10 === 0;
}

async function handleCheckoutAssistant(req, res) {
  setCors(req, res);
  if (!originAllowed(req)) {
    res.writeHead(403, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'Origen no permitido' }));
    return;
  }

  const ip = clientIp(req);
  if (rateLimited(ip)) {
    res.writeHead(429, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'Demasiadas consultas seguidas. Espere un momento.' }));
    return;
  }

  if (!GEMINI_API_KEY) {
    res.writeHead(503, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'Asistente no disponible.' }));
    return;
  }

  let payload;
  try {
    payload = await readJsonBody(req);
  } catch (err) {
    res.writeHead(err.statusCode || 400, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: err.message || 'Solicitud inválida' }));
    return;
  }

  const messages = sanitizeMessages(payload.messages);
  if (!messages.length || messages[messages.length - 1].role !== 'user') {
    res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'Se requiere un mensaje del cliente.' }));
    return;
  }

  const visitorMessage = messages[messages.length - 1].content;

  // Un número de tarjeta escrito en el chat se corta aquí: no llega al modelo,
  // no se registra y no queda en el historial del navegador.
  if (containsCardNumber(visitorMessage)) {
    res.writeHead(200, {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no'
    });
    const warning =
      'Por su seguridad no puedo recibir números de tarjeta por este chat. Borre ese mensaje e introduzca la tarjeta únicamente en la ventana segura de CardNET que se abre al confirmar el pedido.';
    sendSse(res, 'meta', { model: 'guardia-pci', whatsapp: HOUSE_WHATSAPP_DISPLAY });
    sendSse(res, 'token', { text: warning });
    sendSse(res, 'done', { text: warning });
    res.end();
    console.warn(`[checkout-assistant] mensaje con posible PAN bloqueado · ip=${ip}`);
    return;
  }

  const language = String(payload.language || 'es').slice(0, 8);
  const context = sanitizeCheckoutContext(payload.context);

  res.writeHead(200, {
    'Content-Type': 'text/event-stream; charset=utf-8',
    'Cache-Control': 'no-cache, no-transform',
    Connection: 'keep-alive',
    'X-Accel-Buffering': 'no'
  });

  try {
    await streamGeminiToSse(
      res,
      messages,
      language,
      ip,
      { userText: visitorMessage, page: 'checkout' },
      {
        systemParts: [
          { text: CHECKOUT_CORE_INSTRUCTION },
          {
            text: buildCheckoutPrompt({
              context,
              whatsappDisplay: HOUSE_WHATSAPP_DISPLAY,
              email: HOUSE_EMAIL
            })
          }
        ],
        captureLeads: false,
        temperature: 0.4,
        maxOutputTokens: 512
      }
    );
  } catch (err) {
    console.error('[checkout-assistant]', err);
    sendSse(res, 'error', {
      message: 'El asistente no está disponible. Escríbanos por WhatsApp y le ayudamos.'
    });
  }
  res.end();
}

function handleHealth(req, res) {
  setCors(req, res);
  res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(
    JSON.stringify({
      ok: true,
      service: 'ai-sommelier',
      model: GEMINI_MODEL,
      configured: Boolean(GEMINI_API_KEY)
    })
  );
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url || '/', `http://${req.headers.host || 'localhost'}`);
  const route = url.pathname.replace(/\/+$/, '') || '/';

  if (req.method === 'OPTIONS') {
    setCors(req, res);
    res.writeHead(204);
    res.end();
    return;
  }

  if (
    req.method === 'POST' &&
    (route === '/api/ai-sommelier/checkout' || route === '/checkout')
  ) {
    await handleCheckoutAssistant(req, res);
    return;
  }

  if (req.method === 'GET' && (route === '/api/ai-sommelier/health' || route === '/health')) {
    handleHealth(req, res);
    return;
  }

  if (req.method === 'POST' && (route === '/api/ai-sommelier' || route === '/ai-sommelier')) {
    await handleChat(req, res);
    return;
  }

  res.writeHead(404, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify({ error: 'Not found' }));
});

server.listen(PORT, HOST, () => {
  console.log(`[ai-sommelier] listening on http://${HOST}:${PORT}`);
  console.log(`[ai-sommelier] modelo=${GEMINI_MODEL} api_key=${GEMINI_API_KEY ? 'configurada' : 'AUSENTE'}`);
  console.log(`[ai-sommelier] B2B WhatsApp=${HOUSE_WHATSAPP_DISPLAY} email=${HOUSE_EMAIL} logs=${LOG_REPLIES ? 'on' : 'off'}`);
  if (!GEMINI_API_KEY) {
    console.warn('[ai-sommelier] Falta GEMINI_API_KEY. Copia .env.example a .env o usa /etc/cazador-de-suenos/ai-sommelier.env');
  }
});
