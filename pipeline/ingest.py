"""Ingest one session from OpenF1: raw samples to Parquet, laps and corner metrics to Postgres.

Since 15 Oct 2026 F1's live timing archive requires an F1 TV login, so FastF1 cannot load
sessions without one. OpenF1 serves the same feed (car data ~240 ms, position ~240 ms) free.
FastF1 is still used for one thing: corner markers from the MultiViewer API.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import fastf1.mvapi
import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from . import store
from .geometry import CentreLine, build_centre_line
from .openf1 import OpenF1
from .process import corner_metrics, fuse_lap, pos_distance, refine_apexes

log = logging.getLogger(__name__)

SESSION_CODES = {
    "Practice 1": "FP1",
    "Practice 2": "FP2",
    "Practice 3": "FP3",
    "Qualifying": "Q",
    "Sprint Qualifying": "SQ",
    "Sprint Shootout": "SQ",
    "Sprint": "S",
    "Race": "R",
}
CENTRE_LINE_LAPS = 10
SAMPLE_MARGIN = timedelta(minutes=10)


class NoData(Exception):
    pass


def session_id(season: int, rnd: int, code: str) -> str:
    return f"{season}_{rnd:02d}_{code}"


# ---------------------------------------------------------------- OpenF1 to frames

def _secs(dates: pd.Series, t0: pd.Timestamp) -> pd.Series:
    return (pd.to_datetime(dates, format="ISO8601", utc=True) - t0).dt.total_seconds()


def laps_frame(laps: pd.DataFrame, stints: pd.DataFrame, pits: pd.DataFrame, sid: str, code: str, t0: pd.Timestamp) -> pd.DataFrame:
    if laps.empty:
        raise NoData("no laps")
    L = laps.sort_values(["driver_number", "lap_number"]).reset_index(drop=True)
    L["driver_number"] = L["driver_number"].astype(str)
    L["start"] = _secs(L["date_start"], t0) if "date_start" in L else np.nan
    dur = pd.to_numeric(L["lap_duration"], errors="coerce")
    nxt = L.groupby("driver_number")["start"].shift(-1)
    # a missing start (often lap 1) is recovered from the next lap's start minus this lap's duration
    L["start"] = L["start"].fillna(nxt - dur)
    L["end"] = (L["start"] + dur).fillna(nxt)

    pit_in = set()
    if not pits.empty:
        pit_in = set(zip(pits["driver_number"].astype(str), pits["lap_number"].astype(int)))
    L["pit_in"] = [(d, int(n)) in pit_in for d, n in zip(L["driver_number"], L["lap_number"])]
    L["pit_out"] = L["is_pit_out_lap"].fillna(False).astype(bool) if "is_pit_out_lap" in L else False

    L["compound"] = None
    L["stint"] = np.nan
    L["tyre_life"] = np.nan
    if not stints.empty:
        for _, st in stints.iterrows():
            if pd.isna(st.get("lap_start")) or pd.isna(st.get("lap_end")):
                continue
            m = (L["driver_number"] == str(st["driver_number"])) & (L["lap_number"] >= st["lap_start"]) & (L["lap_number"] <= st["lap_end"])
            L.loc[m, "compound"] = st.get("compound")
            L.loc[m, "stint"] = st.get("stint_number")
            age = st.get("tyre_age_at_start")
            if pd.notna(age):
                L.loc[m, "tyre_life"] = age + (L.loc[m, "lap_number"] - st["lap_start"])

    acc = dur.notna() & L["start"].notna() & ~L["pit_in"] & ~L["pit_out"]
    if code in ("R", "S"):
        acc &= L["lap_number"] > 1
    best = dur.where(acc).groupby(L["driver_number"]).transform("min")

    def ms(c):
        if c not in L:
            return pd.array([pd.NA] * len(L), dtype="Int64")
        return (pd.to_numeric(L[c], errors="coerce") * 1000).round().astype("Int64")

    return pd.DataFrame({
        "session_id": sid,
        "driver_number": L["driver_number"],
        "lap_number": L["lap_number"].astype("Int64"),
        "lap_time_ms": (dur * 1000).round().astype("Int64"),
        "sector1_ms": ms("duration_sector_1"),
        "sector2_ms": ms("duration_sector_2"),
        "sector3_ms": ms("duration_sector_3"),
        "lap_start_s": L["start"],
        "lap_end_s": L["end"],
        "compound": L["compound"],
        "tyre_life": pd.to_numeric(L["tyre_life"], errors="coerce").round().astype("Int64"),
        "stint": pd.to_numeric(L["stint"], errors="coerce").round().astype("Int64"),
        "pit_in": L["pit_in"].astype(bool),
        "pit_out": L["pit_out"],
        "is_personal_best": (acc & (dur == best)).astype(bool),
        "is_accurate": acc.astype(bool),
        "deleted": None,
        "track_status": None,
        "position": pd.array([pd.NA] * len(L), dtype="Int64"),
    }).dropna(subset=["lap_number"])


def fetch_session(oc: OpenF1, s: dict) -> dict:
    """Everything OpenF1 has for one session, on a session clock (seconds from session start)."""
    k = s["session_key"]
    t0 = pd.Timestamp(s["start_utc"])

    laps = oc.frame("laps", session_key=k)
    if laps.empty:
        raise NoData("OpenF1 has no laps")
    # Sample window from the laps actually driven, not the timetable: sessions get delayed
    # (São Paulo 2026 qualifying ran about 1.5 h late).
    starts = pd.to_datetime(laps["date_start"], format="ISO8601", utc=True)
    ends = starts + pd.to_timedelta(pd.to_numeric(laps["lap_duration"], errors="coerce").fillna(180), unit="s")
    lo = min(starts.min(), t0) if starts.notna().any() else t0
    hi = ends.max() if ends.notna().any() else (pd.Timestamp(s["end_utc"]) if s.get("end_utc") else t0 + timedelta(hours=3))
    win = [f"date>={(lo - SAMPLE_MARGIN).isoformat()}", f"date<={(hi + SAMPLE_MARGIN).isoformat()}"]
    log.info("%s: %d laps from OpenF1, %d with a duration", s["session_id"], len(laps), int(laps["lap_duration"].notna().sum()))
    drivers = oc.frame("drivers", session_key=k)
    stints = oc.frame("stints", session_key=k)
    pits = oc.frame("pit", session_key=k)

    car, pos = [], []
    for d in sorted(laps["driver_number"].astype(int).unique()):
        c = oc.frame("car_data", win, session_key=k, driver_number=d)
        p = oc.frame("location", win, session_key=k, driver_number=d)
        if not c.empty:
            car.append(pd.DataFrame({
                "driver_number": str(d), "date": pd.to_datetime(c["date"], format="ISO8601", utc=True), "t": _secs(c["date"], t0),
                "rpm": c["rpm"], "speed": c["speed"], "gear": c["n_gear"], "throttle": c["throttle"],
                "brake": c["brake"], "drs": c["drs"],
            }))
        if not p.empty:
            pos.append(pd.DataFrame({
                "driver_number": str(d), "date": pd.to_datetime(p["date"], format="ISO8601", utc=True), "t": _secs(p["date"], t0),
                "x": p["x"], "y": p["y"], "z": p["z"], "status": "OnTrack",
            }))
    if not car or not pos:
        raise NoData(f"OpenF1 has no car or location data in {win}")
    car = pd.concat(car, ignore_index=True).sort_values(["driver_number", "t"], ignore_index=True)
    pos = pd.concat(pos, ignore_index=True).sort_values(["driver_number", "t"], ignore_index=True)

    if drivers.empty:
        drivers = pd.DataFrame({"driver_number": laps["driver_number"].unique()})
    col = lambda c: drivers[c] if c in drivers else None
    drivers = pd.DataFrame({
        "driver_number": drivers["driver_number"].astype(str),
        "abbreviation": col("name_acronym"),
        "full_name": col("full_name"),
        "team_name": col("team_name"),
        "team_color": col("team_colour"),
    }).drop_duplicates("driver_number")
    return {"laps": laps, "stints": stints, "pits": pits, "car": car, "pos": pos, "drivers": drivers, "t0": t0}


def corner_markers(season: int, circuit_key) -> pd.DataFrame:
    """Corner markers (X, Y, Number, Letter, Angle) from MultiViewer, or empty."""
    if circuit_key is None or pd.isna(circuit_key):
        return pd.DataFrame()
    try:
        ci = fastf1.mvapi.get_circuit_info(year=season, circuit_key=int(circuit_key))
        return ci.corners.copy() if ci is not None else pd.DataFrame()
    except Exception as e:
        log.warning("MultiViewer corners failed: %s", e)
        return pd.DataFrame()


# ---------------------------------------------------------------- processing, source independent

def centre_line(laps: pd.DataFrame, pos: pd.DataFrame) -> CentreLine:
    """Centre line from the fastest accurate lap of up to 10 drivers, overall fastest first."""
    ok = laps[laps["is_accurate"] & laps["lap_time_ms"].notna()]
    best = ok.sort_values("lap_time_ms").groupby("driver_number").head(1).head(CENTRE_LINE_LAPS)
    tracks = []
    for _, lap in best.iterrows():
        p = pos[(pos["driver_number"] == lap["driver_number"]) & (pos["t"] >= lap["lap_start_s"]) & (pos["t"] <= lap["lap_end_s"])]
        if len(p) > 100:
            tracks.append(p[["x", "y", "z"]].to_numpy() / 10.0)
    if not tracks:
        raise NoData(f"no accurate lap to build a centre line ({len(ok)} accurate laps, {len(best)} candidates, "
                     f"position samples per candidate: {[int(((pos['driver_number'] == r.driver_number) & (pos['t'] >= r.lap_start_s) & (pos['t'] <= r.lap_end_s)).sum()) for r in best.itertuples()][:5]}; "
                     f"pos t {pos['t'].min():.0f}..{pos['t'].max():.0f} s ({len(pos)} rows, drivers {sorted(pos['driver_number'].unique())[:5]}); "
                     f"lap starts {ok['lap_start_s'].min():.0f}..{ok['lap_start_s'].max():.0f} s, drivers {sorted(ok['driver_number'].unique())[:5]})")
    return CentreLine(build_centre_line(tracks))


def auto_corners(ref_lap: pd.DataFrame, sid: str) -> pd.DataFrame:
    """Fallback when no markers exist: corners at the reference lap's speed minima."""
    lap = ref_lap[ref_lap["in_lap"]].sort_values("lap_dist_m")
    sp = lap["speed"].to_numpy().astype(float)
    spacing = max(float(np.median(np.diff(lap["lap_dist_m"].to_numpy()))), 1.0)
    idx, _ = find_peaks(-sp, prominence=25, distance=max(1, int(150 / spacing)))
    d = lap["lap_dist_m"].to_numpy()[idx]
    n = np.arange(1, len(idx) + 1)
    return pd.DataFrame({"session_id": sid, "corner": n.astype(str), "number": n, "letter": None,
                         "x": None, "y": None, "angle": None, "marker_m": d, "apex_m": d,
                         "prev_apex_m": np.concatenate([[np.nan], d[:-1]]),
                         "next_apex_m": np.concatenate([d[1:], [np.nan]])})


def store_session(sb, meta: dict, laps: pd.DataFrame, car: pd.DataFrame, pos: pd.DataFrame,
                  drivers: pd.DataFrame, markers: pd.DataFrame) -> dict:
    """Process and store one session. meta: sid, season, round, code, name."""
    sid, season, rnd, code = meta["sid"], meta["season"], meta["round"], meta["code"]
    line = centre_line(laps, pos)

    fused = []
    for drv, dpos in pos.groupby("driver_number"):
        dpos = pos_distance(dpos[["t", "x", "y", "z", "status"]], line)
        dcar = car[car["driver_number"] == drv].sort_values("t")
        for _, lap in laps[laps["driver_number"] == drv].iterrows():
            if pd.isna(lap["lap_start_s"]) or pd.isna(lap["lap_end_s"]):
                continue
            f = fuse_lap(dcar, dpos, lap["lap_start_s"], lap["lap_end_s"], line)
            if f is not None:
                f["lap_number"] = int(lap["lap_number"])
                fused.append(f)
    dist = pd.concat(fused, ignore_index=True) if fused else pd.DataFrame()

    corners, metrics, corner_source = pd.DataFrame(), [], None
    if len(dist):
        ref = laps[laps["is_accurate"] & laps["lap_time_ms"].notna()].sort_values("lap_time_ms").iloc[0]
        ref_lap = dist[(dist["driver_number"] == ref["driver_number"]) & (dist["lap_number"] == int(ref["lap_number"]))]
        if len(markers):
            flat = CentreLine(line.p[:, :2])
            s, _ = flat.project(markers[["X", "Y"]].to_numpy() / 10.0)
            letters = markers["Letter"].fillna("").astype(str)
            corners = pd.DataFrame({
                "session_id": sid,
                "corner": markers["Number"].astype(int).astype(str) + letters,
                "number": markers["Number"].astype(int),
                "letter": letters.where(letters != "", None),
                "x": markers["X"], "y": markers["Y"], "angle": markers["Angle"],
                "marker_m": s * line.length / flat.length,
            })
            corners = refine_apexes(corners, ref_lap)
            corner_source = "multiviewer"
        else:
            corners = auto_corners(ref_lap, sid)
            corner_source = "speed minima"
        for (drv, ln), lap in dist.groupby(["driver_number", "lap_number"]):
            for _, cr in corners.iterrows():
                m = corner_metrics(lap, cr["apex_m"], cr.get("prev_apex_m"), cr.get("next_apex_m"))
                if m:
                    metrics.append({"session_id": sid, "driver_number": drv, "lap_number": int(ln), "corner": cr["corner"], **m})

    base = f"{season}/{rnd:02d}/{code}"
    car_path = store.upload_parquet(sb, f"{base}/car_raw.parquet", car)
    pos_path = store.upload_parquet(sb, f"{base}/pos_raw.parquet", pos)
    # Distance only: join back to car_raw on (driver_number, t) for the channels. Keeps storage down.
    if len(dist):
        slim = dist[["driver_number", "lap_number", "t", "lap_dist_m", "in_lap"]].astype({"lap_dist_m": "float32", "lap_number": "int16"})
        dist_path = store.upload_parquet(sb, f"{base}/lap_distance.parquet", slim)
    else:
        dist_path = None

    store.delete_session_rows(sb, sid)
    store.upsert(sb, "sessions", [{
        "session_id": sid, "season": season, "round": rnd, "session_code": code, "session_name": meta["name"],
        "status": "ingested", "ingested_at": datetime.now(timezone.utc).isoformat(),
        "n_drivers": int(laps["driver_number"].nunique()), "n_laps": int(len(laps)),
        "track_length_m": round(line.length, 1), "car_path": car_path, "pos_path": pos_path,
        "dist_path": dist_path, "fastf1_version": f"source openf1; corners {corner_source}", "error": None,
    }], "session_id")
    store.upsert(sb, "drivers", store.records(drivers.assign(session_id=sid)), "session_id,driver_number")
    store.upsert(sb, "laps", store.records(laps), "session_id,driver_number,lap_number")
    if len(corners):
        store.upsert(sb, "corners", store.records(corners.drop(columns=["marker_m", "prev_apex_m", "next_apex_m"], errors="ignore")), "session_id,corner")
    if metrics:
        known = set(zip(laps["driver_number"], laps["lap_number"].astype(int)))
        rows = [m for m in metrics if (m["driver_number"], m["lap_number"]) in known]
        store.upsert(sb, "corner_metrics", store.records(pd.DataFrame(rows)), "session_id,driver_number,lap_number,corner")
    summary = {"sid": sid, "laps": len(laps), "car_samples": len(car), "corner_rows": len(metrics),
               "corners": len(corners), "corner_source": corner_source, "track_m": round(line.length, 1)}
    log.info("done %s", summary)
    return summary


def ingest_session(sb, oc: OpenF1, s: dict) -> dict:
    """s: one schedule entry (session_id, season, round, session_code, session_name, session_key, start_utc, end_utc, circuit_key)."""
    log.info("loading %s (%s, OpenF1 key %s)", s["session_id"], s["session_name"], s["session_key"])
    raw = fetch_session(oc, s)
    laps = laps_frame(raw["laps"], raw["stints"], raw["pits"], s["session_id"], s["session_code"], raw["t0"])
    markers = corner_markers(s["season"], s.get("circuit_key"))
    meta = {"sid": s["session_id"], "season": s["season"], "round": s["round"], "code": s["session_code"], "name": s["session_name"]}
    return store_session(sb, meta, laps, raw["car"], raw["pos"], raw["drivers"], markers)
