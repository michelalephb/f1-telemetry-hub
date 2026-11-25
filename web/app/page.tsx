'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import Countdown from '@/components/Countdown'
import Flag from '@/components/Flag'
import TrackThumb from '@/components/TrackThumb'
import { Failed, Loading, useAsync } from '@/components/useAsync'
import { getEvents, getLatestSeason, getSessions } from '@/lib/api'
import { SESSION_LABEL, SHOWN_SESSIONS } from '@/lib/format'

// Dates and times in the visitor's own time zone and locale.
const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })
const wday = (iso: string) => new Date(iso).toLocaleDateString(undefined, { weekday: 'short' })
const clock = (iso: string) => new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
const RACE_DONE_H = 3  // a round counts as over this long after the race start, data or not

export default function Home() {
  const { data, error, loading } = useAsync(async () => {
    const season = await getLatestSeason()
    const [events, sessions] = await Promise.all([getEvents(season), getSessions(season)])
    return { season, events, sessions }
  }, [])
  const { season, events, sessions } = data ?? { season: null, events: [], sessions: [] }
  const shown = sessions.filter((s) => SHOWN_SESSIONS.includes(s.session_code))
  const ready = shown.filter((s) => s.status === 'ingested').length
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="text-xs uppercase tracking-widest text-mute">{season ?? ''} season</p>
        <h1 className="mt-1 font-head text-3xl font-bold sm:text-4xl">Every lap. Every corner.</h1>
        <p className="mt-2 text-sm text-mute">
          {loading ? ' ' : `${ready} sessions analysed. Open a session for the result, corner by corner telemetry and the race story.`}
        </p>
      </div>
      {error && <Failed error={error} />}
      {loading && <Loading what="the season" />}
      <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {[...events].reverse().map((e) => {
          const ss = shown.filter((s) => s.round === e.round).sort((a, b) => SHOWN_SESSIONS.indexOf(a.session_code) - SHOWN_SESSIONS.indexOf(b.session_code))
          const any = ss.some((s) => s.status === 'ingested')
          const all = sessions.filter((s) => s.round === e.round && s.start_utc)
          const first = all[0]?.start_utc ?? null            // sessions come sorted by start
          const race = all.find((s) => s.session_code === 'R')?.start_utc ?? null
          const upcoming = !any && first != null && now < Date.parse(first)
          const live = !any && !upcoming && race != null && now < Date.parse(race) + RACE_DONE_H * 3600_000
          const ahead = upcoming || live
          return (
            <li key={e.round} className={`rounded-xl border bg-card p-4 ${ahead ? 'border-cyan/40' : 'border-line'} ${any || ahead ? '' : 'opacity-60'}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  {ahead && (
                    <span className="mb-2 inline-block rounded-full border border-cyan/60 bg-cyan/10 px-2 py-0.5 font-mono text-[11px] font-bold uppercase tracking-widest text-cyan">
                      {upcoming ? 'Upcoming' : 'This weekend'}
                    </span>
                  )}
                  <span className="block font-mono text-xs text-mute">R{String(e.round).padStart(2, '0')} · {ahead ? (e.location ?? e.country) : `${e.event_date} · ${e.location ?? e.country}`}</span>
                  <h2 className="mt-1 flex items-center gap-2 font-head text-lg font-bold"><Flag country={e.country} className="h-5 shrink-0" />{e.event_name}</h2>
                </div>
                <TrackThumb season={e.season} round={e.round} className="h-16 w-20 shrink-0" />
              </div>
              {ahead && race && first && (
                <div className="mt-3 flex flex-col gap-1">
                  <p className="font-head text-xl font-bold text-ink">
                    Race {day(race)} <span className="font-mono text-sm font-normal text-mute">{clock(race)}</span>
                  </p>
                  <p className="text-xs text-mute">Weekend {day(first)} to {day(race)}, your local time</p>
                  {upcoming && <Countdown to={first} label="Weekend starts in" onDone={() => setNow(Date.now())} />}
                </div>
              )}
              <div className="mt-3 flex flex-wrap gap-2">
                {ss.map((s) =>
                  s.status === 'ingested' ? (
                    <Link key={s.session_id} href={`/session/?id=${s.session_id}`}
                      className="flex min-h-11 items-center rounded-lg border border-cyan/60 px-3 text-sm text-cyan hover:bg-cyan/10">
                      {SESSION_LABEL[s.session_code] ?? s.session_code}
                    </Link>
                  ) : (
                    <span key={s.session_id} aria-disabled="true" title={ahead ? 'Available after the session' : s.status}
                      className={`flex min-h-11 cursor-not-allowed items-center gap-2 rounded-lg border border-line px-3 text-sm text-mute ${ahead ? 'opacity-60' : ''}`}>
                      {SESSION_LABEL[s.session_code] ?? s.session_code}
                      {ahead && s.start_utc && <span className="font-mono text-[11px]">{wday(s.start_utc)}</span>}
                    </span>
                  ),
                )}
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
