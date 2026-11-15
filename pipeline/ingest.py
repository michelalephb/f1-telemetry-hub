"""Ingest one session with FastF1: raw samples to Parquet, laps and corner metrics to Postgres."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import fastf1
import numpy as np
import pandas as pd

from . import store
from .geometry import CentreLine, build_centre_line
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


class NoData(Exception):
    pass


def session_id(season: int, rnd: int, code: str) -> str:
    return f"{season}_{rnd:02d}_{code}"


def _secs(td: pd.Series) -> pd.Series:
    return td.dt.total_seconds()


def _ms(td: pd.Series) -> pd.Series:
    return (td.dt.total_seconds() * 1000).round().astype("Int64")


def raw_frames(session) -> tuple[pd.DataFrame, pd.DataFrame]:
    """All drivers' raw car and position samples, unmerged and not resampled."""
    car, pos = [], []
    for drv, df in session.car_data.items():
        d = pd.DataFrame(df).copy()
        car.append(pd.DataFrame({
            "driver_number": str(drv), "date": d["Date"], "t": _secs(d["SessionTime"]),
            "rpm": d["RPM"], "speed": d["Speed"], "gear": d["nGear"], "throttle": d["Throttle"],
            "brake": d["Brake"].astype(bool), "drs": d["DRS"],
        }))
    for drv, df in session.pos_data.items():
        d = pd.DataFrame(df).copy()
        pos.append(pd.DataFrame({
            "driver_number": str(drv), "date": d["Date"], "t": _secs(d["SessionTime"]),
            "x": d["X"], "y": d["Y"], "z": d["Z"], "status": d["Status"],
        }))
    if not car or not pos:
        raise NoData("no car or position data")
    return pd.concat(car, ignore_index=True), pd.concat(pos, ignore_index=True)


def laps_frame(session, sid: str) -> pd.DataFrame:
    L = session.laps
    if L is None or len(L) == 0:
        raise NoData("no laps")
    return pd.DataFrame({
        "session_id": sid,
        "driver_number": L["DriverNumber"].astype(str),
        "lap_number": L["LapNumber"].astype("Int64"),
        "lap_time_ms": _ms(L["LapTime"]),
        "sector1_ms": _ms(L["Sector1Time"]),
        "sector2_ms": _ms(L["Sector2Time"]),
        "sector3_ms": _ms(L["Sector3Time"]),
        "lap_start_s": _secs(L["LapStartTime"]),
        "lap_end_s": _secs(L["Time"]),
        "compound": L["Compound"],
        "tyre_life": L["TyreLife"].astype("Int64"),
        "stint": L["Stint"].astype("Int64"),
        "pit_in": L["PitInTime"].notna(),
        "pit_out": L["PitOutTime"].notna(),
        "is_personal_best": L["IsPersonalBest"].fillna(False).astype(bool),
        "is_accurate": L["IsAccurate"].fillna(False).astype(bool),
        "deleted": L["Deleted"].fillna(False).astype(bool) if "Deleted" in L else False,
        "track_status": L["TrackStatus"],
        "position": L["Position"].astype("Int64"),
    }).dropna(subset=["lap_number"])


def centre_line(laps: pd.DataFrame, pos: pd.DataFrame) -> CentreLine:
    """Centre line from the fastest accurate lap of up to 10 drivers, overall fastest first."""
    ok = laps[laps["is_accurate"] & laps["lap_time_ms"].notna() & ~laps["pit_in"] & ~laps["pit_out"]]
    best = ok.sort_values("lap_time_ms").groupby("driver_number").head(1).head(CENTRE_LINE_LAPS)
    tracks = []
    for _, lap in best.iterrows():
        p = pos[(pos["driver_number"] == lap["driver_number"]) & (pos["t"] >= lap["lap_start_s"]) & (pos["t"] <= lap["lap_end_s"])]
        p = p[p["status"].fillna("OnTrack") == "OnTrack"]
        if len(p) > 100:
            tracks.append(p[["x", "y", "z"]].to_numpy() / 10.0)
    if not tracks:
        raise NoData("no accurate lap to build a centre line")
    return CentreLine(build_centre_line(tracks))


def ingest_session(sb, season: int, rnd: int, name: str, force: bool = False) -> str:
    code = SESSION_CODES[name]
    sid = session_id(season, rnd, code)
    log.info("loading %s (%s)", sid, name)

    session = fastf1.get_session(season, rnd, name)
    session.load(laps=True, telemetry=True, weather=False, messages=True)

    laps = laps_frame(session, sid)
    car, pos = raw_frames(session)
    line = centre_line(laps, pos)

    # Distance for every car sample, lap by lap
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

    # Corners: markers projected onto the centre line, apex = reference lap min speed nearby
    corners = pd.DataFrame()
    metrics = []
    try:
        ci = session.get_circuit_info()
        c = ci.corners.copy() if ci is not None else pd.DataFrame()
    except Exception as e:  # circuit info is optional
        log.warning("no circuit info: %s", e)
        c = pd.DataFrame()
    if len(c) and len(dist):
        flat = CentreLine(line.p[:, :2])
        s, _ = flat.project(c[["X", "Y"]].to_numpy() / 10.0)
        corners = pd.DataFrame({
            "session_id": sid,
            "corner": c["Number"].astype(int).astype(str) + c["Letter"].fillna("").astype(str),
            "number": c["Number"].astype(int),
            "letter": c["Letter"].fillna("").astype(str).where(c["Letter"].fillna("").astype(str) != "", None),
            "x": c["X"], "y": c["Y"], "angle": c["Angle"],
            "marker_m": s * line.length / flat.length,
        })
        ref = laps[laps["is_accurate"] & laps["lap_time_ms"].notna()].sort_values("lap_time_ms").iloc[0]
        ref_lap = dist[(dist["driver_number"] == ref["driver_number"]) & (dist["lap_number"] == int(ref["lap_number"]))]
        corners = refine_apexes(corners, ref_lap)
        for (drv, ln), lap in dist.groupby(["driver_number", "lap_number"]):
            for _, cr in corners.iterrows():
                m = corner_metrics(lap, cr["apex_m"])
                if m:
                    metrics.append({"session_id": sid, "driver_number": drv, "lap_number": int(ln), "corner": cr["corner"], **m})

    # Parquet: raw stays raw; processed carries distance
    base = f"{season}/{rnd:02d}/{code}"
    car_path = store.upload_parquet(sb, f"{base}/car_raw.parquet", car)
    pos_path = store.upload_parquet(sb, f"{base}/pos_raw.parquet", pos)
    dist_cols = ["driver_number", "lap_number", "t", "lap_dist_m", "in_lap", "speed", "throttle", "brake", "gear", "rpm", "drs", "fit_scale"]
    dist_path = store.upload_parquet(sb, f"{base}/lap_distance.parquet", dist[dist_cols]) if len(dist) else None

    drivers = pd.DataFrame({
        "session_id": sid,
        "driver_number": session.results["DriverNumber"].astype(str),
        "abbreviation": session.results["Abbreviation"],
        "full_name": session.results["FullName"],
        "team_name": session.results["TeamName"],
        "team_color": session.results["TeamColor"],
    })

    store.delete_session_rows(sb, sid)
    store.upsert(sb, "sessions", [{
        "session_id": sid, "season": season, "round": rnd, "session_code": code, "session_name": name,
        "status": "ingested", "ingested_at": datetime.now(timezone.utc).isoformat(),
        "n_drivers": int(laps["driver_number"].nunique()), "n_laps": int(len(laps)),
        "track_length_m": round(line.length, 1), "car_path": car_path, "pos_path": pos_path,
        "dist_path": dist_path, "fastf1_version": fastf1.__version__, "error": None,
    }], "session_id")
    store.upsert(sb, "drivers", store.records(drivers), "session_id,driver_number")
    store.upsert(sb, "laps", store.records(laps), "session_id,driver_number,lap_number")
    if len(corners):
        store.upsert(sb, "corners", store.records(corners.drop(columns=["marker_m"])), "session_id,corner")
    if metrics:
        known = set(zip(laps["driver_number"], laps["lap_number"].astype(int)))
        rows = [m for m in metrics if (m["driver_number"], m["lap_number"]) in known]
        store.upsert(sb, "corner_metrics", store.records(pd.DataFrame(rows)), "session_id,driver_number,lap_number,corner")
    log.info("%s done: %d laps, %d car samples, %d corner rows, track %.0f m", sid, len(laps), len(car), len(metrics), line.length)
    return sid
