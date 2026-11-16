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
MIN_GAIN_S = 0.010           # smaller corner gains are not worth a slide
CORNER_BEFORE_M, CORNER_AFTER_M = 250.0, 150.0   # same window as the pipeline's corner metrics


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
class CornerGain:
    corner: str
    apex_m: float
    gain_s: float            # time B lost to A through the window (positive = A faster)
    apex_a: float            # minimum speed in the window, km/h
    apex_b: float


@dataclass
class QualiStory:
    kind: str                # "quali"
    a: Lap                   # pole
    b: Lap                   # P2
    official_gap_s: float
    grid: np.ndarray         # common distance grid, m
    delta: np.ndarray        # B time minus A time at each grid point, s
    best_a: CornerGain       # where pole gained most
    best_b: CornerGain | None  # where P2 gained most (None if P2 gained nowhere)
    track_m: float
    checks: dict = field(default_factory=dict)


@dataclass
class RaceStory:
    kind: str                # "race"
    winner: dict
    podium: list[dict]
    mover: dict | None       # {"code", "color", "grid", "position", "gained"}
    gaps: dict               # code -> np.ndarray of gap to the leader on track (s) per lap, NaN where unknown
    colors: dict
    positions: np.ndarray    # position per lap of the mover (index = lap number, 0 = grid)
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
    inq3 = set(results.loc[results["q3_ms"].notna(), "driver_number"].astype(str))
    if not inq3 or len(results) <= len(inq3):
        raise StoryError("no final segment in the official result")
    out = laps[~laps["driver_number"].isin(inq3) & laps["lap_end_s"].notna()]
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

def corner_gains(a: Lap, b: Lap, grid: np.ndarray, delta: np.ndarray, corners: pd.DataFrame, track_m: float) -> list[CornerGain]:
    out = []
    for _, c in corners.iterrows():
        lo, hi = c["apex_m"] - CORNER_BEFORE_M, c["apex_m"] + CORNER_AFTER_M
        if lo < 0 or hi > track_m:
            continue
        g = float(np.interp(hi, grid, delta) - np.interp(lo, grid, delta))
        win = lambda L: L.speed[(L.dist >= lo) & (L.dist <= hi)]
        sa, sb = win(a), win(b)
        if len(sa) < 3 or len(sb) < 3:
            continue
        out.append(CornerGain(str(c["corner"]), float(c["apex_m"]), g, float(sa.min()), float(sb.min())))
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

    grid = np.arange(0.0, track_m + GRID_STEP_M / 2, GRID_STEP_M)
    grid[-1] = track_m
    delta = time_at(b, grid) - time_at(a, grid)
    official = (int(p2["q3_ms"]) - int(p1["q3_ms"])) / 1000.0
    checks = {"gap_at_line_s": round(float(delta[-1]), 3), "official_gap_s": official,
              "line_error_ms": round(abs(float(delta[-1]) - official) * 1000, 1)}
    if abs(delta[-1] - official) > LINE_TOLERANCE_S:
        raise StoryError(f"computed gap {delta[-1]:.3f} s vs official {official:.3f} s")
    delta = pin_to_sectors(a, b, picked[0], picked[1], grid, delta, official, track_m, checks)

    gains = corner_gains(a, b, grid, delta, corners, track_m)
    if not gains:
        raise StoryError("no corner windows")
    best_a = max(gains, key=lambda g: g.gain_s)
    best_b = min(gains, key=lambda g: g.gain_s)
    return QualiStory("quali", a, b, official, grid, delta, best_a, best_b if best_b.gain_s <= -MIN_GAIN_S else None, track_m, checks)


def pin_to_sectors(a: Lap, b: Lap, la: pd.Series, lb: pd.Series, grid: np.ndarray, delta: np.ndarray,
                   official: float, track_m: float, checks: dict) -> np.ndarray:
    """Make the gap curve pass exactly through the official gaps at the sector splits and the line.

    Distance alignment between two laps drifts by up to about 0.1 s mid lap even when the line
    is exact, which is enough to invent a corner gain. The error between pins is spread linearly.
    Refuses the story when the raw curve misses a split by more than SECTOR_TOLERANCE_S.
    """
    pins_x, pins_y, errs = [0.0], [0.0], []
    ta = tb = 0.0
    for k in ("sector1_ms", "sector2_ms"):
        if pd.isna(la.get(k)) or pd.isna(lb.get(k)):
            checks["sector_pins"] = "missing sector times"
            break
        ta += float(la[k]) / 1000
        tb += float(lb[k]) / 1000
        d = (float(np.interp(ta, a.time, a.dist)) + float(np.interp(tb, b.time, b.dist))) / 2
        raw = float(np.interp(d, grid, delta))
        errs.append(round((raw - (tb - ta)) * 1000, 1))
        if abs(raw - (tb - ta)) > SECTOR_TOLERANCE_S:
            raise StoryError(f"gap at the {k[:7]} split is {raw:.3f} s, official {tb - ta:.3f} s")
        pins_x.append(d)
        pins_y.append((tb - ta) - raw)
    pins_x.append(track_m)
    pins_y.append(official - float(delta[-1]))
    checks["sector_error_ms"] = errs
    checks["sector_split_m"] = [round(x) for x in pins_x[1:-1]]
    if any(np.diff(pins_x) <= 0):
        raise StoryError(f"sector splits out of order: {pins_x}")
    return delta + np.interp(grid, pins_x, pins_y)


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
    leader = end.min(axis=1)   # gap to whoever led at the end of each lap: never negative
    gaps = {}
    for t in top:
        if t["driver"] in end:
            g = (end[t["driver"]] - leader).reindex(range(1, n + 1))
            gaps[t["code"]] = g.to_numpy(float)

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
    pos = np.full(n + 1, np.nan)
    if mover:
        pos[0] = mover["grid"]
        for k, order in orders.items():
            if mover["driver"] in order:
                pos[k] = order.index(mover["driver"]) + 1
    return RaceStory("race", winner, top[:3], mover, gaps, {t["code"]: t["color"] for t in top}, pos, n, checks)


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


def corner_label(c: str) -> str:
    return f"Turn {c}"
