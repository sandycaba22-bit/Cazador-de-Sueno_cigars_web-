/**
 * Utilidades HTTP mínimas.
 *
 * El servicio de comercio no usa framework a propósito. Es el proceso que toca
 * dinero y datos personales: cuantas menos dependencias de terceros haya en esa
 * ruta de código, menos superficie de cadena de suministro hay que auditar para
 * PCI DSS. El servicio del sommelier ya seguía este patrón.
 */

const { CheckoutError, ERROR_CODES } = require('./errors');

const MAX_BODY_BYTES = 64 * 1024;

function readJsonBody(req, limit = MAX_BODY_BYTES) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;

    req.on('data', (chunk) => {
      size += chunk.length;
      if (size > limit) {
        reject(
          new CheckoutError(ERROR_CODES.VALIDATION_FAILED, 'La petición es demasiado grande.', {
            httpStatus: 413,
          })
        );
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });

    req.on('end', () => {
      if (!chunks.length) return resolve({});
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')));
      } catch {
        reject(
          new CheckoutError(ERROR_CODES.VALIDATION_FAILED, 'La petición no es válida.', {
            httpStatus: 400,
          })
        );
      }
    });

    req.on('error', reject);
  });
}

function sendJson(res, status, payload, headers = {}) {
  if (res.writableEnded) return;
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    ...headers,
  });
  res.end(JSON.stringify(payload));
}

function sendStatus(res, status) {
  if (res.writableEnded) return;
  res.writeHead(status);
  res.end();
}

/**
 * Enrutador diminuto: coincidencia exacta o con un único parámetro final.
 * Suficiente para seis rutas, y sin sorpresas de comodines.
 */
function createRouter() {
  const routes = [];

  function add(method, pattern, handler) {
    const segments = pattern.split('/').filter(Boolean);
    routes.push({ method, segments, handler });
  }

  return {
    get: (pattern, handler) => add('GET', pattern, handler),
    post: (pattern, handler) => add('POST', pattern, handler),

    match(method, pathname) {
      const parts = pathname.split('/').filter(Boolean);

      for (const route of routes) {
        if (route.method !== method) continue;
        if (route.segments.length !== parts.length) continue;

        const params = {};
        let matched = true;

        for (let i = 0; i < route.segments.length; i += 1) {
          const segment = route.segments[i];
          if (segment.startsWith(':')) {
            params[segment.slice(1)] = decodeURIComponent(parts[i]);
          } else if (segment !== parts[i]) {
            matched = false;
            break;
          }
        }

        if (matched) return { handler: route.handler, params };
      }

      return null;
    },
  };
}

module.exports = { readJsonBody, sendJson, sendStatus, createRouter, MAX_BODY_BYTES };
