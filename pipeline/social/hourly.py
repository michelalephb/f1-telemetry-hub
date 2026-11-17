"""Hourly posting for race week: one post per hour inside the posting window.

Fixed feed slots (Pacific time, days counted from qualifying day) take their hour; every other hour
posts the next story from the week's pool, cycling so nothing repeats until the pool is used up.
Each hour has its own session id, so a rerun in the same hour never posts twice. Automatic
qualifying and race posts keep coming from the ingest trigger, on top of this.
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
WINDOW = range(7, 23)            # 7 AM to 10 PM PT: 16 posts a day (3 PM to 6 AM next day in Europe)

# day offset from qualifying day -> {PT hour: preview kind}
SLOTS = {
    -3: {9: "history_carousel", 12: "starthere", 18: "history"},
    -2: {9: "carousel", 18: "braking"},
    -1: {9: "reel", 18: "lap"},
    0: {9: "gears"},
    1: {9: "raceday"},
}


def storyize(card: Path, out: Path) -> Path:
    """A 4:5 card centred on a 9:16 Paddock Cyan story background, inside the story safe zone."""
    from .preview import Card
    from .render import H_REEL, W
    bg = out.with_name(out.stem + "_bg.jpg")
    Card(H_REEL, story=True).save(bg)
    canvas = Image.open(bg).convert("RGB")
    im = Image.open(card).convert("RGB")
    canvas.paste(im, ((W - im.width) // 2, (H_REEL - im.height) // 2))
    canvas.save(out, quality=94, optimize=True)
    bg.unlink(missing_ok=True)
    return out


def pool(p) -> list[tuple[str, int]]:
    """The week's story pool, interleaved by source so consecutive hours differ."""
    from . import brand, history
    groups = {
        "preview": 8,
        "braking": p.stats.get("braking_zones", 0) + 2,
        "history": (len(history.HISTORY[p.title]["chapters"]) + 2) if history.available(p) else 0,
        "start": 4,
        "lap": 1,
        "gears": 1,
        "raceday": 1 if p.title in brand.RACE_DAY else 0,
    }
    order = []
    for i in range(max(groups.values())):
        for g, n in groups.items():
            if i < n:
                order.append((g, i))
    return order


def render_story(p, item: tuple[str, int], out: Path) -> Path:
    from . import brand, history, lapdata, preview
    g, i = item
    out.mkdir(parents=True, exist_ok=True)
    if g == "preview":
        return preview.stories(p, out)[i]
    if g == "braking":
        card = lapdata.braking_carousel(p, out / "src")[i]
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


def next_round(oc, season: int, now_utc: datetime) -> tuple[int, datetime] | None:
    """Round of the next Grand Prix whose race has not finished, and its qualifying start (PT)."""
    from ..__main__ import schedule
    rows = [s for s in schedule(oc, season)]
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df["start"] = pd.to_datetime(df["start_utc"], utc=True)
    races = df[df["session_code"] == "R"].sort_values("start")
    nxt = races[races["start"] + pd.Timedelta(hours=3) >= pd.Timestamp(now_utc)]
    if nxt.empty:
        return None
    rnd = int(nxt.iloc[0]["round"])
    q = df[(df["round"] == rnd) & (df["session_code"] == "Q")]
    if q.empty:
        return None
    return rnd, q.iloc[0]["start"].to_pydatetime().astimezone(TZ)


def published_count(sb, prefix: str) -> int:
    r = sb.table("ig_posts").select("session_id", count="exact").like("session_id", f"{prefix}%").eq(
        "status", "published").execute()
    return int(r.count or 0)


def cmd_hourly(a) -> int:
    from .. import store
    from . import preview
    from .__main__ import connect, finish, preview_jobs, publish_jobs, post_row
    from ..openf1 import OpenF1

    now = datetime.fromisoformat(a.now).astimezone(TZ) if a.now else datetime.now(TZ)
    if now.hour not in WINDOW:
        log.info("%s PT is outside the posting window %s to %s: nothing to do", now.strftime("%a %H:%M"),
                 WINDOW.start, WINDOW.stop)
        return 0
    sb = store.client()
    ig = connect(sb, a.dry_run)
    if ig is not None and not getattr(ig, "sends_files", False):
        log.error("hourly posts need the Upload-Post publisher")
        return 1
    oc = OpenF1()
    if a.round:
        rnd, qstart = a.round, None
        found = next_round(oc, a.season, now.astimezone(ZoneInfo("UTC")))
        if found and found[0] == rnd:
            qstart = found[1]
    else:
        found = next_round(oc, a.season, now.astimezone(ZoneInfo("UTC")))
        if not found:
            log.info("no Grand Prix ahead in %s: nothing to do", a.season)
            return 0
        rnd, qstart = found
    p = preview.load(a.season, rnd)
    sid = f"{a.season}_{rnd:02d}_PREVIEW"
    checks = p.stats | {"round": rnd, "now_pt": now.isoformat(timespec="minutes")}
    out = Path(a.out) / sid / f"hourly_{now:%Y%m%d%H}"

    slot = None
    if qstart is not None:
        off = (now.date() - qstart.date()).days
        slot = SLOTS.get(off, {}).get(now.hour)
    jobs = None
    if slot:
        jobs = preview_jobs(p, sid, [slot], str(out), a.season)
        if jobs:
            jsid, kind, _ = jobs[0]
            row = post_row(sb, jsid, kind, "session") if ig is not None else None
            if row and row["status"] == "published":
                log.info("slot %s already published, posting a story this hour instead", slot)
                jobs = None
    if not jobs:
        items = pool(p)
        k = published_count(sb, f"{sid}_H") if ig is not None else 0
        item = items[k % len(items)]
        img = render_story(p, item, out)
        jobs = [(f"{sid}_H{now:%Y%m%d%H}", "story", {"video": None, "cover": None, "files": [img], "caption": ""})]
        checks |= {"story": f"{item[0]} {item[1] + 1}", "pool": len(items), "posted_before": k}
    else:
        checks |= {"slot": slot}
    report, failed = publish_jobs(sb, ig, jobs, checks)
    return finish(report, a.out, failed)
