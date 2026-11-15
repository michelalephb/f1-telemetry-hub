import 'server-only'
import { createClient, SupabaseClient } from '@supabase/supabase-js'
import { parquetReadObjects } from 'hyparquet'
import { compressors } from 'hyparquet-compressors'
import type { CarRow, DistRow, PosRow } from './telemetry'

// Server only. Tables are read with the publishable key (RLS: public read).
// Parquet files sit in a private bucket and are read with the secret key, never sent to the browser.

function env(name: string, ...alts: string[]): string {
  for (const n of [name, ...alts]) {
    const v = process.env[n]
    if (v) return v
  }
  throw new Error(`Missing environment variable ${name}`)
}

let _pub: SupabaseClient | null = null
let _sec: SupabaseClient | null = null
const opts = { auth: { persistSession: false, autoRefreshToken: false } }
const pub = () => (_pub ??= createClient(env('SUPABASE_URL'), env('SUPABASE_PUBLISHABLE_KEY'), opts))
const sec = () => (_sec ??= createClient(env('SUPABASE_URL'), env('SUPABASE_SECRET_KEY', 'SUPABASE_SERVICE_ROLE_KEY'), opts))

export type Session = {
  session_id: string; season: number; round: number; session_code: string; session_name: string
  start_utc: string | null; status: string; n_drivers: number | null; n_laps: number | null; track_length_m: number | null
  car_path: string | null; pos_path: string | null; dist_path: string | null
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

async function all<T>(q: PromiseLike<{ data: T[] | null; error: { message: string } | null }>): Promise<T[]> {
  const { data, error } = await q
  if (error) throw new Error(error.message)
  return data ?? []
}

export async function getEvents(season: number) {
  return all<Event>(pub().from('events').select('*').eq('season', season).order('round'))
}

export async function getSessions(season: number) {
  return all<Session>(pub().from('sessions').select('*').eq('season', season).order('start_utc'))
}

export async function getSession(sid: string) {
  const rows = await all<Session>(pub().from('sessions').select('*').eq('session_id', sid).limit(1))
  return rows[0] ?? null
}

export async function getEvent(season: number, round: number) {
  const rows = await all<Event>(pub().from('events').select('*').eq('season', season).eq('round', round).limit(1))
  return rows[0] ?? null
}

export async function getDrivers(sid: string) {
  return all<Driver>(pub().from('drivers').select('*').eq('session_id', sid))
}

export async function getLaps(sid: string) {
  // A race has ~1500 laps; PostgREST caps responses at 1000 rows, so page through.
  const out: Lap[] = []
  for (let from = 0; ; from += 1000) {
    const page = await all<Lap>(pub().from('laps').select('*').eq('session_id', sid).order('driver_number').order('lap_number').range(from, from + 999))
    out.push(...page)
    if (page.length < 1000) break
  }
  return out
}

export async function getCorners(sid: string) {
  return all<Corner>(pub().from('corners').select('*').eq('session_id', sid).order('apex_m'))
}

export async function getCornerMetrics(sid: string, laps: { driver_number: string; lap_number: number }[]) {
  const out: CornerMetric[] = []
  for (const l of laps) {
    out.push(...(await all<CornerMetric>(
      pub().from('corner_metrics').select('*').eq('session_id', sid).eq('driver_number', l.driver_number).eq('lap_number', l.lap_number),
    )))
  }
  return out
}

// ---------------------------------------------------------------- Parquet

const fileCache = new Map<string, Promise<ArrayBuffer>>() // per server instance; files are immutable per ingest

async function download(path: string): Promise<ArrayBuffer> {
  let p = fileCache.get(path)
  if (!p) {
    p = (async () => {
      const { data, error } = await sec().storage.from('telemetry').download(path)
      if (error || !data) throw new Error(`storage ${path}: ${error?.message ?? 'no data'}`)
      return data.arrayBuffer()
    })()
    fileCache.set(path, p)
    p.catch(() => fileCache.delete(path))
  }
  return p
}

const num = (v: unknown) => (typeof v === 'bigint' ? Number(v) : (v as number))

async function readRows(path: string, columns: string[]) {
  const file = await download(path)
  return parquetReadObjects({ file, compressors, columns }) as Promise<Record<string, unknown>[]>
}

// Parsed rows per (file, driver). A session file holds all drivers; parse once, keep each driver's
// slice. Bounded so a long running instance does not grow without limit.
const rowCache = new Map<string, Promise<unknown[]>>()
const MAX_ROW_ENTRIES = 120

async function perDriver<T>(path: string, columns: string[], drivers: string[], map: (r: Record<string, unknown>) => T): Promise<T[]> {
  const missing = drivers.filter((d) => !rowCache.has(`${path}#${d}`))
  if (missing.length) {
    const parsed = readRows(path, columns).then((rows) => {
      const by = new Map<string, T[]>()
      for (const r of rows) {
        const d = r.driver_number as string
        if (!by.has(d)) by.set(d, [])
        by.get(d)!.push(map(r))
      }
      return by
    })
    for (const d of missing) {
      const p = parsed.then((by) => by.get(d) ?? [])
      rowCache.set(`${path}#${d}`, p)
      p.catch(() => rowCache.delete(`${path}#${d}`))
    }
    while (rowCache.size > MAX_ROW_ENTRIES) rowCache.delete(rowCache.keys().next().value as string)
  }
  const parts = await Promise.all(drivers.map((d) => rowCache.get(`${path}#${d}`) as Promise<T[]>))
  return parts.flat()
}

export function readCar(path: string, drivers: string[]): Promise<CarRow[]> {
  return perDriver(path, ['driver_number', 't', 'speed', 'throttle', 'brake', 'gear', 'rpm', 'drs'], drivers, (r) => ({
    driver_number: r.driver_number as string, t: num(r.t), speed: num(r.speed), throttle: num(r.throttle),
    brake: num(r.brake), gear: num(r.gear), rpm: num(r.rpm), drs: num(r.drs),
  }))
}

export function readPos(path: string, drivers: string[]): Promise<PosRow[]> {
  return perDriver(path, ['driver_number', 't', 'x', 'y'], drivers, (r) => ({
    driver_number: r.driver_number as string, t: num(r.t), x: num(r.x), y: num(r.y),
  }))
}

export async function readDist(path: string, laps: { driver_number: string; lap_number: number }[]): Promise<DistRow[]> {
  const rows = await perDriver(path, ['driver_number', 'lap_number', 't', 'lap_dist_m', 'in_lap'], [...new Set(laps.map((l) => l.driver_number))], (r) => ({
    driver_number: r.driver_number as string, lap_number: num(r.lap_number), t: num(r.t), lap_dist_m: num(r.lap_dist_m), in_lap: Boolean(r.in_lap),
  }))
  const want = new Set(laps.map((l) => `${l.driver_number}/${l.lap_number}`))
  return rows.filter((r) => want.has(`${r.driver_number}/${r.lap_number}`))
}
