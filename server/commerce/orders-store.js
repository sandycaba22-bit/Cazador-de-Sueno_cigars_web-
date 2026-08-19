/**
 * Persistencia de pedidos.
 *
 * Dos correcciones respecto al almacén anterior:
 *
 *  1. Ubicación. Los pedidos ya no viven en <repo>/data/orders.json, que Nginx
 *     y express.static servían como fichero estático: cualquiera podía
 *     descargar el nombre, correo, teléfono y dirección de todos los clientes.
 *     Ahora el directorio se configura por entorno y en producción está fuera
 *     del webroot.
 *
 *  2. Concurrencia. El fichero único obligaba a leer-modificar-escribir todo el
 *     historial en cada pedido; dos compras simultáneas se pisaban. Ahora cada
 *     pedido es un fichero propio creado con la bandera 'wx', que falla si ya
 *     existe. Esa exclusividad la garantiza el sistema de ficheros, no nosotros.
 */

const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');
const { CheckoutError, ERROR_CODES } = require('./errors');

const SAFE_NAME = /^[A-Za-z0-9_-]{1,64}$/;

function createOrdersStore(dataDir, log) {
  const ordersDir = path.join(dataDir, 'orders');
  const idempotencyDir = path.join(dataDir, 'idempotency');

  function ensureDirs() {
    for (const dir of [dataDir, ordersDir, idempotencyDir]) {
      fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
    }
  }

  ensureDirs();

  function assertSafeName(value, label) {
    if (!SAFE_NAME.test(String(value || ''))) {
      throw new CheckoutError(ERROR_CODES.VALIDATION_FAILED, 'Referencia de pedido inválida.', {
        diagnostics: { label, value },
      });
    }
  }

  async function writeAtomic(filePath, data) {
    const tmp = `${filePath}.${process.pid}.tmp`;
    await fsp.writeFile(tmp, JSON.stringify(data, null, 2), { mode: 0o600 });
    await fsp.rename(tmp, filePath);
  }

  return {
    dataDir,

    /**
     * Crea el pedido de forma exclusiva. Si la referencia ya existe, falla:
     * es la última barrera contra un cobro duplicado.
     */
    async create(order) {
      assertSafeName(order.reference, 'reference');
      const filePath = path.join(ordersDir, `${order.reference}.json`);
      const record = { ...order, registeredAt: new Date().toISOString() };

      try {
        await fsp.writeFile(filePath, JSON.stringify(record, null, 2), {
          flag: 'wx',
          mode: 0o600,
        });
      } catch (cause) {
        if (cause.code === 'EEXIST') {
          throw new CheckoutError(
            ERROR_CODES.DUPLICATE_ORDER,
            'Este pedido ya fue registrado. Revisa tu correo antes de reintentar.',
            { httpStatus: 409, diagnostics: { reference: order.reference }, cause }
          );
        }
        log.error('orders.create.fallo_escritura', { reference: order.reference, cause });
        throw new CheckoutError(
          ERROR_CODES.ORDER_PERSIST_FAILED,
          'No pudimos guardar tu pedido. Escríbenos por WhatsApp con tu referencia.',
          { httpStatus: 500, diagnostics: { code: cause.code }, cause }
        );
      }

      return record;
    },

    /** Actualiza un pedido ya creado (por ejemplo, al confirmar el pago). */
    async update(reference, patch) {
      assertSafeName(reference, 'reference');
      const filePath = path.join(ordersDir, `${reference}.json`);
      const current = await this.get(reference);
      if (!current) return null;

      const next = { ...current, ...patch, updatedAt: new Date().toISOString() };
      await writeAtomic(filePath, next);
      return next;
    },

    async get(reference) {
      if (!SAFE_NAME.test(String(reference || ''))) return null;
      try {
        const raw = await fsp.readFile(path.join(ordersDir, `${reference}.json`), 'utf8');
        return JSON.parse(raw);
      } catch (cause) {
        if (cause.code === 'ENOENT') return null;
        log.error('orders.get.fallo_lectura', { reference, cause });
        return null;
      }
    },

    /**
     * Idempotencia de intentos de pago. Si el navegador reintenta con la misma
     * clave (doble clic, red inestable), devolvemos el resultado ya obtenido en
     * lugar de volver a cobrar.
     */
    async findAttempt(idempotencyKey) {
      if (!SAFE_NAME.test(String(idempotencyKey || ''))) return null;
      try {
        const raw = await fsp.readFile(
          path.join(idempotencyDir, `${idempotencyKey}.json`),
          'utf8'
        );
        return JSON.parse(raw);
      } catch (cause) {
        if (cause.code === 'ENOENT') return null;
        return null;
      }
    },

    async saveAttempt(idempotencyKey, result) {
      assertSafeName(idempotencyKey, 'idempotencyKey');
      await writeAtomic(path.join(idempotencyDir, `${idempotencyKey}.json`), {
        ...result,
        savedAt: new Date().toISOString(),
      });
    },

    /** Purga de claves de idempotencia caducadas. */
    async pruneAttempts(ttlSeconds) {
      const cutoff = Date.now() - ttlSeconds * 1000;
      let removed = 0;
      let entries = [];
      try {
        entries = await fsp.readdir(idempotencyDir);
      } catch {
        return 0;
      }
      for (const entry of entries) {
        const filePath = path.join(idempotencyDir, entry);
        try {
          const stat = await fsp.stat(filePath);
          if (stat.mtimeMs < cutoff) {
            await fsp.unlink(filePath);
            removed += 1;
          }
        } catch {
          /* la entrada desapareció entre readdir y stat */
        }
      }
      return removed;
    },
  };
}

module.exports = { createOrdersStore };
