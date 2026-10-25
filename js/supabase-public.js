/**
 * Conexión pública del portal mayorista con Supabase.
 * Solo la publishable key (anon). La clave secreta no vive en este archivo.
 * El navegador puede crear una solicitud pendiente. No puede leer la tabla
 * ni aprobarla: eso lo hace el bot con la clave de servicio, en el servidor.
 */
(function (root) {
  'use strict';

  var SUPABASE_URL = 'https://moptcgtbvsjzzuqbjfzo.supabase.co';
  var SUPABASE_PUBLISHABLE_KEY = 'sb_publishable_y2qece4Z92W2BMjxp5jigg_E3L8RHuF';
  var TABLA_SOLICITUDES = 'solicitudes_precios';
  var VITOLAS = { sultan: 1, ligero: 1, 'puro-habano': 1, exquisito: 1, emperador: 1 };

  function clip(value, max) {
    return String(value || '').trim().slice(0, max);
  }

  function solicitudId() {
    var bytes = new Uint8Array(6);
    if (root.crypto && root.crypto.getRandomValues) root.crypto.getRandomValues(bytes);
    else {
      for (var i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
    }
    var hex = '';
    for (var j = 0; j < bytes.length; j += 1) hex += bytes[j].toString(16).padStart(2, '0');
    return hex;
  }

  function filaSolicitud(body) {
    var data = body || {};
    var tipo = data.tipo === 'cotizacion' ? 'cotizacion' : 'acceso';
    var empresa = clip(data.empresa, 160);
    if (empresa.length < 2) return null;
    var correo = clip(data.correo, 180);
    if (correo && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(correo)) return null;
    var volumen = Number(data.volumen);
    var total = Number(data.totalUsd);
    var tier = Number(data.tier);
    var vitolas = Array.isArray(data.vitolas)
      ? data.vitolas.filter(function (line) {
          return line && VITOLAS[String(line.id)];
        }).slice(0, 8).map(function (line) {
          return {
            id: String(line.id),
            qty: Math.max(0, Math.min(1000000, Math.floor(Number(line.qty) || 0))),
          };
        })
      : [];
    return {
      id: solicitudId(),
      tipo: tipo,
      empresa: empresa,
      pais: clip(data.pais, 80),
      correo: correo,
      telefono: clip(data.telefono, 40),
      estado: 'pendiente',
      volumen: Number.isFinite(volumen) ? Math.max(0, Math.min(10000000, Math.floor(volumen))) : null,
      vitolas: vitolas,
      total_usd: Number.isFinite(total) ? Math.round(total * 100) / 100 : null,
      tier: Number.isFinite(tier) ? Math.max(0, Math.min(9, Math.floor(tier))) : null,
    };
  }

  function insertSolicitud(body) {
    var fila = filaSolicitud(body);
    if (!fila) return Promise.resolve({ ok: false, id: '' });
    return fetch(SUPABASE_URL + '/rest/v1/' + TABLA_SOLICITUDES, {
      method: 'POST',
      headers: {
        apikey: SUPABASE_PUBLISHABLE_KEY,
        Authorization: 'Bearer ' + SUPABASE_PUBLISHABLE_KEY,
        'Content-Type': 'application/json',
        Prefer: 'return=minimal',
      },
      body: JSON.stringify(fila),
    }).then(function (response) {
      return { ok: response.ok, id: fila.id };
    }).catch(function () {
      return { ok: false, id: fila.id };
    });
  }

  root.CDSSupabase = {
    url: SUPABASE_URL,
    tablaSolicitudes: TABLA_SOLICITUDES,
    tablaLeads: 'leads_b2b',
    insertSolicitud: insertSolicitud,
  };
})(window);
