import numpy as np
import pandas as pd

from pipeline import tracks


def ellipse(n=400):
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.c_[3000 * np.cos(th), 1500 * np.sin(th)]


def test_outline_box_and_transform():
    xy = ellipse()
    o = tracks.outline(xy, rot=0)
    pts = np.array([[float(v) for v in p.split(",")] for p in o["pts"].split()])
    assert len(pts) == tracks.N_POINTS and o["w"] == 100
    assert abs(pts[:, 0].min() - tracks.PAD) < 0.2 and abs(pts[:, 0].max() - (100 - tracks.PAD)) < 0.2
    assert abs(o["h"] - ((100 - 2 * tracks.PAD) / 2 + 2 * tracks.PAD)) < 0.2  # 2:1 ellipse: half as tall
    # any raw point maps onto the outline through the stored transform
    r = tracks.rotate(xy[100:101], o["rot"])[0]
    u, v = (r[0] - o["x0"]) * o["k"], (o["y0"] - r[1]) * o["k"]
    assert np.min(np.hypot(pts[:, 0] - u, pts[:, 1] - v)) < 1.5


def test_rotation_turns_the_layout():
    o = tracks.outline(ellipse(), rot=90)
    assert o["h"] > 150  # wide ellipse becomes tall


def test_fastest_complete_lap_is_used():
    xy = ellipse()
    tr = pd.DataFrame({
        "lap_number": np.repeat([1, 2, 3], 400),
        "t": np.r_[np.linspace(0, 95, 400), np.linspace(95, 180, 400), np.linspace(180, 300, 400)],
        "lap_dist_m": np.r_[np.linspace(0, 5000, 400), np.linspace(0, 5000, 400), np.linspace(0, 2000, 400)],
        "in_lap": True, "x": np.tile(xy[:, 0], 3), "y": np.tile(xy[:, 1], 3) + np.repeat([0, 7, 0], 400),
    })
    out = tracks.lap_xy_from_trace(tr)
    assert len(out) == 400 and out[0, 1] == xy[0, 1] + 7  # lap 2: complete and fastest
