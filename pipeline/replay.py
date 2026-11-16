"""Race replay file for the website: where every car is, every second of the race.

web bucket: <season>/<round>/<code>/replay.parquet, one int32 column per driver number plus "_t".
Values are DELTAS (first row absolute): _t is session time in s, a driver column is the distance
the car has covered since the start of lap 1, in metres ((lap - 1) * track length + lap distance).
Null before a car's first sample and after its last. The browser takes a cumulative sum.
Deltas of a smooth series compress to about 150 kB for a full race, against about 11 MB of traces.
"""
from __future__ import annotations

import io
import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)
STEP_S = 1.0


def covered(tr: pd.DataFrame, track_m: float) -> tuple[np.ndarray, np.ndarray]:
    """(t, metres covered) for one driver's trace rows, made non decreasing in both."""
    tr = tr.sort_values("t")
    t = tr["t"].to_numpy(dtype=float)
    m = (tr["lap_number"].to_numpy(dtype=float) - 1.0) * track_m + tr["lap_dist_m"].to_numpy(dtype=float)
    ok = np.isfinite(t) & np.isfinite(m)
    t, m = t[ok], m[ok]
    if len(t) == 0:
        return t, m
    m = np.maximum.accumulate(m)  # projection noise never moves a car backwards
    keep = np.r_[True, np.diff(t) > 0]
    return t[keep], m[keep]


def build(traces: dict[str, pd.DataFrame], track_m: float, step: float = STEP_S) -> pd.DataFrame:
    series = {d: covered(tr, track_m) for d, tr in traces.items()}
    series = {d: s for d, s in series.items() if len(s[0]) >= 2}
    if not series:
        raise ValueError("no trace data for a replay")
    t0 = np.floor(min(s[0][0] for s in series.values()))
    t1 = np.ceil(max(s[0][-1] for s in series.values()))
    grid = np.arange(t0, t1 + step, step)
    out = {"_t": grid.astype("int64")}
    for d, (t, m) in sorted(series.items(), key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else 999):
        v = np.interp(grid, t, m)
        v[(grid < t[0]) | (grid > t[-1])] = np.nan
        out[str(d)] = v
    wide = pd.DataFrame(out)
    enc = {}
    for c in wide.columns:
        v = np.round(wide[c].to_numpy(dtype=float))
        first = np.argmax(np.isfinite(v)) if np.isfinite(v).any() else None
        dv = np.full(len(v), np.nan)
        if first is not None:
            dv[first] = v[first]
            dv[first + 1:] = np.diff(v[first:])
        enc[c] = pd.array(np.where(np.isfinite(dv), dv, 0).astype("int64"), dtype="Int32")
        enc[c][~np.isfinite(dv)] = pd.NA
    return pd.DataFrame(enc)


def decode(df: pd.DataFrame) -> pd.DataFrame:
    """Inverse of build (tests and checks): absolute values, NaN where absent."""
    out = {}
    for c in df.columns:
        v = df[c].astype("float64").to_numpy()
        out[c] = np.where(np.isnan(v), np.nan, np.nancumsum(v))
    return pd.DataFrame(out)


def upload(sb, path: str, df: pd.DataFrame, bucket: str) -> str:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, compression="zstd")
    sb.storage.from_(bucket).upload(path, buf.getvalue(), {"content-type": "application/vnd.apache.parquet", "upsert": "true"})
    return path
