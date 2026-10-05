// Alternativa a systemd. Un solo proceso: cada vuelta lee la cola y termina el ciclo.
// pm2 start ecosystem.config.cjs
// No lances una segunda copia: los dos enviarían el mismo prospecto.

module.exports = {
  apps: [
    {
      name: "cds-b2b-outreach",
      script: "/var/www/html/server/b2b-outreach/telegram_bot.py",
      interpreter: "python3",
      args: "--vigilar",
      cwd: "/var/www/html/server/b2b-outreach",
      max_memory_restart: "80M",
      autorestart: true,
      restart_delay: 15000,
      env: {
        B2B_QUEUE_DIR: "/var/lib/cazador-de-suenos/b2b-outreach",
        B2B_POLL_SECONDS: "15",
      },
    },
  ],
};
