-- Applied 17 Nov 2026 via the Supabase connector. Reliable trigger for the Instagram posting workflow:
-- GitHub's schedule event is best effort (delayed or dropped at busy times), pg_cron is not.
create extension if not exists pg_cron;
create extension if not exists pg_net;

create or replace function public.ig_dispatch() returns bigint
language plpgsql security definer set search_path = public, extensions, net, vault as $$
declare tok text; rid bigint;
begin
  select decrypted_secret into tok from vault.decrypted_secrets where name = 'gh_dispatch_token' limit 1;
  if tok is null or tok = '' then
    return null;
  end if;
  select net.http_post(
    url := 'https://api.github.com/repos/michelalephb/f1-telemetry-hub/actions/workflows/instagram.yml/dispatches',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || tok,
      'Accept', 'application/vnd.github+json',
      'X-GitHub-Api-Version', '2022-11-28',
      'User-Agent', 'f1th-supabase-cron',
      'Content-Type', 'application/json'),
    body := jsonb_build_object('ref', 'main', 'inputs', jsonb_build_object('mode', 'hourly', 'dry_run', 'false'))
  ) into rid;
  return rid;
end $$;

revoke all on function public.ig_dispatch() from public, anon, authenticated;

select cron.schedule('ig-hourly-dispatch', '2,12,22,32,42,52 * * * *', $$select public.ig_dispatch()$$);
