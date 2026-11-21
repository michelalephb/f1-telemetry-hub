"""Always on Instagram cadence, for every Grand Prix of every season (rolls into the next season by
itself). The workflow runs this at minute 4 of every hour.

Race week (Monday of the week of qualifying until 3 h after the race start): one post per hour,
7 AM to 10 PM Pacific. Fixed feed slots (counted in days from qualifying day) take their hour;
every other hour posts the next story from that GP's pool.

Every other week: one post a day at 9 AM Pacific: a story recapping the last Grand Prix (race,
then qualifying, from our own data), then teasers for the next one.

Every hour and every day has its own session id, so a rerun never posts twice. The automatic
qualifying and race posts still follow each ingest, on top of this. Hand checked facts (tyres,
history, race day) come from gp_facts.py; a GP without them still gets the data posts.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from PIL import Image

log = logging.getLogger(__name__)

TZ = ZoneInfo("America/Los_Angeles")
# Michel, 20 Nov 2026: through the end of the weekend, stories are only about this GP and this year: the
# sessions (reports, timing data), its news and its forecast. Nothing from other years or the season.
GP_ONLY = {"LAS VEGAS": (2026, datetime(2026, 11, 23, tzinfo=ZoneInfo("America/Los_Angeles")))}
GP_ONLY_GROUPS = {"session", "live", "news", "rain"}
# Michel, 20 Nov (growth plan approved): Reels reach about 35x more accounts than stories (avg 771 vs 21 over
# 28 days), so every race week now runs about 4 data stories a day; the effort goes into Reels. A data story
# goes out only at these hours; session reports from the news still go out in any hour (first in line).
STORY_HOURS = {8, 11, 14, 20}
GP_ONLY_STORY_HOURS = STORY_HOURS                 # kept for older imports
UTC = ZoneInfo("UTC")
WINDOW = range(7, 23)            # race week: 7 AM to 10 PM PT, 16 posts a day
DAILY_HOUR = 9                   # other weeks: one post at 9 AM PT (6 PM in central Europe)
RACE_OVER_H = 3                  # race week ends 3 h after the race start

# day offset from qualifying day -> {PT hour: preview kind}
SLOTS = {
    -3: {9: "history_carousel", 12: "starthere", 18: "history"},
    -2: {9: "titlemath", 18: "strategy"},       # 17 Nov: championship math and the strategy file (no duplicates)
    # 18 Nov, no replicas: the Preview Reel, Lap in data and Gear map repeated Tuesday's stories; new Reels instead
    # 20 Nov growth plan: braking and pedal Reels lead (top reach); braker_z2 moved to day -2 in REEL_SLOTS,
    # FP2 braking and FP3 pedal take these slots (live data; a fallback Reel runs when it is not in)
    -1: {9: "reeltel:pedal_wet", 18: "reeltel:braker_fp2"},
    0: {9: "reeltel:pedal_fp3"},
    1: {9: "raceday"},
}


# ---------------------------------------------------------------- calendar

def calendar(oc, season: int) -> pd.DataFrame:
    """Qualifying and race start of every round of a season (empty when not published yet)."""
    from ..__main__ import schedule
    try:
        rows = schedule(oc, season)
    except Exception as e:
        log.warning("no %s calendar: %s", season, e)
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["start"] = pd.to_datetime(df["start_utc"], utc=True)
    out = []
    for rnd, g in df.groupby("round"):
        q = g[g["session_code"] == "Q"]["start"]
        r = g[g["session_code"] == "R"]["start"]
        if len(r):
            out.append({"season": season, "round": int(rnd),
                        "q": q.iloc[0] if len(q) else r.iloc[0] - pd.Timedelta(days=1), "r": r.iloc[0]})
    return pd.DataFrame(out).sort_values("r").reset_index(drop=True) if out else pd.DataFrame()


def where_are_we(oc, now: datetime, cals: list | None = None) -> dict | None:
    """The next Grand Prix (this season, else next season), whether `now` is in its race week, the
    last Grand Prix before it (for recaps) and every round already raced (for the season rewind).
    round is None when no published calendar has a race ahead. None when there is no calendar at all."""
    if cals is None:
        cals = [calendar(oc, now.year - 1), calendar(oc, now.year), calendar(oc, now.year + 1)]
    cals = [c for c in cals if not c.empty]
    if not cals:
        return None
    cal = pd.concat(cals, ignore_index=True).sort_values("r").reset_index(drop=True)
    ts = pd.Timestamp(now.astimezone(UTC))
    done = cal[cal["r"] + pd.Timedelta(hours=RACE_OVER_H) < ts]
    last = done.iloc[-1] if len(done) else None
    out = {"season": None, "round": None, "q": None, "race_week": False, "days_to_q": None,
           "last": (int(last["season"]), int(last["round"])) if last is not None else None,
           "done": [(int(r["season"]), int(r["round"])) for _, r in done.iterrows()]}
    ahead = cal[cal["r"] + pd.Timedelta(hours=RACE_OVER_H) >= ts]
    if ahead.empty:
        return out
    nxt = ahead.iloc[0]
    q_pt = nxt["q"].to_pydatetime().astimezone(TZ)
    monday = (q_pt - timedelta(days=q_pt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return out | {"season": int(nxt["season"]), "round": int(nxt["round"]), "q": q_pt, "race_week": now >= monday,
                  "days_to_q": (q_pt - now).total_seconds() / 86400}


# ---------------------------------------------------------------- stories

def storyize(card: Path, out: Path) -> Path:
    """A 4:5 card centred on a 9:16 Paddock Cyan story background, inside the story safe zone."""
    from .preview import Card
    from .render import H_REEL, W
    out.parent.mkdir(parents=True, exist_ok=True)
    bg = out.with_name(out.stem + "_bg.jpg")
    Card(H_REEL, story=True).save(bg)
    canvas = Image.open(bg).convert("RGB")
    im = Image.open(card).convert("RGB")
    canvas.paste(im, ((W - im.width) // 2, (H_REEL - im.height) // 2))
    canvas.save(out, quality=94, optimize=True)
    bg.unlink(missing_ok=True)
    return out


def pool(p, weights: dict | None = None) -> list[tuple]:
    """Race week story pool for a GP: only cards that carry data (Michel, 17 Nov: "informative technical or
    historical info people can learn from and save, less marketing"). No brand slides, no title covers,
    no closing cards. Interleaved by source so consecutive hours differ.
    p is None when the circuit has no previous race to draw the lap posts from: brand stories as fallback."""
    from . import brand, history
    if p is None:
        return [("start", i) for i in range(4)]
    nz = p.stats.get("braking_zones", 0)
    from . import insights
    # Lap in data, Gear map and Race day numbers are feed posts this week: not repeated as stories (17 Nov)
    groups = {
        "preview": list(range(1, 8)),                                   # facts and session times, not the cover
        "strategy": list(range(insights.group_size(p, insights.STRATEGY))),     # last year's race craft
        "braking": list(range(0, nz + 2)),                              # zone map, every zone, the table
        "conditions": list(range(insights.group_size(p, insights.CONDITIONS))), # forecast, track temp, pits, SC
        "history": list(range(1, len(history.HISTORY[p.title]["chapters"]) + 1)) if history.available(p) else [],
    }
    # weekly optimiser: a group with weight w gets w turns per round (more of what people save and share)
    w = {g: max(1, int((weights or {}).get(g, 1))) for g in groups}
    order, pos = [], {g: 0 for g in groups}
    while any(pos[g] < len(idx) for g, idx in groups.items()):
        for g, idx in groups.items():
            for _ in range(w[g]):
                if pos[g] < len(idx):
                    order.append((g, idx[pos[g]]))
                    pos[g] += 1
    return order


# Michel, 17 Nov: "no duplicates are allowed". In race week every story is a card not posted before that
# week, as a story or inside a feed post. Feed posts this week carry the lap facts (Preview reel), the
# history (History reel), last year's strategy (Strategy file), championship math, Lap in data, Gear map and
# Race day numbers, so those never run as stories. Stories get what is left: every braking zone, a fresh
# forecast once a day (new numbers each day), and the FIA news cards as their facts are checked.
# When nothing new is left, the hour gets no story rather than a repeat.

def story_units(sb, p, sid: str, now: datetime, q: datetime | None = None) -> list[tuple]:
    """Unposted story cards, in posting order: (group, index, content key)."""
    from . import insights, news
    if p is None:
        return []
    rows = sb.table("ig_posts").select("content").like("session_id", f"{sid}_H%").eq("status", "published").execute().data
    rows += sb.table("ig_posts").select("content").like("session_id", f"{sid}_NEWS%").eq("status", "published").execute().data
    used = {r["content"] for r in rows if r.get("content")}
    out = []
    day = f"{now:%Y-%m-%d}"
    fc_days = {(q + timedelta(days=k)).date() for k in (-2, 0, 1)} if q is not None else set()   # Wed, quali day, race day
    if now.date() in fc_days and f"rain {day}" not in used and insights.available(p, [insights.rain]):
        out.append(("rain", 0, f"rain {day}"))                      # first story of the day: today's forecast
    from . import extras
    nz = p.stats.get("braking_zones", 0)
    from . import live
    try:
        fresh = [("live", name, f"live {name}") for name, _ in live.available(p) if f"live {name}" not in used]
    except Exception as e:
        log.warning("live practice cards unavailable: %s", e)
        fresh = []
    out += fresh                                                      # fresh practice data goes first
    lanes = [
        [("news", i, f"news {name}") for i, name in enumerate(news.available(p)) if f"news {name}" not in used],
        [("braking", i, f"braking {i + 1}") for i in range(nz + 2) if f"braking {i + 1}" not in used],
    ]
    for g, fns in extras.GROUPS.items():                              # 17 Nov: more cards, each once
        lanes.append([(g, f.__name__, f"{g} {f.__name__}") for f in insights.available(p, fns)
                      if f"{g} {f.__name__}" not in used])
    pins = _pins().get(f"{now:%Y-%m-%d %H}")                         # the order Michel approved in advance
    news_lane, other = lanes[0], [x for x in lanes[1:] if x]
    if other:                                                         # rotate so consecutive hours change topic
        r = len(used) % len(other)
        other = other[r:] + other[:r]
    out += news_lane
    for i in range(max((len(x) for x in other), default=0)):
        for lane in other:
            out += lane[i:i + 1]
    if pins:
        hit = [u for u in out if u[2] == pins]
        if hit:
            out = hit + [u for u in out if u[2] != pins]
        else:
            log.warning("pinned card %s not available this hour: next new card instead", pins)
    # Session reports from the news come before everything, pins included: the hours after a session are
    # about that session, data or not (Michel, 19 Nov)
    try:
        from .gp_facts import SESSION_NEWS
        sess = [("session", f"{code}:{i}", f"news {code} {i}")
                for code, items in SESSION_NEWS.get(p.title, {}).get(q.year if q is not None else now.year, {}).items()
                for i in range(1, len(items) + 1) if f"news {code} {i}" not in used]
    except Exception as e:
        log.error("session reports unavailable: %s", e)
        sess = []
    only = GP_ONLY.get(p.title)
    if only and q is not None and q.year == only[0] and now < only[1]:
        out = [u for u in out if u[0] in GP_ONLY_GROUPS]
    return sess + out


def _pins() -> dict:
    """Approved story order for a day: pins.json {"YYYY-MM-DD HH": content key} (optional)."""
    import json
    f = Path(__file__).with_name("pins.json")
    try:
        return json.loads(f.read_text()) if f.exists() else {}
    except Exception as e:
        log.warning("pins.json unreadable: %s", e)
        return {}


def render_story(p, item: tuple, out: Path) -> Path:
    from . import brand, history, lapdata, preview
    g, i = item[0], item[1]
    out.mkdir(parents=True, exist_ok=True)
    if g == "preview":
        return preview.stories(p, out)[i]
    if g == "recap":
        return storyize(item[2], out / f"story_recap_{i + 1:02d}.jpg")
    if g == "rain":
        from . import insights
        return storyize(insights.card_path(p, [insights.rain], 0, out / "src"), out / "story_rain.jpg")
    if g == "live":
        from . import live
        return storyize(live.card_path(p, i, out / "src"), out / f"story_live_{i}.jpg")
    if g in ("craft", "champ", "circuit", "learn"):
        from . import extras
        return storyize(extras.card_path(p, i, out / "src"), out / f"story_{g}_{i}.jpg")
    if g == "session":
        from . import news
        from .gp_facts import SESSION_NEWS
        code, k = i.split(":")
        it = SESSION_NEWS[p.title][next(iter(y for y in SESSION_NEWS[p.title] if code in SESSION_NEWS[p.title][y]))][code][int(k) - 1]
        out.mkdir(parents=True, exist_ok=True)
        return news.session_story(p, it).save(out / f"story_session_{code}_{k}.jpg")
    if g == "news":
        from . import news
        return storyize(news.card_path(p, i, out / "src"), out / f"story_news_{i + 1:02d}.jpg")
    if g in ("strategy", "conditions"):
        from . import insights
        fns = insights.STRATEGY if g == "strategy" else insights.CONDITIONS
        return storyize(insights.card_path(p, fns, i, out / "src"), out / f"story_{g}_{i + 1:02d}.jpg")
    if g == "braking":
        card = lapdata.braking_carousel(p, out / "src", story=True)[i]
    elif g == "history":
        card = history.carousel(p, out / "src")[i]
    elif g == "start":
        card = brand.start_here(out / "src")[i]
    elif g == "lap":
        card = lapdata.lap_in_data(p, out)
    elif g == "gears":
        card = lapdata.gear_map(p, out)
    else:
        card = brand.race_day(p, out)
    return storyize(card, out / f"story_{g}_{i + 1:02d}.jpg")


def recap_cards(sb, season: int, rnd: int, out: Path) -> list[Path]:
    """Race then qualifying carousel slides of a past round, rendered from our own data."""
    from . import render
    from .data import load_story
    cards = []
    for code in ("R", "Q"):
        sid = f"{season}_{rnd:02d}_{code}"
        try:
            meta, st, rot = load_story(sb, sid)
            if code == "R":
                cards += render.race_carousel(st, meta, out / sid)[:-1]          # without the closing slide
            else:
                cards += render.quali_carousel(st, meta, rot, out / sid)[:-1]
        except Exception as e:
            log.info("no recap from %s: %s", sid, e)
    return cards


def published_count(sb, prefix: str) -> int:
    r = sb.table("ig_posts").select("session_id", count="exact").like("session_id", f"{prefix}%").eq(
        "status", "published").execute()
    return int(r.count or 0)


REWIND_GAP_DAYS = 14             # next qualifying further away than this: daily season rewind instead


def due(w: dict | None, now: datetime) -> bool:
    """Is a post due this hour? Race week: every hour in the window. Otherwise: the daily hour."""
    if w is None or now.hour not in WINDOW:
        return False
    return w["race_week"] or now.hour == DAILY_HOUR


def rewinding(w: dict) -> bool:
    """Off season or a long break: no race ahead, or the next qualifying is more than two weeks away."""
    return w["round"] is None or (not w["race_week"] and (w["days_to_q"] or 0) > REWIND_GAP_DAYS)


def rewind_items(w: dict) -> list[tuple]:
    """Every race and qualifying of the latest season raced so far, three slides each, in order."""
    if not w["done"]:
        return []
    season = w["done"][-1][0]
    rounds = [r for s, r in w["done"] if s == season]
    return [("rewind", n, (season, r, code, i)) for n, (r, code, i) in
            enumerate((r, code, i) for r in rounds for code in ("R", "Q") for i in range(3))]


def render_rewind(sb, item: tuple, out: Path) -> Path | None:
    from . import render
    from .data import load_story
    season, rnd, code, i = item[2]
    sid = f"{season}_{rnd:02d}_{code}"
    try:
        meta, st, rot = load_story(sb, sid)
    except Exception as e:
        log.info("no rewind from %s: %s", sid, e)
        return None
    slides = (render.race_carousel(st, meta, out / sid) if code == "R"
              else render.quali_carousel(st, meta, rot, out / sid))[:-1]   # without the closing slide
    return storyize(slides[min(i, len(slides) - 1)], out / f"story_rewind_{sid}_{i + 1}.jpg")


# ---------------------------------------------------------------- Reels with a fallback

FALLBACK_TRIES = 3              # Reels to try in one run before giving the hour up (each build reads OpenF1)


def build_reel(sb, ig, p, sid: str, rk: str, out: Path, post_row, window: tuple[datetime, datetime] | None = None):
    """The scheduled Reel, or when its data is not in (a live session not run yet, no wet pole at this track)
    the next unpublished Reel from reels_tel.FALLBACK, so a Reel slot never goes empty (Michel, 20 Nov: more
    Reels). Each kind posts once per GP (session id per kind), so a fallback never repeats a Reel, and a slot
    that already put out a Reel inside its time window (its own or a stand in) is "done", so the reruns every
    10 minutes never post a second one. Returns (kind, session id, video, caption), None when nothing could be
    built, or "done"."""
    from . import reels_tel

    def published(kind: str) -> bool:
        if ig is None:
            return False
        row = post_row(sb, f"{sid}_REEL_{kind.upper()}", "reel", "session")
        return bool(row and row["status"] in ("published", "held"))   # held: waiting for Michel, never rebuilt

    if window is not None and ig is not None:
        lo, hi = (t.astimezone(UTC).isoformat() for t in window)
        hit = sb.table("ig_posts").select("session_id").like("session_id", f"{sid}_REEL_%").eq("status", "published") \
            .gte("published_at", lo).lt("published_at", hi).execute().data
        held = sb.table("ig_posts").select("session_id").like("session_id", f"{sid}_REEL_%").eq("status", "held") \
            .gte("created_at", lo).lt("created_at", hi).execute().data
        if hit or held:
            return "done"
    tries = 0
    for kind in [rk] + [k for k in reels_tel.FALLBACK if k != rk]:
        if tries >= FALLBACK_TRIES:
            break
        if published(kind):                      # scheduled or stand in, never twice per GP
            continue
        tries += 1
        try:
            built = reels_tel.build(p, kind, out / f"reel_{kind}")
        except Exception as e:
            log.error("reel %s failed: %s", kind, e)
            built = None
        if built is None:
            log.warning("reel %s: data not in, trying the next Reel", kind)
            continue
        if kind != rk:
            log.info("reel %s stands in for %s", kind, rk)
        video, cap = built
        return kind, f"{sid}_REEL_{kind.upper()}", video, cap
    log.warning("no Reel could be built for %s this run", rk)
    return None


# ---------------------------------------------------------------- command

def cmd_hourly(a) -> int:
    from .. import store
    from ..openf1 import OpenF1
    from . import preview
    from .__main__ import connect, finish, post_row, preview_jobs, publish_jobs

    now = datetime.fromisoformat(a.now).astimezone(TZ) if a.now else datetime.now(TZ)
    if now.hour not in WINDOW:
        log.info("%s PT is outside the posting window: nothing to do", now.strftime("%a %H:%M"))
        return 0
    w = where_are_we(OpenF1(), now)
    if not due(w, now):
        if w is None:
            log.info("no F1 calendar published around %s: nothing to do", now.year)
        else:
            log.info("%s PT, not race week (next: %s round %s): the daily post is at %s:04",
                     now.strftime("%a %H:%M"), w["season"], w["round"], DAILY_HOUR)
        return 0

    sb = store.client()
    ig = connect(sb, a.dry_run)
    if ig is not None and not getattr(ig, "sends_files", False):
        log.error("posts need the Upload-Post publisher")
        return 1
    if rewinding(w):
        return daily_rewind(sb, ig, w, now, a)
    season, rnd = w["season"], w["round"]
    try:
        p = preview.load(season, rnd)
    except Exception as e:                       # new circuit, or data not published yet
        log.warning("no race week data for %s round %s: %s", season, rnd, e)
        p = None
    sid = f"{season}_{rnd:02d}_PREVIEW"
    tag = f"{now:%Y%m%d%H}" if w["race_week"] else f"{now:%Y%m%d}"
    out = Path(a.out) / sid / f"{'hourly' if w['race_week'] else 'daily'}_{tag}"
    checks = {"season": season, "round": rnd, "now_pt": now.isoformat(timespec="minutes"), "race_week": w["race_week"],
              "gp": p.title if p is not None else None}

    # Telemetry Reels at half past the hour, between the stories (Michel, 17 Nov)
    if w["race_week"] and p is not None and now.minute >= 25:
        from . import reels_tel
        rk = reels_tel.REEL_SLOTS.get((now.date() - w["q"].date()).days, {}).get(now.hour)
        if rk:
            h0 = now.replace(minute=0, second=0, microsecond=0)
            got = build_reel(sb, ig, p, sid, rk, out, post_row, (h0 + timedelta(minutes=25), h0 + timedelta(hours=1)))
            if got is not None and got != "done":
                rk, rsid, video, cap = got
                jobs = [(rsid, "reel", {"video": video, "cover": video.parent / "cover.jpg", "files": [], "caption": cap})]
                checks |= {"reel": rk}
                report, failed = publish_jobs(sb, ig, jobs, checks)
                if ig is not None:
                    sb.table("ig_posts").update({"content": f"reel {rk}"}).eq("session_id", rsid).eq("kind", "reel").execute()
                return finish(report, a.out, failed)

    jobs = None
    if w["race_week"] and p is not None:
        slot = SLOTS.get((now.date() - w["q"].date()).days, {}).get(now.hour)
        if slot and slot.startswith("reeltel:"):
            from . import reels_tel
            rk = slot.split(":", 1)[1]
            h0 = now.replace(minute=0, second=0, microsecond=0)
            got = build_reel(sb, ig, p, sid, rk, out, post_row, (h0, h0 + timedelta(minutes=25)))
            if got == "done":
                log.info("slot %s already published: nothing more this hour", slot)
                return 0
            if got is not None:
                rk, rsid, video, cap = got
                jobs = [(rsid, "reel", {"video": video, "cover": video.parent / "cover.jpg", "files": [], "caption": cap})]
                checks["slot"] = slot
                report, failed = publish_jobs(sb, ig, jobs, checks)
                if ig is not None:
                    sb.table("ig_posts").update({"content": f"reel {rk}"}).eq("session_id", rsid).eq("kind", "reel").execute()
                return finish(report, a.out, failed)
            log.warning("slot reel %s not built: a story this hour instead", rk)
            slot = None
        if slot:
            jobs = preview_jobs(p, sid, [slot], str(out), season)
            if jobs:
                jsid, kind, _ = jobs[0]
                row = post_row(sb, jsid, kind, "session") if ig is not None else None
                if row and row["status"] == "published":
                    log.info("slot %s already published: nothing more this hour", slot)
                    return 0
                checks["slot"] = slot
    if not jobs:
        from .metrics import weights
        if w["race_week"] and ig is not None and published_count(sb, f"{sid}_H{tag}"):
            log.info("%s_H%s already published: nothing more this hour", sid, tag)    # before the heavy card checks
            return 0
        if w["race_week"]:
            items, prefix = story_units(sb, p, sid, now, w["q"]), f"{sid}_H"
            if now.hour not in STORY_HOURS:
                items = [u for u in items if u[0] == "session"]          # reports only between story hours
                if not items:
                    log.info("story hour skipped: Reels first in race week (Michel, 20 Nov)")
                    return 0
            if not items:
                log.info("no story this hour: every card of the week is already out (no duplicates)")
                return 0
        else:
            recap = recap_cards(sb, *w["last"], out / "recap") if w["last"] else []
            teaser = [x for x in pool(p) if x[0] in ("history", "preview")][:6] if p is not None else []
            items, prefix = [("recap", i, c) for i, c in enumerate(recap)] + teaser, f"{sid}_D"
            if not items:
                items = pool(None)
        if ig is not None and published_count(sb, f"{prefix}{tag}"):
            log.info("%s%s already published: nothing more this %s", prefix, tag, "hour" if w["race_week"] else "day")
            return 0
        k = published_count(sb, f"{prefix}20") if ig is not None else 0   # only hourly or daily ids (prefix + date),
        item = items[0] if w["race_week"] else items[k % len(items)]       # not _HISTORY and the like
        try:
            img = render_story(p, item, out)
        except Exception as e:                    # never lose the hour to one card: take the next one
            if not w["race_week"] or len(items) < 2:
                raise
            log.error("story %s failed (%s): next card instead", item[2] if len(item) > 2 else item, e)
            item = items[1]
            img = render_story(p, item, out)
        jobs = [(f"{prefix}{tag}", "story", {"video": None, "cover": None, "files": [img], "caption": ""})]
        content = item[2] if w["race_week"] and len(item) > 2 and isinstance(item[2], str) else f"{item[0]} {item[1] + 1}"
        checks |= {"story": content, "pool": len(items), "posted_before": k}
    else:
        content = checks.get("slot")
    report, failed = publish_jobs(sb, ig, jobs, checks)
    if ig is not None and content:                    # what was shown, for the weekly optimiser
        for jsid, kind, _ in jobs:
            sb.table("ig_posts").update({"content": content}).eq("session_id", jsid).eq("kind", kind).execute()
    return finish(report, a.out, failed)


def daily_rewind(sb, ig, w: dict, now: datetime, a) -> int:
    """Off season or long break: one story a day walking back through the season, race by race."""
    from .__main__ import finish, publish_jobs
    items = rewind_items(w)
    season = w["done"][-1][0] if w["done"] else now.year
    prefix = f"{season}_REWIND_D"
    out = Path(a.out) / f"{season}_REWIND" / f"daily_{now:%Y%m%d}"
    if ig is not None and published_count(sb, f"{prefix}{now:%Y%m%d}"):
        log.info("today's rewind story is already out")
        return 0
    k = published_count(sb, f"{prefix}20") if ig is not None else 0
    img, item = None, None
    for j in range(len(items)):                      # skip sessions we have no data for
        item = items[(k + j) % len(items)]
        img = render_rewind(sb, item, out)
        if img is not None:
            break
    if img is None:
        item, img = ("start", 0), render_story(None, ("start", k % 4), out)
    checks = {"mode": "season rewind", "now_pt": now.isoformat(timespec="minutes"), "next_round": w["round"],
              "story": str(item[2] if len(item) > 2 else item), "pool": len(items), "posted_before": k}
    jobs = [(f"{prefix}{now:%Y%m%d}", "story", {"video": None, "cover": None, "files": [img], "caption": ""})]
    report, failed = publish_jobs(sb, ig, jobs, checks)
    return finish(report, a.out, failed)
