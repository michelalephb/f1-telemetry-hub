-- GP Historique audit fixes.
-- 1. Shared drives (1951 France, 1956 Argentina, 1957 Great Britain): F1DB lists both drivers as
--    winners, the relief driver with shared_car = true. A race and a team win are counted once;
--    each driver still keeps the win, as in the official driver records.
-- 2. Ties for most wins at a circuit list every tied driver or team instead of the most recent one.
-- create or replace keeps the existing grants (service_role only).

create or replace function public.historique_eras()
returns jsonb language sql stable security definer set search_path = '' as $$
  with w as (
    select (r.year / 10) * 10 as decade, rr.constructor_id, rr.engine_manufacturer_id
    from f1db.race_result rr join f1db.race r on r.id = rr.race_id
    where rr.position_number = 1 and not coalesce(rr.shared_car, false)
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

create or replace function public.historique_circuits()
returns jsonb language sql stable security definer set search_path = '' as $$
  with rr as (
    select r.circuit_id, r.year, rr.driver_id, rr.constructor_id, rr.position_number as p, rr.grid_position_number as g,
      coalesce(rr.shared_car, false) as shared
    from f1db.race_result rr join f1db.race r on r.id = rr.race_id
  ), base as (
    select circuit_id, count(*) filter (where p = 1 and not shared) as races, count(*) filter (where p = 1 and g = 1 and not shared) as pole_wins,
      min(year) as first_year, max(year) as last_year
    from rr group by circuit_id
  ), dw as (
    select circuit_id, driver_id, count(*) as wins, rank() over (partition by circuit_id order by count(*) desc) as rk
    from rr where p = 1 group by circuit_id, driver_id
  ), cw as (
    select circuit_id, constructor_id, count(*) as wins, rank() over (partition by circuit_id order by count(*) desc) as rk
    from rr where p = 1 and not shared group by circuit_id, constructor_id
  ), dtop as (
    select dw.circuit_id, string_agg(d.name, ' / ' order by d.name) as names, max(dw.wins) as wins
    from dw join f1db.driver d on d.id = dw.driver_id where dw.rk = 1 group by dw.circuit_id
  ), ctop as (
    select cw.circuit_id, string_agg(cn.name, ' / ' order by cn.name) as names, max(cw.wins) as wins
    from cw join f1db.constructor cn on cn.id = cw.constructor_id where cw.rk = 1 group by cw.circuit_id
  )
  select jsonb_agg(jsonb_build_object(
    'circuit', ci.name, 'place', ci.place_name, 'country', co.name, 'races', b.races, 'first', b.first_year, 'last', b.last_year,
    'pole_win_pct', round(100.0 * b.pole_wins / nullif(b.races, 0), 1),
    'top_driver', dtop.names, 'top_driver_wins', dtop.wins, 'top_team', ctop.names, 'top_team_wins', ctop.wins)
    order by b.last_year desc, b.races desc)
  from base b join f1db.circuit ci on ci.id = b.circuit_id join f1db.country co on co.id = ci.country_id
  left join dtop on dtop.circuit_id = b.circuit_id left join ctop on ctop.circuit_id = b.circuit_id
  where b.races > 0;
$$;
