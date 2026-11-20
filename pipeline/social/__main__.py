"""Command line entry point for the Instagram automation (see pipeline/social/__init__.py).

Live posting needs all of: the social_settings row with enabled = true, an access token
(social_settings.access_token, else the IG_ACCESS_TOKEN secret), and no --dry-run.
Otherwise everything is rendered into --out and nothing is written or posted.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import store
from . import captions, render, style
from .data import load_story, rows
import uuid

from .publish import Instagram, UploadPost, now_iso, refresh_token
from .story import StoryError

log = logging.getLogger("social")
CODES = ("R", "Q", "S", "SQ")
RECENT = timedelta(hours=72)        # only sessions this recent are posted (never the back catalogue)
OFF_SEASON = timedelta(days=10)     # no session this recently means rewind posts may run
MAX_ATTEMPTS = 3                    # publish failures before giving up on a post
MAX_WAITS = 12                      # hourly runs a session may wait for data or the official result
KINDS = ("reel", "carousel")        # Reel first; one publish per run spaces them an hour apart


# ---------------------------------------------------------------- settings and queue

def settings(sb) -> dict:
    try:
        d = sb.table("social_settings").select("*").eq("id", 1).execute().data
        return d[0] if d else {}
    except Exception as e:
        log.warning("social_settings unreadable (%s); treating as disabled", type(e).__name__)
        return {}


def token_of(cfg: dict) -> str | None:
    return cfg.get("access_token") or os.environ.get("IG_ACCESS_TOKEN") or None


def post_row(sb, sid: str, kind: str, story: str) -> dict | None:
    d = sb.table("ig_posts").select("*").eq("session_id", sid).eq("kind", kind).eq("story", story).execute().data
    return d[0] if d else None


def save_row(sb, row: dict) -> dict:
    return sb.table("ig_posts").upsert(row, on_conflict="session_id,kind,story").execute().data[0]


def recent_sessions(sb) -> list[str]:
    since = (datetime.now(timezone.utc) - RECENT).isoformat()
    d = (sb.table("sessions").select("session_id,session_code,start_utc").eq("status", "ingested")
         .gte("start_utc", since).order("start_utc").execute().data)
    return [r["session_id"] for r in d if r["session_code"] in CODES]


# ---------------------------------------------------------------- render

def build(meta: dict, st, rot: float, kind: str, out: Path, rewind: bool = False) -> dict:
    """Render one post. Returns {"files": [...], "video": path or None, "cover": path or None, "caption": str}."""
    out.mkdir(parents=True, exist_ok=True)
    if st.kind == "quali":
        cap = captions.quali(st, meta, kind, rewind)
        if kind == "reel":
            v, c = render.quali_reel(st, meta, rot, out)
            return {"files": [], "video": v, "cover": c, "caption": cap}
        return {"files": render.quali_carousel(st, meta, rot, out), "video": None, "cover": None, "caption": cap}
    cap = captions.race(st, meta, kind)
    if kind == "reel":
        v, c = render.race_reel(st, meta, out)
        return {"files": [], "video": v, "cover": c, "caption": cap}
    return {"files": render.race_carousel(st, meta, out), "video": None, "cover": None, "caption": cap}


def upload(sb, local: Path, remote: str) -> str:
    ctype = "video/mp4" if local.suffix == ".mp4" else "image/jpeg"
    sb.storage.from_(store.WEB_BUCKET).upload(remote, local.read_bytes(), {"content-type": ctype, "upsert": "true"})
    return f"{os.environ['SUPABASE_URL'].rstrip('/')}/storage/v1/object/public/{store.WEB_BUCKET}/{remote}"


def remove(sb, paths: list[str]) -> None:
    """Delete rendered videos from the web bucket (approved: every video goes once posted)."""
    if paths:
        try:
            sb.storage.from_(store.WEB_BUCKET).remove(paths)
            log.info("deleted from bucket: %s", paths)
        except Exception as e:
            log.error("could not delete %s: %s", paths, e)


# ---------------------------------------------------------------- one post

def handle(sb, ig: Instagram | None, sid: str, kind: str, story: str, out: Path, cache: dict, report: list) -> bool:
    """Render (and in live mode publish) one post. Returns True when something was published."""
    live = ig is not None
    row = post_row(sb, sid, kind, story) if live else None
    if row and (row["status"] in ("published", "skipped") or (row["status"] == "failed" and row["attempts"] >= MAX_ATTEMPTS)):
        return False
    if row and row["status"] == "queued" and (row.get("container_id") or "").startswith("up:"):
        return resume(sb, ig, row, report)   # an earlier run sent it: never send twice
    entry = {"session_id": sid, "kind": kind, "story": story}
    try:
        if sid not in cache:
            cache[sid] = load_story(sb, sid)
        meta, st, rot = cache[sid]
        entry["checks"] = st.checks
        built = build(meta, st, rot, kind, out / sid / f"{story}_{kind}", rewind=(story == "rewind"))
    except StoryError as e:
        log.warning("%s %s: not posted: %s", sid, kind, e)
        if live:
            # results or traces can land hours after the session: wait, then give up
            n = ((row or {}).get("attempts", 0) + 1) if (row or {}).get("status") in (None, "waiting") else 1
            status = "skipped" if n >= MAX_WAITS else "waiting"
            save_row(sb, {"session_id": sid, "kind": kind, "story": story, "status": status, "error": str(e)[:1000], "attempts": n})
            report.append(entry | {"status": status, "reason": str(e)})
        else:
            report.append(entry | {"status": "not postable", "reason": str(e)})
        return False

    entry |= {"caption": built["caption"], "files": [str(p) for p in built["files"]],
              "video": str(built["video"]) if built["video"] else None}
    if not live:
        report.append(entry | {"status": "rendered (dry run)"})
        return False

    base = f"ig/{meta['season']}/{meta['round']:02d}/{meta['code']}/{story}_{kind}"
    attempts = ((row or {}).get("attempts", 0) + 1) if (row or {}).get("status") == "failed" else 1
    save_row(sb, {"session_id": sid, "kind": kind, "story": story, "status": "queued", "caption": built["caption"],
                        "attempts": attempts, "error": None})
    if getattr(ig, "sends_files", False):
        return send_files(sb, ig, sid, kind, story, built, attempts, entry, report)
    video_paths = []
    try:
        if kind == "reel":
            video_paths = [f"{base}/reel.mp4"]
            v_url = upload(sb, built["video"], video_paths[0])
            c_url = upload(sb, built["cover"], f"{base}/cover.jpg")
            container, media = ig.post_reel(v_url, c_url, built["caption"])
            media_paths = video_paths + [f"{base}/cover.jpg"]
        else:
            media_paths = [f"{base}/{p.name}" for p in built["files"]]
            urls = [upload(sb, p, r) for p, r in zip(built["files"], media_paths)]
            container, media = ig.post_carousel(urls, built["caption"])
        link = ig.permalink(media)
        save_row(sb, {"session_id": sid, "kind": kind, "story": story, "status": "published", "container_id": container,
                      "media_id": media, "permalink": link, "published_at": now_iso(), "media_paths": media_paths,
                      "attempts": attempts, "error": None})
        report.append(entry | {"status": "published", "permalink": link})
        log.info("published %s %s: %s", sid, kind, link)
        return True
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"[:1000]
        log.error("%s %s failed (attempt %d): %s", sid, kind, attempts, msg)
        save_row(sb, {"session_id": sid, "kind": kind, "story": story, "status": "failed", "error": msg, "attempts": attempts})
        report.append(entry | {"status": "failed", "reason": msg})
        raise
    finally:
        remove(sb, video_paths)   # posted or failed, the video is not kept (a retry renders it again)


def send_files(sb, ig: UploadPost, sid: str, kind: str, story: str, built: dict, attempts: int, entry: dict, report: list) -> bool:
    """Upload-Post: send the local files. The request id is saved first, so a crash or timeout is
    picked up by resume() on the next run instead of being sent again."""
    rid = f"{sid}-{story}-{kind}-a{attempts}-{uuid.uuid4().hex[:8]}"
    key = {"session_id": sid, "kind": kind, "story": story}
    save_row(sb, key | {"status": "queued", "container_id": f"up:{rid}", "attempts": attempts, "error": None})
    try:
        if kind == "reel":
            ig.send_reel(str(built["video"]), str(built["cover"]) if built["cover"] else None, built["caption"], rid)
        elif kind == "story":
            ig.send_story(str(built["files"][0]), rid)
        else:
            ig.send_carousel([str(p) for p in built["files"]], built["caption"], rid)
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"[:1000]
        log.error("%s %s not sent (attempt %d): %s", sid, kind, attempts, msg)
        save_row(sb, key | {"status": "failed", "error": msg, "attempts": attempts})
        report.append(entry | {"status": "failed", "reason": msg})
        raise
    return resume(sb, ig, key | {"container_id": f"up:{rid}", "attempts": attempts}, report, entry)


def resume(sb, ig: UploadPost, row: dict, report: list, entry: dict | None = None) -> bool:
    """Check a sent Upload-Post request: published, failed, or still processing (left queued)."""
    rid = row["container_id"][3:]
    key = {k: row[k] for k in ("session_id", "kind", "story")}
    entry = entry or dict(key)
    try:
        res = ig.wait(rid)
    except TimeoutError as e:
        log.warning("%s: still processing, will check again next run (%s)", rid, e)
        report.append(entry | {"status": "processing", "reason": str(e)})
        return False
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"[:1000]
        save_row(sb, key | {"status": "failed", "error": msg, "attempts": row.get("attempts", 1)})
        report.append(entry | {"status": "failed", "reason": msg})
        raise
    link = res.get("url") or res.get("post_url")
    media = res.get("post_id") or res.get("media_id") or res.get("container_id")
    save_row(sb, key | {"status": "published", "media_id": str(media) if media else None, "permalink": link,
                        "published_at": now_iso(), "media_paths": None, "attempts": row.get("attempts", 1), "error": None})
    report.append(entry | {"status": "published", "permalink": link})
    log.info("published %s %s: %s", key["session_id"], key["kind"], link)
    return True


# ---------------------------------------------------------------- commands

def connect(sb, dry_run: bool) -> Instagram | UploadPost | None:
    """Upload-Post when UPLOADPOST_API_KEY is set (no Facebook account needed), else Meta's API."""
    if dry_run:
        return None
    cfg = settings(sb)
    tok = token_of(cfg)
    if not cfg.get("enabled"):
        log.info("posting disabled (social_settings.enabled is not true): dry run")
        return None
    if os.environ.get("UPLOADPOST_API_KEY"):
        return UploadPost(os.environ["UPLOADPOST_API_KEY"], os.environ.get("UPLOADPOST_USER") or "f1telemetryhub")
    if not tok:
        log.info("no Instagram token: dry run")
        return None
    ig = Instagram(tok, cfg.get("ig_user_id") or os.environ.get("IG_USER_ID") or None)
    left = ig.quota_left()
    if left is not None and left < 2:
        log.warning("publishing quota nearly used (%s left): skipping this run", left)
        return None
    return ig


def cmd_run(a) -> int:
    sb = store.client()
    ig = connect(sb, a.dry_run)
    sids = [a.session] if a.session else recent_sessions(sb)
    kinds = [a.kind] if a.kind else list(KINDS)
    log.info("%s mode, sessions: %s", "LIVE" if ig else "dry run", sids)
    report, cache, failed = [], {}, 0
    for sid in sids:
        for kind in kinds:
            try:
                if handle(sb, ig, sid, kind, "session", Path(a.out), cache, report) and not a.session:
                    return finish(report, a.out, failed)   # one post per scheduled run
            except Exception:
                failed += 1
    return finish(report, a.out, failed)


def cmd_rewind(a) -> int:
    """Off season: one qualifying Reel a week from the archive, oldest round first."""
    sb = store.client()
    since = (datetime.now(timezone.utc) - OFF_SEASON).isoformat()
    if sb.table("sessions").select("session_id").eq("status", "ingested").gte("start_utc", since).limit(1).execute().data and not a.force:
        log.info("season is running: no rewind post")
        return 0
    ig = connect(sb, a.dry_run)
    q = rows(sb, "sessions", "session_id,season,round,session_code,status", session_code="Q", status="ingested")
    q = q.sort_values(["season", "round"])
    done = set()
    if ig is not None:
        done = {r["session_id"] for r in sb.table("ig_posts").select("session_id,status").eq("story", "rewind").execute().data
                if r["status"] in ("published", "skipped")}
    report, cache, failed = [], {}, 0
    latest = q["season"].max() if len(q) else None
    for sid in q[q["season"] == latest]["session_id"]:
        if sid in done:
            continue
        try:
            if handle(sb, ig, sid, "reel", "rewind", Path(a.out), cache, report) or ig is None:
                break
        except Exception:
            failed += 1
            break
    return finish(report, a.out, failed)


def publish_jobs(sb, ig, jobs: list, checks: dict) -> tuple[list, int]:
    """Post each job once: skip what is published, resume what is queued, send the rest."""
    report, failed = [], 0
    for jsid, kind, built in jobs:
        entry = {"session_id": jsid, "kind": kind, "story": "session", "checks": checks, "caption": built["caption"]}
        if ig is None:
            report.append(entry | {"status": "rendered (dry run)"})
            continue
        row = post_row(sb, jsid, kind, "session")
        if row and row["status"] == "published":
            report.append(entry | {"status": "already published", "permalink": row.get("permalink")})
            continue
        try:
            if row and row["status"] == "queued" and (row.get("container_id") or "").startswith("up:"):
                resume(sb, ig, row, report, entry)
            else:
                send_files(sb, ig, jsid, kind, "session", built, (row or {}).get("attempts", 0) + 1, entry, report)
        except Exception:
            failed += 1
    return report, failed


def preview_jobs(p, sid: str, kinds: list[str], out_dir: str, season: int, story: int | None = None) -> list | None:
    """(session id, kind, built) for each requested race week post; None when a GP lacks checked facts."""
    from . import preview
    jobs = []
    for kind in kinds:
        out = Path(out_dir) / sid / f"preview_{kind}"
        if kind == "reel":
            v, c = preview.reel(p, out)
            jobs.append((sid, "reel", {"video": v, "cover": c, "files": [], "caption": preview.caption(p, kind)}))
        elif kind == "history":
            from . import history
            if not history.available(p):
                log.error("no checked history facts for %s: add them to gp_facts.HISTORY", p.title)
                return None
            v, c = history.reel(p, out)
            jobs.append((f"{sid}_HISTORY", "reel", {"video": v, "cover": c, "files": [], "caption": history.caption(p)}))
        elif kind in ("braking", "lap", "gears", "raceday", "starthere"):
            from . import brand, lapdata
            if kind == "braking":
                jobs.append((f"{sid}_BRAKING", "carousel", {"video": None, "cover": None, "files": lapdata.braking_carousel(p, out),
                                                            "caption": lapdata.braking_caption(p)}))
            elif kind == "lap":
                jobs.append((f"{sid}_LAP", "carousel", {"video": None, "cover": None, "files": [lapdata.lap_in_data(p, out)],
                                                        "caption": lapdata.lap_caption(p)}))
            elif kind == "gears":
                jobs.append((f"{sid}_GEARS", "carousel", {"video": None, "cover": None, "files": [lapdata.gear_map(p, out)],
                                                          "caption": lapdata.gear_caption(p)}))
            elif kind == "raceday":
                if p.title not in brand.RACE_DAY:
                    log.error("no checked race day facts for %s: add them to gp_facts.RACE_DAY", p.title)
                    return None
                jobs.append((f"{sid}_RACEDAY", "carousel", {"video": None, "cover": None, "files": [brand.race_day(p, out)],
                                                            "caption": brand.race_day_caption(p)}))
            else:
                jobs.append((f"{season}_BRAND_START", "carousel", {"video": None, "cover": None, "files": brand.start_here(out),
                                                                     "caption": brand.start_here_caption()}))
        elif kind == "titlemath":
            from . import news
            try:
                files = news.title_carousel(p, out)
            except Exception as e:
                log.error("no championship math for %s: %s", p.title, e)
                return None
            jobs.append((f"{sid}_TITLE", "carousel", {"video": None, "cover": None, "files": files, "caption": news.title_caption(p)}))
        elif kind == "strategy":
            from . import insights
            try:
                files = insights.carousel(p, out)
            except Exception as e:
                log.error("no strategy carousel for %s: %s", p.title, e)
                return None
            jobs.append((f"{sid}_STRATEGY", "carousel", {"video": None, "cover": None, "files": files,
                                                         "caption": insights.caption(p)}))
        elif kind == "reels_data":                    # review only: the data the telemetry Reels need, as JSON in the log
            from . import reels_tel
            import json as _json
            from . import learn as _learn
            try:
                lp = _learn.laps_data(p.season, p.round)[["code", "lap_number", "st_speed", "lap_duration", "duration_sector_1",
                                                          "duration_sector_2", "duration_sector_3"]]
                lj = lp.to_json(orient="records")
                for k in range(0, len(lj), 20000):
                    print(f"LAPS_PART {k // 20000:04d} {lj[k:k + 20000]}", flush=True)
            except Exception as e:
                log.warning("laps dump: %s", e)
            blob = _json.dumps(reels_tel.gather(p), default=str)
            print(f"REELS_SIZE {len(blob)}", flush=True)
            for k in range(0, len(blob), 20000):                    # GitHub drops very long log lines
                print(f"REELS_PART {k // 20000:04d} {blob[k:k + 20000]}", flush=True)
            print("PREVIEW_JSON " + _json.dumps({"title": p.title, "event": p.event, "season": p.season, "round": p.round,
                                                 "ref_year": p.ref_year, "driver": p.driver, "lap_s": p.lap_s,
                                                 "sessions": p.sessions, "country": p.country, "gp": p.gp, "colors": p.colors,
                                                 "corners": p.corners, "stats": {k: (list(v) if isinstance(v, tuple) else v) for k, v in p.stats.items()}},
                                                default=str))
        elif kind == "insights":                      # review only: every insight card, one image each
            from . import insights
            import json as _json
            print("INSIGHTS_JSON " + _json.dumps(insights.gather(p.season, p.round, p.title), default=str))
            from . import news
            try:
                print("STANDINGS_JSON " + _json.dumps(news.standings(p.season), default=str))
            except Exception as e:
                log.warning("standings unavailable: %s", e)
            from . import extras
            print("CRAFT_JSON " + _json.dumps({k: v for k, v in extras.craft_data(p.season, p.round, p.title).items()
                                                if k != "positions"}, default=str))
            print("CIRCUIT_JSON " + _json.dumps(extras.circuit_history(p.season, p.round), default=str))
            from . import live
            import dataclasses as _dc
            prev = _dc.replace(p, round=p.round - 1)          # live cards tested on the previous round's practice
            for name, _ in live.available(prev):
                try:
                    jobs.append((f"{sid}_REVIEW_live_{name}", "story", {"video": None, "cover": None, "caption": "",
                                 "files": [live.card_path(prev, name, out)]}))
                except Exception as e:
                    log.warning("review live %s: %s", name, e)
            for g, fns in extras.GROUPS.items():
                for f in fns:
                    try:
                        path = extras.card_path(p, f.__name__, out)
                        jobs.append((f"{sid}_REVIEW_{g}_{f.__name__}", "story", {"video": None, "cover": None, "caption": "", "files": [path]}))
                    except Exception as e:
                        log.warning("review card %s: %s", f.__name__, e)
        elif kind == "history_carousel":
            from . import history
            if not history.available(p):
                log.error("no checked history facts for %s: add them to gp_facts.HISTORY", p.title)
                return None
            jobs.append((f"{sid}_HISTORY", "carousel", {"video": None, "cover": None, "files": history.carousel(p, out),
                                                        "caption": history.caption(p)}))
        elif kind == "carousel":
            jobs.append((sid, "carousel", {"video": None, "cover": None, "files": preview.carousel(p, out), "caption": preview.caption(p, kind)}))
        else:
            imgs = preview.stories(p, out)
            pick = range(len(imgs)) if story is None else [story - 1]
            for i in pick:
                jobs.append((f"{sid}_S{i + 1:02d}", "story", {"video": None, "cover": None, "files": [imgs[i]], "caption": ""}))
    return jobs


def cmd_preview(a) -> int:
    """Race week fact posts for one round: Reel, carousel and/or stories (original artwork, own data).
    Stories go out one image per story, in order; each is recorded so none is ever posted twice."""
    from . import preview
    sb = store.client()
    ig = connect(sb, a.dry_run)
    if ig is not None and not getattr(ig, "sends_files", False):
        log.error("preview posts need the Upload-Post publisher")
        return 1
    if a.kind in ("insights", "reels_data") and not a.dry_run:
        log.error("kind insights is for review only: run it as a dry run")
        return 1
    p = preview.load(a.season, a.round)
    if a.dump:
        import dataclasses
        import pickle
        Path(a.dump).write_bytes(pickle.dumps(dataclasses.asdict(p)))
    sid = f"{a.season}_{a.round:02d}_PREVIEW"
    checks = p.stats | {"driver": p.driver, "lap_s": p.lap_s, "ref_year": p.ref_year, "sessions": p.sessions, "last_year": p.last_year}
    jobs = preview_jobs(p, sid, [a.kind] if a.kind else ["reel", "carousel"], a.out, a.season, a.story)
    if jobs is None:
        return 1
    report, failed = publish_jobs(sb, ig, jobs, checks)
    return finish(report, a.out, failed)


def cmd_refresh(a) -> int:
    sb = store.client()
    cfg = settings(sb)
    tok = token_of(cfg)
    if not tok:
        log.info("no token yet: nothing to refresh")
        return 0
    new, ttl = refresh_token(tok)
    exp = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat() if ttl else None
    sb.table("social_settings").upsert({"id": 1, "access_token": new, "token_expires_at": exp, "updated_at": now_iso()}).execute()
    log.info("token refreshed, expires %s", exp)
    return 0


def finish(report: list, out: str, failed: int) -> int:
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "report.json").write_text(json.dumps(report, indent=2, default=str))
    for r in report:
        print(f"{r['status']:>20}  {r['session_id']}  {r['kind']:<8}  {r.get('permalink') or r.get('reason') or ''}")
        if r.get("checks"):
            print(f"{'checks':>20}  {json.dumps(r['checks'], default=str)}")
        if r["status"].startswith("rendered") and r.get("caption"):        # dry run: show the exact caption
            for line in r["caption"].splitlines():
                print(f"{'caption |':>20}  {line}")
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pipeline.social")
    ap.add_argument("cmd", choices=["run", "rewind", "refresh", "preview", "hourly", "metrics", "optimize", "reel", "news"])
    ap.add_argument("--season", type=int, default=datetime.now(timezone.utc).year)
    ap.add_argument("--round", type=int, help="preview: round of the coming Grand Prix")
    ap.add_argument("--session", help="one session id, e.g. 2026_20_Q (default: ingested sessions from the last 72 h)")
    ap.add_argument("--kind", choices=KINDS + ("stories", "history", "history_carousel", "braking", "lap", "gears", "raceday", "starthere", "strategy", "insights", "titlemath", "reels_data"))
    ap.add_argument("--story", type=int, help="preview stories: post only story number N (1 = cover)")
    ap.add_argument("--dry-run", action="store_true", help="render only: no uploads, no rows, no posts")
    ap.add_argument("--force", action="store_true", help="rewind even while the season is running")
    ap.add_argument("--out", default="ig_out")
    ap.add_argument("--dump", help="preview: also save the lap data (pickle) for design work")
    ap.add_argument("--now", help="hourly: pretend it is this time (ISO), for testing")
    ap.add_argument("--news", help="news: post the grid penalty story of this driver code (gp_facts.NEWS, story: True) now")
    ap.add_argument("--reel", help="reel: post this telemetry Reel now (a reels_tel.REEL_SLOTS kind); its slot then stays done")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)   # request URLs can carry the token
    style.load_fonts()
    from .hourly import cmd_hourly
    from .metrics import cmd_metrics, cmd_optimize
    return {"run": cmd_run, "rewind": cmd_rewind, "refresh": cmd_refresh, "preview": cmd_preview,
            "hourly": cmd_hourly, "metrics": cmd_metrics, "optimize": cmd_optimize, "reel": cmd_reel, "news": cmd_news}[a.cmd](a)


def cmd_reel(a) -> int:
    """Post one telemetry Reel now, outside its slot (Michel asked, 17 Nov). Same id as the slot, so it never
    posts twice. Nothing else is posted by this command."""
    from . import preview, reels_tel
    from .hourly import TZ, where_are_we
    from ..openf1 import OpenF1
    sb = store.client()
    ig = connect(sb, a.dry_run)
    w = where_are_we(OpenF1(), datetime.now(TZ))
    p = preview.load(w["season"], w["round"])
    sid = f"{w['season']}_{w['round']:02d}_PREVIEW_REEL_{a.reel.upper()}"
    row = post_row(sb, sid, "reel", "session") if ig is not None else None
    if row and row["status"] == "published":
        log.info("reel %s already published", a.reel)
        return 0
    built = reels_tel.build(p, a.reel, Path(a.out) / f"reel_{a.reel}")
    if built is None:
        log.error("reel %s: data not in", a.reel)
        return 1
    video, cap = built
    jobs = [(sid, "reel", {"video": video, "cover": video.parent / "cover.jpg", "files": [], "caption": cap})]
    report, failed = publish_jobs(sb, ig, jobs, {"reel": a.reel, "manual": True})
    if ig is not None:
        sb.table("ig_posts").update({"content": f"reel {a.reel}"}).eq("session_id", sid).eq("kind", "reel").execute()
    return finish(report, a.out, failed)



def cmd_news(a) -> int:
    """Post one breaking news story now (Michel, 18 Nov: Piastri's grid penalty). One id per driver, so it never
    posts twice; its content key keeps the hourly news lane from showing him again."""
    from . import news, preview
    from .hourly import TZ, where_are_we
    from ..openf1 import OpenF1
    sb = store.client()
    ig = connect(sb, a.dry_run)
    w = where_are_we(OpenF1(), datetime.now(TZ))
    p = preview.load(w["season"], w["round"])
    preview.set_event(p)
    code = a.news.upper()
    from .gp_facts import SESSION_NEWS
    reports = SESSION_NEWS.get(p.title, {}).get(w["season"], {}).get(code)
    if reports:                                  # session report stories: FP1, FP2, FP3, Q, R
        report, failed = [], 0
        for i, it in enumerate(reports, 1):
            sid = f"{w['season']}_{w['round']:02d}_PREVIEW_NEWS_{code}_{i}"
            row = post_row(sb, sid, "story", "session") if ig is not None else None
            if row and row["status"] == "published":
                log.info("%s report %s already published", code, i)
                continue
            img = news.session_story(p, it).save(Path(a.out) / f"news_{code}_{i}.jpg")
            jobs = [(sid, "story", {"video": None, "cover": None, "files": [img], "caption": ""})]
            r, f = publish_jobs(sb, ig, jobs, {"news": f"{code} {i}", "manual": True})
            report += r
            failed += f
            if ig is not None:
                sb.table("ig_posts").update({"content": f"news {code} {i}"}).eq("session_id", sid).eq("kind", "story").execute()
            break                                # one now; the hourly posts the rest, one an hour, first in line
        return finish(report, a.out, failed)
    it = next((x for x in news.facts(p).get("penalties", []) if x.get("code") == code and x.get("story")), None)
    if it is None:
        log.error("no checked penalty story for %s", code)
        return 1
    sid = f"{w['season']}_{w['round']:02d}_PREVIEW_NEWS_PEN_{code}"
    row = post_row(sb, sid, "story", "session") if ig is not None else None
    if row and row["status"] == "published":
        log.info("penalty story %s already published", code)
        return 0
    img = news.penalty_story(p, it).save(Path(a.out) / f"news_penalty_{code}.jpg")
    jobs = [(sid, "story", {"video": None, "cover": None, "files": [img], "caption": ""})]
    report, failed = publish_jobs(sb, ig, jobs, {"news": f"penalty {code}", "manual": True})
    if ig is not None:
        sb.table("ig_posts").update({"content": f"news penalty {code}"}).eq("session_id", sid).eq("kind", "story").execute()
    return finish(report, a.out, failed)


if __name__ == "__main__":
    sys.exit(main())
