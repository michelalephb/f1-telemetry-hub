"""Pure story logic, no I/O: which comparison a session's post is about, and the numbers in it.

Qualifying (Q, SQ): pole lap against P2, final segment laps only, matched to the official times.
Race (R, S): winner, gaps to the winner lap by lap for the top 5, and the biggest mover.

Every story carries checks against the official result. A story that fails a check is not posted.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

GRID_STEP_M = 5.0
LINE_TOLERANCE_S = 0.05      # computed gap at the line vs official gap (São Paulo Q: 5.5 ms)
SECTOR_TOLERANCE_S = 0.15    # raw gap at the official sector splits (São Paulo Q: about 0.1 s off mid lap)
LAP_MATCH_MS = 30            # OpenF1 lap duration vs official Q3 time
MIN_SPEED_KPH = 3.0          # smaller apex speed differences are within sampling noise
APEX_WINDOW_M = 60.0         # minimum speed is taken within this distance of the marked apex
BRAKING_RATIO = 0.85         # a corner counts when its apex speed is below 85 % of the speed around it


class StoryError(Exception):
    """The data does not support a post (missing, or disagrees with the official result)."""


@dataclass
class Lap:
    driver: str
    code: str
    color: str
    lap_number: int
    lap_ms: int
    dist: np.ndarray
    time: np.ndarray
    speed: np.ndarray
    throttle: np.ndarray
    brake: np.ndarray
    x: np.ndarray
    y: np.ndarray


@dataclass
class CornerSpeed:
    corner: str
    apex_m: float
    min_a: float             # lowest speed within APEX_WINDOW_M of the apex, km/h
    min_b: float

    @property
    def diff(self) -> float:  # positive = A carried more speed
        return self.min_a - self.min_b


@dataclass
class QualiStory:
    """Time claims come only from official timing (lap and sector times). Corner claims are apex
    speeds, which do not depend on aligning the two laps: at 240 ms sampling, a few metres of
    alignment error through a slow apex is worth 0.1 to 0.2 s, so per corner time gains are not
    published."""
    kind: str                # "quali"
    a: Lap                   # pole
    b: Lap                   # P2
    official_gap_s: float
    sector_gaps: list[float]  # per sector, B minus A, s (positive = A faster), official sector times
    split_m: list[float]      # distance of the S1 and S2 splits on A's lap
    best_a: CornerSpeed       # where pole carried the most extra apex speed
    best_b: CornerSpeed | None  # where P2 did (None if nowhere by MIN_SPEED_KPH)
    track_m: float
    checks: dict = field(default_factory=dict)


@dataclass
class RaceStory:
    kind: str                # "race"
    winner: dict
    podium: list[dict]
    mover: dict | None       # {"code", "color", "grid", "position", "gained"}
    gaps: dict               # code -> gap to the winner at the flag, s (podium)
    colors: dict
    positions: dict          # code -> position per lap (index = lap number, 0 = grid), top 5 plus the mover
    n_laps: int
    checks: dict = field(default_factory=dict)


# ---------------------------------------------------------------- laps

def lap_trace(rows: pd.DataFrame, lap: int, track_m: float) -> pd.DataFrame:
    """Same rules as the site (web/lib/telemetry.ts lapTrace): window, frozen samples, clock at the line."""
    s = rows[(rows["lap_number"] == lap) & (rows["lap_dist_m"] >= -40) & (rows["lap_dist_m"] <= track_m + 40)].sort_values("t")
    if len(s) < 50:
        raise StoryError(f"lap {lap}: only {len(s)} samples")
    cols = ["speed", "rpm", "gear", "throttle", "brake"]
    same = (s[cols].shift() == s[cols]).all(axis=1) & (s["speed"] > 0)
    s = s[~same].copy()
    s["lap_dist_m"] = np.maximum.accumulate(s["lap_dist_m"].to_numpy(dtype=float))
    d, t = s["lap_dist_m"].to_numpy(dtype=float), s["t"].to_numpy(dtype=float)
    s["t"] = t - _extrap(0.0, d, t)
    return s


def _extrap(x: float, xs: np.ndarray, ys: np.ndarray) -> float:
    if x < xs[0]:
        i, j = 0, 1
    elif x > xs[-1]:
        i, j = len(xs) - 2, len(xs) - 1
    else:
        return float(np.interp(x, xs, ys))
    return float(ys[i] + (x - xs[i]) / ((xs[j] - xs[i]) or 1) * (ys[j] - ys[i]))


def to_lap(tr: pd.DataFrame, driver: str, code: str, color: str, lap_number: int, lap_ms: int) -> Lap:
    return Lap(driver, code, color, lap_number, lap_ms,
               tr["lap_dist_m"].to_numpy(float), tr["t"].to_numpy(float), tr["speed"].to_numpy(float),
               tr["throttle"].to_numpy(float), tr["brake"].to_numpy(float), tr["x"].to_numpy(float), tr["y"].to_numpy(float))


def time_at(lap: Lap, d: np.ndarray) -> np.ndarray:
    out = np.interp(d, lap.dist, lap.time)
    end = d > lap.dist[-1]
    if end.any():  # extend past the last sample so the gap at the line is exact
        out[end] = [_extrap(v, lap.dist, lap.time) for v in d[end]]
    return out


def final_segment_laps(laps: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    """Laps in Q3 / SQ3: after the last lap of every driver who did not reach it (site rule)."""
    # A driver can reach Q3 and set no time (Miami 2026), so the top ten count too
    top = results["position"].notna() & (results["position"] <= 10) if "position" in results else False
    inq3 = set(results.loc[results["q3_ms"].notna() | top, "driver_number"].astype(str))
    if not inq3 or len(results) <= len(inq3):
        raise StoryError("no final segment in the official result")
    # Ignore "laps" that span a garage stop (longer than twice the fastest lap): they bridge the break
    best = laps["lap_time_ms"].dropna()
    dur = laps["lap_end_s"] - laps["lap_start_s"]
    real = dur < 2 * best.min() / 1000 if len(best) else dur.notna()
    # Only drivers knocked out with an official time mark the end of Q2 (a driver with no time may have run in Q3)
    timed = results[[c for c in ("q1_ms", "q2_ms") if c in results]].notna().any(axis=1) if {"q1_ms", "q2_ms"} & set(results) else True
    knocked = set(results.loc[~results["driver_number"].astype(str).isin(inq3) & timed, "driver_number"].astype(str))
    out = laps[laps["driver_number"].isin(knocked) & laps["lap_end_s"].notna() & real]
    if out.empty:
        raise StoryError("cannot place the start of the final segment")
    cut = out["lap_end_s"].max()
    return laps[laps["driver_number"].isin(inq3) & (laps["lap_start_s"] >= cut)]


def match_lap(q3: pd.DataFrame, driver: str, official_ms: int) -> pd.Series:
    mine = q3[(q3["driver_number"] == driver) & q3["lap_time_ms"].notna()]
    if mine.empty:
        raise StoryError(f"driver {driver}: no final segment lap")
    i = (mine["lap_time_ms"] - official_ms).abs().idxmin()
    if abs(int(mine.loc[i, "lap_time_ms"]) - official_ms) > LAP_MATCH_MS:
        raise StoryError(f"driver {driver}: no lap within {LAP_MATCH_MS} ms of the official {official_ms} ms")
    return mine.loc[i]


# ---------------------------------------------------------------- qualifying

def apex_min(L: Lap, lo: float, hi: float) -> float | None:
    """Lowest speed between lo and hi, only if it is a true local minimum (not at either edge)."""
    m = (L.dist >= lo) & (L.dist <= hi)
    sp = L.speed[m]
    if len(sp) < 3:
        return None
    i = int(np.argmin(sp))
    return float(sp[i]) if 0 < i < len(sp) - 1 else None


def corner_speeds(a: Lap, b: Lap, corners: pd.DataFrame) -> list[CornerSpeed]:
    """Apex speed per corner, from each corner's own stretch (never reaching into the next corner),
    braking corners only: flat out kinks have no apex speed worth comparing."""
    c = corners.sort_values("apex_m").reset_index(drop=True)
    apex = c["apex_m"].to_numpy(float)
    out = []
    for k, row in c.iterrows():
        half = APEX_WINDOW_M
        if k > 0:
            half = min(half, 0.45 * (apex[k] - apex[k - 1]))
        if k < len(c) - 1:
            half = min(half, 0.45 * (apex[k + 1] - apex[k]))
        lo, hi = apex[k] - half, apex[k] + half
        ma, mb = apex_min(a, lo, hi), apex_min(b, lo, hi)
        if ma is None or mb is None:
            continue
        around = a.speed[(a.dist >= apex[k] - 250) & (a.dist <= apex[k] + 150)]
        if len(around) == 0 or ma > BRAKING_RATIO * around.max():
            continue
        out.append(CornerSpeed(str(row["corner"]), float(apex[k]), ma, mb))
    return out


def quali_story(results: pd.DataFrame, laps: pd.DataFrame, drivers: pd.DataFrame, corners: pd.DataFrame,
                traces: dict[str, pd.DataFrame], track_m: float) -> QualiStory:
    res = results[results["position"].notna()].sort_values("position")
    res = res[res["q3_ms"].notna()]
    if len(res) < 2:
        raise StoryError("official result has fewer than two final segment times")
    p1, p2 = res.iloc[0], res.iloc[1]
    q3 = final_segment_laps(laps, results)
    out, picked = [], []
    for r in (p1, p2):
        drv = str(r["driver_number"])
        lap = match_lap(q3, drv, int(r["q3_ms"]))
        if drv not in traces:
            raise StoryError(f"no trace for driver {drv}")
        info = drivers.set_index("driver_number").loc[drv] if drv in set(drivers["driver_number"]) else {}
        tr = lap_trace(traces[drv], int(lap["lap_number"]), track_m)
        code = (info.get("abbreviation") if len(info) else None) or r.get("driver_code") or drv
        out.append(to_lap(tr, drv, code, team_color(info.get("team_color") if len(info) else None), int(lap["lap_number"]), int(lap["lap_time_ms"])))
        picked.append(lap)
    a, b = out
    if colors_close(a.color, b.color):
        b.color = "#FFFFFF"

    # The traces must be the right laps: their gap at the line and at the splits must agree with timing.
    grid = np.arange(0.0, track_m + GRID_STEP_M / 2, GRID_STEP_M)
    grid[-1] = track_m
    delta = time_at(b, grid) - time_at(a, grid)
    official = (int(p2["q3_ms"]) - int(p1["q3_ms"])) / 1000.0
    checks = {"gap_at_line_s": round(float(delta[-1]), 3), "official_gap_s": official,
              "line_error_ms": round(abs(float(delta[-1]) - official) * 1000, 1)}
    if abs(delta[-1] - official) > LINE_TOLERANCE_S:
        raise StoryError(f"computed gap {delta[-1]:.3f} s vs official {official:.3f} s")
    la, lb = picked
    secs = []
    for k in ("sector1_ms", "sector2_ms", "sector3_ms"):
        if pd.isna(la.get(k)) or pd.isna(lb.get(k)):
            raise StoryError(f"no official {k[:7]} time for both laps")
        secs.append((float(lb[k]) - float(la[k])) / 1000)
    checks["sector_gaps_s"] = [round(x, 3) for x in secs]
    if abs(sum(secs) - official) > 0.003:
        raise StoryError(f"sector gaps add up to {sum(secs):.3f} s, lap gap is {official:.3f} s")
    split_m = sector_splits(a, b, la, lb, grid, delta, checks)

    speeds = corner_speeds(a, b, corners)
    if not speeds:
        raise StoryError("no corner apex speeds")
    best_a = max(speeds, key=lambda c: c.diff)
    best_b = min(speeds, key=lambda c: c.diff)
    if best_a.diff < MIN_SPEED_KPH:
        raise StoryError(f"pole carried no apex speed advantage of {MIN_SPEED_KPH} km/h anywhere")
    return QualiStory("quali", a, b, official, secs, split_m, best_a,
                      best_b if -best_b.diff >= MIN_SPEED_KPH else None, track_m, checks)


def sector_splits(a: Lap, b: Lap, la: pd.Series, lb: pd.Series, grid: np.ndarray, delta: np.ndarray, checks: dict) -> list[float]:
    """Distances of the S1 and S2 splits on A's lap, plus a sanity check that the traces agree with
    timing there (a wrong lap or a broken trace misses by far more than SECTOR_TOLERANCE_S)."""
    out, errs, ta, tb = [], [], 0.0, 0.0
    for k in ("sector1_ms", "sector2_ms"):
        ta += float(la[k]) / 1000
        tb += float(lb[k]) / 1000
        d = float(np.interp(ta, a.time, a.dist))
        raw = float(np.interp(d, grid, delta))
        errs.append(round((raw - (tb - ta)) * 1000, 1))
        if abs(raw - (tb - ta)) > SECTOR_TOLERANCE_S:
            raise StoryError(f"trace gap at the {k[:7]} split is {raw:.3f} s, official {tb - ta:.3f} s")
        out.append(d)
    checks["trace_vs_split_ms"] = errs
    checks["split_m"] = [round(x) for x in out]
    if not 0 < out[0] < out[1] < grid[-1]:
        raise StoryError(f"sector splits out of order: {out}")
    return out


# ---------------------------------------------------------------- race

def orders_by_lap(laps: pd.DataFrame) -> dict[int, list[str]]:
    """Running order at the end of each lap: drivers who completed the lap, by the time they did."""
    L = laps[laps["lap_end_s"].notna()]
    return {int(n): g.sort_values("lap_end_s")["driver_number"].astype(str).tolist() for n, g in L.groupby("lap_number")}


def race_story(results: pd.DataFrame, laps: pd.DataFrame, drivers: pd.DataFrame) -> RaceStory:
    res = results[results["position"].notna()].sort_values("position")
    if len(res) < 3:
        raise StoryError("official result has fewer than three classified drivers")
    info = drivers.set_index("driver_number") if len(drivers) else pd.DataFrame()
    def who(r):
        d = str(r["driver_number"])
        code = (info.loc[d, "abbreviation"] if d in info.index else None) or r.get("driver_code") or d
        return {"driver": d, "code": code, "color": team_color(info.loc[d, "team_color"] if d in info.index else None),
                "grid": _int(r.get("grid")), "position": int(r["position"])}
    top = [who(r) for _, r in res.head(5).iterrows()]
    winner = top[0]
    seen = []
    for t in top:  # teammates share a colour: lighten the second one
        if any(colors_close(t["color"], s) for s in seen):
            t["color"] = "#FFFFFF" if "#FFFFFF" not in seen else "#9AA4B2"
        seen.append(t["color"])

    orders = orders_by_lap(laps)
    if not orders:
        raise StoryError("no lap end times")
    n = max(orders)
    final = orders[n]
    checks = {"laps": n, "order_at_flag": final[:3], "official_top3": [t["driver"] for t in top[:3]]}
    if final[:3] != checks["official_top3"]:
        raise StoryError(f"order at the flag {final[:3]} differs from the official top 3 {checks['official_top3']}")

    end = laps.pivot_table(index="lap_number", columns="driver_number", values="lap_end_s", aggfunc="first")
    gaps = {}
    for t in top:
        if t["driver"] in end and n in end.index:
            gaps[t["code"]] = float(end.loc[n, t["driver"]] - end.loc[n, winner["driver"]])

    fin = res[res["status"].fillna("").str.contains("Finished|Lap", case=False) & res["grid"].notna()]
    mover = None
    if len(fin):
        grid = fin["grid"].astype(int).where(lambda g: g > 0, 22)   # 0 = pit lane start
        gained = grid - fin["position"].astype(int)
        i = gained.idxmax()
        if gained[i] >= 3:
            mover = who(fin.loc[i]) | {"gained": int(gained[i])}
            if mover["grid"] in (0, None):
                mover["grid"] = 22
    tracked = top + ([mover] if mover and mover["driver"] not in [t["driver"] for t in top] else [])
    positions = {}
    for t in tracked:
        p = np.full(n + 1, np.nan)
        p[0] = t["grid"] if t.get("grid") else np.nan
        for k, order in orders.items():
            if t["driver"] in order:
                p[k] = order.index(t["driver"]) + 1
        positions[t["code"]] = p
    colors = {t["code"]: t["color"] for t in tracked}
    return RaceStory("race", winner, top[:3], mover, gaps, colors, positions, n, checks)


# ---------------------------------------------------------------- helpers

def _int(v):
    try:
        return None if v is None or pd.isna(v) else int(v)
    except (TypeError, ValueError):
        return None


def team_color(c) -> str:
    if not c or (isinstance(c, float) and np.isnan(c)):
        return "#00E5FF"
    c = str(c).lstrip("#")
    return f"#{c.upper()}" if len(c) == 6 else "#00E5FF"


def colors_close(a: str, b: str, tol: int = 60) -> bool:
    ra = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    rb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return sum(abs(x - y) for x, y in zip(ra, rb)) < tol


def sector_text(g: float, a: str, b: str, unit: str = " s") -> str:
    """Official sector gap as text: who gained and by how much, or level."""
    if abs(g) < 0.0005:
        return "level"
    return f"{a if g > 0 else b} +{abs(g):.3f}{unit}"


def corner_label(c: str) -> str:
    return f"Turn {c}"
