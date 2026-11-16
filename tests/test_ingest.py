"""End to end: OpenF1 shaped responses for one synthetic session through fetch, laps, processing and store."""
import types

import numpy as np
import pandas as pd

import pipeline.ingest as ing
from pipeline.__main__ import schedule
from tests.test_process import APEX, L, TRUE, make_frames

T0 = pd.Timestamp("2026-11-08T17:00:00Z")


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


def iso(sec):
    return (T0 + pd.to_timedelta(sec, unit="s")).isoformat()


class FakeOpenF1:
    """Serves synthetic laps, car_data and location the way OpenF1 shapes them."""
    def __init__(self):
        self.data = {}
        laps = []
        for drv in (1, 4):
            pos, car, starts = make_frames()
            self.data[("car_data", drv)] = pd.DataFrame({"date": [iso(t) for t in car.t], "speed": car.speed, "rpm": 11000, "n_gear": 6,
                                                         "throttle": 100, "brake": np.where(car.brake, 100, 0), "drs": 0})
            self.data[("location", drv)] = pd.DataFrame({"date": [iso(t) for t in pos.t], "x": pos.x, "y": pos.y, "z": pos.z})
            for n in range(1, 4):
                t0, t1 = starts[n - 1], starts[n]
                laps.append({"driver_number": drv, "lap_number": n, "date_start": None if n == 1 else iso(t0), "lap_duration": t1 - t0,
                             "duration_sector_1": 20.0, "duration_sector_2": 30.0, "duration_sector_3": t1 - t0 - 50, "is_pit_out_lap": False})
        self.data["laps"] = pd.DataFrame(laps)
        self.data["stints"] = pd.DataFrame([{"driver_number": d, "stint_number": 1, "lap_start": 1, "lap_end": 3, "compound": "SOFT", "tyre_age_at_start": 2} for d in (1, 4)])
        self.data["pit"] = pd.DataFrame()
        self.data["drivers"] = pd.DataFrame({"driver_number": [1, 4], "name_acronym": ["AAA", "BBB"], "full_name": ["A", "B"], "team_name": ["T", "U"], "team_colour": ["fff", "000"]})
        self.data["sessions"] = pd.DataFrame([
            {"session_key": 9, "session_name": "Race", "meeting_key": 2, "date_start": "2026-11-08T17:00:00+00:00", "date_end": "2026-11-08T19:00:00+00:00", "circuit_key": 14, "country_name": "Brazil"},
            {"session_key": 8, "session_name": "Qualifying", "meeting_key": 2, "date_start": "2026-11-07T18:00:00+00:00", "date_end": "2026-11-07T19:00:00+00:00", "circuit_key": 14, "country_name": "Brazil"},
            {"session_key": 5, "session_name": "Race", "meeting_key": 1, "date_start": "2026-11-01T20:00:00+00:00", "date_end": "2026-11-01T22:00:00+00:00", "circuit_key": 65, "country_name": "Mexico"},
            {"session_key": 1, "session_name": "Day 1", "meeting_key": 0, "date_start": "2026-02-20T08:00:00+00:00", "date_end": None, "circuit_key": 63, "country_name": "Bahrain"},
        ])
        self.data["meetings"] = pd.DataFrame({"meeting_key": [0, 1, 2], "meeting_name": ["Testing", "Mexico City Grand Prix", "São Paulo Grand Prix"]})

    def frame(self, path, filters=None, **p):
        key = (path, p["driver_number"]) if "driver_number" in p else path
        return self.data.get(key, pd.DataFrame()).copy()


def test_schedule_uses_official_rounds():
    # OpenF1 lists an extra meeting; official calendar has Mexico as 19 and São Paulo as 20 (local race date)
    s = schedule(FakeOpenF1(), 2026, {"2026-11-01": 19, "2026-11-07": 20})
    ids = [x["session_id"] for x in s]
    assert ids == ["2026_19_R", "2026_20_Q", "2026_20_R"], ids
    assert s[-1]["session_key"] == 9 and s[-1]["circuit_key"] == 14


def test_ingest_session_openf1(monkeypatch):
    marker = np.array([np.interp(APEX, TRUE.s0, TRUE.p[:, i]) for i in range(2)]) * 10 + 150  # 15 m off the line
    corners = pd.DataFrame({"X": [marker[0]], "Y": [marker[1]], "Number": [4], "Letter": [""], "Angle": [0.0], "Distance": [np.nan]})
    monkeypatch.setattr(ing.fastf1.mvapi, "get_circuit_info", lambda **kw: types.SimpleNamespace(corners=corners))
    sb, oc = FakeSB(), FakeOpenF1()
    s = {"session_id": "2026_20_R", "season": 2026, "round": 20, "session_code": "R", "session_name": "Race", "session_key": 9,
         "start_utc": T0.isoformat(), "end_utc": None, "circuit_key": 14}
    out = ing.ingest_session(sb, oc, s)

    assert set(sb.files) == {"2026/20/R/car_raw.parquet", "2026/20/R/pos_raw.parquet", "2026/20/R/trace_1.parquet", "2026/20/R/trace_4.parquet", "2026/20/R/replay.parquet", "tracks/2026/20.json"}
    assert sb.db["sessions"][0]["trace_prefix"] == "2026/20/R/"
    laps = pd.DataFrame(sb.db["laps"])
    assert len(laps) == 6
    assert laps["lap_start_s"].notna().all()            # lap 1 start recovered from lap 2
    assert not laps.loc[laps.lap_number == 1, "is_accurate"].any()  # race lap 1 excluded
    assert (laps.loc[laps.lap_number == 3, "tyre_life"] == 4).all()
    assert abs(sb.db["sessions"][0]["track_length_m"] - L) / L < 0.01
    assert out["corner_source"] == "multiviewer"
    m = pd.DataFrame(sb.db["corner_metrics"])
    assert len(m) >= 4
    assert (abs(m["brake_point_m"] + 120) < 15).all(), m


def test_auto_corners_when_no_markers(monkeypatch):
    monkeypatch.setattr(ing.fastf1.mvapi, "get_circuit_info", lambda **kw: None)
    sb = FakeSB()
    s = {"session_id": "2026_20_R", "season": 2026, "round": 20, "session_code": "R", "session_name": "Race", "session_key": 9,
         "start_utc": T0.isoformat(), "end_utc": None, "circuit_key": 14}
    out = ing.ingest_session(sb, FakeOpenF1(), s)
    assert out["corner_source"] == "speed minima" and out["corners"] == 1
