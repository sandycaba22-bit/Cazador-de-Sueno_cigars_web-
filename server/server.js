/**
 * Servidor de desarrollo local.
 *
 * Sirve el sitio estático y monta la API de comercio en el mismo puerto, para
 * poder probar el checkout completo con `npm run dev` sin montar Nginx.
 *
 * EN PRODUCCIÓN ESTE FICHERO NO SE USA. Allí Nginx sirve los estáticos y hace
 * de proxy hacia cds-commerce (8788) y cds-ai-sommelier (8787). La versión
 * anterior de este archivo servía el repositorio entero con express.static, lo
 * que dejaba data/orders.json —con los datos personales de cada cliente—
 * accesible por HTTP.
 */

const http = require('http');
const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');

const { config } = require('./commerce/config');
const { createLogger } = require('./commerce/logger');
const { createCommerceApp } = require('./commerce/app');

const PORT = Number(process.env.PORT || 3000);
const ROOT = path.join(__dirname, '..');

/** Rutas que jamás deben servirse como fichero, ni siquiera en desarrollo. */
const BLOCKED = [
  /^\/server(\/|$)/,
  /^\/deploy(\/|$)/,
  /^\/data(\/|$)/,
  /^\/\.commerce-data(\/|$)/,
  /^\/node_modules(\/|$)/,
  /^\/\.git(\/|$)/,
  /\/\.env/,
  /^\/package(-lock)?\.json$/,
];

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.pdf': 'application/pdf',
};

const log = createLogger({ service: 'cds-dev', env: config.nodeEnv });
const commerce = createCommerceApp({ config, logger: log });

const AI_PORT = Number(process.env.AI_SOMMELIER_PORT || 8787);

/**
 * Reproduce el proxy que hace Nginx hacia el servicio del sommelier, para poder
 * probar el asistente del checkout en local. Si ese servicio no está levantado
 * responde 503 con JSON: el asistente lo interpreta y avisa al cliente, en vez
 * de recibir una página de error y romperse al parsearla.
 */
function proxyToSommelier(req, res) {
  const upstream = http.request(
    { host: '127.0.0.1', port: AI_PORT, path: req.url, method: req.method, headers: req.headers },
    (upstreamRes) => {
      res.writeHead(upstreamRes.statusCode || 502, upstreamRes.headers);
      upstreamRes.pipe(res);
    }
  );

  upstream.on('error', () => {
    log.warn('ai.no_disponible', { port: AI_PORT });
    res.writeHead(503, { 'Content-Type': 'application/json; charset=utf-8' }).end(
      JSON.stringify({
        error: 'El asistente no está disponible ahora mismo.',
        hint: `Arranca el sommelier: node server/ai-sommelier/server.js (puerto ${AI_PORT})`,
      })
    );
  });

  req.pipe(upstream);
}

async function serveStatic(pathname, res) {
  const relative = decodeURIComponent(pathname).replace(/^\/+/, '') || 'index.html';
  const target = path.join(ROOT, relative);

  // Barrera contra salto de directorio: el fichero resuelto debe seguir dentro
  // de la raíz del sitio.
  if (!path.resolve(target).startsWith(path.resolve(ROOT))) {
    res.writeHead(403).end('Prohibido');
    return;
  }

  let filePath = target;
  try {
    const stat = await fsp.stat(filePath);
    if (stat.isDirectory()) filePath = path.join(filePath, 'index.html');
  } catch {
    res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }).end('No encontrado');
    return;
  }

  const contentType = MIME[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
  res.writeHead(200, { 'Content-Type': contentType, 'Cache-Control': 'no-cache' });
  fs.createReadStream(filePath).pipe(res);
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url || '/', `http://${req.headers.host || 'localhost'}`);

  if (await commerce(req, res)) return;

  if (url.pathname.startsWith('/api/ai-sommelier')) {
    proxyToSommelier(req, res);
    return;
  }

  if (BLOCKED.some((pattern) => pattern.test(url.pathname))) {
    log.warn('estatico.ruta_bloqueada', { path: url.pathname });
    res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }).end('No encontrado');
    return;
  }

  // Sin comodín hacia index.html para /api/*: una ruta inexistente debe
  // responder JSON, no HTML que el frontend intentaría parsear como JSON.
  if (url.pathname.startsWith('/api/')) {
    res
      .writeHead(404, { 'Content-Type': 'application/json; charset=utf-8' })
      .end(JSON.stringify({ error: 'Recurso no encontrado.', code: 'NOT_FOUND' }));
    return;
  }

  await serveStatic(url.pathname, res);
});

server.listen(PORT, () => {
  log.info('dev.iniciado', {
    url: `http://localhost:${PORT}`,
    checkout: `http://localhost:${PORT}/checkout.html`,
    dataDir: config.dataDir,
    sandbox: config.sandbox.enabled,
  });
});
