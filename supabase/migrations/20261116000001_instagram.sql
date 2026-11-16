-- Instagram automation for @f1telemetryhub.
-- ig_posts: one row per post (session x kind x story); the unique key means a session is posted once.
-- social_settings: single row. Posting is OFF until enabled is set to true by hand.
-- Both tables are service role only (RLS on, no policies): the site never reads them, and the
-- access token in social_settings is never exposed through the publishable key.

create table if not exists public.ig_posts (
  id            bigint generated always as identity primary key,
  session_id    text not null,
  kind          text not null check (kind in ('reel', 'carousel')),
  story         text not null default 'session' check (story in ('session', 'rewind')),
  status        text not null check (status in ('queued', 'waiting', 'published', 'failed', 'skipped')),
  caption       text,
  media_paths   text[],                 -- files in the web bucket; videos are deleted once posted
  container_id  text,
  media_id      text,
  permalink     text,
  attempts      smallint not null default 0,
  error         text,
  created_at    timestamptz not null default now(),
  published_at  timestamptz,
  unique (session_id, kind, story)
);
alter table public.ig_posts enable row level security;

create table if not exists public.social_settings (
  id                smallint primary key default 1 check (id = 1),
  enabled           boolean not null default false,
  ig_user_id        text,
  access_token      text,               -- long lived token, refreshed weekly by the workflow
  token_expires_at  timestamptz,
  updated_at        timestamptz not null default now()
);
alter table public.social_settings enable row level security;
insert into public.social_settings (id) values (1) on conflict (id) do nothing;
