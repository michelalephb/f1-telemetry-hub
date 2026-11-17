"""Reads one session from Supabase (tables plus the public web bucket) and builds its story."""
from __future__ import annotations

import io
import json
import logging

import pandas as pd

from .. import store
from .story import StoryError, quali_story, race_story

log = logging.getLogger(__name__)
LAP_COLS = "driver_number,lap_number,lap_time_ms,sector1_ms,sector2_ms,sector3_ms,lap_start_s,lap_end_s,is_accurate,pit_in,pit_out"


def rows(sb, table: str, cols: str, **eq) -> pd.DataFrame:
    out, start = [], 0
    while True:  # PostgREST returns 1000 rows per page
        q = sb.table(table).select(cols)
        for k, v in eq.items():
            q = q.eq(k, v)
        page = q.range(start, start + 999).execute().data
        out += page
        if len(page) < 1000:
            return pd.DataFrame(out)
        start += 1000


def session_meta(sb, sid: str) -> dict:
    s = rows(sb, "sessions", "session_id,season,round,session_code,status,track_length_m,trace_prefix,start_utc", session_id=sid)
    if s.empty:
        raise StoryError(f"{sid}: no such session")
    s = s.iloc[0].to_dict()
    if s["status"] != "ingested" or not s["trace_prefix"]:
        raise StoryError(f"{sid}: status {s['status']}, nothing to post")
    e = rows(sb, "events", "event_name,country", season=s["season"], round=s["round"])
    s["event"] = e.iloc[0]["event_name"] if len(e) else f"Round {s['round']}"
    s["country"] = e.iloc[0]["country"] if len(e) else ""
    s["code"] = s["session_code"]
    return s


def rotation(sb, season: int, rnd: int) -> float:
    try:
        raw = sb.storage.from_(store.WEB_BUCKET).download(f"tracks/{season}/{rnd}.json")
        return float(json.loads(raw).get("rot", 0.0))
    except Exception as e:
        log.warning("no track outline rotation for %s/%s: %s", season, rnd, e)
        return 0.0


def trace(sb, prefix: str, driver: str) -> pd.DataFrame:
    return pd.read_parquet(io.BytesIO(sb.storage.from_(store.WEB_BUCKET).download(f"{prefix}trace_{driver}.parquet")))


def load_story(sb, sid: str):
    """(meta, story, rotation) for a session, or StoryError when it should not be posted."""
    m = session_meta(sb, sid)
    results = rows(sb, "results", "driver_number,driver_code,position,grid,status,q3_ms",
                   season=m["season"], round=m["round"], session_code=m["code"])
    if results.empty:
        raise StoryError(f"{sid}: no official result yet")
    results["driver_number"] = results["driver_number"].astype(str)
    laps = rows(sb, "laps", LAP_COLS, session_id=sid)
    laps["driver_number"] = laps["driver_number"].astype(str)
    drivers = rows(sb, "drivers", "driver_number,abbreviation,team_color", session_id=sid)
    drivers["driver_number"] = drivers["driver_number"].astype(str)
    if m["code"] in ("Q", "SQ"):
        corners = rows(sb, "corners", "corner,apex_m", session_id=sid)
        top = results[results["q3_ms"].notna()].sort_values("position").head(2)["driver_number"]
        traces = {d: trace(sb, m["trace_prefix"], d) for d in top}
        st = quali_story(results, laps, drivers, corners, traces, float(m["track_length_m"]))
    elif m["code"] in ("R", "S"):
        st = race_story(results, laps, drivers)
    else:
        raise StoryError(f"{sid}: session type {m['code']} is not posted")
    return m, st, rotation(sb, m["season"], m["round"])
