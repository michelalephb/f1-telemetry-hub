-- Comebacks: podiums ranked by places gained (start minus finish), pit lane starts included.
-- A pit lane start (grid_position_text 'PL', no grid number in F1DB) counts as starting last of the
-- cars that took the start. Before this, pit lane starts were left out (Vettel Abu Dhabi 2012,
-- Hamilton Hungary 2014, Verstappen Sao Paulo 2025 and three more). Indy 500 and shared drives excluded.
-- create or replace keeps the existing grants (service_role only).

create or replace function public.historique_climbs()
returns jsonb language sql stable security definer set search_path = '' as $$
  with st as (
    select race_id, count(*) filter (where grid_position_number is not null or grid_position_text = 'PL') as starters
    from f1db.race_result group by race_id
  ), c as (
    select r.year, r.round, gp.name as gp, d.name as driver, cn.name as team,
      rr.grid_position_number as grid, rr.grid_position_text as grid_text, st.starters,
      coalesce(rr.grid_position_number, st.starters) as start, rr.position_number as finish,
      coalesce(rr.grid_position_number, st.starters) - rr.position_number as gained
    from f1db.race_result rr join f1db.race r on r.id = rr.race_id join f1db.grand_prix gp on gp.id = r.grand_prix_id
    join f1db.driver d on d.id = rr.driver_id join f1db.constructor cn on cn.id = rr.constructor_id
    join st on st.race_id = rr.race_id
    where rr.position_number <= 3 and r.grand_prix_id <> 'indianapolis' and not coalesce(rr.shared_car, false)
      and (rr.grid_position_number is not null or rr.grid_position_text = 'PL')
  )
  select jsonb_agg(to_jsonb(x) order by x.gained desc, x.finish, x.year desc)
  from (select * from c where gained >= 10 order by gained desc, finish, year desc limit 80) x;
$$;
