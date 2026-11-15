"""In memory stand in for the Supabase client, plus a quality report. Nothing is written remotely.

python -m pipeline round --season 2026 --round 20 --session Race --dry-run
"""
from __future__ import annotations

import itertools
import types

import numpy as np
import pandas as pd


class _Query:
    def __init__(self, db, table):
        self.db, self.table, self.rows = db, table, None

    def upsert(self, rows, on_conflict=None):
        self.db.setdefault(self.table, []).extend(rows)
        self.rows = rows
        return self

    def insert(self, row):
        row = {**row, "id": next(DryClient._ids)}
        self.db.setdefault(self.table, []).append(row)
        self.rows = [row]
        return self

    def update(self, *_):
        return self

    def delete(self):
        return self

    def select(self, *_):
        self.rows = []
        return self

    def eq(self, *_):
        return self

    def execute(self):
        return types.SimpleNamespace(data=self.rows or [])


class DryClient:
    _ids = itertools.count(1)

    def __init__(self):
        self.db: dict[str, list[dict]] = {}
        self.files: dict[str, int] = {}
        self.storage = types.SimpleNamespace(from_=lambda b: types.SimpleNamespace(upload=self._upload))

    def _upload(self, path, data, opts=None):
        self.files[path] = len(data)

    def table(self, name):
        return _Query(self.db, name)


def report(sb: DryClient) -> str:
    out = []
    for path, n in sorted(sb.files.items()):
        out.append(f"file {path}: {n / 1e6:.2f} MB")
    for s in sb.db.get("sessions", []):
        if s.get("status") == "ingested":
            out.append(f"session {s['session_id']}: {s['n_drivers']} drivers, {s['n_laps']} laps, centre line {s['track_length_m']} m, {s['fastf1_version']}")
    laps = pd.DataFrame(sb.db.get("laps", []))
    if len(laps):
        acc = laps[laps["is_accurate"]]
        best = acc.sort_values("lap_time_ms").head(5)
        out.append("fastest accurate laps: " + ", ".join(f"#{r.driver_number} L{r.lap_number} {r.lap_time_ms / 1000:.3f}" for r in best.itertuples()))
        out.append(f"accurate laps {len(acc)} of {len(laps)}; compounds {laps['compound'].value_counts(dropna=False).to_dict()}")
    m = pd.DataFrame(sb.db.get("corner_metrics", []))
    c = pd.DataFrame(sb.db.get("corners", []))
    if len(m) and len(laps):
        m = m.merge(laps[["driver_number", "lap_number", "is_accurate"]], on=["driver_number", "lap_number"])
        m = m[m["is_accurate"]]
        out.append(f"corners {len(c)}; corner rows on accurate laps {len(m)}")
        out.append("per corner over accurate laps, all drivers (median and spread):")
        out.append(f"  {'corner':>6} {'apex_m':>7} {'min kph':>8} {'IQR':>5} {'brake m':>8} {'IQR':>5} {'braked%':>7} {'exit kph':>8} {'n':>5}")
        for corner, g in sorted(m.groupby("corner"), key=lambda kv: float(c.set_index("corner").loc[kv[0], "apex_m"]) if len(c) else 0):
            q = lambda s: (np.nanpercentile(s, 75) - np.nanpercentile(s, 25)) if s.notna().any() else np.nan
            bp = g["brake_point_m"]
            apex = float(c.set_index("corner").loc[corner, "apex_m"]) if len(c) else np.nan
            out.append(f"  {corner:>6} {apex:7.0f} {g['min_speed_kph'].median():8.0f} {q(g['min_speed_kph']):5.0f} "
                       f"{bp.median():8.0f} {q(bp):5.0f} {100 * bp.notna().mean():7.0f} {g['exit_speed_kph'].median():8.0f} {len(g):5d}")
    return "\n".join(out)
