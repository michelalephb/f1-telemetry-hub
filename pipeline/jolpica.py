"""Calendar and results from Jolpica (the Ergast successor). https://api.jolpi.ca/ergast/f1"""
from __future__ import annotations

import time

import requests

BASE = "https://api.jolpi.ca/ergast/f1"
HEADERS = {"User-Agent": "f1-telemetry-hub/0.1 (+https://github.com/michelalephb/f1-telemetry-hub)"}


def _get(path: str) -> dict:
    for attempt in range(4):
        r = requests.get(f"{BASE}/{path}", headers=HEADERS, timeout=30)
        if r.status_code == 429:
            time.sleep(5 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()["MRData"]
    r.raise_for_status()
    return {}


def events(season: int) -> list[dict]:
    races = _get(f"{season}.json?limit=100")["RaceTable"]["Races"]
    return [
        {
            "season": int(r["season"]),
            "round": int(r["round"]),
            "event_name": r["raceName"],
            "country": r["Circuit"]["Location"].get("country"),
            "location": r["Circuit"]["Location"].get("locality"),
            "circuit_id": r["Circuit"]["circuitId"],
            "event_date": r["date"],
        }
        for r in races
    ]


def results(season: int, rnd: int) -> list[dict]:
    out = []
    for code, path, key in (("R", "results", "Results"), ("S", "sprint", "SprintResults")):
        races = _get(f"{season}/{rnd}/{path}.json?limit=100")["RaceTable"]["Races"]
        if not races:
            continue
        for x in races[0].get(key, []):
            out.append(
                {
                    "season": season,
                    "round": rnd,
                    "session_code": code,
                    "driver_number": x["number"],
                    "driver_code": x["Driver"].get("code"),
                    "constructor": x["Constructor"]["name"],
                    "grid": int(x["grid"]) if x.get("grid") not in (None, "") else None,
                    "position": int(x["position"]) if x.get("position") else None,
                    "position_text": x.get("positionText"),
                    "points": float(x.get("points", 0)),
                    "status": x.get("status"),
                    "laps": int(x["laps"]) if x.get("laps") else None,
                }
            )
    return out
