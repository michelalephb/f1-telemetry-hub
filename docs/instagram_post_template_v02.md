# @f1telemetryhub post template v02 (16 Nov 2026)

Supersedes v01 (kept). Adds hourly posting, the race week data posts, the Start here post and the
2027 highlight covers. Look and rules of v01 unchanged: Paddock Cyan, flag and GP on every card,
chequered motif, tyre glyphs, logo and website on every card, a number, a unit and a source on every card, no DRS.

## Cadence (every Grand Prix, every season, no manual step)
- GitHub Actions cron at minute 4 of every hour runs `pipeline/social/hourly.py`.
- Race week (Monday of the qualifying week until 3 h after the race start): hourly, 7 AM to 10 PM Pacific.
- Other weeks: one story a day at 9 AM Pacific, a recap of the last GP (race, then qualifying), then teasers for the next.
- Off season or breaks longer than 2 weeks: one story a day from the season rewind (every race and qualifying, 3 slides each).
- The calendar comes from OpenF1 and Jolpica for this year and next, so 2027 starts by itself once published.
- A weekly scheduled task (Sundays) researches and checks tyre, history and race day facts for the next two GPs and merges them.
- Fixed feed slots, days counted from qualifying day (PT):

| Day | 9 AM | 12 PM | 6 PM |
|---|---|---|---|
| Q-3 | History carousel | Start here | History Reel |
| Q-2 | Race week carousel | | Braking zones |
| Q-1 | Preview Reel | | The lap in data |
| Q | Gear map | | |
| Q+1 | Race day in numbers | | |

- Every other hour: next story from the week's pool (about 33: race week stories, braking zones,
  history, Start here, lap, gears, race day), interleaved, one per hour, never twice in the same hour.
- Automatic qualifying and race posts still follow each ingest, on top of the hourly posts.

## Post types (`--kind`)
reel, carousel, stories, history, history_carousel, braking, lap, gears, raceday, starthere.

## Data rules added in v02
- Braking zones: entry speed from the straight; slowest point shown as "about", rounded to 5 km/h,
  because OpenF1 car data is about 4 samples a second. Turn numbers from MultiViewer markers.
- No average speed from integrated distance (2 percent short); use official figures or none.
- Pole vs race card: rain card only when OpenF1 shows the pole sitter on intermediates or wets;
  dry card when pole beat the race lap; otherwise no card.
- Race day facts live in `gp_facts.RACE_DAY` with sources; no entry, no card.

## Page
- Pin: Start here, The lap in data, History carousel (pin by hand in the app).
- Highlights 2027: START HERE, RACE WEEK, QUALI, RACES, TYRES, TELEMETRY, HISTORY, 2026.
  Covers: `brand.highlight_covers()`, champagne ring, cyan glyph, set by hand (the API cannot).
