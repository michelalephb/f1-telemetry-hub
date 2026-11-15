-- Public bucket for per driver trace files the website reads directly.
-- Raw samples stay in the private "telemetry" bucket.
insert into storage.buckets (id, name, public)
values ('web', 'web', true)
on conflict (id) do update set public = true;

alter table public.sessions add column if not exists trace_prefix text;  -- path in the web bucket, e.g. 2026/20/R/
