# F1 Telemetry Hub website

Static site (Next.js 15 export, TypeScript, Tailwind) published on GitHub Pages by `.github/workflows/pages.yml`.
All data loads live in the browser from Supabase, so new sessions appear without a rebuild.

| Page | What |
|---|---|
| `/` | Season: every round and its analysed sessions |
| `/session/?id=2026_20_R` | Fastest laps (sectors, tyres, theoretical best), pace and tyre degradation |
| `/compare/?id=2026_20_R&a=12&b=6&la=&lb=&c=4` | Two driver telemetry: delta, speed, throttle, brake, gear against distance; track map with live cursor; corner zoom |

Data access, all public by design:

* tables through the publishable key (RLS: read only)
* one trace file per driver per session from the public `web` bucket (`SEASON/ROUND/CODE/trace_<driver>.parquet`), parsed in the browser
* raw samples stay in the private `telemetry` bucket and never reach the site

Custom domain later: add it in repo Settings › Pages, then set `NEXT_PUBLIC_BASE_PATH` to an empty string in `pages.yml`.

```bash
npm ci
npm run dev                                          # http://localhost:3000
npm test                                             # unit tests
node --experimental-strip-types scripts/verify.ts 2026_20_R   # real data check, no secrets needed
```
