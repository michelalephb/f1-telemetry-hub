-- Growth measurement: per post metrics, daily profile numbers, rotation weights, and the cron jobs that collect them.
-- Already applied to project rcfguuehiojwjzodtrrj on 2026-11-17 (migration "instagram_metrics"); recorded here.

alter table ig_posts add column if not exists content text;

create table if not exists ig_metrics (
  session_id text not null,
  kind text not null,
  day date not null,
  likes int, comments int, saves int, shares int, reach int, views int,
  raw jsonb,
  fetched_at timestamptz not null default now(),
  primary key (session_id, kind, day)
);
alter table ig_metrics enable row level security;

create table if not exists ig_profile_daily (
  day date primary key,
  followers int, reach int, views int, profile_views int,
  likes int, comments int, shares int, saves int,
  raw jsonb,
  fetched_at timestamptz not null default now()
);
alter table ig_profile_daily enable row level security;

create table if not exists social_weights (
  grp text primary key,
  weight int not null default 1 check (weight between 1 and 3),
  score double precision,
  n int,
  updated_at timestamptz not null default now()
);
alter table social_weights enable row level security;

create or replace function public.ig_dispatch_mode(mode text) returns bigint
language plpgsql security definer set search_path to 'public', 'extensions', 'net', 'vault' as $function$
declare tok text; rid bigint;
begin
  select decrypted_secret into tok from vault.decrypted_secrets where name = 'gh_dispatch_token' limit 1;
  if tok is null or tok = '' then return null; end if;
  select net.http_post(
    url := 'https://api.github.com/repos/michelalephb/f1-telemetry-hub/actions/workflows/instagram.yml/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || tok, 'Accept', 'application/vnd.github+json',
      'X-GitHub-Api-Version', '2022-11-28', 'User-Agent', 'f1th-supabase-cron', 'Content-Type', 'application/json'),
    body := jsonb_build_object('ref', 'main', 'inputs', jsonb_build_object('mode', mode, 'dry_run', 'false'))
  ) into rid;
  return rid;
end $function$;
revoke all on function public.ig_dispatch_mode(text) from public, anon, authenticated;

select cron.schedule('ig-metrics', '47 5,17 * * *', $$select public.ig_dispatch_mode('metrics')$$);
select cron.schedule('ig-optimize', '37 7 * * 1', $$select public.ig_dispatch_mode('optimize')$$);
