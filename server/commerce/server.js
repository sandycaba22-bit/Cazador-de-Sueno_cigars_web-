/**
 * Arranque del servicio de comercio (cds-commerce).
 *
 * Escucha solo en loopback: Nginx es quien lo expone al mundo bajo
 * /api/commerce/. Así el proceso nunca queda accesible directamente aunque el
 * cortafuegos falle.
 */

const http = require('http');

const { config, collectConfigWarnings, collectProductionBlocks } = require('./config');
const { createLogger } = require('./logger');
const { createCommerceApp } = require('./app');
const { createOrdersStore } = require('./orders-store');
const { sendJson } = require('./http');

const log = createLogger({ service: 'cds-commerce', env: config.nodeEnv });

for (const warning of collectConfigWarnings(config)) {
  log.warn('config.advertencia', { detail: warning });
}

const blocks = collectProductionBlocks(config);
if (blocks.length) {
  for (const detail of blocks) log.error('config.bloqueo', { detail });
  process.exit(1);
}

const ordersStore = createOrdersStore(config.dataDir, log);
const app = createCommerceApp({ config, logger: log, store: ordersStore });

const server = http.createServer(async (req, res) => {
  const attended = await app(req, res);
  if (!attended) {
    sendJson(res, 404, { error: 'Recurso no encontrado.', code: 'NOT_FOUND' });
  }
});

server.listen(config.port, config.host, () => {
  log.info('servicio.iniciado', {
    url: `http://${config.host}:${config.port}`,
    dataDir: config.dataDir,
    corsOrigins: config.corsOrigins,
    cardnet: config.cardnet.enabled ? 'habilitada' : 'deshabilitada',
    paypal: config.paypal.enabled ? config.paypal.mode : 'inactivo',
  });
});

/** Limpieza periódica de claves de idempotencia caducadas. */
const pruneTimer = setInterval(
  () => {
    ordersStore
      .pruneAttempts(config.idempotencyTtlSeconds)
      .then((removed) => {
        if (removed > 0) log.info('idempotencia.purgada', { removed });
      })
      .catch((cause) => log.error('idempotencia.purga_fallida', { cause }));
  },
  15 * 60 * 1000
);
pruneTimer.unref();

function shutdown(signal) {
  log.info('servicio.deteniendo', { signal });
  clearInterval(pruneTimer);
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(1), 10_000).unref();
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
process.on('unhandledRejection', (cause) => log.error('promesa_no_capturada', { cause }));
process.on('uncaughtException', (cause) => {
  log.error('excepcion_no_capturada', { cause });
  shutdown('uncaughtException');
});
