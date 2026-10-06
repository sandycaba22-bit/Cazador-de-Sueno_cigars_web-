// Configuración PM2 para el servidor de producción (rutas absolutas bajo
// /var/www/html/server/b2b-outreach). Requiere .venv en esa ruta con dependencias
// instaladas. En local ejecuta el bot a mano (python telegram_bot.py); no uses
// este archivo salvo que reproduzcas las mismas rutas.
//
// pm2 start ecosystem.config.cjs
// No lances una segunda copia: los dos enviarían el mismo prospecto.

module.exports = {
  apps: [
    {
      name: "cds-b2b-outreach",
      script: "/var/www/html/server/b2b-outreach/telegram_bot.py",
      interpreter: "/var/www/html/server/b2b-outreach/.venv/bin/python",
      args: "--vigilar",
      cwd: "/var/www/html/server/b2b-outreach",
      max_memory_restart: "80M",
      autorestart: true,
      restart_delay: 15000,
      env: {
        B2B_QUEUE_DIR: "/var/www/html/server/b2b-outreach/cola",
        B2B_POLL_SECONDS: "15",
      },
    },
  ],
};
