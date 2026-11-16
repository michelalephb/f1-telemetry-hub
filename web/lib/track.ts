// Track outlines written by the pipeline (pipeline/tracks.py): tracks/<season>/<round>.json in the
// public web bucket. One per round, rotated the way F1 graphics show the layout.
import { SUPABASE_URL } from './api'

export type Outline = { w: number; h: number; pts: string; rot: number; x0: number; y0: number; k: number }

const cache = new Map<string, Promise<Outline | null>>()

/** Outline for a round, or null when it has not been built yet (never throws). */
export function getOutline(season: number, round: number): Promise<Outline | null> {
  const url = `${SUPABASE_URL}/storage/v1/object/public/web/tracks/${season}/${round}.json`
  let p = cache.get(url)
  if (!p) {
    p = fetch(url).then((r) => (r.ok ? (r.json() as Promise<Outline>) : null)).catch(() => null)
    cache.set(url, p)
  }
  return p
}

/** Rotation applied to raw trace coordinates (x, y in the trace frame). */
export function rotator(rotDeg: number) {
  const a = (rotDeg * Math.PI) / 180, c = Math.cos(a), s = Math.sin(a)
  return (x: number, y: number): [number, number] => [x * c - y * s, x * s + y * c]
}

/** Map a raw trace point (or a corner marker) onto the outline box: [u, v] with v pointing down. */
export function project(o: Outline, x: number, y: number): [number, number] {
  const [rx, ry] = rotator(o.rot)(x, y)
  return [(rx - o.x0) * o.k, (o.y0 - ry) * o.k]
}

/** Stand in outline from one lap of raw points (no rotation), used until the stored one exists. */
export function outlineFrom(xs: number[], ys: number[], width = 100, pad = 3): Outline | null {
  const p = xs.map((x, i) => [x, ys[i]] as const).filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y))
  if (p.length < 20) return null
  const step = Math.max(1, Math.floor(p.length / 200))
  const q = p.filter((_, i) => i % step === 0)
  const x0 = Math.min(...q.map((v) => v[0])), x1 = Math.max(...q.map((v) => v[0]))
  const y0 = Math.min(...q.map((v) => v[1])), y1 = Math.max(...q.map((v) => v[1]))
  const k = (width - 2 * pad) / Math.max(x1 - x0, 1e-9)
  const o: Outline = { w: width, h: (y1 - y0) * k + 2 * pad, pts: '', rot: 0, x0: x0 - pad / k, y0: y1 + pad / k, k }
  o.pts = q.map(([x, y]) => project(o, x, y).map((v) => v.toFixed(1)).join(',')).join(' ')
  return o
}
