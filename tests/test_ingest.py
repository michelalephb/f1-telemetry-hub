"""End to end run of ingest_session against a fake FastF1 session and a fake Supabase client."""
import types

import numpy as np
import pandas as pd

import pipeline.ingest as ing
from tests.test_process import APEX, L, TRUE, make_frames


class FakeTable:
    def __init__(self, db, name):
        self.db, self.name = db, name
    def upsert(self, rows, on_conflict=None):
        self.db.setdefault(self.name, []).extend(rows); return self
    def delete(self): return self
    def eq(self, *a): return self
    def execute(self): return types.SimpleNamespace(data=[])


class FakeSB:
    def __init__(self):
        self.db, self.files = {}, {}
        self.storage = types.SimpleNamespace(from_=lambda b: types.SimpleNamespace(upload=lambda p, data, o: self.files.__setitem__(p, len(data))))
    def table(self, name): return FakeTable(self.db, name)


def fake_session():
    cars, poss, laps = {}, {}, []
    for k, drv in enumerate(["1", "4"]):
        pos, car, starts = make_frames()
        td = lambda s: pd.to_timedelta(s, unit="s")
        cars[drv] = pd.DataFrame({"Date": pd.Timestamp("2026-11-08 17:00") + td(car.t), "SessionTime": td(car.t), "RPM": 11000,
                                  "Speed": car.speed, "nGear": 6, "Throttle": 100, "Brake": car.brake, "DRS": 0})
        poss[drv] = pd.DataFrame({"Date": pd.Timestamp("2026-11-08 17:00") + td(pos.t), "SessionTime": td(pos.t),
                                  "X": pos.x, "Y": pos.y, "Z": pos.z, "Status": "OnTrack"})
        for n in range(1, 3):
            t0, t1 = starts[n], starts[n + 1]
            laps.append({"DriverNumber": drv, "LapNumber": float(n + 1), "LapTime": td(t1 - t0), "Sector1Time": td(20.0), "Sector2Time": td(30.0),
                         "Sector3Time": td(t1 - t0 - 50), "LapStartTime": td(t0), "Time": td(t1), "Compound": "SOFT", "TyreLife": 3.0, "Stint": 1.0,
                         "PitInTime": pd.NaT, "PitOutTime": pd.NaT, "IsPersonalBest": True, "IsAccurate": True, "Deleted": False,
                         "TrackStatus": "1", "Position": float(k + 1)})
    s_apex = APEX
    xy = np.array([np.interp(s_apex, TRUE.s0, TRUE.p[:, i]) for i in range(2)]) * 10 + 150  # marker 15 m off line
    corners = pd.DataFrame({"X": [xy[0]], "Y": [xy[1]], "Number": [4], "Letter": [""], "Angle": [0.0], "Distance": [0.0]})
    return types.SimpleNamespace(
        load=lambda **kw: None, laps=pd.DataFrame(laps), car_data=cars, pos_data=poss,
        results=pd.DataFrame({"DriverNumber": ["1", "4"], "Abbreviation": ["AAA", "BBB"], "FullName": ["A", "B"], "TeamName": ["T", "U"], "TeamColor": ["fff", "000"]}),
        get_circuit_info=lambda: types.SimpleNamespace(corners=corners),
    )


def test_ingest_session(monkeypatch):
    monkeypatch.setattr(ing.fastf1, "get_session", lambda *a: fake_session())
    sb = FakeSB()
    sid = ing.ingest_session(sb, 2026, 21, "Race")
    assert sid == "2026_21_R"
    assert set(sb.files) == {"2026/21/R/car_raw.parquet", "2026/21/R/pos_raw.parquet", "2026/21/R/lap_distance.parquet"}
    assert len(sb.db["laps"]) == 4
    s = sb.db["sessions"][0]
    assert abs(s["track_length_m"] - L) / L < 0.01
    c = sb.db["corners"][0]
    assert c["corner"] == "4" and c["letter"] is None
    m = sb.db["corner_metrics"]
    assert len(m) == 4
    assert all(abs(r["brake_point_m"] + 120) < 15 for r in m), m
