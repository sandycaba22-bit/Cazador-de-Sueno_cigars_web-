// NO usar junto a systemd.
// El lector de Telegram en el servidor es cds-b2b-outreach.service.
// Si PM2 y systemd leen getUpdates a la vez, se roban las actualizaciones
// y los botones dejan de responder. Si aparece en `pm2 list`:
//   pm2 delete cds-b2b-outreach && pm2 save
//
// Este archivo queda solo como referencia de las rutas viejas. No lo arranques.

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
        FUENTE_LEADS: "google",
        B2B_ZONA_BUSQUEDA: "caribe",
        OSM_SEGUNDA_PASADA: "0",
        B2B_OMITIR_MERCADO_LOCAL: "0",
      },
    },
    {
      name: "cds-b2b-buscar",
      script: "/var/www/html/server/b2b-outreach/telegram_bot.py",
      interpreter: "/var/www/html/server/b2b-outreach/.venv/bin/python",
      args: "--buscar --limite 15",
      cwd: "/var/www/html/server/b2b-outreach",
      autorestart: false,
      cron_restart: "0 13 * * *",
      env: {
        B2B_QUEUE_DIR: "/var/www/html/server/b2b-outreach/cola",
        FUENTE_LEADS: "google",
        B2B_ZONA_BUSQUEDA: "caribe",
        OSM_SEGUNDA_PASADA: "0",
        B2B_MAX_PAISES_POR_BUSCAR: "18",
        B2B_OMITIR_MERCADO_LOCAL: "0",
        B2B_RD_CIUDADES_MAX: "8",
      },
    },
  ],
};
