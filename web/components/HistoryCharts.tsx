'use client'

import type { ReactNode } from 'react'
import { Failed, Loading, useAsync } from '@/components/useAsync'

// Landing view of F1 History Analytics: six charts, each with the numbers it is drawn from right
// underneath, and a link to the full table. Everything is read from the same historique/*.json files.

type Row = Record<string, unknown>
type Doc = { generated_at: string; source: string; data: unknown }
export type Loader = (name: string) => Promise<Doc>

const INK = '#E8ECF2', MUTE = '#93A0B4', LINE = '#232D3F', BG = '#0B0E14'
const ACC = '#E8ECF2'      // data accent: ice white (the cyan is under review)
const OLD = '#5B6B85'      // secondary series
const NEUTRAL = '#8A94A6'  // teams without a current colour
const TEAM: Record<string, string> = {
  Ferrari: '#E8002D', McLaren: '#FF8000', Williams: '#64C4FF', Mercedes: '#27F4D2', 'Red Bull': '#3671C6',
  'Aston Martin': '#229971', Alpine: '#0093CC', Haas: '#B6BABD',
}
const MONO = "'JetBrains Mono', ui-monospace, monospace"

function T({ x, y, children, size = 12, fill = MUTE, anchor = 'start', weight = 400, mono = true }: {
  x: number; y: number; children: ReactNode; size?: number; fill?: string; anchor?: 'start' | 'middle' | 'end'; weight?: number; mono?: boolean
}) {
  return <text x={x} y={y} fontSize={size} fill={fill} textAnchor={anchor} fontWeight={weight} fontFamily={mono ? MONO : 'Inter, sans-serif'}>{children}</text>
}

function Svg({ h, label, children }: { h: number; label: string; children: ReactNode }) {
  return <svg viewBox={`0 0 640 ${h}`} width="100%" role="img" aria-label={label} className="block">{children}</svg>
}

function Swatch({ c, label, ring }: { c: string; label: string; ring?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: c, border: ring ? `2px solid ${OLD}` : undefined }} />{label}
    </span>
  )
}

function DataTable({ head, rows, num }: { head: string[]; rows: (string | number)[][]; num: number[] }) {
  return (
    <details open className="border-t border-line pt-2">
      <summary className="min-h-8 cursor-pointer text-xs text-mute hover:text-ink">Data ({rows.length} rows)</summary>
      <div className="mt-1 max-h-64 overflow-auto">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="text-mute">
              {head.map((h, i) => <th key={h} scope="col" className={`whitespace-nowrap px-2 py-1.5 font-medium ${num.includes(i) ? 'text-right' : 'text-left'}`}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-line">
                {r.map((c, j) => <td key={j} className={`whitespace-nowrap px-2 py-1 ${num.includes(j) ? 'num text-right' : ''}`}>{c}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}

function Card({ title, take, legend, chart, table, note, more }: {
  title: string; take: ReactNode; legend: ReactNode; chart: ReactNode; table: ReactNode; note: string; more: string
}) {
  return (
    <section className="flex min-w-0 flex-col gap-3 rounded-xl border border-line bg-card p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-head text-lg font-bold">{title}</h2>
        <span className="flex flex-wrap gap-3 font-mono text-xs text-mute">{legend}</span>
      </div>
      <p className="text-sm leading-relaxed">{take}</p>
      {chart}
      {table}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-mono text-[11px] text-mute">{note}</p>
        <a href={`#${more}`} className="flex min-h-11 items-center text-sm text-ink underline-offset-4 hover:underline">Full table →</a>
      </div>
    </section>
  )
}

const n1 = (v: unknown) => (v == null ? '—' : (v as number).toFixed(1))
const B = ({ children }: { children: ReactNode }) => <b className="num font-bold">{children}</b>

export default function HistoryCharts({ load }: { load: Loader }) {
  const { data, error, loading } = useAsync(async () => {
    const names = ['grid', 'eras', 'grand_slams', 'teammates', 'climbs', 'circuits'] as const
    const docs = await Promise.all(names.map((n) => load(n)))
    return Object.fromEntries(names.map((n, i) => [n, docs[i]])) as Record<(typeof names)[number], Doc>
  }, [])
  if (error) return <Failed error={error} />
  if (loading || !data) return <Loading what="charts" />
  const src = `${data.grid.source.split(' (')[0]} · updated ${data.grid.generated_at.slice(0, 10)}`
  return (
    <div className="grid gap-6" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 520px), 1fr))' }}>
      <GridValue rows={data.grid.data as Row[]} src={src} />
      <Eras rows={data.eras.data as Row[]} src={src} />
      <Slams d={data.grand_slams.data as { drivers: Row[] }} src={src} />
      <Teammates rows={data.teammates.data as Row[]} src={src} />
      <Comebacks rows={data.climbs.data as Row[]} src={src} />
      <PoleMatters rows={data.circuits.data as Row[]} src={src} />
    </div>
  )
}

function GridValue({ rows, src }: { rows: Row[]; src: string }) {
  const g = rows.filter((r) => (r.grid as number) <= 12)
  const W = 640, H = 290, L = 44, Bt = 30, Tp = 16, ph = H - Bt - Tp, mx = 60
  const slot = (W - 8 - L) / g.length, bw = slot * 0.34
  const p1 = g[0]
  return (
    <Card title="Grid value" more="grid" note={`${src} · Indy 500 excluded`}
      legend={<><Swatch c={OLD} label="all time" /><Swatch c={ACC} label="since 2000" /></>}
      take={<>P1 on the grid won <B>{n1(p1?.win_pct)}%</B> of all races, <B>{n1(p1?.win_pct_2000)}%</B> since 2000.</>}
      chart={
        <Svg h={H} label="Win percentage by starting grid slot, all time and since 2000">
          {[0, 20, 40, 60].map((v) => { const y = Tp + ph * (1 - v / mx); return <g key={v}><line x1={L} x2={W - 8} y1={y} y2={y} stroke={LINE} /><T x={L - 8} y={y + 4} anchor="end" size={11}>{v}%</T></g> })}
          {g.map((r, i) => {
            const x = L + i * slot + slot * 0.14
            return (
              <g key={i}>
                {[[r.win_pct, OLD], [r.win_pct_2000, ACC]].map(([v, c], j) => {
                  const h = (ph * ((v as number) ?? 0)) / mx
                  return <rect key={j} x={x + j * (bw + 2)} y={Tp + ph - h} width={bw} height={Math.max(h, 0.5)} rx={2} fill={c as string} />
                })}
                <T x={L + i * slot + slot / 2} y={H - Bt + 18} anchor="middle" size={11}>P{r.grid as number}</T>
              </g>
            )
          })}
        </Svg>
      }
      table={<DataTable head={['Grid', 'Starts', 'Win % all time', 'Win % since 2000', 'Podium %']} num={[1, 2, 3, 4]}
        rows={g.map((r) => [`P${r.grid}`, r.starts as number, `${n1(r.win_pct)}%`, `${n1(r.win_pct_2000)}%`, `${n1(r.podium_pct)}%`])} />}
    />
  )
}

function Eras({ rows, src }: { rows: Row[]; src: string }) {
  const e = rows.map((r) => ({ decade: r.decade as number, races: r.races as number, top: (r.constructors as Row[])[0] }))
  const W = 640, H = 290, L = 100, rh = (H - 24) / e.length, sc = (W - L - 120) / 50
  const now = new Date().getFullYear()
  return (
    <Card title="Eras of dominance" more="eras" note={`${src} · shared drives counted once`}
      legend={<span>top team per decade · races held</span>}
      take={<>The most successful team of each decade and its share of that decade&apos;s wins.</>}
      chart={
        <Svg h={H} label="Most successful constructor share of race wins per decade">
          {[0, 25, 50].map((v) => <g key={v}><line x1={L + v * sc} x2={L + v * sc} y1={6} y2={H - 18} stroke={LINE} /><T x={L + v * sc} y={H - 4} anchor="middle" size={11}>{v}%</T></g>)}
          {e.map((r, i) => {
            const y = 8 + i * rh, pct = r.top.pct as number, c = TEAM[r.top.name as string] ?? NEUTRAL
            return (
              <g key={r.decade}>
                <T x={8} y={y + rh * 0.55} fill={INK} weight={600}>{r.decade}s</T>
                <T x={58} y={y + rh * 0.55} size={11}>{r.races}</T>
                <rect x={L} y={y + rh * 0.18} width={pct * sc} height={rh * 0.56} rx={3} fill={c} />
                <T x={L + pct * sc + 8} y={y + rh * 0.55} fill={INK} weight={600}>{`${r.top.name} ${n1(pct)}%`}</T>
              </g>
            )
          })}
        </Svg>
      }
      table={<DataTable head={['Decade', 'Races', 'Top team', 'Wins', 'Share']} num={[1, 3, 4]}
        rows={e.slice().reverse().map((r) => [`${r.decade}s${r.decade + 9 >= now ? ' (to date)' : ''}`, r.races, r.top.name as string, r.top.wins as number, `${n1(r.top.pct)}%`])} />}
    />
  )
}

function Slams({ d, src }: { d: { drivers: Row[] }; src: string }) {
  const all = d.drivers ?? []
  const s = all.slice(0, 10)
  const total = all.reduce((a, r) => a + (r.count as number), 0)
  const max = Math.max(...s.map((r) => r.count as number), 1)
  const W = 640, H = 290, L = 150, rh = (H - 10) / s.length, step = (W - L - 40) / max
  return (
    <Card title="Grand slams" more="grand-slams" note={`${src} · includes 1 documented correction`}
      legend={<span>top 10 drivers</span>}
      take={<>Pole, win, fastest lap and every lap led. <B>{total}</B> in history; {s[0]?.driver as string} holds the record with <B>{s[0]?.count as number}</B>.</>}
      chart={
        <Svg h={H} label="Drivers with the most grand slams">
          {s.map((r, i) => {
            const y = 4 + i * rh, c = r.count as number
            return (
              <g key={r.driver as string}>
                <T x={L - 10} y={y + rh * 0.62} anchor="end" fill={INK} weight={500} mono={false}>{r.driver as string}</T>
                {Array.from({ length: c }, (_, k) => <circle key={k} cx={L + k * step + step / 2} cy={y + rh * 0.45} r={Math.min(rh * 0.34, 11)} fill={i === 0 ? ACC : OLD} />)}
                <T x={L + c * step + 4} y={y + rh * 0.62} fill={INK} weight={700}>{c}</T>
              </g>
            )
          })}
        </Svg>
      }
      table={<DataTable head={['Driver', 'Grand slams']} num={[1]} rows={all.map((r) => [r.driver as string, r.count as number])} />}
    />
  )
}

function Teammates({ rows, src }: { rows: Row[]; src: string }) {
  const last = (s: unknown) => String(s).split(' ').slice(-1)[0]
  const t = rows.slice(0, 8).map((r) => {
    const flip = (r.race2 as number) > (r.race1 as number)
    return {
      a: flip ? r.driver2 : r.driver1, b: flip ? r.driver1 : r.driver2,
      ra: (flip ? r.race2 : r.race1) as number, rb: (flip ? r.race1 : r.race2) as number,
      qa: (flip ? r.quali2 : r.quali1) as number, qb: (flip ? r.quali1 : r.quali2) as number,
      team: String(r.teams).split(', ')[0], races: r.races as number, years: r.from === r.to ? `${r.from}` : `${r.from} to ${r.to}`,
    }
  })
  const W = 640, H = 290, mid = W / 2, rh = (H - 10) / t.length
  const sc = (W / 2 - 130) / Math.max(...t.map((x) => Math.max(x.ra, x.rb)), 1)
  const top = t.reduce((m, x) => (x.ra / (x.ra + x.rb || 1) > m.ra / (m.ra + m.rb || 1) ? x : m), t[0])
  return (
    <Card title="Teammate head to head" more="teammates" note={`${src} · classified ahead, retirements count`}
      legend={<span>solid: ahead more often · light: teammate</span>}
      take={<>Race finishes ahead of the teammate, longest pairings. {top && <>{last(top.a)} beat {last(top.b)} <B>{top.ra} to {top.rb}</B>.</>}</>}
      chart={
        <Svg h={H} label="Teammate race head to head, finishes ahead">
          <line x1={mid} x2={mid} y1={2} y2={H - 4} stroke={LINE} />
          {t.map((x, i) => {
            const y = 4 + i * rh, c = TEAM[x.team] ?? NEUTRAL
            return (
              <g key={i}>
                <rect x={mid - x.ra * sc} y={y + rh * 0.2} width={x.ra * sc} height={rh * 0.56} rx={3} fill={c} />
                <rect x={mid + 2} y={y + rh * 0.2} width={x.rb * sc} height={rh * 0.56} rx={3} fill={c} fillOpacity={0.38} />
                <T x={mid - x.ra * sc - 8} y={y + rh * 0.6} anchor="end" fill={INK} weight={600}>{`${last(x.a)} ${x.ra}`}</T>
                <T x={mid + x.rb * sc + 10} y={y + rh * 0.6}>{`${x.rb} ${last(x.b)}`}</T>
              </g>
            )
          })}
        </Svg>
      }
      table={<DataTable head={['Driver', 'Teammate', 'Team', 'Years', 'Races', 'Race', 'Quali']} num={[4, 5, 6]}
        rows={t.map((x) => [x.a as string, x.b as string, x.team, x.years, x.races, `${x.ra}–${x.rb}`, `${x.qa}–${x.qb}`])} />}
    />
  )
}

function Comebacks({ rows, src }: { rows: Row[]; src: string }) {
  const c = rows.slice(0, 10)
  const startTxt = (r: Row) => (r.grid_text === 'PL' ? `PL (${r.starters})` : `P${r.start}`)
  const maxStart = Math.max(30, ...c.map((r) => r.start as number))
  const W = 640, H = 310, L = 210, rh = (H - 28) / c.length, X = (p: number) => L + ((W - L - 24) * (p - 1)) / (maxStart - 1)
  const win = c.find((r) => r.finish === 1)
  return (
    <Card title="Comebacks" more="comebacks" note={`${src} · Indy 500 and shared drives excluded · pit lane start counts as last`}
      legend={<><Swatch c={BG} label="start" ring /><Swatch c={ACC} label="finish" /></>}
      take={<>Biggest climbs to a podium, by places gained.{win && <> {String(win.driver).split(' ').slice(-1)[0]} won from <B>{startTxt(win)}</B> ({win.gp as string} {win.year as number}).</>}</>}
      chart={
        <Svg h={H} label="Biggest climbs from the start to a podium finish">
          {[1, 10, 20, 30].filter((p) => p <= maxStart).map((p) => <g key={p}><line x1={X(p)} x2={X(p)} y1={2} y2={H - 22} stroke={LINE} /><T x={X(p)} y={H - 6} anchor="middle" size={11}>P{p}</T></g>)}
          {c.map((r, i) => {
            const y = 6 + i * rh + rh / 2, s = r.start as number, f = r.finish as number
            return (
              <g key={i}>
                <T x={8} y={y + 4} fill={INK} weight={600} mono={false}>{String(r.driver).split(' ').slice(-1)[0]}</T>
                <T x={100} y={y + 4} size={10}>{`${r.year} ${String(r.gp).slice(0, 14)}`}</T>
                <line x1={X(f)} x2={X(s)} y1={y} y2={y} stroke={OLD} strokeWidth={3} />
                <circle cx={X(s)} cy={y} r={5} fill={BG} stroke={OLD} strokeWidth={2} />
                {r.grid_text === 'PL' && <T x={X(s) + 9} y={y + 4} size={10}>PL</T>}
                <circle cx={X(f)} cy={y} r={6} fill={ACC} />
              </g>
            )
          })}
        </Svg>
      }
      table={<DataTable head={['Driver', 'Grand Prix', 'Year', 'Start', 'Finish', 'Gained']} num={[2, 3, 4, 5]}
        rows={c.map((r) => [r.driver as string, r.gp as string, r.year as number, startTxt(r), `P${r.finish}`, r.gained as number])} />}
    />
  )
}

function PoleMatters({ rows, src }: { rows: Row[]; src: string }) {
  const season = Math.max(...rows.map((r) => r.last as number))
  const ci = rows.filter((r) => r.last === season).sort((a, b) => (b.races as number) - (a.races as number)).slice(0, 12)
  const hi = ci.reduce((m, r) => ((r.pole_win_pct as number) > (m.pole_win_pct as number) ? r : m), ci[0])
  const lo = ci.reduce((m, r) => ((r.pole_win_pct as number) < (m.pole_win_pct as number) ? r : m), ci[0])
  const races = ci.map((r) => r.races as number), pcts = ci.map((r) => r.pole_win_pct as number)
  const x0 = Math.floor(Math.min(...races) / 10) * 10, x1 = Math.ceil(Math.max(...races) / 10) * 10
  const y0 = Math.floor(Math.min(...pcts) / 15) * 15, y1 = Math.ceil(Math.max(...pcts) / 15) * 15
  const W = 640, H = 300, L = 48, Bt = 34
  const X = (r: number) => L + ((W - L - 20) * (r - x0)) / Math.max(x1 - x0, 1)
  const Y = (p: number) => 10 + (H - Bt - 10) * (1 - (p - y0) / Math.max(y1 - y0, 1))
  // simple label placement: right of the dot, else left, else nudged down; never over another label
  const boxes: [number, number, number, number][] = []
  const place = (x: number, y: number, w: number) => {
    for (const [dx, dy, anchor] of [[9, 4, 'start'], [-9, 4, 'end'], [9, 16, 'start'], [-9, 16, 'end'], [9, -8, 'start'], [-9, -8, 'end']] as const) {
      const bx = anchor === 'start' ? x + dx : x + dx - w, by = y + dy - 10
      if (bx < L || bx + w > W - 4) continue
      if (boxes.every(([a, b, c, d]) => bx + w < a || bx > c || by + 12 < b || by > d)) { boxes.push([bx, by, bx + w, by + 12]); return { dx, dy, anchor } }
    }
    return { dx: 9, dy: 4, anchor: 'start' as const }
  }
  const short = (s: string) => s.replace('Spa-Francorchamps', 'Spa').replace('Gilles Villeneuve', 'Montréal').replace('José Carlos Pace', 'Interlagos')
  return (
    <Card title="Does pole matter here?" more="circuits" note={`${src} · the ${ci.length} circuits on the ${season} calendar with the most races`}
      legend={<span>{`circuits on the ${season} calendar`}</span>}
      take={<>Share of races won from P1 on the grid. {short(hi.circuit as string)} <B>{n1(hi.pole_win_pct)}%</B>, {short(lo.circuit as string)} <B>{n1(lo.pole_win_pct)}%</B>.</>}
      chart={
        <Svg h={H} label="Share of races won from P1 on the grid, by circuit">
          {Array.from({ length: (y1 - y0) / 15 + 1 }, (_, i) => y0 + i * 15).map((p) => <g key={p}><line x1={L} x2={W - 20} y1={Y(p)} y2={Y(p)} stroke={LINE} /><T x={L - 8} y={Y(p) + 4} anchor="end" size={11}>{p}%</T></g>)}
          {Array.from({ length: (x1 - x0) / 10 + 1 }, (_, i) => x0 + i * 10).filter((r, i) => i % 2 === 0 || x1 - x0 <= 40).map((r) => <T key={r} x={X(r)} y={H - Bt + 18} anchor="middle" size={11}>{r}</T>)}
          <T x={(W + L) / 2} y={H - 2} anchor="middle" size={11}>races held</T>
          {ci.map((r) => { const x = X(r.races as number), y = Y(r.pole_win_pct as number); return <circle key={r.circuit as string} cx={x} cy={y} r={6} fill={r === hi || r === lo ? ACC : OLD} /> })}
          {ci.map((r) => {
            const x = X(r.races as number), y = Y(r.pole_win_pct as number), hot = r === hi || r === lo
            const label = hot ? `${short(r.circuit as string)} ${n1(r.pole_win_pct)}%` : short(r.circuit as string)
            const p = place(x, y, label.length * 6.4)
            return <T key={r.circuit as string} x={x + p.dx} y={y + p.dy} anchor={p.anchor} size={11} fill={hot ? INK : MUTE} weight={hot ? 700 : 400} mono={false}>{label}</T>
          })}
        </Svg>
      }
      table={<DataTable head={['Circuit', 'Races', 'Won from P1', 'Share']} num={[1, 2, 3]}
        rows={ci.map((r) => [short(r.circuit as string), r.races as number, Math.round(((r.races as number) * (r.pole_win_pct as number)) / 100), `${n1(r.pole_win_pct)}%`])} />}
    />
  )
}
