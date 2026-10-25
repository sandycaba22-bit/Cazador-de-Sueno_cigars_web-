-- Tarifario y prospección B2B de Cazador de Sueño Cigars SRL.
-- Ejecutar en el SQL Editor de Supabase, o con SUPABASE_DB_URL:
--   python server/b2b-outreach/scripts/aplicar_esquema_supabase.py
--
-- La clave anónima no puede crear tablas. El bot y el API de comercio
-- escriben con SUPABASE_SERVICE_ROLE_KEY, que no sale del servidor.

create extension if not exists pgcrypto;

create table if not exists public.leads_b2b (
  id uuid primary key default gen_random_uuid(),
  place_id text unique,
  nombre text not null,
  direccion text not null default '',
  ciudad text not null default '',
  pais text not null default '',
  tipo_establecimiento text not null default '',
  telefono text not null default '',
  web text not null default '',
  contacto text not null default '',
  fuente text not null default '',
  capturado_en timestamptz not null default now()
);

create index if not exists leads_b2b_pais_idx
  on public.leads_b2b (pais, capturado_en desc);

create table if not exists public.solicitudes_precios (
  id text primary key,
  tipo text not null check (tipo in ('acceso', 'cotizacion')),
  empresa text not null,
  pais text not null default '',
  correo text not null default '',
  telefono text not null default '',
  estado text not null default 'pendiente'
    check (estado in ('pendiente', 'aprobado', 'rechazado')),
  volumen integer,
  vitolas jsonb not null default '[]'::jsonb,
  total_usd numeric(12, 2),
  tier integer,
  creado_en timestamptz not null default now(),
  actualizado_en timestamptz not null default now()
);

create index if not exists solicitudes_precios_estado_idx
  on public.solicitudes_precios (estado, creado_en desc);

alter table public.leads_b2b enable row level security;
alter table public.solicitudes_precios enable row level security;

revoke all on table public.leads_b2b from anon, authenticated;
revoke all on table public.solicitudes_precios from anon, authenticated;
grant insert on table public.solicitudes_precios to anon, authenticated;

drop policy if exists solicitudes_precios_insert_public on public.solicitudes_precios;
create policy solicitudes_precios_insert_public
  on public.solicitudes_precios
  for insert
  to anon, authenticated
  with check (
    estado = 'pendiente'
    and tipo in ('acceso', 'cotizacion')
    and char_length(empresa) between 2 and 160
    and id ~ '^[a-f0-9]{12}$'
  );

-- leads_b2b no tiene política para el navegador.
-- La clave de servicio del bot ignora RLS.
