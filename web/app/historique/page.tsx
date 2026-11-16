'use client'

import { useEffect, useMemo, useState } from 'react'
import ShareButton from '@/components/ShareButton'
import { Failed, Loading, useAsync } from '@/components/useAsync'
import { SUPABASE_URL } from '@/lib/api'

// GP Historique: all time numbers from F1DB, tables only (no charts or illustrations, by design).
type Row = Record<string, unknown>
type Doc = { generated_at: string; source: string; data: unknown }
type Col = { key: string; label: string; num?: boolean; fmt?: (r: Row) => string }

async function load(name: string): Promise<Doc> {
  const res = await fetch(`${SUPABASE_URL}/storage/v1/object/public/web/historique/${name}.json`)
  if (!res.ok) throw new Error(`${name}: HTTP ${res.status}`)
  return res.json()
}

const pct = (k: string) => (r: Row) => (r[k] == null ? '—' : `${(r[k] as number).toFixed(1)} %`)
const span = (r: Row) => (r.from === r.to ? `${r.from}` : `${r.from} to ${r.to ?? 'now'}`)

type Section = { id: string; title: string; file: string; note: string; search?: string[]; cols: Col[]; rows?: (d: unknown) => Row[] }

const SECTIONS: Section[] = [
  {
    id: 'grid', title: 'Grid value', file: 'grid',
    note: 'What each starting position has produced in every championship race. Indianapolis 500 (1950 to 1960) excluded: separate race, 33 car grids.',
    cols: [
      { key: 'grid', label: 'Grid', num: true }, { key: 'starts', label: 'Starts', num: true }, { key: 'wins', label: 'Wins', num: true },
      { key: 'win_pct', label: 'Win %', num: true, fmt: pct('win_pct') }, { key: 'podium_pct', label: 'Podium %', num: true, fmt: pct('podium_pct') },
      { key: 'avg_finish', label: 'Avg finish', num: true }, { key: 'starts_2000', label: 'Starts since 2000', num: true },
      { key: 'win_pct_2000', label: 'Win % since 2000', num: true, fmt: pct('win_pct_2000') },
      { key: 'podium_pct_2000', label: 'Podium % since 2000', num: true, fmt: pct('podium_pct_2000') },
    ],
  },
  {
    id: 'teammates', title: 'Teammates', file: 'teammates', search: ['driver1', 'driver2', 'teams'],
    note: 'Every pairing with at least 20 races in the same team. Race: who was classified ahead (retirements count). Qualifying: who qualified ahead.',
    cols: [
      { key: 'driver1', label: 'Driver A' }, { key: 'driver2', label: 'Driver B' }, { key: 'teams', label: 'Team' },
      { key: 'from', label: 'Years', fmt: span }, { key: 'races', label: 'Races', num: true },
      { key: 'race1', label: 'Race A–B', num: true, fmt: (r) => `${r.race1}–${r.race2}` },
      { key: 'quali1', label: 'Quali A–B', num: true, fmt: (r) => `${r.quali1}–${r.quali2}` },
    ],
  },
  {
    id: 'comebacks', title: 'Comebacks', file: 'climbs', search: ['driver', 'gp', 'team'],
    note: 'Podium finishes from 12th on the grid or lower, lowest grid slot first. Indianapolis 500 excluded.',
    cols: [
      { key: 'grid', label: 'Grid', num: true }, { key: 'finish', label: 'Finish', num: true }, { key: 'driver', label: 'Driver' },
      { key: 'team', label: 'Team' }, { key: 'gp', label: 'Grand Prix' }, { key: 'year', label: 'Year', num: true },
    ],
  },
  {
    id: 'grand-slams', title: 'Grand slams', file: 'grand_slams', search: ['driver', 'gp', 'team'],
    note: 'Pole position, win, fastest lap and every lap led, in the same race.',
    rows: (d) => ((d as { races: Row[] }).races ?? []).slice().reverse(),
    cols: [
      { key: 'year', label: 'Year', num: true }, { key: 'round', label: 'Round', num: true }, { key: 'gp', label: 'Grand Prix' },
      { key: 'driver', label: 'Driver' }, { key: 'team', label: 'Team' },
    ],
  },
  {
    id: 'eras', title: 'Eras', file: 'eras',
    note: 'Race wins by decade: the three most successful teams and engine makers, share of the decade\'s races.',
    rows: (d) => (d as Row[]).slice().reverse(),
    cols: [
      { key: 'decade', label: 'Decade', fmt: (r) => `${r.decade}s` }, { key: 'races', label: 'Races', num: true },
      ...[0, 1, 2].map((i) => ({ key: `c${i}`, label: `Team ${i + 1}`, fmt: (r: Row) => { const x = (r.constructors as Row[] | null)?.[i]; return x ? `${x.name} ${x.wins} (${(x.pct as number).toFixed(1)} %)` : '—' } })),
      ...[0, 1, 2].map((i) => ({ key: `e${i}`, label: `Engine ${i + 1}`, fmt: (r: Row) => { const x = (r.engines as Row[] | null)?.[i]; return x ? `${x.name} ${x.wins} (${(x.pct as number).toFixed(1)} %)` : '—' } })),
    ],
  },
  {
    id: 'circuits', title: 'Circuits', file: 'circuits', search: ['circuit', 'place', 'country', 'top_driver', 'top_team'],
    note: 'Every circuit that has held a championship race, most recently used first.',
    cols: [
      { key: 'circuit', label: 'Circuit' }, { key: 'country', label: 'Country' }, { key: 'races', label: 'Races', num: true },
      { key: 'first', label: 'Years', fmt: (r) => `${r.first} to ${r.last}` },
      { key: 'pole_win_pct', label: 'Won from pole', num: true, fmt: pct('pole_win_pct') },
      { key: 'top_driver', label: 'Most wins: driver', fmt: (r) => `${r.top_driver} (${r.top_driver_wins})` },
      { key: 'top_team', label: 'Most wins: team', fmt: (r) => `${r.top_team} (${r.top_team_wins})` },
    ],
  },
  {
    id: 'families', title: 'Families', file: 'families', search: ['driver', 'of'],
    note: 'Drivers related to other F1 drivers. Starts, wins and titles for each.',
    cols: [
      { key: 'driver', label: 'Driver' }, { key: 'relation', label: 'Relation' }, { key: 'of', label: 'Of' },
      { key: 'starts', label: 'Starts', num: true, fmt: (r) => `${r.starts} / ${r.of_starts}` },
      { key: 'wins', label: 'Wins', num: true, fmt: (r) => `${r.wins} / ${r.of_wins}` },
      { key: 'titles', label: 'Titles', num: true, fmt: (r) => `${r.titles} / ${r.of_titles}` },
    ],
  },
  {
    id: 'lineage', title: 'Team lineage', file: 'lineage', search: ['team', 'line'],
    note: 'Teams that ran under other names, in order. Wins and titles are for the team under its current name.',
    rows: (d) => (d as Row[]).map((r) => ({ ...r, line: (r.chain as Row[]).map((c) => `${c.name} ${c.from}${c.to ? `–${c.to}` : '+'}`).join('  →  ') })),
    cols: [
      { key: 'team', label: 'Team' }, { key: 'current', label: 'Racing', fmt: (r) => (r.current ? 'yes' : 'no') },
      { key: 'line', label: 'Lineage' }, { key: 'wins', label: 'Wins', num: true }, { key: 'titles', label: 'Titles', num: true },
    ],
  },
]

export default function Page() {
  const [id, setId] = useState('grid')
  useEffect(() => {
    const read = () => { const h = window.location.hash.slice(1); if (SECTIONS.some((s) => s.id === h)) setId(h) }
    read()
    window.addEventListener('hashchange', read)
    return () => window.removeEventListener('hashchange', read)
  }, [])
  const sec = SECTIONS.find((s) => s.id === id)!
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-widest text-mute">All time · numbers only</p>
          <h1 className="mt-1 font-head text-3xl font-bold sm:text-4xl">GP Historique</h1>
        </div>
        <ShareButton title={`GP Historique: ${sec.title}`} />
      </div>
      <nav aria-label="GP Historique sections" className="flex flex-wrap gap-2">
        {SECTIONS.map((s) => (
          <a key={s.id} href={`#${s.id}`} onClick={() => setId(s.id)} aria-current={s.id === id ? 'page' : undefined}
            className={`flex min-h-11 items-center rounded-full border px-4 text-sm ${s.id === id ? 'border-cyan text-cyan' : 'border-line text-mute hover:text-ink'}`}>
            {s.title}
          </a>
        ))}
      </nav>
      <Table key={sec.id} sec={sec} />
    </div>
  )
}

function Table({ sec }: { sec: Section }) {
  const { data, error, loading } = useAsync(() => load(sec.file), [sec.file])
  const [q, setQ] = useState('')
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null)
  const rows = useMemo(() => {
    if (!data) return []
    let r = sec.rows ? sec.rows(data.data) : (data.data as Row[])
    if (q && sec.search) {
      const s = q.toLowerCase()
      r = r.filter((x) => sec.search!.some((k) => String(x[k] ?? '').toLowerCase().includes(s)))
    }
    if (sort) {
      r = [...r].sort((a, b) => {
        const va = a[sort.key], vb = b[sort.key]
        const c = typeof va === 'number' && typeof vb === 'number' ? va - vb : String(va ?? '').localeCompare(String(vb ?? ''))
        return c * sort.dir
      })
    }
    return r
  }, [data, q, sort, sec])
  if (error) return <Failed error={error} />
  if (loading || !data) return <Loading what={sec.title.toLowerCase()} />
  const flip = (key: string) => setSort((s) => (s?.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: 1 }))
  return (
    <section className="rounded-xl border border-line bg-card p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="font-head text-lg font-bold">{sec.title}</h2>
        <p className="text-xs text-mute">{sec.note}</p>
      </div>
      {sec.search && (
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter by name" aria-label={`Filter ${sec.title}`}
          className="mt-3 min-h-11 w-full max-w-sm rounded-lg border border-line bg-bg px-3 text-sm" />
      )}
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wider text-mute">
              {sec.cols.map((c) => (
                <th key={c.key} className={`px-2 py-2 font-medium ${c.num ? 'text-right' : ''}`}>
                  <button type="button" onClick={() => flip(c.key)} className="min-h-8 uppercase hover:text-ink">
                    {c.label}{sort?.key === c.key ? (sort.dir === 1 ? ' ↑' : ' ↓') : ''}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-line">
                {sec.cols.map((c) => (
                  <td key={c.key} className={`px-2 py-2 ${c.num ? 'num text-right' : ''}`}>{c.fmt ? c.fmt(r) : String(r[c.key] ?? '—')}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-mute">{rows.length} rows · {data.source} · updated {data.generated_at.slice(0, 10)}</p>
    </section>
  )
}
