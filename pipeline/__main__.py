"""Command line entry point.

python -m pipeline calendar --season 2026          sync events, sessions and results
python -m pipeline latest   --season 2026 --max 6  ingest finished sessions not yet stored
python -m pipeline round    --season 2026 --round 20 [--session Race] [--no-sync]
python -m pipeline rounds   --season 2026          JSON list of finished rounds (for the backfill matrix)
python -m pipeline tracks   --season 2026          (re)build the track outlines from stored traces
python -m pipeline replay   --season 2026          (re)build race replays from stored traces
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
from . import replay, tracks
from .ingest import SESSION_CODES, NoData, corner_markers, ingest_session, session_id
from .openf1 import OpenF1

log = logging.getLogger("pipeline")
SETTLE = timedelta(hours=1)        # OpenF1 data is historical (free) 30 min after a session ends
NO_DATA_RETRY = timedelta(days=3)  # keep retrying sessions with no data for this long


def official_rounds(season: int) -> dict:
    """Round number by race date (UTC date string), from Jolpica, else FastF1's schedule."""
    try:
        return {e["event_date"]: e["round"] for e in jolpica.events(season)}
    except Exception as e:
        log.warning("Jolpica calendar failed (%s); using FastF1 schedule for round numbers", e)
    try:
        sched = fastf1.get_event_schedule(season, include_testing=False)
        return {pd.Timestamp(r["EventDate"]).date().isoformat(): int(r["RoundNumber"]) for _, r in sched.iterrows()}
    except Exception as e:
        log.warning("FastF1 schedule failed too (%s)", e)
        return {}


def schedule(oc: OpenF1, season: int, rounds_by_date: dict | None = None) -> list[dict]:
    """Every championship session of the season from OpenF1, numbered with the official rounds.

    A meeting gets the official round whose race date is within one day of its Race session
    (UTC vs local dates). Meetings with no Race session (testing) or no official match
    (OpenF1 lists events that are not in the championship calendar) are skipped.
    """
    sessions = oc.frame("sessions", year=season)
    meetings = oc.frame("meetings", year=season)
    if sessions.empty:
        return []
    if rounds_by_date is None:
        rounds_by_date = official_rounds(season)
    official = {pd.Timestamp(d): r for d, r in rounds_by_date.items()}
    sessions = sessions[sessions["session_name"].isin(SESSION_CODES)]
    races = sessions[sessions["session_name"] == "Race"].assign(
        d=lambda x: pd.to_datetime(x["date_start"], format="ISO8601", utc=True).dt.tz_localize(None).dt.normalize())
    rnd = {}
    for _, r in races.iterrows():
        near = [(abs((r["d"] - d).days), n) for d, n in official.items() if abs((r["d"] - d).days) <= 1]
        if near:
            rnd[r["meeting_key"]] = min(near)[1]
        else:
            log.info("OpenF1 meeting %s (race %s) has no official round, skipped", r["meeting_key"], r["d"].date())
    mt = meetings.set_index("meeting_key") if not meetings.empty else pd.DataFrame()
    out = []
    for _, s in sessions.iterrows():
        mk = s["meeting_key"]
        if mk not in rnd:
            continue
        code = SESSION_CODES[s["session_name"]]
        m = mt.loc[mk] if mk in mt.index else {}
        out.append({
            "season": season, "round": rnd[mk], "session_name": s["session_name"], "session_code": code,
            "session_id": session_id(season, rnd[mk], code), "session_key": int(s["session_key"]),
            "start_utc": s["date_start"], "end_utc": s.get("date_end"),
            "circuit_key": s.get("circuit_key", m.get("circuit_key") if len(m) else None),
            "meeting_name": m.get("meeting_name") if len(m) else None,
            "country": s.get("country_name"), "location": s.get("location"),
            "circuit_short_name": s.get("circuit_short_name"),
        })
    return sorted(out, key=lambda x: x["start_utc"])


def sync_calendar(sb, oc: OpenF1, season: int) -> list[dict]:
    try:
        jol = {e["round"]: e for e in jolpica.events(season)}
    except Exception as e:
        log.warning("Jolpica calendar failed (%s); using OpenF1 names", e)
        jol = {}
    sess = schedule(oc, season, {e["event_date"]: r for r, e in jol.items()} if jol else None)
    by_round: dict[int, list[dict]] = {}
    for s in sess:
        by_round.setdefault(s["round"], []).append(s)

    events = []
    for r, ss in sorted(by_round.items()):
        race = next((s for s in ss if s["session_code"] == "R"), ss[-1])
        j = jol.get(r, {})
        if j and race.get("meeting_name") and j["event_name"] != race["meeting_name"]:
            log.info("round %s name: Jolpica '%s', OpenF1 '%s'", r, j["event_name"], race["meeting_name"])
        events.append({
            "season": season, "round": r,
            "event_name": j.get("event_name") or race.get("meeting_name") or race.get("country"),
            "country": j.get("country") or race.get("country"),
            "location": j.get("location") or race.get("location"),
            "circuit_id": j.get("circuit_id") or race.get("circuit_short_name"),
            "event_date": pd.Timestamp(race["start_utc"]).date().isoformat(),
            "event_format": "sprint" if any(s["session_code"] == "S" for s in ss) else "conventional",
        })
    store.upsert(sb, "events", events, "season,round")
    store.upsert(sb, "sessions", [{k: s[k] for k in ("session_id", "season", "round", "session_code", "session_name", "start_utc")} for s in sess], "session_id")

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
    def end(s):
        e = s.get("end_utc") or s["start_utc"]
        return pd.Timestamp(e) + (SETTLE if s.get("end_utc") else timedelta(hours=4))
    return [s for s in sess if s.get("start_utc") and end(s) < now]


def run_one(sb, oc: OpenF1, s: dict, mode: str) -> bool:
    run = sb.table("ingest_runs").insert({"mode": mode, "session_id": s["session_id"]}).execute().data[0]
    ok, msg = False, ""
    try:
        summary = ingest_session(sb, oc, s)
        ok, msg = True, json.dumps(summary)
    except NoData as e:
        msg = f"no data: {e}"
        log.warning("%s: %s", s["session_id"], msg)
        sb.table("sessions").update({"status": "no_data", "error": msg}).eq("session_id", s["session_id"]).execute()
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"[:2000]
        log.exception("failed %s", s["session_id"])
        sb.table("sessions").update({"status": "failed", "error": msg}).eq("session_id", s["session_id"]).execute()
    finally:
        sb.table("ingest_runs").update({"finished_at": datetime.now(timezone.utc).isoformat(), "ok": ok, "message": msg[:2000]}).eq("id", run["id"]).execute()
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pipeline")
    ap.add_argument("cmd", choices=["calendar", "latest", "round", "rounds", "tracks", "replay"])
    ap.add_argument("--season", type=int, default=datetime.now(timezone.utc).year)
    ap.add_argument("--round", type=int)
    ap.add_argument("--session", help="session name, e.g. Race, Qualifying")
    ap.add_argument("--max", type=int, default=6, help="max sessions per run in latest mode")
    ap.add_argument("--no-sync", action="store_true", help="skip the calendar and results sync (backfill jobs)")
    ap.add_argument("--dry-run", action="store_true", help="process for real but write nothing; print a quality report")
    ap.add_argument("--codes", default="FP1,FP2,FP3,SQ,S,Q,R", help="session codes to ingest, e.g. R,Q,S,SQ")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cache_dir = os.environ.get("FASTF1_CACHE", ".fastf1_cache")
    os.makedirs(cache_dir, exist_ok=True)  # FastF1 (corner markers only) needs an existing cache dir
    fastf1.Cache.configure(cache_dir=cache_dir)
    oc = OpenF1()

    if a.cmd == "rounds":
        print(json.dumps(sorted({s["round"] for s in finished(schedule(oc, a.season))})))
        return 0

    if a.cmd == "tracks":
        return build_tracks(store.client(), oc, a.season)
    if a.cmd == "replay":
        return build_replays(store.client(), a.season)

    if a.dry_run:
        from .dryrun import DryClient, report
        sb = DryClient()
    else:
        sb = store.client()
    sess = schedule(oc, a.season) if a.no_sync else sync_calendar(sb, oc, a.season)
    if a.cmd == "calendar":
        return 0

    if a.cmd == "round":
        todo = [s for s in finished(sess) if s["round"] == a.round and (not a.session or s["session_name"] == a.session)]
    else:  # latest
        state = {r["session_id"]: r for r in sb.table("sessions").select("session_id,status").eq("season", a.season).execute().data}
        cutoff = datetime.now(timezone.utc) - NO_DATA_RETRY
        todo = []
        for s in finished(sess):
            st = state.get(s["session_id"], {}).get("status", "pending")
            if st in ("pending", "failed") or (st == "no_data" and pd.Timestamp(s["start_utc"]) > cutoff):
                todo.append(s)
        todo = sorted(todo, key=lambda s: s["start_utc"], reverse=True)[: a.max]

    codes = {c.strip() for c in a.codes.split(",") if c.strip()}
    todo = [s for s in todo if s["session_code"] in codes]
    log.info("%d session(s) to ingest: %s", len(todo), [s["session_id"] for s in todo])
    results = {s["session_id"]: run_one(sb, oc, s, a.cmd) for s in todo}
    fails = sum(0 if ok else 1 for ok in results.values())
    if a.dry_run:
        for r in sb.db.get("ingest_runs", []):
            print("run", r["session_id"])
        print(report(sb))
    if a.cmd == "latest" and not a.dry_run:
        return health(sb, sess, codes, results)
    return 1 if (a.cmd == "round" and fails) else 0


def build_tracks(sb, oc: OpenF1, season: int) -> int:
    """Outline for every round that has a stored trace (prefers the race, then qualifying)."""
    keys = {s["round"]: s.get("circuit_key") for s in schedule(oc, season)}
    rows = sb.table("sessions").select("round,session_code,trace_prefix").eq("season", season).eq("status", "ingested").execute().data
    pref = {"R": 0, "Q": 1, "S": 2, "SQ": 3}
    best: dict[int, dict] = {}
    for r in rows:
        if r["trace_prefix"] and r["session_code"] in pref:
            if r["round"] not in best or pref[r["session_code"]] < pref[best[r["round"]]["session_code"]]:
                best[r["round"]] = r
    fails = 0
    for rnd, r in sorted(best.items()):
        try:
            files = sb.storage.from_(store.WEB_BUCKET).list(r["trace_prefix"].rstrip("/"))
            name = next(f["name"] for f in files if f["name"].startswith("trace_"))
            tr = tracks.read_trace(sb, store.WEB_BUCKET, r["trace_prefix"] + name)
            rot = corner_markers(season, keys.get(rnd)).attrs.get("rotation", 0.0)
            path = tracks.upload(sb, season, rnd, tracks.outline(tracks.lap_xy_from_trace(tr), rot), store.WEB_BUCKET)
            log.info("round %s: %s (from %s%s, rotation %s)", rnd, path, r["trace_prefix"], name, rot)
        except Exception as e:
            fails += 1
            log.error("round %s outline failed: %s", rnd, e)
    return 1 if fails else 0


def build_replays(sb, season: int) -> int:
    """Replay file for every race and sprint race that has stored traces."""
    rows = sb.table("sessions").select("session_id,session_code,trace_prefix,track_length_m").eq("season", season) \
        .eq("status", "ingested").in_("session_code", ["R", "S"]).execute().data
    fails = 0
    for r in sorted(rows, key=lambda x: x["session_id"]):
        if not r["trace_prefix"] or not r["track_length_m"]:
            continue
        try:
            files = sb.storage.from_(store.WEB_BUCKET).list(r["trace_prefix"].rstrip("/"), {"limit": 100})
            names = [f["name"] for f in files if f["name"].startswith("trace_")]
            traces = {n[len("trace_"):-len(".parquet")]: tracks.read_trace(sb, store.WEB_BUCKET, r["trace_prefix"] + n) for n in names}
            df = replay.build(traces, float(r["track_length_m"]))
            path = replay.upload(sb, r["trace_prefix"] + "replay.parquet", df, store.WEB_BUCKET)
            log.info("%s: %s (%d drivers, %d s)", r["session_id"], path, len(df.columns) - 1, len(df))
        except Exception as e:
            fails += 1
            log.error("%s replay failed: %s", r["session_id"], e)
    return 1 if fails else 0


def health(sb, sess: list[dict], codes: set[str], results: dict[str, bool]) -> int:
    """Fail the scheduled job (GitHub then emails the owner) when the site is missing recent data.

    Red when a session failed in this run, or when a session that ended between 3 hours and
    7 days ago is still not ingested (no_data included: OpenF1 normally has it within an hour).
    """
    now = datetime.now(timezone.utc)
    state = {r["session_id"]: r for r in sb.table("sessions").select("session_id,status,error").execute().data}
    late = []
    for s in sess:
        end = pd.Timestamp(s.get("end_utc") or s["start_utc"])
        if s["session_code"] in codes and now - timedelta(days=7) < end < now - timedelta(hours=3):
            st = state.get(s["session_id"], {})
            if st.get("status") != "ingested":
                late.append(f"{s['session_id']} ({st.get('status', 'missing')}: {(st.get('error') or '')[:120]})")
    failed = [sid for sid, ok in results.items() if not ok]
    for sid in failed:
        log.error("HEALTH: %s failed in this run", sid)
    for x in late:
        log.error("HEALTH: recent session not on the site: %s", x)
    if not failed and not late:
        log.info("HEALTH: every session from the last 7 days is on the site")
    return 1 if failed or late else 0


if __name__ == "__main__":
    sys.exit(main())
