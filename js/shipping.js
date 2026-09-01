/**
 * Tarifas de envío en USD.
 *
 * La primera unidad de carga (un puro suelto o la primera caja) entra en
 * `base`. Cada caja adicional suma `perBox`. Así un solo cigarro a EE.UU.
 * no hereda la tarifa de un envío DHL de varias cajas (~$37).
 *
 * República Dominicana usa mensajería nacional (~$5). El resto va por
 * paquetería internacional con una base justa de $15–$20 para paquetes
 * pequeños.
 */

const DHL_SHIPPING = {
  carrier: 'DHL Express',
  maxBoxesPerShipment: 10,
  originCountry: 'DO',
  originLabel: 'República Dominicana',
  warningMessage:
    'Por normativa de envíos internacionales desde República Dominicana, el máximo permitido es 10 cajas por pedido DHL. Reduce la cantidad para continuar.',
};

const LOCAL_CARRIER = 'Mensajería nacional';

const SHIPPING_ZONES = {
  DO: { name: 'República Dominicana', base: 5, perBox: 2, days: '2-4', carrier: LOCAL_CARRIER },
  MX: { name: 'México', base: 14, perBox: 5, days: '3-5' },
  US: { name: 'Estados Unidos', base: 16, perBox: 6, days: '5-8' },
  CA: { name: 'Canadá', base: 18, perBox: 7, days: '6-10' },
  EU: { name: 'Unión Europea', base: 20, perBox: 8, days: '8-14' },
  UK: { name: 'Reino Unido', base: 20, perBox: 8, days: '8-14' },
  JP: { name: 'Japón', base: 22, perBox: 8, days: '10-16' },
  CN: { name: 'China', base: 22, perBox: 8, days: '12-20' },
  HK: { name: 'Hong Kong', base: 20, perBox: 8, days: '10-16' },
  SG: { name: 'Singapur', base: 20, perBox: 8, days: '10-16' },
  AU: { name: 'Australia', base: 24, perBox: 9, days: '12-20' },
  BR: { name: 'Brasil', base: 18, perBox: 7, days: '10-18' },
  AR: { name: 'Argentina', base: 18, perBox: 7, days: '10-18' },
  CO: { name: 'Colombia', base: 15, perBox: 6, days: '7-12' },
  OTHER: { name: 'Resto del mundo', base: 20, perBox: 8, days: '14-25' },
};

/** Mapeo ISO alpha-2 → zona de envío */
const COUNTRY_TO_ZONE = {
  DO: 'DO',
  MX: 'MX',
  US: 'US',
  CA: 'CA',
  GB: 'UK',
  UK: 'UK',
  JP: 'JP',
  CN: 'CN',
  HK: 'HK',
  SG: 'SG',
  AU: 'AU',
  NZ: 'AU',
  BR: 'BR',
  AR: 'AR',
  CO: 'CO',
  DE: 'EU',
  FR: 'EU',
  ES: 'EU',
  IT: 'EU',
  PT: 'EU',
  NL: 'EU',
  BE: 'EU',
  AT: 'EU',
  IE: 'EU',
  PL: 'EU',
  SE: 'EU',
  DK: 'EU',
  FI: 'EU',
  GR: 'EU',
  CZ: 'EU',
  RO: 'EU',
  HU: 'EU',
  CH: 'EU',
};

const COUNTRIES = [
  { code: 'DO', name: 'República Dominicana' },
  { code: 'MX', name: 'México' },
  { code: 'US', name: 'Estados Unidos' },
  { code: 'CA', name: 'Canadá' },
  { code: 'GB', name: 'Reino Unido' },
  { code: 'DE', name: 'Alemania' },
  { code: 'FR', name: 'Francia' },
  { code: 'ES', name: 'España' },
  { code: 'IT', name: 'Italia' },
  { code: 'PT', name: 'Portugal' },
  { code: 'NL', name: 'Países Bajos' },
  { code: 'BE', name: 'Bélgica' },
  { code: 'CH', name: 'Suiza' },
  { code: 'JP', name: 'Japón' },
  { code: 'CN', name: 'China' },
  { code: 'HK', name: 'Hong Kong' },
  { code: 'SG', name: 'Singapur' },
  { code: 'AU', name: 'Australia' },
  { code: 'NZ', name: 'Nueva Zelanda' },
  { code: 'BR', name: 'Brasil' },
  { code: 'AR', name: 'Argentina' },
  { code: 'CO', name: 'Colombia' },
  { code: 'OTHER', name: 'Otro país' },
];

function resolveZone(countryCode) {
  if (!countryCode || countryCode === 'OTHER') return 'OTHER';
  return COUNTRY_TO_ZONE[countryCode.toUpperCase()] || 'OTHER';
}

/**
 * Valida el límite de cajas permitidas por envío DHL internacional.
 * @param {number} totalBoxes
 * @returns {{ valid: boolean, error?: string, currentBoxes: number, maxBoxes: number }}
 */
function validateDhlBoxLimit(totalBoxes) {
  const boxes = Math.max(0, Math.floor(Number(totalBoxes) || 0));
  const maxBoxes = DHL_SHIPPING.maxBoxesPerShipment;

  if (boxes > maxBoxes) {
    return {
      valid: false,
      error: DHL_SHIPPING.warningMessage,
      currentBoxes: boxes,
      maxBoxes,
    };
  }

  return { valid: true, currentBoxes: boxes, maxBoxes };
}

/**
 * @param {string} countryCode
 * @param {number} totalBoxes - bultos/cajas equivalentes del pedido
 * @param {number} [totalUnits] - puros sueltos (reserva para paquetes pequeños)
 * @returns {{ cost: number, zone: object, zoneKey: string, estimatedDays: string, carrier: string, maxBoxes: number, originCountry: string, originLabel: string, boxLimit: ReturnType<typeof validateDhlBoxLimit> }}
 */
function calculateShipping(countryCode, totalBoxes, totalUnits) {
  const boxes = Math.max(0, Math.floor(Number(totalBoxes) || 0));
  const units = Math.max(0, Math.floor(Number(totalUnits) || 0));
  const zoneKey = resolveZone(countryCode);
  const zone = SHIPPING_ZONES[zoneKey] || SHIPPING_ZONES.OTHER;

  // Un pedido vacío no cobra flete. Un puro o la primera caja pagan solo `base`.
  const billable = boxes > 0 || units > 0;
  const extraBoxes = Math.max(0, boxes - 1);
  const cost = billable ? zone.base + zone.perBox * extraBoxes : 0;
  const boxLimit = validateDhlBoxLimit(boxes);

  return {
    cost: Math.round(cost * 100) / 100,
    zone,
    zoneKey,
    estimatedDays: zone.days,
    countryCode: countryCode?.toUpperCase() || 'OTHER',
    carrier: zone.carrier || DHL_SHIPPING.carrier,
    maxBoxes: DHL_SHIPPING.maxBoxesPerShipment,
    originCountry: DHL_SHIPPING.originCountry,
    originLabel: DHL_SHIPPING.originLabel,
    boxLimit,
  };
}

/**
 * País inicial del checkout. Prioriza RD si el navegador o la zona horaria
 * indican República Dominicana. Si no hay señal, el origen de la casa (DO)
 * — no EE.UU., que cobraba $37 a todo el mundo.
 */
function detectPreferredShippingCountry() {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
    if (/Santo_Domingo/i.test(tz)) return 'DO';
  } catch (_) {
    /* Intl no disponible */
  }

  const langs = [];
  if (typeof navigator !== 'undefined') {
    if (navigator.language) langs.push(navigator.language);
    if (Array.isArray(navigator.languages)) langs.push(...navigator.languages);
  }

  for (const lang of langs) {
    const region = String(lang).split(/[-_]/)[1];
    if (region && region.toUpperCase() === 'DO') return 'DO';
  }

  for (const lang of langs) {
    const region = String(lang).split(/[-_]/)[1];
    if (!region) continue;
    const code = region.toUpperCase();
    if (code === 'UK') return 'GB';
    if (COUNTRY_TO_ZONE[code]) return code;
  }

  return DHL_SHIPPING.originCountry;
}

function getCountryList() {
  return COUNTRIES.slice();
}

function getCountryName(countryCode) {
  if (!countryCode) return '';
  const match = COUNTRIES.find((c) => c.code === countryCode.toUpperCase());
  return match ? match.name : countryCode;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    DHL_SHIPPING,
    SHIPPING_ZONES,
    COUNTRY_TO_ZONE,
    COUNTRIES,
    resolveZone,
    validateDhlBoxLimit,
    calculateShipping,
    detectPreferredShippingCountry,
    getCountryList,
    getCountryName,
  };
}

