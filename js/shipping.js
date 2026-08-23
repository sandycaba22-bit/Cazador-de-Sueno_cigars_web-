/**
 * Envío internacional vía DHL Express — tarifas por región/país (USD).
 * Pesos estimados: ~0.8 kg por caja estándar, ~0.5 kg por caja Rango.
 */

const DHL_SHIPPING = {
  carrier: 'DHL Express',
  maxBoxesPerShipment: 10,
  originCountry: 'DO',
  originLabel: 'República Dominicana',
  warningMessage:
    'Por normativa de envíos internacionales desde República Dominicana, el máximo permitido es 10 cajas por pedido DHL. Reduce la cantidad para continuar.',
};

const SHIPPING_ZONES = {
  DO: { name: 'República Dominicana', base: 12, perBox: 5, days: '2-4' },
  MX: { name: 'México', base: 18, perBox: 6, days: '3-5' },
  US: { name: 'Estados Unidos', base: 28, perBox: 9, days: '5-8' },
  CA: { name: 'Canadá', base: 32, perBox: 10, days: '6-10' },
  EU: { name: 'Unión Europea', base: 45, perBox: 14, days: '8-14' },
  UK: { name: 'Reino Unido', base: 48, perBox: 15, days: '8-14' },
  JP: { name: 'Japón', base: 52, perBox: 16, days: '10-16' },
  CN: { name: 'China', base: 55, perBox: 17, days: '12-20' },
  HK: { name: 'Hong Kong', base: 50, perBox: 15, days: '10-16' },
  SG: { name: 'Singapur', base: 48, perBox: 15, days: '10-16' },
  AU: { name: 'Australia', base: 58, perBox: 18, days: '12-20' },
  BR: { name: 'Brasil', base: 42, perBox: 13, days: '10-18' },
  AR: { name: 'Argentina', base: 40, perBox: 12, days: '10-18' },
  CO: { name: 'Colombia', base: 35, perBox: 11, days: '7-12' },
  OTHER: { name: 'Resto del mundo', base: 65, perBox: 20, days: '14-25' },
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
 * @param {number} totalBoxes - total de cajas en el pedido
 * @returns {{ cost: number, zone: object, zoneKey: string, estimatedDays: string, carrier: string, maxBoxes: number, originCountry: string, originLabel: string, boxLimit: ReturnType<typeof validateDhlBoxLimit> }}
 */
function calculateShipping(countryCode, totalBoxes) {
  const boxes = Math.max(0, Math.floor(Number(totalBoxes) || 0));
  const zoneKey = resolveZone(countryCode);
  const zone = SHIPPING_ZONES[zoneKey] || SHIPPING_ZONES.OTHER;
  const cost = zone.base + zone.perBox * boxes;
  const boxLimit = validateDhlBoxLimit(boxes);

  return {
    cost: Math.round(cost * 100) / 100,
    zone,
    zoneKey,
    estimatedDays: zone.days,
    countryCode: countryCode?.toUpperCase() || 'OTHER',
    carrier: DHL_SHIPPING.carrier,
    maxBoxes: DHL_SHIPPING.maxBoxesPerShipment,
    originCountry: DHL_SHIPPING.originCountry,
    originLabel: DHL_SHIPPING.originLabel,
    boxLimit,
  };
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
    getCountryList,
    getCountryName,
  };
}
