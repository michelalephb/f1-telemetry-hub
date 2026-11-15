"""One off check: does OpenF1 serve 2026 laps, car data and location after F1's 15 Oct paywall?"""
import time
import pandas as pd
import requests

B = "https://api.openf1.org/v1"
H = {"User-Agent": "f1-telemetry-hub-probe/0.1"}


def get(path, **params):
    for _ in range(4):
        r = requests.get(f"{B}/{path}", params=params, headers=H, timeout=60)
        if r.status_code == 429:
            time.sleep(5); continue
        print(f"  GET {path} {params} -> {r.status_code}, {len(r.content)} bytes")
        if r.status_code != 200:
            print("   ", r.text[:300]); return []
        time.sleep(2.2)  # stay under 30 requests per minute
        return r.json()
    return []


for country in ["Brazil", "Mexico", "United States", "Singapore"]:
    print(f"\n=== {country} 2026 ===")
    sess = get("sessions", year=2026, country_name=country)
    for s in sess:
        print(f"  {s['session_key']} {s['session_name']:<18} {s['date_start']}")
    race = [s for s in sess if s["session_name"] == "Race"]
    if not race:
        continue
    k = race[0]["session_key"]
    drivers = get("drivers", session_key=k)
    laps = get("laps", session_key=k)
    print(f"  drivers {len(drivers)}  laps {len(laps)}")
    if laps:
        df = pd.DataFrame(laps)
        print("  lap columns:", list(df.columns))
        print(df.dropna(subset=["lap_duration"]).nsmallest(3, "lap_duration")[["driver_number", "lap_number", "lap_duration"]].to_string())
    if not drivers:
        continue
    d = drivers[0]["driver_number"]
    for ep in ("car_data", "location"):
        rows = get(ep, session_key=k, driver_number=d)
        if rows:
            df = pd.DataFrame(rows)
            t = pd.to_datetime(df["date"], format="ISO8601")
            dt = t.diff().dt.total_seconds().dropna()
            print(f"  {ep} driver {d}: {len(df)} rows, {t.min()} .. {t.max()}, median dt {dt.median():.3f} s, p95 dt {dt.quantile(.95):.3f} s")
            print("   columns:", list(df.columns))
    for ep in ("stints", "pit"):
        print(f"  {ep}: {len(get(ep, session_key=k))} rows")
