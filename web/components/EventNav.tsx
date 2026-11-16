'use client'

import Link from 'next/link'
import { useAsync } from '@/components/useAsync'
import { getSessions } from '@/lib/api'
import { SESSION_LABEL, SHOWN_SESSIONS } from '@/lib/format'

export type Tab = 'overview' | 'corners' | 'race'

const TABS: { key: Tab; label: string; path: string }[] = [
  { key: 'overview', label: 'GP overview', path: '/session/' },
  { key: 'corners', label: 'Corner compare', path: '/compare/' },
  { key: 'race', label: 'Race story', path: '/race/' },
]
const RACES = ['R', 'S']  // the race story needs a race or a sprint race

/**
 * The three views of one Grand Prix, and the sessions of that weekend.
 * Switching tab keeps the session where the tab supports it (race story: race or sprint race).
 */
export default function EventNav({ season, round, sid, tab }: { season: number; round: number; sid: string; tab: Tab }) {
  const { data } = useAsync(() => getSessions(season), [season])
  const ss = (data ?? [])
    .filter((s) => s.round === round && s.status === 'ingested' && SHOWN_SESSIONS.includes(s.session_code))
    .sort((a, b) => SHOWN_SESSIONS.indexOf(a.session_code) - SHOWN_SESSIONS.indexOf(b.session_code))
  const code = sid.split('_').pop() ?? ''
  const raceSid = RACES.includes(code) ? sid : ss.find((s) => s.session_code === 'R')?.session_id ?? ss.find((s) => s.session_code === 'S')?.session_id
  const target = (t: Tab, id: string) => `${TABS.find((x) => x.key === t)!.path}?id=${id}`

  return (
    <nav aria-label="Grand Prix views" className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-1 rounded-xl border border-line bg-card p-1">
        {TABS.map((t) => {
          const id = t.key === 'race' ? raceSid : sid
          const on = t.key === tab
          return id ? (
            <Link key={t.key} href={target(t.key, id)} aria-current={on ? 'page' : undefined}
              className={`flex min-h-11 flex-1 items-center justify-center rounded-lg px-4 text-sm font-semibold ${on ? 'bg-cyan text-bg' : 'text-mute hover:bg-line/60 hover:text-ink'}`}>
              {t.label}
            </Link>
          ) : (
            <span key={t.key} className="flex min-h-11 flex-1 items-center justify-center rounded-lg px-4 text-sm text-mute/50" title="no race data yet">{t.label}</span>
          )
        })}
      </div>
      {ss.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {ss.map((s) => {
            const usable = tab !== 'race' || RACES.includes(s.session_code)
            const on = s.session_id === sid
            const cls = `flex min-h-11 items-center rounded-full border px-4 text-sm ${on ? 'border-cyan text-cyan' : 'border-line text-mute'}`
            return usable && !on ? (
              <Link key={s.session_id} href={target(tab, s.session_id)} className={`${cls} hover:border-cyan/60 hover:text-ink`}>
                {SESSION_LABEL[s.session_code] ?? s.session_code}
              </Link>
            ) : (
              <span key={s.session_id} aria-current={on ? 'true' : undefined} className={`${cls} ${usable ? '' : 'opacity-40'}`}>
                {SESSION_LABEL[s.session_code] ?? s.session_code}
              </span>
            )
          })}
        </div>
      )}
    </nav>
  )
}
