# @f1telemetryhub post template v01 (16 Nov 2026)

The locked template for every Instagram post. Builds on brand system v02 "Paddock Cyan".
Code: `pipeline/social/preview.py` (cards, Reel), `pipeline/social/history.py` (history Reel),
`pipeline/social/gp_facts.py` (hand checked tyre and history facts), `pipeline/social/style.py` (palette, logo).

## Principle
Every post gives the viewer data. Each card carries one hero number with its unit, one line that
explains it, and a source line. No card without a number, no number without a source.

## Every card and every frame
| Zone | Content |
|---|---|
| Top edge | Chequered band, two rows of 12 px squares, strong at both edges, gone in the middle |
| Header | Flag, "<EVENT> GP <season>" tracked caps, champagne "ROUND n", champagne hairline |
| Body | Kicker (cyan tracked caps), hero number (Inter 200) with unit (cyan caps), explainer (Inter 300) |
| Source | Muted, one line, above the footer |
| Bottom right | Faint chequered field waving up from the corner (8 percent opacity) |
| Footer | Logo (white wordmark) left, F1TELEMETRYHUB.COM centre, SWIPE → right (carousel only) |

Stories and Reels keep all text between 14 percent and 87.5 percent of the height (Instagram UI safe zone).

## F1 markers
- Tyre glyph: original artwork (rubber disc, sidewall band in the compound colour with four breaks,
  rim, compound code in the hub). Never the Pirelli logo or "P Zero" text.
- Compound colours: Soft #FF3333, Medium #FFF200, Hard #F2F4F7, Inter #39B54A, Wet #00AEEF.
- Cover: three small tyres (hard, medium, soft) above "N FACTS BEFORE LIGHTS OUT".
- Tyre card: "3 SOFTEST OF 5", the three tyres with HARD / MEDIUM / SOFT labels, Pirelli as source.
- History Reel: a soft tyre travels the timeline as the year marker; title years glow in champagne.

## Race week set (per GP)
| Post | Content |
|---|---|
| Carousel, 8 slides | Cover, Top speed, Flat out, Longest flat out run, Braking zones, Last year flashback, Tyres, Closing |
| Stories, 8 | Same cards at 1080x1920 |
| Preview Reel | Lap draws itself with live km/h, then flashes: top speed, flat out, longest run, braking zones, tyres, times |
| History Reel | Intro, one chapter per fact (year, headline, hero number, line, source), outro with times |

## Data rules
- Lap numbers come from last year's fastest race lap (OpenF1), computed in code.
- Tyre compounds and history facts live in `gp_facts.py`, each with its source URLs. A GP without
  checked entries gets no tyre card and no history Reel: nothing is guessed.
- 2026 has no DRS: never mention DRS zones.
- Captions repeat every number with its unit, list the sources, end with "f1telemetryhub.com (link in bio)".

## Adding the next GP
1. Pirelli compound selection for that GP (press.pirelli.com), into `TYRES`.
2. Five to eight history facts with sources, into `HISTORY`.
3. Dry run: `python -m pipeline.social preview --round N --dry-run --kind history` (and carousel, stories, reel).
