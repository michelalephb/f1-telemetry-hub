-- F1 Telemetry Hub: initial schema
-- Metadata, laps and per corner metrics live in Postgres.
-- Raw car and position samples live as Parquet in the private "telemetry" storage bucket.

create table if not exists public.events (
  season        smallint    not null,
  round         smallint    not null,
  event_name    text        not null,
  country       text,
  location      text,
  circuit_id    text,
  event_date    date,
  event_format  text,
  primary key (season, round)
);

create table if not exists public.sessions (
  session_id      text primary key,               -- e.g. 2026_21_R
  season          smallint not null,
  round           smallint not null,
  session_code    text not null,                  -- FP1 FP2 FP3 SQ S Q R
  session_name    text not null,                  -- FastF1 name, e.g. "Race"
  start_utc       timestamptz,
  status          text not null default 'pending' check (status in ('pending','ingested','failed','no_data')),
  ingested_at     timestamptz,
  n_drivers       smallint,
  n_laps          integer,
  track_length_m  real,                           -- length of the computed centre line
  car_path        text,                           -- storage path of raw car data parquet
  pos_path        text,                           -- storage path of raw position data parquet
  dist_path       text,                           -- storage path of processed distance parquet
  fastf1_version  text,
  error           text,
  foreign key (season, round) references public.events (season, round) on delete cascade
);
create index if not exists sessions_season_round_idx on public.sessions (season, round);

create table if not exists public.drivers (
  session_id     text not null references public.sessions (session_id) on delete cascade,
  driver_number  text not null,
  abbreviation   text,
  full_name      text,
  team_name      text,
  team_color     text,
  primary key (session_id, driver_number)
);

create table if not exists public.laps (
  session_id        text not null references public.sessions (session_id) on delete cascade,
  driver_number     text not null,
  lap_number        smallint not null,
  lap_time_ms       integer,
  sector1_ms        integer,
  sector2_ms        integer,
  sector3_ms        integer,
  lap_start_s       double precision,               -- session time at lap start, seconds
  lap_end_s         double precision,               -- session time at lap end, seconds
  compound          text,
  tyre_life         smallint,
  stint             smallint,
  pit_in            boolean,
  pit_out           boolean,
  is_personal_best  boolean,
  is_accurate       boolean,
  deleted           boolean,
  track_status      text,
  position          smallint,
  primary key (session_id, driver_number, lap_number)
);
create index if not exists laps_fastest_idx on public.laps (session_id, lap_time_ms);

create table if not exists public.results (
  season          smallint not null,
  round           smallint not null,
  session_code    text not null check (session_code in ('R','S')),
  driver_number   text not null,
  driver_code     text,
  constructor     text,
  grid            smallint,
  position        smallint,
  position_text   text,
  points          real,
  status          text,
  laps            smallint,
  primary key (season, round, session_code, driver_number),
  foreign key (season, round) references public.events (season, round) on delete cascade
);

create table if not exists public.corners (
  session_id   text not null references public.sessions (session_id) on delete cascade,
  corner       text not null,                    -- "4", "10A"
  number       smallint not null,
  letter       text,
  x            real,
  y            real,
  angle        real,
  apex_m       real not null,                    -- distance along centre line
  primary key (session_id, corner)
);

create table if not exists public.corner_metrics (
  session_id        text not null,
  driver_number     text not null,
  lap_number        smallint not null,
  corner            text not null,
  brake_point_m     real,     -- relative to apex, negative = before apex; null if no braking
  entry_speed_kph   real,     -- max speed in the approach before braking
  min_speed_kph     real,
  min_speed_at_m    real,     -- relative to apex
  exit_speed_kph    real,     -- speed at apex + 100 m
  window_time_s     real,     -- time from apex - 250 m to apex + 150 m
  n_samples         smallint, -- car samples inside the window
  primary key (session_id, driver_number, lap_number, corner),
  foreign key (session_id, driver_number, lap_number) references public.laps (session_id, driver_number, lap_number) on delete cascade,
  foreign key (session_id, corner) references public.corners (session_id, corner) on delete cascade
);

create table if not exists public.ingest_runs (
  id           bigint generated always as identity primary key,
  started_at   timestamptz not null default now(),
  finished_at  timestamptz,
  mode         text,
  session_id   text,
  ok           boolean,
  message      text
);

-- Read access for the app (anon and signed in). Writes only via the service role, which bypasses RLS.
do $$
declare t text;
begin
  foreach t in array array['events','sessions','drivers','laps','results','corners','corner_metrics'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists "public read" on public.%I', t);
    execute format('create policy "public read" on public.%I for select to anon, authenticated using (true)', t);
  end loop;
end $$;

alter table public.ingest_runs enable row level security;  -- no policies: service role only

-- Private bucket for raw and processed Parquet files
insert into storage.buckets (id, name, public)
values ('telemetry', 'telemetry', false)
on conflict (id) do nothing;
