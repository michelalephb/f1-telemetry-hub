# F1 Telemetry Hub

Every lap of every 2026 Grand Prix, fastest laps, and two driver corner comparisons.

Data pipeline (this repo, phase 1). The web app comes next.

## Sources

| Source | Used for | Notes |
|---|---|---|
| [OpenF1](https://openf1.org) | Sessions, laps, stints, pit stops, drivers, raw car data, raw location | Free for historical sessions (2023 on), no key, 30 requests per minute. Car data and location about every 240 ms |
| [MultiViewer](https://api.multiviewer.app) via FastF1 | Corner markers | Fallback: corners found at the fastest lap's speed minima |
| [Jolpica](https://api.jolpi.ca/ergast/f1) | Event names, race and sprint results | Ergast successor, no key |

Why not FastF1 for laps and telemetry: since 15 October 2026 F1's live timing archive answers only to signed in F1 TV subscribers, so FastF1 loads nothing without an F1 TV account. OpenF1 serves the same feed for free.

All raw samples are kept exactly as received. Nothing is resampled.

## Where data lives (Supabase project `f1-telemetry-hub`)

Postgres, readable by the app with the anon key (RLS: public read, writes only with the service role):

| Table | One row per |
|---|---|
| `events` | round |
| `sessions` | session (FP1, FP2, FP3, SQ, S, Q, R) with ingest status and Parquet paths |
| `drivers` | driver in a session |
| `laps` | lap: time, sectors, tyre, stint, pit flags, accuracy, deleted |
| `results` | race and sprint classification |
| `corners` | corner in a session, with its apex distance |
| `corner_metrics` | lap through a corner: brake point, entry, minimum and exit speed, window time |
| `ingest_runs` | pipeline run log (service role only) |

Storage bucket `telemetry` (private), per session `SEASON/ROUND/CODE/`:

* `car_raw.parquet`: speed, rpm, gear, throttle, brake, DRS, untouched
* `pos_raw.parquet`: X, Y, Z, status, untouched
* `lap_distance.parquet`: distance from the timing line for every car sample, per lap (join to `car_raw` on `driver_number`, `t`)

## How distance is computed

1. **Centre line.** The fastest accurate lap (not lap 1 of a race, not in or out laps) of up to 10 drivers, aligned, median combined and smoothed. 3D, so crossover circuits (Suzuka) resolve correctly.
2. **Position to distance.** Each position sample is projected onto the centre line and unwrapped.
3. **Fusion.** Car samples get distance by integrating speed, then a per lap linear fit (scale and offset) pins that to the position distance. Speed gives the local shape, position stops drift and absorbs speed sensor scale error.
4. **Apex.** Corner markers from FastF1 are approximate, so each apex is moved to the reference lap's minimum speed within 75 m of the marker.
5. **Corner metrics.** Window from 250 m before to 150 m after the apex. Brake onset is placed midway between the last sample off and the first sample on.

Accuracy is bounded by the sample rate: at 300 km/h there are about 20 m between car samples. On synthetic laps with 0.6 m position noise and a 1 % speed sensor error, the fused distance is within 0.15 m (95th percentile) and the brake point within about 5 m. Real data will be noisier; check against video before trusting single laps, and prefer averages over many laps.

## Running

GitHub Actions does everything:

* **ingest latest** (`ingest.yml`): every 3 hours, Race, Qualifying, Sprint and Sprint Qualifying only until storage for practice is decided (about 11 MB per practice session). Syncs calendar and results, then ingests up to 6 finished sessions that are pending or failed. Sessions are picked up 1 hour after they end.
* **backfill season** (`backfill.yml`): manual. One job per finished round, one at a time (OpenF1 rate limit). About 2 minutes per session.
* **test** (`test.yml`): unit tests on every push.

Required repository secrets:

* `SUPABASE_URL`: `https://rcfguuehiojwjzodtrrj.supabase.co`
* `SUPABASE_SERVICE_ROLE_KEY`: Supabase dashboard, Project Settings, API keys. Never commit it.

Local run:

```bash
pip install -r requirements-dev.txt
python -m pytest -q tests
export SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=...
python -m pipeline calendar --season 2026
python -m pipeline round --season 2026 --round 20 --session Race
```

Schema: `supabase/migrations/`.

## Instagram (@f1telemetryhub)

`pipeline/social` turns each new session (R, Q, S, SQ) into two posts: a Reel (1080x1920 H.264, no audio) and a carousel (1080x1350 JPEG), published through the Instagram API with Instagram Login.

* **instagram** (`instagram.yml`): after every ingest run. Posts sessions ingested in the last 72 hours, one post per run (Reel first, carousel an hour later). Tuesdays in the off season: one "season rewind" qualifying Reel. Pushes to other branches dry run São Paulo (round 20) and keep the renders as a workflow artifact.
* **instagram token** (`ig_token.yml`): weekly refresh of the long lived token.
* Stories: qualifying = pole lap vs P2 (final segment laps, matched to the official times), the corner where pole gained most and where P2 hit back. Race = winner, gaps to the winner lap by lap, biggest climb from the grid.
* Guardrails: no post unless the computed gap at the line is within 50 ms of the official gap (qualifying) or the order at the flag matches the official top 3 (race). Sessions wait up to 12 runs for results, then are skipped. One post per session and kind, ever (`ig_posts` unique key). Publish failures retry 3 times.
* Storage: videos are uploaded to the public `web` bucket only while Instagram fetches them, then deleted (posted or failed). Covers and slides stay (`web/ig/...`).
* Kill switch: `social_settings.enabled` (off by default). Set it to false to stop posting at once.

Extra secrets: `IG_ACCESS_TOKEN` (long lived Instagram user token), `IG_USER_ID` (optional, looked up from the token otherwise). After the first refresh the live token is kept in `social_settings` (service role only).

## Notice

Unofficial project, not associated with Formula 1 companies. F1, FORMULA ONE, FORMULA 1, FIA FORMULA ONE WORLD CHAMPIONSHIP, GRAND PRIX and related marks are trademarks of Formula One Licensing B.V.
