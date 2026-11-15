-- Official qualifying classification (Jolpica) alongside race and sprint results.
alter table public.results drop constraint if exists results_session_code_check;
alter table public.results add constraint results_session_code_check check (session_code in ('R', 'S', 'Q', 'SQ'));
alter table public.results add column if not exists q1_ms integer;
alter table public.results add column if not exists q2_ms integer;
alter table public.results add column if not exists q3_ms integer;
