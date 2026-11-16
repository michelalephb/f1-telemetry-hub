"""Instagram story, captions and rendering on synthetic laps (no network)."""
import json
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest

from pipeline.social import captions, render, story
from pipeline.social.publish import Instagram

TRACK_M = 4000.0
CORNERS = pd.DataFrame({"corner": ["1", "4", "8", "12"], "apex_m": [600.0, 1500.0, 2500.0, 3400.0]})


def speed_profile(d, slow=None):
    v = np.full_like(d, 300.0)
    for apex, vmin in zip(CORNERS["apex_m"], [110.0, 160.0, 90.0, 200.0]):
        if slow and slow[0] == apex:
            vmin -= slow[1]
        v = np.minimum(v, vmin + np.abs(d - apex) * 0.6)
    return v


def lap_rows(lap, slow=None, start=0.0, dt=0.24):
    """Samples of one lap, from 50 m before the line to 50 m after the next one."""
    d = np.arange(-50.0, TRACK_M + 50, 1.0)
    v = speed_profile(np.mod(d, TRACK_M), slow) / 3.6
    t = np.concatenate([[0.0], np.cumsum(np.diff(d) / v[1:])])
    t -= np.interp(0.0, d, t)
    ts = np.arange(t[0], t[-1], dt)
    ds = np.interp(ts, t, d)
    ang = 2 * np.pi * np.mod(ds, TRACK_M) / TRACK_M
    sp = np.interp(ds, d, v * 3.6)
    return pd.DataFrame({
        "lap_number": lap, "t": ts + start, "lap_dist_m": ds, "in_lap": (ds >= 0) & (ds <= TRACK_M),
        "speed": sp.round().astype(int), "throttle": np.where(np.gradient(sp) > 0, 100, 0),
        "brake": (np.gradient(sp) < -0.5).astype(int), "gear": np.clip((sp / 40).astype(int), 1, 8),
        "rpm": (sp * 35).astype(int) + np.arange(len(sp)) % 7, "drs": 0,
        "x": 10000 * np.cos(ang) + 3000 * np.cos(3 * ang), "y": 6000 * np.sin(ang),
    }), float(np.interp(TRACK_M, d, t))


def quali_fixture():
    tr_a, la = lap_rows(10, start=1000)
    tr_b, lb = lap_rows(11, slow=(2500.0, 12.0), start=1100)
    results = pd.DataFrame({"driver_number": ["1", "63", "12", "44"], "driver_code": ["NOR", "RUS", "ANT", "HAM"],
                            "position": [1, 2, 3, 11], "grid": None, "status": None,
                            "q3_ms": [round(la * 1000), round(lb * 1000), round(lb * 1000) + 300, None]})
    def split(tr, start, d):  # official style sector time: lap clock at distance d
        return round((np.interp(d, tr["lap_dist_m"], tr["t"]) - start) * 1000)
    s1a, s2a = split(tr_a, 1000, 1300), split(tr_a, 1000, 2700) - split(tr_a, 1000, 1300)
    s1b, s2b = split(tr_b, 1100, 1300), split(tr_b, 1100, 2700) - split(tr_b, 1100, 1300)
    laps = pd.DataFrame({
        "driver_number": ["44", "1", "63"], "lap_number": [5, 10, 11],
        "lap_time_ms": [90000, round(la * 1000), round(lb * 1000)],
        "sector1_ms": [30000, s1a, s1b], "sector2_ms": [30000, s2a, s2b],
        "sector3_ms": [30000, round(la * 1000) - s1a - s2a, round(lb * 1000) - s1b - s2b],
        "lap_start_s": [800.0, 1000.0, 1100.0], "lap_end_s": [890.0, 1000 + la, 1100 + lb],
    })
    drivers = pd.DataFrame({"driver_number": ["1", "63"], "abbreviation": ["NOR", "RUS"], "team_color": ["F47600", "00D7B6"]})
    return results, laps, drivers, {"1": tr_a, "63": tr_b}


def race_fixture(n=20):
    rows = []
    pace = {"1": 90.0, "3": 90.3, "6": 90.6, "16": 90.8, "44": 91.0}
    grid = {"1": 1, "3": 15, "6": 5, "16": 2, "44": 3}
    for drv, p in pace.items():
        t = grid[drv] * 0.5
        for lap in range(1, n + 1):
            t += p
            rows.append({"driver_number": drv, "lap_number": lap, "lap_time_ms": int(p * 1000), "lap_start_s": t - p, "lap_end_s": t})
    laps = pd.DataFrame(rows)
    order = sorted(pace, key=lambda d: laps[(laps.driver_number == d) & (laps.lap_number == n)].lap_end_s.iloc[0])
    results = pd.DataFrame({"driver_number": order, "driver_code": order, "position": range(1, 6),
                            "grid": [grid[d] for d in order], "status": "Finished", "q3_ms": None})
    drivers = pd.DataFrame({"driver_number": list(pace), "abbreviation": ["NOR", "VER", "HAD", "LEC", "HAM"],
                            "team_color": ["F47600", "4781D7", "4781D7", "ED1131", "ED1131"]})
    return results, laps, drivers


def test_quali_story_matches_official_gap_and_finds_the_corner():
    results, laps, drivers, traces = quali_fixture()
    st = story.quali_story(results, laps, drivers, CORNERS, traces, TRACK_M)
    assert st.a.code == "NOR" and st.b.code == "RUS"
    assert st.checks["line_error_ms"] < 5
    assert st.best_a.corner == "8" and st.best_a.diff == pytest.approx(12, abs=2)
    assert st.best_b is None
    assert sum(st.sector_gaps) == pytest.approx(st.official_gap_s, abs=0.003)
    assert abs(st.sector_gaps[0]) < 0.003 and min(st.sector_gaps[1:]) > 0   # T8 straddles the S2 split; S1 is level


def test_quali_story_refuses_a_gap_that_disagrees_with_the_official_one():
    results, laps, drivers, traces = quali_fixture()
    results.loc[1, "q3_ms"] += 0      # lap still matches
    traces["63"] = traces["63"].assign(t=traces["63"]["t"] * 1.002)  # stretch RUS's clock: gap no longer matches
    with pytest.raises(story.StoryError):
        story.quali_story(results, laps, drivers, CORNERS, traces, TRACK_M)


def test_quali_story_refuses_when_a_split_disagrees():
    results, laps, drivers, traces = quali_fixture()
    laps.loc[laps.driver_number == "63", "sector1_ms"] += 400
    laps.loc[laps.driver_number == "63", "sector2_ms"] -= 400   # same lap time, but the splits no longer fit the trace
    with pytest.raises(story.StoryError, match="split"):
        story.quali_story(results, laps, drivers, CORNERS, traces, TRACK_M)


def test_apex_speed_ignores_flat_out_kinks_and_neighbouring_corners():
    results, laps, drivers, traces = quali_fixture()
    corners = pd.concat([CORNERS, pd.DataFrame({"corner": ["9"], "apex_m": [2560.0]}),
                         pd.DataFrame({"corner": ["K"], "apex_m": [1000.0]})])   # 9: 60 m after T8; K: on a straight
    st = story.quali_story(results, laps, drivers, corners, traces, TRACK_M)
    names = [c.corner for c in story.corner_speeds(st.a, st.b, corners)]
    assert "K" not in names and "9" not in names and st.best_a.corner == "8"


def test_race_story_and_biggest_climb():
    results, laps, drivers = race_fixture()
    st = story.race_story(results, laps, drivers)
    assert st.winner["code"] == "NOR"
    assert st.mover["code"] == "VER" and st.mover["grid"] == 15 and st.mover["position"] == 2
    assert st.positions["VER"][0] == 15 and st.positions["VER"][-1] == 2
    assert st.colors["HAD"] != st.colors["VER"]   # teammates get distinct colours
    assert st.gaps["VER"] > 0 and set(st.positions) >= {"NOR", "VER", "HAD", "LEC", "HAM"}


def test_race_story_refuses_a_wrong_order_at_the_flag():
    results, laps, drivers = race_fixture()
    results = results.assign(driver_number=results["driver_number"].iloc[[1, 0, 2, 3, 4]].to_numpy())
    with pytest.raises(story.StoryError):
        story.race_story(results, laps, drivers)


def test_captions_have_no_hyphens_and_fit():
    results, laps, drivers, traces = quali_fixture()
    st = story.quali_story(results, laps, drivers, CORNERS, traces, TRACK_M)
    meta = {"event": "Brazilian Grand Prix", "code": "Q", "round": 20}
    for kind in ("reel", "carousel"):
        c = captions.quali(st, meta, kind)
        assert "-" not in c and len(c) <= 2200 and "#BrazilianGP" in c
    rs = story.race_story(*race_fixture())
    assert "-" not in captions.race(rs, {"event": "Las Vegas Grand Prix", "code": "R", "round": 21}, "reel")


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="needs ffmpeg")
def test_reel_meets_instagram_spec(tmp_path):
    results, laps, drivers, traces = quali_fixture()
    st = story.quali_story(results, laps, drivers, CORNERS, traces, TRACK_M)
    meta = {"event": "Test Grand Prix", "code": "Q", "round": 1}
    video, cover = render.quali_reel(st, meta, 0.0, tmp_path, lap_s=2.0)
    p = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)],
                                  capture_output=True, text=True, check=True).stdout)
    v = [s for s in p["streams"] if s["codec_type"] == "video"]
    assert len(v) == 1 and not [s for s in p["streams"] if s["codec_type"] == "audio"]
    v = v[0]
    assert v["codec_name"] == "h264" and v["pix_fmt"] == "yuv420p"
    assert (v["width"], v["height"]) == (1080, 1920)
    assert v["r_frame_rate"] == "30/1"
    assert 3 <= float(p["format"]["duration"]) <= 900
    assert video.stat().st_size < 300e6
    head = video.read_bytes()[:64]
    assert b"moov" in video.read_bytes()[:4096] or head.find(b"moov") >= 0   # faststart: moov before mdat
    assert video.read_bytes().find(b"moov") < video.read_bytes().find(b"mdat")
    assert cover.suffix == ".jpg" and cover.stat().st_size < 8e6


def test_carousels_render(tmp_path):
    results, laps, drivers, traces = quali_fixture()
    st = story.quali_story(results, laps, drivers, CORNERS, traces, TRACK_M)
    files = render.quali_carousel(st, {"event": "Test Grand Prix", "code": "Q", "round": 1}, 0.0, tmp_path / "q")
    assert 3 <= len(files) <= 10
    from PIL import Image
    for f in files:
        with Image.open(f) as im:
            assert im.size == (1080, 1350) and im.format == "JPEG"
    rs = story.race_story(*race_fixture())
    assert len(render.race_carousel(rs, {"event": "Test Grand Prix", "code": "R", "round": 1}, tmp_path / "r")) >= 3


class FakeHTTP:
    """Records calls; container status goes IN_PROGRESS then FINISHED."""
    def __init__(self):
        self.calls, self.polls, self.n = [], {}, 0

    def request(self, method, url, params=None, data=None, timeout=None):
        body = params or data
        self.calls.append((method, url.split("/v26.0/")[-1], {k: v for k, v in body.items() if k != "access_token"}))
        path = url.split("/v26.0/")[-1]
        if path.endswith("/media"):
            self.n += 1
            return Resp({"id": f"c{self.n}"})
        if path.endswith("/media_publish"):
            return Resp({"id": "m1"})
        if "fields" in body and "status_code" in body["fields"]:
            self.polls[path] = self.polls.get(path, 0) + 1
            return Resp({"status_code": "FINISHED" if self.polls[path] > 1 else "IN_PROGRESS"})
        return Resp({})


class Resp:
    def __init__(self, body, status=200):
        self.body, self.status_code, self.text = body, status, json.dumps(body)

    def json(self):
        return self.body


def test_publisher_carousel_and_reel_flow(monkeypatch):
    monkeypatch.setattr("pipeline.social.publish.POLL_S", 0)
    http = FakeHTTP()
    ig = Instagram("TOKEN", "123", session=http)
    assert ig.post_carousel(["https://x/1.jpg", "https://x/2.jpg"], "cap") == ("c3", "m1")
    kinds = [c[2].get("media_type") or ("item" if c[2].get("is_carousel_item") else None) for c in http.calls if c[1].endswith("/media")]
    assert kinds == ["item", "item", "CAROUSEL"]
    assert ig.post_reel("https://x/r.mp4", "https://x/c.jpg", "cap")[1] == "m1"
    reel = [c for c in http.calls if c[2].get("media_type") == "REELS"][0][2]
    assert reel["share_to_feed"] == "true" and reel["cover_url"] == "https://x/c.jpg"
    assert all("TOKEN" not in json.dumps(c) for c in http.calls)


class FakeTable:
    def __init__(self, db, name):
        self.db, self.name, self.f = db, name, {}

    def select(self, *_):
        return self

    def eq(self, k, v):
        self.f[k] = v
        return self

    def upsert(self, row, on_conflict=None):
        keys = on_conflict.split(",")
        rows = self.db.setdefault(self.name, [])
        old = next((r for r in rows if all(r.get(k) == row.get(k) for k in keys)), None)
        if old:
            old.update(row)
        else:
            rows.append(dict(row))
        self.data = [old or rows[-1]]
        return self

    def execute(self):
        if not hasattr(self, "data"):
            self.data = [r for r in self.db.get(self.name, []) if all(r.get(k) == v for k, v in self.f.items())]
        return self


class FakeBucket:
    def __init__(self, files):
        self.files = files

    def upload(self, path, data, opts):
        self.files[path] = len(data)

    def remove(self, paths):
        for p in paths:
            self.files.pop(p, None)


class FakeSB:
    def __init__(self):
        self.db, self.files, self.removed_after_publish = {}, {}, None
        self.storage = self

    def table(self, name):
        return FakeTable(self.db, name)

    def from_(self, bucket):
        return FakeBucket(self.files)


class FakeIG:
    def __init__(self, sb, fail=False):
        self.sb, self.fail = sb, fail

    def post_reel(self, v, c, cap):
        assert any(p.endswith("reel.mp4") for p in self.sb.files)   # video is up while Instagram fetches it
        if self.fail:
            raise RuntimeError("boom")
        return "c1", "m1"

    def post_carousel(self, urls, cap):
        return "c2", "m2"

    def permalink(self, m):
        return f"https://instagram.com/p/{m}"


def test_live_post_records_row_and_deletes_the_video(tmp_path, monkeypatch):
    from pipeline.social import __main__ as m
    results, laps, drivers, traces = quali_fixture()
    st = story.quali_story(results, laps, drivers, CORNERS, traces, TRACK_M)
    meta = {"event": "Test Grand Prix", "code": "Q", "round": 1, "season": 2026}
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(render, "quali_reel", lambda st, meta, rot, out: (_touch(out / "reel.mp4"), _touch(out / "cover.jpg")))
    sb, cache, report = FakeSB(), {"2026_01_Q": (meta, st, 0.0)}, []
    assert m.handle(sb, FakeIG(sb), "2026_01_Q", "reel", "session", tmp_path, cache, report)
    row = sb.db["ig_posts"][0]
    assert row["status"] == "published" and row["permalink"].endswith("m1") and row["attempts"] == 1
    assert not any(p.endswith(".mp4") for p in sb.files) and any(p.endswith("cover.jpg") for p in sb.files)
    assert not m.handle(sb, FakeIG(sb), "2026_01_Q", "reel", "session", tmp_path, cache, report)   # never twice

    sb2 = FakeSB()
    with pytest.raises(RuntimeError):
        m.handle(sb2, FakeIG(sb2, fail=True), "2026_01_Q", "reel", "session", tmp_path, cache, [])
    assert sb2.db["ig_posts"][0]["status"] == "failed" and not any(p.endswith(".mp4") for p in sb2.files)


def _touch(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return p


class FakeUpHTTP:
    """Upload-Post: records multipart posts; status goes pending, in_progress, completed."""
    def __init__(self, fail=False):
        self.posts, self.polls, self.fail = [], 0, fail

    def post(self, url, headers=None, data=None, files=None, timeout=None):
        self.posts.append((url.rsplit("/", 1)[-1], dict(data), [f[0] for f in files], headers))
        return Resp({"success": True, "request_id": dict(data)["request_id"]})

    def get(self, url, headers=None, params=None, timeout=None):
        self.polls += 1
        if self.polls == 1:
            return Resp({"status": "pending", "results": []})
        if self.fail:
            return Resp({"status": "completed", "results": [{"platform": "instagram", "success": False, "error": "bad media"}]})
        if self.polls == 2:
            return Resp({"status": "in_progress", "results": [{"platform": "instagram", "success": True, "message": "Queued"}]})
        return Resp({"status": "completed", "results": [{"platform": "instagram", "success": True, "url": "https://www.instagram.com/reel/abc/"}]})


def test_uploadpost_reel_sends_the_file_and_records_the_link(tmp_path, monkeypatch):
    from pipeline.social import __main__ as m
    from pipeline.social.publish import UploadPost
    monkeypatch.setattr("pipeline.social.publish.POLL_S", 0)
    results, laps, drivers, traces = quali_fixture()
    st = story.quali_story(results, laps, drivers, CORNERS, traces, TRACK_M)
    meta = {"event": "Test Grand Prix", "code": "Q", "round": 1, "season": 2026}
    monkeypatch.setattr(render, "quali_reel", lambda st, meta, rot, out: (_touch(out / "reel.mp4"), _touch(out / "cover.jpg")))
    sb, http = FakeSB(), FakeUpHTTP()
    up = UploadPost("KEY", "f1telemetryhub", session=http)
    assert m.handle(sb, up, "2026_01_Q", "reel", "session", tmp_path, {"2026_01_Q": (meta, st, 0.0)}, [])
    path, data, files, headers = http.posts[0]
    assert path == "upload" and files == ["video", "cover_image"]
    assert data["platform[]"] == "instagram" and data["media_type"] == "REELS" and data["async_upload"] == "true"
    assert data["user"] == "f1telemetryhub" and headers["Idempotency-Key"] == data["request_id"]
    row = sb.db["ig_posts"][0]
    assert row["status"] == "published" and row["permalink"] == "https://www.instagram.com/reel/abc/"
    assert sb.files == {}   # nothing stored in the bucket
    assert not m.handle(sb, up, "2026_01_Q", "reel", "session", tmp_path, {"2026_01_Q": (meta, st, 0.0)}, [])
    assert len(http.posts) == 1   # never sent twice


def test_uploadpost_timeout_resumes_instead_of_resending(tmp_path, monkeypatch):
    from pipeline.social import __main__ as m
    from pipeline.social.publish import UploadPost
    monkeypatch.setattr("pipeline.social.publish.POLL_S", 0)
    monkeypatch.setattr("pipeline.social.publish.POLL_MAX_S", -1)   # first check times out
    results, laps, drivers, traces = quali_fixture()
    st = story.quali_story(results, laps, drivers, CORNERS, traces, TRACK_M)
    meta = {"event": "Test Grand Prix", "code": "Q", "round": 1, "season": 2026}
    monkeypatch.setattr(render, "quali_carousel", lambda st, meta, rot, out: [_touch(out / "s1.jpg"), _touch(out / "s2.jpg")])
    sb, http = FakeSB(), FakeUpHTTP()
    up = UploadPost("KEY", "f1telemetryhub", session=http)
    cache = {"2026_01_Q": (meta, st, 0.0)}
    assert not m.handle(sb, up, "2026_01_Q", "carousel", "session", tmp_path, cache, [])
    assert sb.db["ig_posts"][0]["status"] == "queued" and http.posts[0][2] == ["photos[]", "photos[]"]
    monkeypatch.setattr("pipeline.social.publish.POLL_MAX_S", 60)
    assert m.handle(sb, up, "2026_01_Q", "carousel", "session", tmp_path, cache, [])
    assert len(http.posts) == 1 and sb.db["ig_posts"][0]["status"] == "published"


def test_uploadpost_rejection_marks_failed(tmp_path, monkeypatch):
    from pipeline.social import __main__ as m
    from pipeline.social.publish import UploadPost
    monkeypatch.setattr("pipeline.social.publish.POLL_S", 0)
    results, laps, drivers, traces = quali_fixture()
    st = story.quali_story(results, laps, drivers, CORNERS, traces, TRACK_M)
    meta = {"event": "Test Grand Prix", "code": "Q", "round": 1, "season": 2026}
    monkeypatch.setattr(render, "quali_reel", lambda st, meta, rot, out: (_touch(out / "reel.mp4"), _touch(out / "cover.jpg")))
    sb = FakeSB()
    up = UploadPost("KEY", "f1telemetryhub", session=FakeUpHTTP(fail=True))
    with pytest.raises(Exception, match="bad media"):
        m.handle(sb, up, "2026_01_Q", "reel", "session", tmp_path, {"2026_01_Q": (meta, st, 0.0)}, [])
    assert sb.db["ig_posts"][0]["status"] == "failed"
