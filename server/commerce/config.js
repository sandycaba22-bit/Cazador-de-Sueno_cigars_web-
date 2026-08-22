/**
 * Configuración del servicio de comercio.
 *
 * Todo secreto llega por entorno. Nunca se lee desde el árbol público del sitio
 * ni se escribe en el repositorio.
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const REPO_ROOT = path.join(__dirname, '..', '..');

/**
 * Carga un fichero .env sin depender de dotenv. Las variables ya presentes en
 * el entorno ganan, para que systemd (EnvironmentFile) tenga la última palabra
 * en producción.
 */
function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return;
  for (const line of fs.readFileSync(filePath, 'utf8').split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const separator = trimmed.indexOf('=');
    if (separator < 1) continue;
    const key = trimmed.slice(0, separator).trim();
    let value = trimmed.slice(separator + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (process.env[key] == null) process.env[key] = value;
  }
}

loadEnvFile(path.join(__dirname, '.env'));
loadEnvFile(path.join(REPO_ROOT, '.env'));

function bool(value, fallback = false) {
  if (value === undefined || value === '') return fallback;
  return /^(1|true|yes|on)$/i.test(String(value));
}

function int(value, fallback) {
  const n = Number.parseInt(value, 10);
  return Number.isFinite(n) ? n : fallback;
}

function list(value) {
  return String(value || '')
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean);
}

const NODE_ENV = process.env.NODE_ENV || 'development';
const IS_PRODUCTION = NODE_ENV === 'production';

/**
 * En producción el almacén de pedidos vive fuera del webroot. Es el único modo
 * de garantizar que Nginx no lo pueda servir aunque la configuración cambie.
 */
const DEFAULT_DATA_DIR = IS_PRODUCTION
  ? '/var/lib/cazador-de-suenos/commerce'
  : path.join(REPO_ROOT, '.commerce-data');

const config = {
  nodeEnv: NODE_ENV,
  isProduction: IS_PRODUCTION,

  port: int(process.env.COMMERCE_PORT, 8788),
  host: process.env.COMMERCE_HOST || '127.0.0.1',

  /**
   * Orígenes autorizados. En producción, solo el dominio canónico. En
   * desarrollo se añade localhost para poder probar el checkout completo sin
   * exportar variables a mano; nunca se añade si NODE_ENV es production.
   */
  corsOrigins: list(process.env.COMMERCE_CORS_ORIGINS).length
    ? list(process.env.COMMERCE_CORS_ORIGINS)
    : IS_PRODUCTION
      ? ['https://www.cazadordesuenocigars.com']
      : [
          'https://www.cazadordesuenocigars.com',
          'http://localhost:3000',
          'http://127.0.0.1:3000',
        ],

  dataDir: process.env.COMMERCE_DATA_DIR || DEFAULT_DATA_DIR,

  /**
   * Clave para firmar las cotizaciones. Si no se define, se genera una
   * efímera: las cotizaciones dejan de ser válidas al reiniciar el proceso,
   * lo cual es aceptable en desarrollo pero no en producción.
   */
  quoteSecret: process.env.COMMERCE_QUOTE_SECRET || crypto.randomBytes(32).toString('hex'),
  quoteSecretProvided: Boolean(process.env.COMMERCE_QUOTE_SECRET),
  quoteTtlSeconds: int(process.env.COMMERCE_QUOTE_TTL_SECONDS, 900),

  /** Ventana de idempotencia para evitar cobros duplicados por doble clic. */
  idempotencyTtlSeconds: int(process.env.COMMERCE_IDEMPOTENCY_TTL_SECONDS, 3600),

  rateLimit: {
    windowMs: int(process.env.COMMERCE_RATE_WINDOW_MS, 60_000),
    maxQuotes: int(process.env.COMMERCE_RATE_MAX_QUOTES, 60),
    maxPayments: int(process.env.COMMERCE_RATE_MAX_PAYMENTS, 8),
  },

  /**
   * Sandbox de cobro simulado: desactivado de forma permanente. El código del
   * adaptador puede existir para pruebas unitarias aisladas, pero el registro
   * de pasarelas ya no lo monta nunca.
   */
  sandbox: {
    enabled: false,
  },

  cardnet: {
    enabled: bool(process.env.CARDNET_ENABLED, false),
    /** Base del API de tokenización/compra (Ztrans servicios). */
    baseUrl: process.env.CARDNET_BASE_URL || 'https://labservicios.cardnet.com.do/servicios/tokens',
    publicAccountKey: process.env.CARDNET_PUBLIC_ACCOUNT_KEY || '',
    privateAccountKey: process.env.CARDNET_PRIVATE_ACCOUNT_KEY || '',
    /** Moneda con la que el afiliado está habilitado a liquidar. */
    currency: (process.env.CARDNET_CURRENCY || 'DOP').toUpperCase(),
    /** Solo se usa si la moneda del catálogo (USD) difiere de la del afiliado. */
    usdToDopRate: Number(process.env.CARDNET_USD_DOP_RATE || 0),
    timeoutMs: int(process.env.CARDNET_TIMEOUT_MS, 30_000),
    captureImmediately: bool(process.env.CARDNET_CAPTURE, true),
  },

  bankTransfer: {
    enabled: bool(process.env.BANK_TRANSFER_ENABLED, true),
  },

  /**
   * PayPal Checkout. El Client ID es público (viaja al SDK del navegador).
   * El secret jamás sale de este proceso.
   * Con Client ID + Secret se activa solo (salvo PAYPAL_ENABLED=false).
   * En producción el modo por defecto es live.
   */
  paypal: {
    enabled: (() => {
      const hasKeys = Boolean(
        String(process.env.PAYPAL_CLIENT_ID || '').trim() &&
          String(process.env.PAYPAL_CLIENT_SECRET || '').trim()
      );
      // Si hay claves, preferimos activar. Solo un "false" explícito lo apaga.
      if (Object.prototype.hasOwnProperty.call(process.env, 'PAYPAL_ENABLED')) {
        const raw = String(process.env.PAYPAL_ENABLED || '').trim();
        if (/^(0|false|no|off)$/i.test(raw)) return false;
        if (/^(1|true|yes|on)$/i.test(raw)) return true;
      }
      return hasKeys;
    })(),
    clientId: String(process.env.PAYPAL_CLIENT_ID || '').trim(),
    clientSecret: String(process.env.PAYPAL_CLIENT_SECRET || '').trim(),
    mode:
      (process.env.PAYPAL_MODE || (IS_PRODUCTION ? 'live' : 'sandbox')).toLowerCase() === 'live'
        ? 'live'
        : 'sandbox',
    currency: (process.env.PAYPAL_CURRENCY || 'USD').toUpperCase(),
    timeoutMs: int(process.env.PAYPAL_TIMEOUT_MS, 30_000),
  },

  contact: {
    whatsapp: process.env.HOUSE_WHATSAPP_E164 || '18094645016',
    email: process.env.HOUSE_EMAIL || 'cazadordesueno2024@gmail.com',
  },
};

/**
 * Problemas de configuración que deben ser visibles al arrancar, no cuando
 * un cliente intenta pagar.
 */
function collectConfigWarnings(cfg = config) {
  const warnings = [];

  if (cfg.isProduction && !cfg.quoteSecretProvided) {
    warnings.push(
      'COMMERCE_QUOTE_SECRET no está definida: las cotizaciones se invalidarán en cada reinicio.'
    );
  }
  if (cfg.isProduction && cfg.sandbox.enabled) {
    warnings.push('COMMERCE_SANDBOX_ENABLED está activo; el registro ya no monta sandbox, desactívalo de todos modos.');
  }
  if (cfg.cardnet.enabled) {
    if (!cfg.cardnet.publicAccountKey) warnings.push('CARDNET_PUBLIC_ACCOUNT_KEY vacía.');
    if (!cfg.cardnet.privateAccountKey) warnings.push('CARDNET_PRIVATE_ACCOUNT_KEY vacía.');
    if (cfg.isProduction && /labservicios/.test(cfg.cardnet.baseUrl)) {
      warnings.push('CARDNET_BASE_URL apunta al ambiente de certificación (labservicios).');
    }
    if (cfg.cardnet.currency !== 'USD' && !cfg.cardnet.usdToDopRate) {
      warnings.push(
        `El catálogo está en USD y CardNET liquidará en ${cfg.cardnet.currency}, pero CARDNET_USD_DOP_RATE no está definida.`
      );
    }
  }
  if (cfg.paypal.enabled) {
    if (!cfg.paypal.clientId) warnings.push('PAYPAL_CLIENT_ID vacía.');
    if (!cfg.paypal.clientSecret) warnings.push('PAYPAL_CLIENT_SECRET vacía.');
    if (cfg.isProduction && cfg.paypal.mode !== 'live') {
      warnings.push('PAYPAL_MODE no es live en producción.');
    }
  }
  if (cfg.isProduction && cfg.corsOrigins?.some((o) => /localhost|127\.0\.0\.1/.test(o))) {
    warnings.push('COMMERCE_CORS_ORIGINS incluye localhost en producción.');
  }
  if (cfg.isProduction && isPathInside(cfg.dataDir, REPO_ROOT)) {
    warnings.push(
      'COMMERCE_DATA_DIR está dentro del árbol público del sitio. Los pedidos quedarían servibles por HTTP.'
    );
  }
  if (cfg.isProduction && !isLoopbackHost(cfg.host)) {
    warnings.push('COMMERCE_HOST no es loopback: el servicio quedaría expuesto sin pasar por Nginx.');
  }

  return warnings;
}

function isLoopbackHost(host) {
  return host === '127.0.0.1' || host === 'localhost' || host === '::1';
}

function isPathInside(inner, outer) {
  const resolvedInner = path.resolve(inner);
  const resolvedOuter = path.resolve(outer);
  return resolvedInner === resolvedOuter || resolvedInner.startsWith(resolvedOuter + path.sep);
}

/**
 * Condiciones que en producción impiden arrancar. Un warning se puede ignorar;
 * un bloqueo no: significaría volver a cobrar mal, firmar precios con una
 * clave efímera o filtrar pedidos.
 */
function collectProductionBlocks(cfg = config) {
  if (!cfg.isProduction) return [];
  const blocks = [];
  if (isPathInside(cfg.dataDir, REPO_ROOT)) {
    blocks.push(
      'COMMERCE_DATA_DIR está dentro del árbol público del sitio. Los pedidos quedarían servibles por HTTP.'
    );
  }
  if (!isLoopbackHost(cfg.host)) {
    blocks.push('COMMERCE_HOST no es loopback: el servicio quedaría expuesto sin pasar por Nginx.');
  }
  if (cfg.sandbox.enabled) {
    blocks.push(
      'COMMERCE_SANDBOX_ENABLED está activo. El cobro simulado está retirado del checkout; desactívalo.'
    );
  }
  if (!cfg.quoteSecretProvided) {
    blocks.push(
      'COMMERCE_QUOTE_SECRET no está definida: las cotizaciones se invalidarán en cada reinicio y no hay clave estable para firmar precios.'
    );
  }
  return blocks;
}

module.exports = {
  config,
  collectConfigWarnings,
  collectProductionBlocks,
  loadEnvFile,
  REPO_ROOT,
};
