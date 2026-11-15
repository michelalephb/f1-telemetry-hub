"""Command line entry point.

python -m pipeline calendar --season 2026          sync events, sessions and results
python -m pipeline latest   --season 2026 --max 6  ingest finished sessions not yet stored
python -m pipeline round    --season 2026 --round 21 [--session Race] [--no-sync]
python -m pipeline rounds   --season 2026          JSON list of finished rounds (for the backfill matrix)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import fastf1
import pandas as pd

from . import jolpica, store
from .ingest import SESSION_CODES, NoData, ingest_session, session_id

log = logging.getLogger("pipeline")
SETTLE = timedelta(hours=3)        # wait this long after a session starts before ingesting
NO_DATA_RETRY = timedelta(days=3)  # keep retrying sessions with no data for this long


def schedule(season: int) -> list[dict]:
    """Every session of the season from FastF1's event schedule (testing excluded)."""
    sched = fastf1.get_event_schedule(season, include_testing=False)
    out = []
    for _, ev in sched.iterrows():
        rnd = int(ev["RoundNumber"])
        for i in range(1, 6):
            name, when = ev.get(f"Session{i}"), ev.get(f"Session{i}DateUtc")
            if not isinstance(name, str) or name not in SESSION_CODES:
                continue
            start = None
            if not pd.isna(when):
                ts = pd.Timestamp(when)
                start = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
            out.append({
                "season": season, "round": rnd, "session_name": name, "session_code": SESSION_CODES[name],
                "session_id": session_id(season, rnd, SESSION_CODES[name]),
                "start_utc": None if start is None else start.isoformat(),
                "event_format": ev.get("EventFormat"),
            })
    return out


def sync_calendar(sb, season: int) -> list[dict]:
    sess = schedule(season)
    try:
        events = jolpica.events(season)
    except Exception as e:
        log.warning("Jolpica calendar failed (%s), using FastF1 schedule", e)
        sched = fastf1.get_event_schedule(season, include_testing=False)
        events = [{"season": season, "round": int(r["RoundNumber"]), "event_name": r["EventName"],
                   "country": r["Country"], "location": r["Location"], "circuit_id": None,
                   "event_date": pd.Timestamp(r["EventDate"]).date().isoformat()} for _, r in sched.iterrows()]
    fmt = {s["round"]: s["event_format"] for s in sess}
    for e in events:
        e["event_format"] = fmt.get(e["round"])
    store.upsert(sb, "events", events, "season,round")
    known = {e["round"] for e in events}
    rows = [{k: s[k] for k in ("session_id", "season", "round", "session_code", "session_name", "start_utc")}
            for s in sess if s["round"] in known]
    store.upsert(sb, "sessions", rows, "session_id")

    now = datetime.now(timezone.utc)
    for e in events:
        if pd.Timestamp(e["event_date"]).tz_localize("UTC") + timedelta(days=1) < now:
            try:
                res = jolpica.results(season, e["round"])
                if res:
                    store.upsert(sb, "results", res, "season,round,session_code,driver_number")
            except Exception as ex:
                log.warning("results %s round %s failed: %s", season, e["round"], ex)
    return sess


def finished(sess: list[dict]) -> list[dict]:
    now = datetime.now(timezone.utc)
    return [s for s in sess if s["start_utc"] and pd.Timestamp(s["start_utc"]) + SETTLE < now]


def run_one(sb, s: dict, mode: str) -> bool:
    run = sb.table("ingest_runs").insert({"mode": mode, "session_id": s["session_id"]}).execute().data[0]
    ok, msg = False, ""
    try:
        ingest_session(sb, s["season"], s["round"], s["session_name"])
        ok, msg = True, "ingested"
    except NoData as e:
        msg = f"no data: {e}"
        sb.table("sessions").update({"status": "no_data", "error": msg}).eq("session_id", s["session_id"]).execute()
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"[:2000]
        log.exception("failed %s", s["session_id"])
        sb.table("sessions").update({"status": "failed", "error": msg}).eq("session_id", s["session_id"]).execute()
        if "RateLimit" in type(e).__name__:
            raise
    finally:
        sb.table("ingest_runs").update({"finished_at": datetime.now(timezone.utc).isoformat(), "ok": ok, "message": msg}).eq("id", run["id"]).execute()
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pipeline")
    ap.add_argument("cmd", choices=["calendar", "latest", "round", "rounds"])
    ap.add_argument("--season", type=int, default=datetime.now(timezone.utc).year)
    ap.add_argument("--round", type=int)
    ap.add_argument("--session", help="FastF1 session name, e.g. Race, Qualifying")
    ap.add_argument("--max", type=int, default=6, help="max sessions per run in latest mode")
    ap.add_argument("--no-sync", action="store_true", help="skip the calendar and results sync (backfill jobs)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    fastf1.Cache.enable_cache(os.environ.get("FASTF1_CACHE", ".fastf1_cache"))

    if a.cmd == "rounds":
        print(json.dumps(sorted({s["round"] for s in finished(schedule(a.season))})))
        return 0

    sb = store.client()
    sess = schedule(a.season) if a.no_sync else sync_calendar(sb, a.season)
    if a.cmd == "calendar":
        return 0

    if a.cmd == "round":
        todo = [s for s in finished(sess) if s["round"] == a.round and (not a.session or s["session_name"] == a.session)]
    else:  # latest
        state = {r["session_id"]: r for r in sb.table("sessions").select("session_id,status,start_utc").eq("season", a.season).execute().data}
        cutoff = datetime.now(timezone.utc) - NO_DATA_RETRY
        todo = []
        for s in finished(sess):
            st = state.get(s["session_id"], {}).get("status", "pending")
            if st in ("pending", "failed") or (st == "no_data" and pd.Timestamp(s["start_utc"]) > cutoff):
                todo.append(s)
        todo = sorted(todo, key=lambda s: s["start_utc"], reverse=True)[: a.max]

    log.info("%d session(s) to ingest: %s", len(todo), [s["session_id"] for s in todo])
    fails = 0
    for s in todo:
        try:
            fails += 0 if run_one(sb, s, a.cmd) else 1
        except Exception:
            log.error("rate limited, stopping this run; the next scheduled run continues")
            return 1
    return 1 if (a.cmd == "round" and fails) else 0


if __name__ == "__main__":
    sys.exit(main())
