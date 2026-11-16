"""Small track outlines for the site (landing page thumbnails, race story map).

One JSON file per round in the public "web" bucket: tracks/<season>/<round>.json
  {"w": 100, "h": 63.2, "pts": "x,y x,y ...", "rot": 92.0, "x0": .., "y0": .., "k": ..}
pts is the outline in a box 100 wide (y down, start/finish first). rot, x0, y0 and k map any
point in the trace frame (trace x, y and corners x, y) onto the same box:
  u = (R(rot) . p).x - x0) * k,  v = (y0 - (R(rot) . p).y) * k
rot is MultiViewer's circuit rotation, so the layout faces the way F1 graphics show it.
"""
from __future__ import annotations

import io
import json
import logging
import math

import numpy as np
import pandas as pd

from .geometry import resample_closed

log = logging.getLogger(__name__)
N_POINTS = 180
WIDTH = 100.0
PAD = 3.0


def rotate(xy: np.ndarray, deg: float) -> np.ndarray:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.column_stack([xy[:, 0] * c - xy[:, 1] * s, xy[:, 0] * s + xy[:, 1] * c])


def outline(xy: np.ndarray, rot: float = 0.0, n: int = N_POINTS) -> dict:
    """xy: one closed lap in the trace frame, in driving order, starting at the line."""
    xy = np.asarray(xy, dtype=float)
    xy = xy[np.isfinite(xy).all(axis=1)]
    if len(xy) < 20:
        raise ValueError("not enough points for an outline")
    pts = resample_closed(xy, n)
    r = rotate(pts, rot)
    x0, x1 = r[:, 0].min(), r[:, 0].max()
    y0, y1 = r[:, 1].min(), r[:, 1].max()
    span = max(x1 - x0, 1e-9)
    k = (WIDTH - 2 * PAD) / span
    u = (r[:, 0] - x0) * k + PAD
    v = (y1 - r[:, 1]) * k + PAD
    h = (y1 - y0) * k + 2 * PAD
    return {
        "w": WIDTH, "h": round(float(h), 1),
        "pts": " ".join(f"{a:.1f},{b:.1f}" for a, b in zip(u, v)),
        "rot": float(rot), "x0": float(x0 - PAD / k), "y0": float(y1 + PAD / k), "k": float(k),
    }


def lap_xy_from_trace(tr: pd.DataFrame) -> np.ndarray:
    """Fastest complete lap of one driver's web trace, as an (n, 2) array in driving order."""
    tr = tr[tr["in_lap"].astype(bool)] if "in_lap" in tr else tr
    best, best_t = None, math.inf
    span_max = tr.groupby("lap_number")["lap_dist_m"].agg(lambda d: d.max() - d.min()).max()
    for lap, g in tr.groupby("lap_number"):
        g = g.sort_values("lap_dist_m")
        if g["lap_dist_m"].max() - g["lap_dist_m"].min() < 0.97 * span_max or len(g) < 50:
            continue
        dt = g["t"].max() - g["t"].min()
        if dt < best_t:
            best, best_t = g, dt
    if best is None:
        raise ValueError("no complete lap in trace")
    return best[["x", "y"]].to_numpy(dtype=float)


def upload(sb, season: int, rnd: int, data: dict, bucket: str) -> str:
    path = f"tracks/{season}/{rnd}.json"
    sb.storage.from_(bucket).upload(
        path, json.dumps(data, separators=(",", ":")).encode(),
        {"content-type": "application/json", "cache-control": "3600", "upsert": "true"},
    )
    return path


def read_trace(sb, bucket: str, path: str) -> pd.DataFrame:
    return pd.read_parquet(io.BytesIO(sb.storage.from_(bucket).download(path)))
