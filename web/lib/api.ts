// Browser data access. Everything here is public: tables via the publishable key (RLS allows
// read only), per driver traces from the public "web" bucket. No secret ever reaches the site.
import { createClient } from '@supabase/supabase-js'
import { parquetReadObjects } from 'hyparquet'
import { compressors } from 'hyparquet-compressors'

export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? 'https://rcfguuehiojwjzodtrrj.supabase.co'
// Publishable keys are designed to ship in web pages; access is limited by RLS.
export const SUPABASE_KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? 'sb_publishable_UBWA-8XZ_tQqXvPiETYwCQ_9jW_R1v8'

const sb = createClient(SUPABASE_URL, SUPABASE_KEY, { auth: { persistSession: false, autoRefreshToken: false } })

export type Session = {
  session_id: string; season: number; round: number; session_code: string; session_name: string
  start_utc: string | null; status: string; n_drivers: number | null; n_laps: number | null; track_length_m: number | null
  trace_prefix: string | null
}
export type Event = { season: number; round: number; event_name: string; country: string | null; location: string | null; event_date: string | null }
export type Driver = { driver_number: string; abbreviation: string | null; full_name: string | null; team_name: string | null; team_color: string | null }
export type Lap = {
  driver_number: string; lap_number: number; lap_time_ms: number | null; sector1_ms: number | null; sector2_ms: number | null; sector3_ms: number | null
  lap_start_s: number | null; lap_end_s: number | null; compound: string | null; tyre_life: number | null; stint: number | null
  pit_in: boolean; pit_out: boolean; is_accurate: boolean
}
export type Corner = { corner: string; number: number; letter: string | null; x: number | null; y: number | null; apex_m: number }
export type CornerMetric = {
  driver_number: string; lap_number: number; corner: string; brake_point_m: number | null; entry_speed_kph: number | null
  min_speed_kph: number | null; min_speed_at_m: number | null; exit_speed_kph: number | null; window_time_s: number | null
}
export type Result = {
  season: number; round: number; session_code: string; driver_number: string; driver_code: string | null; constructor: string | null
  grid: number | null; position: number | null; position_text: string | null; points: number | null; status: string | null; laps: number | null
  q1_ms: number | null; q2_ms: number | null; q3_ms: number | null
}
export type TraceRow = {
  lap_number: number; t: number; lap_dist_m: number; in_lap: boolean
  speed: number; throttle: number; brake: number; gear: number; rpm: number; drs: number; x: number; y: number
}

async function all<T>(q: PromiseLike<{ data: unknown; error: { message: string } | null }>): Promise<T[]> {
  const { data, error } = await q
  if (error) throw new Error(error.message)
  return (data as T[] | null) ?? []
}

/** Newest season with at least one analysed session (rolls over to the next year on its own). */
export async function getLatestSeason(): Promise<number> {
  const rows = await all<{ season: number }>(sb.from('sessions').select('season').eq('status', 'ingested').order('season', { ascending: false }).limit(1))
  return rows[0]?.season ?? new Date().getUTCFullYear()
}

export const getEvents = (season: number) => all<Event>(sb.from('events').select('*').eq('season', season).order('round'))
export const getSessions = (season: number) => all<Session>(sb.from('sessions').select('*').eq('season', season).order('start_utc'))
export const getDrivers = (sid: string) => all<Driver>(sb.from('drivers').select('*').eq('session_id', sid))
export const getCorners = (sid: string) => all<Corner>(sb.from('corners').select('*').eq('session_id', sid).order('apex_m'))

export async function getSession(sid: string): Promise<Session | null> {
  return (await all<Session>(sb.from('sessions').select('*').eq('session_id', sid).limit(1)))[0] ?? null
}

export async function getEvent(season: number, round: number): Promise<Event | null> {
  return (await all<Event>(sb.from('events').select('*').eq('season', season).eq('round', round).limit(1)))[0] ?? null
}

/** Official classification for a session (R, S from race results; Q from qualifying). */
export const getResults = (season: number, round: number, code: string) =>
  all<Result>(sb.from('results').select('*').eq('season', season).eq('round', round).eq('session_code', code).order('position'))

export async function getLaps(sid: string): Promise<Lap[]> {
  // A race has ~1500 laps and responses are capped at 1000 rows: page through.
  const out: Lap[] = []
  for (let from = 0; ; from += 1000) {
    const page = await all<Lap>(sb.from('laps').select('*').eq('session_id', sid).order('driver_number').order('lap_number').range(from, from + 999))
    out.push(...page)
    if (page.length < 1000) break
  }
  return out
}

export async function getCornerMetrics(sid: string, laps: { driver_number: string; lap_number: number }[]): Promise<CornerMetric[]> {
  const parts = await Promise.all(laps.map((l) =>
    all<CornerMetric>(sb.from('corner_metrics').select('*').eq('session_id', sid).eq('driver_number', l.driver_number).eq('lap_number', l.lap_number))))
  return parts.flat()
}

const traceCache = new Map<string, Promise<TraceRow[]>>()
const num = (v: unknown) => (typeof v === 'bigint' ? Number(v) : (v as number))

/** All laps of one driver in one session, from the public web bucket. */
export function getTrace(prefix: string, driver: string): Promise<TraceRow[]> {
  const url = `${SUPABASE_URL}/storage/v1/object/public/web/${prefix}trace_${driver}.parquet`
  let p = traceCache.get(url)
  if (!p) {
    p = (async () => {
      const res = await fetch(url)
      if (!res.ok) throw new Error(`trace ${driver}: HTTP ${res.status}`)
      const rows = (await parquetReadObjects({ file: await res.arrayBuffer(), compressors })) as Record<string, unknown>[]
      return rows.map((r) => ({
        lap_number: num(r.lap_number), t: num(r.t), lap_dist_m: num(r.lap_dist_m), in_lap: Boolean(r.in_lap),
        speed: num(r.speed), throttle: num(r.throttle), brake: num(r.brake), gear: num(r.gear), rpm: num(r.rpm), drs: num(r.drs),
        x: num(r.x), y: num(r.y),
      }))
    })()
    traceCache.set(url, p)
    p.catch(() => traceCache.delete(url))
  }
  return p
}

/** Bug report from the site footer. The table accepts inserts only: nobody can read it with the public key. */
export async function sendFeedback(message: string, contact: string, page: string): Promise<void> {
  const { error } = await sb.from('feedback').insert({ message, contact: contact || null, page })
  if (error) throw new Error(error.message)
}
