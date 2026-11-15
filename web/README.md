# F1 Telemetry Hub web app (test build)

Next.js 15 (App Router, TypeScript, Tailwind). Reads the data the pipeline writes to Supabase.

| Route | What |
|---|---|
| `/` | Season: every round and its analysed sessions |
| `/s/[sessionId]` | Fastest laps (sectors, tyres, theoretical best), pace and tyre degradation chart |
| `/s/[sessionId]/compare?a=&b=&la=&lb=&c=` | Two driver telemetry: delta, speed, throttle, brake, gear against distance, track map with live cursor, corner zoom with brake point, minimum, entry and exit speed |

Data access is server side only:

* tables with the publishable key (RLS allows public read)
* Parquet in the private `telemetry` bucket with the secret key, cached per server instance

## Environment

| Variable | Value |
|---|---|
| `SUPABASE_URL` | `https://rcfguuehiojwjzodtrrj.supabase.co` |
| `SUPABASE_PUBLISHABLE_KEY` | `sb_publishable_...` (Supabase › Project Settings › API Keys) |
| `SUPABASE_SECRET_KEY` | `sb_secret_...` (same page). Never prefix with `NEXT_PUBLIC_`. |

## Run

```bash
npm ci
cp .env.example .env.local   # fill the keys
npm run dev
npm test                     # unit tests
node --experimental-strip-types --conditions=react-server scripts/verify.ts 2026_20_R   # real data check
```

Deploy on Vercel with Root Directory `web`.
