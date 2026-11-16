-- GP Historique: all time statistics computed from F1DB (schema f1db, CC BY 4.0).
-- Each function returns one JSON document; the pipeline writes them to the public web bucket
-- (historique/<name>.json) after every F1DB load, so the site reads static files.
-- Service role only: the public never runs these queries.

-- What a grid slot is worth: starts, wins, podiums and average finish from each grid position.
create or replace function public.historique_grid()
returns jsonb language sql stable security definer set search_path = '' as $$
  with rr as (
    select r.year, rr.grid_position_number as g, rr.position_number as p
    from f1db.race_result rr join f1db.race r on r.id = rr.race_id
    where rr.grid_position_number between 1 and 26 and r.grand_prix_id <> 'indianapolis'  -- Indy 500 1950 to 1960: separate race, 33 car grids
  ), agg as (
    select g,
      count(*) as starts, count(*) filter (where p = 1) as wins, count(*) filter (where p <= 3) as podiums,
      round(avg(p)::numeric, 1) as avg_finish,
      count(*) filter (where year >= 2000) as starts_2000,
      count(*) filter (where year >= 2000 and p = 1) as wins_2000,
      count(*) filter (where year >= 2000 and p <= 3) as podiums_2000
    from rr group by g
  )
  select jsonb_agg(jsonb_build_object(
    'grid', g, 'starts', starts, 'wins', wins, 'podiums', podiums, 'avg_finish', avg_finish,
    'win_pct', round(100.0 * wins / nullif(starts, 0), 1), 'podium_pct', round(100.0 * podiums / nullif(starts, 0), 1),
    'starts_2000', starts_2000, 'win_pct_2000', round(100.0 * wins_2000 / nullif(starts_2000, 0), 1),
    'podium_pct_2000', round(100.0 * podiums_2000 / nullif(starts_2000, 0), 1)) order by g)
  from agg;
$$;

-- Teammate head to heads: same car, same race. Race: who finished ahead (classification order,
-- retirements included). Qualifying: who qualified ahead. Pairs with at least 20 races together.
create or replace function public.historique_teammates()
returns jsonb language sql stable security definer set search_path = '' as $$
  with rr as (
    select race_id, constructor_id, driver_id, position_display_order as o from f1db.race_result
  ), q as (
    select race_id, driver_id, position_display_order as o from f1db.qualifying_result
  ), pairs as (
    select a.driver_id as d1, b.driver_id as d2, a.constructor_id as c, a.race_id,
      (a.o < b.o) as r1, (qa.o < qb.o) as q1, (qa.o is not null and qb.o is not null) as qboth
    from rr a join rr b on b.race_id = a.race_id and b.constructor_id = a.constructor_id and a.driver_id < b.driver_id
    left join q qa on qa.race_id = a.race_id and qa.driver_id = a.driver_id
    left join q qb on qb.race_id = b.race_id and qb.driver_id = b.driver_id
  ), agg as (
    select d1, d2, count(distinct race_id) as races,
      count(*) filter (where r1) as race1, count(*) filter (where not r1) as race2,
      count(*) filter (where qboth and q1) as quali1, count(*) filter (where qboth and not q1) as quali2,
      min(r.year) as y0, max(r.year) as y1,
      string_agg(distinct cn.name, ', ') as teams
    from pairs p join f1db.race r on r.id = p.race_id join f1db.constructor cn on cn.id = p.c
    group by d1, d2 having count(distinct race_id) >= 20
  )
  select jsonb_agg(jsonb_build_object(
    'driver1', da.name, 'driver2', db.name, 'teams', teams, 'from', y0, 'to', y1, 'races', races,
    'race1', race1, 'race2', race2, 'quali1', quali1, 'quali2', quali2) order by races desc, da.name)
  from agg join f1db.driver da on da.id = d1 join f1db.driver db on db.id = d2;
$$;

-- Team family trees: every constructor that has a recorded lineage, in order.
create or replace function public.historique_lineage()
returns jsonb language sql stable security definer set search_path = '' as $$
  with steps as (
    select cc.constructor_id, cc.position_display_order, o.name, cc.year_from, cc.year_to
    from f1db.constructor_chronology cc join f1db.constructor o on o.id = cc.other_constructor_id
  ), teams as (
    select s.constructor_id, c.name, c.total_race_wins as wins, c.total_championship_wins as titles,
      max(coalesce(s.year_to, 9999)) as last_year,
      jsonb_agg(jsonb_build_object('name', s.name, 'from', s.year_from, 'to', s.year_to) order by s.position_display_order) as chain
    from steps s join f1db.constructor c on c.id = s.constructor_id
    group by s.constructor_id, c.name, c.total_race_wins, c.total_championship_wins
  )
  select jsonb_agg(jsonb_build_object('team', name, 'current', last_year = 9999, 'wins', wins, 'titles', titles, 'chain', chain)
    order by (last_year = 9999) desc, wins desc, name)
  from teams;
$$;

-- Racing families: every recorded family relationship between F1 drivers, each pair once.
create or replace function public.historique_families()
returns jsonb language sql stable security definer set search_path = '' as $$
  with rel as (
    select f.driver_id, f.other_driver_id, f.type from f1db.driver_family_relationship f
    where f.type not in ('CHILD', 'GRANDCHILD', 'SIBLINGS_CHILD', 'SIBLINGS_GRANDCHILD', 'CHILD_IN_LAW', 'SIBLINGS_CHILD_IN_LAW')
       or not exists (select 1 from f1db.driver_family_relationship g where g.driver_id = f.other_driver_id and g.other_driver_id = f.driver_id
                      and g.type not in ('CHILD', 'GRANDCHILD', 'SIBLINGS_CHILD', 'SIBLINGS_GRANDCHILD', 'CHILD_IN_LAW', 'SIBLINGS_CHILD_IN_LAW'))
  ), dedup as (
    select distinct on (least(driver_id, other_driver_id), greatest(driver_id, other_driver_id)) driver_id, other_driver_id, type
    from rel order by least(driver_id, other_driver_id), greatest(driver_id, other_driver_id), type
  )
  -- F1DB: type describes other_driver_id relative to driver_id ("PARENT" = the other driver is the parent).
  select jsonb_agg(jsonb_build_object(
    'driver', b.name, 'relation', case type
        when 'PARENT' then 'parent of' when 'SIBLING' then 'sibling of' when 'HALF_SIBLING' then 'half sibling of'
        when 'GRANDPARENT' then 'grandparent of' when 'PARENTS_SIBLING' then 'uncle or aunt of'
        when 'GRANDPARENTS_SIBLING' then 'great uncle or aunt of' when 'PARENTS_SIBLINGS_CHILD' then 'cousin of'
        when 'PARENT_IN_LAW' then 'parent in law of' when 'SIBLING_IN_LAW' then 'sibling in law of'
        when 'CHILD' then 'child of' when 'GRANDCHILD' then 'grandchild of' when 'SIBLINGS_CHILD' then 'nephew or niece of'
        when 'SIBLINGS_GRANDCHILD' then 'great nephew or niece of' when 'CHILD_IN_LAW' then 'child in law of'
        when 'SIBLINGS_CHILD_IN_LAW' then 'nephew or niece in law of'
        else lower(replace(type, '_', ' ')) || ' of' end,
    'of', a.name,
    'starts', b.total_race_starts, 'wins', b.total_race_wins, 'titles', b.total_championship_wins,
    'of_starts', a.total_race_starts, 'of_wins', a.total_race_wins, 'of_titles', a.total_championship_wins)
    order by (a.total_race_wins + b.total_race_wins) desc, b.name)
  from dedup d join f1db.driver a on a.id = d.driver_id join f1db.driver b on b.id = d.other_driver_id;
$$;

-- Eras of dominance: race wins by decade, top 3 constructors and top 3 engine makers.
create or replace function public.historique_eras()
returns jsonb language sql stable security definer set search_path = '' as $$
  with w as (
    select (r.year / 10) * 10 as decade, rr.constructor_id, rr.engine_manufacturer_id
    from f1db.race_result rr join f1db.race r on r.id = rr.race_id where rr.position_number = 1
  ), tot as (select decade, count(*) as races from w group by decade),
  c as (
    select decade, cn.name, count(*) as wins, row_number() over (partition by decade order by count(*) desc, cn.name) as rk
    from w join f1db.constructor cn on cn.id = w.constructor_id group by decade, cn.name
  ), e as (
    select decade, em.name, count(*) as wins, row_number() over (partition by decade order by count(*) desc, em.name) as rk
    from w join f1db.engine_manufacturer em on em.id = w.engine_manufacturer_id group by decade, em.name
  )
  select jsonb_agg(jsonb_build_object(
    'decade', t.decade, 'races', t.races,
    'constructors', (select jsonb_agg(jsonb_build_object('name', name, 'wins', wins, 'pct', round(100.0 * wins / t.races, 1)) order by rk) from c where c.decade = t.decade and rk <= 3),
    'engines', (select jsonb_agg(jsonb_build_object('name', name, 'wins', wins, 'pct', round(100.0 * wins / t.races, 1)) order by rk) from e where e.decade = t.decade and rk <= 3))
    order by t.decade)
  from tot t;
$$;

-- Grand slams: pole, win, fastest lap and every lap led.
create or replace function public.historique_grand_slams()
returns jsonb language sql stable security definer set search_path = '' as $$
  select jsonb_build_object(
    'races', (select jsonb_agg(jsonb_build_object('year', r.year, 'round', r.round, 'gp', gp.name, 'driver', d.name, 'team', cn.name)
                order by r.year, r.round)
              from f1db.race_result rr join f1db.race r on r.id = rr.race_id join f1db.grand_prix gp on gp.id = r.grand_prix_id
              join f1db.driver d on d.id = rr.driver_id join f1db.constructor cn on cn.id = rr.constructor_id
              where rr.grand_slam),
    'drivers', (select jsonb_agg(jsonb_build_object('driver', name, 'count', total_grand_slams) order by total_grand_slams desc, name)
                from f1db.driver where total_grand_slams > 0));
$$;

-- Biggest climbs to the podium: lowest starting positions that still finished in the top 3.
create or replace function public.historique_climbs()
returns jsonb language sql stable security definer set search_path = '' as $$
  select jsonb_agg(x order by (x->>'grid')::int desc, (x->>'year')::int desc)
  from (
    select jsonb_build_object('year', r.year, 'round', r.round, 'gp', gp.name, 'driver', d.name, 'team', cn.name,
      'grid', rr.grid_position_number, 'finish', rr.position_number) as x
    from f1db.race_result rr join f1db.race r on r.id = rr.race_id join f1db.grand_prix gp on gp.id = r.grand_prix_id
    join f1db.driver d on d.id = rr.driver_id join f1db.constructor cn on cn.id = rr.constructor_id
    where rr.position_number <= 3 and rr.grid_position_number >= 12 and r.grand_prix_id <> 'indianapolis'
    order by rr.grid_position_number desc, r.year desc limit 60
  ) s;
$$;

-- Circuits: races held, how often pole wins, the most successful driver and team.
create or replace function public.historique_circuits()
returns jsonb language sql stable security definer set search_path = '' as $$
  with rr as (
    select r.circuit_id, r.year, rr.driver_id, rr.constructor_id, rr.position_number as p, rr.grid_position_number as g
    from f1db.race_result rr join f1db.race r on r.id = rr.race_id
  ), base as (
    select circuit_id, count(*) filter (where p = 1) as races, count(*) filter (where p = 1 and g = 1) as pole_wins,
      min(year) as first_year, max(year) as last_year
    from rr group by circuit_id
  ), dw as (
    select circuit_id, driver_id, count(*) as wins, row_number() over (partition by circuit_id order by count(*) desc, max(year) desc) as rk
    from rr where p = 1 group by circuit_id, driver_id
  ), cw as (
    select circuit_id, constructor_id, count(*) as wins, row_number() over (partition by circuit_id order by count(*) desc, max(year) desc) as rk
    from rr where p = 1 group by circuit_id, constructor_id
  )
  select jsonb_agg(jsonb_build_object(
    'circuit', ci.name, 'place', ci.place_name, 'country', co.name, 'races', b.races, 'first', b.first_year, 'last', b.last_year,
    'pole_win_pct', round(100.0 * b.pole_wins / nullif(b.races, 0), 1),
    'top_driver', d.name, 'top_driver_wins', dw.wins, 'top_team', cn.name, 'top_team_wins', cw.wins)
    order by b.last_year desc, b.races desc)
  from base b join f1db.circuit ci on ci.id = b.circuit_id join f1db.country co on co.id = ci.country_id
  left join dw on dw.circuit_id = b.circuit_id and dw.rk = 1 left join f1db.driver d on d.id = dw.driver_id
  left join cw on cw.circuit_id = b.circuit_id and cw.rk = 1 left join f1db.constructor cn on cn.id = cw.constructor_id
  where b.races > 0;
$$;

-- Which F1DB release the statistics come from.
create or replace function public.historique_source()
returns jsonb language sql stable security definer set search_path = '' as $$
  select to_jsonb(m) - 'id' from f1db._meta m where id = 1;
$$;

do $$ declare f text; begin
  foreach f in array array['historique_source','historique_grid','historique_teammates','historique_lineage','historique_families',
                           'historique_eras','historique_grand_slams','historique_climbs','historique_circuits'] loop
    execute format('revoke all on function public.%I() from public, anon, authenticated', f);
    execute format('grant execute on function public.%I() to service_role', f);
  end loop;
end $$;
