"""Distance along the lap for every raw car sample, and per corner metrics.

Method (see README, "How distance is computed"):
1. Position samples (about 4.5 Hz) are projected onto the centre line and unwrapped
   into a continuous distance per driver.
2. Car samples (about 4.2 Hz) get a distance from integrating speed, corrected to the
   position derived distance with a per lap linear fit (scale and offset). Speed
   integration gives smooth local shape; position anchors it so it cannot drift.
3. Corner metrics are read from those fused samples, relative to each corner's apex.
No raw sample is resampled or moved in time.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .geometry import CentreLine

LAP_MARGIN_S = 12.0         # car samples kept either side of a lap, so corner windows can cross the line
WIN_BEFORE_M = 250.0        # corner window starts this far before the apex
WIN_AFTER_M = 150.0         # and ends this far after
EXIT_AT_M = 100.0           # exit speed is read here, after the apex
APEX_SEARCH_M = 75.0        # apex = min speed of the reference lap within this distance of the corner marker


def pos_distance(pos: pd.DataFrame, line: CentreLine) -> pd.DataFrame:
    """Add continuous distance `D` to one driver's position samples (sorted by time)."""
    pos = pos.sort_values("t").reset_index(drop=True)
    on = pos["status"].fillna("OnTrack").eq("OnTrack").to_numpy()
    xyz = pos[["x", "y", "z"]].to_numpy() / 10.0
    s, dist = line.project(xyz)
    pos["s"] = s
    pos["off_line_m"] = dist
    pos["valid"] = on & (dist < 40.0)
    pos["D"] = np.nan
    v = pos["valid"].to_numpy()
    if v.any():
        pos.loc[v, "D"] = line.unwrap(s[v])
    return pos


def fuse_lap(car: pd.DataFrame, pos: pd.DataFrame, t0: float, t1: float, line: CentreLine) -> pd.DataFrame | None:
    """Distance from the timing line for one lap's car samples (plus margins).

    car: one driver, columns t (s), speed (kph) and channels, sorted by t.
    pos: same driver after pos_distance().
    Returns car rows in [t0 - margin, t1 + margin] with `lap_dist_m` and `in_lap`.
    """
    c = car[(car["t"] >= t0 - LAP_MARGIN_S) & (car["t"] <= t1 + LAP_MARGIN_S)].copy()
    p = pos[(pos["t"] >= t0 - LAP_MARGIN_S - 2) & (pos["t"] <= t1 + LAP_MARGIN_S + 2) & pos["valid"]]
    if len(c) < 20 or len(p) < 20:
        return None

    t = c["t"].to_numpy()
    v = c["speed"].to_numpy() / 3.6
    integ = np.concatenate([[0.0], np.cumsum(0.5 * (v[1:] + v[:-1]) * np.diff(t))])
    anchor = np.interp(t, p["t"].to_numpy(), p["D"].to_numpy())

    # Least squares: anchor ~ a * integ + b. Robust to a few bad position samples via one refit.
    A = np.column_stack([integ, np.ones_like(integ)])
    coef, *_ = np.linalg.lstsq(A, anchor, rcond=None)
    resid = anchor - A @ coef
    keep = np.abs(resid) < max(3 * np.std(resid), 5.0)
    if keep.sum() > 10:
        coef, *_ = np.linalg.lstsq(A[keep], anchor[keep], rcond=None)
    D = A @ coef

    # Distance of the timing line crossing at lap start: D at t0, minus the wrapped s at t0.
    D_t0 = float(np.interp(t0, t, D))
    s_t0 = D_t0 % line.length
    if s_t0 > line.length / 2:
        s_t0 -= line.length
    base = D_t0 - s_t0

    c["lap_dist_m"] = D - base
    c["in_lap"] = (c["t"] >= t0) & (c["t"] < t1)
    c["fit_scale"] = coef[0]
    return c


def refine_apexes(corners: pd.DataFrame, ref_lap: pd.DataFrame) -> pd.DataFrame:
    """Move each corner's apex to the reference lap's minimum speed near its marker.

    The search never reaches more than 45 % of the way to a neighbouring marker, so close
    pairs (esses, chicanes) keep separate apexes. If the minimum sits on the search edge the
    corner has no local minimum there (flat out kink): the marker position is kept.
    """
    out = corners.sort_values("marker_m").copy()
    d = ref_lap["lap_dist_m"].to_numpy()
    sp = ref_lap["speed"].to_numpy()
    mk = out["marker_m"].to_numpy()
    for j, i in enumerate(out.index):
        lo = APEX_SEARCH_M if j == 0 else min(APEX_SEARCH_M, 0.45 * (mk[j] - mk[j - 1]))
        hi = APEX_SEARCH_M if j == len(mk) - 1 else min(APEX_SEARCH_M, 0.45 * (mk[j + 1] - mk[j]))
        m = (d >= mk[j] - lo) & (d <= mk[j] + hi)
        apex = float(mk[j])
        if m.sum() >= 3:
            k = int(np.argmin(sp[m]))
            if 0 < k < m.sum() - 1:
                apex = float(d[m][k])
        out.at[i, "apex_m"] = apex
    out["prev_apex_m"] = out["apex_m"].shift(1)
    out["next_apex_m"] = out["apex_m"].shift(-1)
    return out


def corner_metrics(lap: pd.DataFrame, apex_m: float, prev_apex_m: float | None = None,
                   next_apex_m: float | None = None) -> dict | None:
    """Metrics for one lap through one corner. Returns None if the window is not fully covered.

    Braking and entry speed are searched only after the previous corner's apex, so a braking
    zone is never credited to the corner after it. Minimum speed is searched only up to halfway
    to each neighbouring apex.
    """
    rel = lap["lap_dist_m"].to_numpy() - apex_m
    rel = np.maximum.accumulate(rel)  # distance must not run backwards
    if rel[0] > -WIN_BEFORE_M or rel[-1] < WIN_AFTER_M:
        return None
    t = lap["t"].to_numpy()
    sp = lap["speed"].to_numpy().astype(float)
    brake = lap["brake"].to_numpy().astype(bool)

    w = (rel >= -WIN_BEFORE_M) & (rel <= WIN_AFTER_M)
    t_in = np.interp(-WIN_BEFORE_M, rel, t)
    t_out = np.interp(WIN_AFTER_M, rel, t)

    # Brake onset: last off to on transition before the apex (+20 m), placed midway between the two samples.
    brake_point = None
    start = -WIN_BEFORE_M
    if prev_apex_m is not None and not np.isnan(prev_apex_m):
        start = max(start, prev_apex_m - apex_m + 10.0)
    idx = np.where(w & (rel >= start) & (rel <= 20.0))[0]
    for j in idx[::-1]:
        if j > 0 and brake[j] and not brake[j - 1] and rel[j - 1] >= start:
            brake_point = 0.5 * (rel[j] + rel[j - 1])
            break

    lo, hi = -150.0, 100.0
    if prev_apex_m is not None and not np.isnan(prev_apex_m):
        lo = max(lo, 0.5 * (prev_apex_m - apex_m))
    if next_apex_m is not None and not np.isnan(next_apex_m):
        hi = min(hi, 0.5 * (next_apex_m - apex_m))
    m = (rel >= lo) & (rel <= hi)
    if not m.any():
        return None
    jmin = np.where(m)[0][np.argmin(sp[m])]

    entry_end = brake_point if brake_point is not None else -50.0
    e = (rel >= start) & (rel <= entry_end)
    entry = float(sp[e].max()) if e.any() else None

    return {
        "brake_point_m": None if brake_point is None else round(float(brake_point), 1),
        "entry_speed_kph": entry,
        "min_speed_kph": float(sp[jmin]),
        "min_speed_at_m": round(float(rel[jmin]), 1),
        "exit_speed_kph": round(float(np.interp(EXIT_AT_M, rel, sp)), 1),
        "window_time_s": round(float(t_out - t_in), 3),
        "n_samples": int(w.sum()),
    }
