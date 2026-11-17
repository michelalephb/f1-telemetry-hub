-- Documented corrections to F1DB, applied on top of it in GP Historique (F1DB itself is reloaded
-- untouched twice a week). Each row names its evidence. When F1DB fixes the record upstream, the
-- correction becomes a no op: nothing is counted twice.

create table if not exists public.historique_corrections (
  id         serial primary key,
  kind       text not null check (kind in ('grand_slam')),
  race_id    integer not null,          -- f1db.race.id
  driver_id  text not null,             -- f1db.driver.id
  note       text not null,
  sources    text[] not null,
  added_on   date not null default current_date,
  unique (kind, race_id, driver_id)
);
alter table public.historique_corrections enable row level security;
revoke all on public.historique_corrections from anon, authenticated;
grant select, insert, update, delete on public.historique_corrections to service_role;
grant usage, select on sequence public.historique_corrections_id_seq to service_role;

-- 2026 Azerbaijan GP (round 15): Russell took pole, the win and fastest lap (all flagged in F1DB
-- v2026.20.0) and led every lap, but F1DB does not set grand_slam.
insert into public.historique_corrections (kind, race_id, driver_id, note, sources)
select 'grand_slam', r.id, 'george-russell',
  'Pole, win, fastest lap and every lap led. Not flagged as a grand slam in F1DB v2026.20.0.',
  array['https://en.wikipedia.org/wiki/Grand_Slam_(Formula_One)',
        'OpenF1 lap timing: Russell first across the line on laps 1 to 50; official win by 0.196 s on lap 51 (F1DB race result)']
from f1db.race r where r.year = 2026 and r.grand_prix_id = 'azerbaijan'
on conflict do nothing;

create or replace function public.historique_grand_slams()
returns jsonb language sql stable security definer set search_path = '' as $$
  with slam as (
    select rr.race_id, rr.driver_id, rr.constructor_id, null::text as note, null::text[] as sources
    from f1db.race_result rr where rr.grand_slam
    union all
    select c.race_id, c.driver_id, rr.constructor_id, c.note, c.sources
    from public.historique_corrections c
    join f1db.race_result rr on rr.race_id = c.race_id and rr.driver_id = c.driver_id
    where c.kind = 'grand_slam' and not rr.grand_slam
  )
  select jsonb_build_object(
    'races', (select jsonb_agg(jsonb_build_object('year', r.year, 'round', r.round, 'gp', gp.name, 'driver', d.name, 'team', cn.name,
                'corrected', s.note is not null, 'note', s.note, 'sources', s.sources)
                order by r.year, r.round)
              from slam s join f1db.race r on r.id = s.race_id join f1db.grand_prix gp on gp.id = r.grand_prix_id
              join f1db.driver d on d.id = s.driver_id join f1db.constructor cn on cn.id = s.constructor_id),
    'drivers', (select jsonb_agg(jsonb_build_object('driver', d.name, 'count', n) order by n desc, d.name)
                from (select driver_id, count(*) as n from slam group by driver_id) x join f1db.driver d on d.id = x.driver_id));
$$;
