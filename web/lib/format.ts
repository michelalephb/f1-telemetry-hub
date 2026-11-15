export function lapTime(ms: number | null | undefined): string {
  if (ms == null) return '—'
  const m = Math.floor(ms / 60000)
  const s = (ms % 60000) / 1000
  return m > 0 ? `${m}:${s.toFixed(3).padStart(6, '0')}` : s.toFixed(3)
}

export function secs(ms: number | null | undefined): string {
  return ms == null ? '—' : (ms / 1000).toFixed(3)
}

export function gap(ms: number | null | undefined, best: number): string {
  if (ms == null) return '—'
  return ms === best ? '' : `+${((ms - best) / 1000).toFixed(3)}`
}

export const TYRE: Record<string, { label: string; color: string }> = {
  SOFT: { label: 'S', color: '#FF3333' },
  MEDIUM: { label: 'M', color: '#FFF200' },
  HARD: { label: 'H', color: '#FFFFFF' },
  INTERMEDIATE: { label: 'I', color: '#39B54A' },
  WET: { label: 'W', color: '#00AEEF' },
}

export function teamColor(hex: string | null | undefined): string {
  if (!hex) return '#9AA3AE'
  return hex.startsWith('#') ? hex : `#${hex}`
}

/** Two traces need two colours that can be told apart: if teammates, B becomes white. */
export function pairColors(a: string, b: string): [string, string] {
  return a.toLowerCase() === b.toLowerCase() ? [a, '#F4F6F8'] : [a, b]
}

export const SESSION_LABEL: Record<string, string> = {
  FP1: 'Practice 1', FP2: 'Practice 2', FP3: 'Practice 3', SQ: 'Sprint Quali', S: 'Sprint', Q: 'Qualifying', R: 'Race',
}
