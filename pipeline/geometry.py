"""Track centre line construction and projection.

FastF1 position data is in 1/10 m. Everything here works in metres.
The centre line is 3D (X, Y, Z) so that circuits with a crossover
(Suzuka) project onto the correct level.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import savgol_filter
from scipy.spatial import cKDTree


def resample_closed(xyz: np.ndarray, n: int) -> np.ndarray:
    """Resample one closed lap to n points equally spaced by arc length."""
    pts = np.vstack([xyz, xyz[:1]])
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    t = np.linspace(0.0, s[-1], n, endpoint=False)
    return np.column_stack([np.interp(t, s, pts[:, k]) for k in range(pts.shape[1])])


def _best_shift(ref: np.ndarray, other: np.ndarray, max_shift: int) -> np.ndarray:
    """Circularly shift `other` so it lines up best with `ref`."""
    best, best_err = 0, np.inf
    for k in range(-max_shift, max_shift + 1):
        err = np.mean(np.sum((ref - np.roll(other, k, axis=0)) ** 2, axis=1))
        if err < best_err:
            best, best_err = k, err
    return np.roll(other, best, axis=0)


def build_centre_line(laps_xyz: list[np.ndarray], n: int = 4000, smooth_m: float = 25.0) -> np.ndarray:
    """Median of several clean laps, aligned and smoothed.

    laps_xyz: list of (k, 3) arrays in metres, each one full lap starting near the timing line.
    The first lap is the reference (pass the session fastest lap first).
    Returns an (n, 3) closed polyline, equally spaced, starting at the timing line.
    """
    if not laps_xyz:
        raise ValueError("no laps to build a centre line from")
    ref = resample_closed(laps_xyz[0], n)
    stack = [ref]
    for lap in laps_xyz[1:]:
        r = resample_closed(lap, n)
        stack.append(_best_shift(ref, r, max_shift=max(5, n // 100)))
    line = np.median(np.stack(stack), axis=0)

    spacing = np.mean(np.linalg.norm(np.diff(np.vstack([line, line[:1]]), axis=0), axis=1))
    win = int(max(5, round(smooth_m / max(spacing, 1e-6))) // 2 * 2 + 1)
    pad = win
    wrapped = np.vstack([line[-pad:], line, line[:pad]])
    smooth = savgol_filter(wrapped, win, 3, axis=0)[pad:-pad]
    return resample_closed(smooth, n)


class CentreLine:
    """Closed 3D polyline with fast projection of points to arc length."""

    def __init__(self, xyz: np.ndarray):
        self.p = np.asarray(xyz, dtype=float)
        self.q = np.roll(self.p, -1, axis=0)
        self.d = self.q - self.p
        self.seglen = np.linalg.norm(self.d, axis=1)
        self.s0 = np.concatenate([[0.0], np.cumsum(self.seglen)[:-1]])
        self.length = float(self.seglen.sum())
        self._tree = cKDTree(self.p)

    def project(self, pts: np.ndarray, k: int = 4) -> tuple[np.ndarray, np.ndarray]:
        """Return (s, dist): arc length in [0, length) and distance to the line, per point."""
        pts = np.asarray(pts, dtype=float)
        _, idx = self._tree.query(pts, k=k)
        idx = np.atleast_2d(idx)
        n = len(self.p)
        cands = np.concatenate([idx, (idx - 1) % n], axis=1)  # segments starting at and before each vertex
        best_s = np.zeros(len(pts))
        best_d = np.full(len(pts), np.inf)
        for j in range(cands.shape[1]):
            i = cands[:, j]
            d = self.d[i]
            l2 = np.maximum(np.sum(d * d, axis=1), 1e-12)
            t = np.clip(np.sum((pts - self.p[i]) * d, axis=1) / l2, 0.0, 1.0)
            foot = self.p[i] + d * t[:, None]
            dist = np.linalg.norm(pts - foot, axis=1)
            better = dist < best_d
            best_d[better] = dist[better]
            best_s[better] = (self.s0[i] + t * self.seglen[i])[better]
        return best_s % self.length, best_d

    def unwrap(self, s: np.ndarray) -> np.ndarray:
        """Turn wrapped arc length into a continuous distance (adds a lap length at each crossing)."""
        if len(s) == 0:
            return s
        ds = np.diff(s)
        ds = np.where(ds < -self.length / 2, ds + self.length, ds)
        ds = np.where(ds > self.length / 2, ds - self.length, ds)
        return s[0] + np.concatenate([[0.0], np.cumsum(ds)])
