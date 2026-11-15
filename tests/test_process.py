"""Synthetic laps with known ground truth: a closed track, a speed profile with one
heavy braking corner, position sampled at 220 ms with noise, car data at 240 ms."""
import numpy as np
import pandas as pd

from pipeline.geometry import CentreLine, build_centre_line
from pipeline.process import corner_metrics, fuse_lap, pos_distance

RNG = np.random.default_rng(1)


def track(n=6000):
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    # stadium with a wobble, about 3.9 km
    x = 900 * np.cos(th) + 120 * np.cos(3 * th)
    y = 450 * np.sin(th)
    z = 5 * np.sin(2 * th)
    return np.column_stack([x, y, z])


TRUE = CentreLine(track())
L = TRUE.length
APEX = 0.5 * L
BRAKE_AT = -120.0  # metres before apex


def speed_at(d):
    rel = (d % L) - APEX
    v = np.full_like(rel, 300.0)
    k = (300.0**2 - 100.0**2) / (-BRAKE_AT)
    br = (rel >= BRAKE_AT) & (rel < 0)
    v[br] = np.sqrt(100.0**2 + k * (-rel[br]))
    ex = (rel >= 0) & (rel < 400)
    v[ex] = np.minimum(300.0, np.sqrt(100.0**2 + 160.0 * rel[ex]))
    return v


def drive(laps=3, dt=0.01):
    t, d = [0.0], [-200.0]  # start 200 m before the line
    while d[-1] < laps * L + 300:
        d.append(d[-1] + speed_at(np.array([d[-1]]))[0] / 3.6 * dt)
        t.append(t[-1] + dt)
    return np.array(t), np.array(d)


def sample(t, d, period, jitter=0.01):
    ts = np.arange(t[0], t[-1], period) + RNG.normal(0, jitter, int(np.ceil((t[-1] - t[0]) / period)))[: len(np.arange(t[0], t[-1], period))]
    ts = np.sort(np.clip(ts, t[0], t[-1]))
    return ts, np.interp(ts, t, d)


def make_frames():
    t, d = drive()
    pt, pd_ = sample(t, d, 0.22)
    s = pd_ % L
    xyz = np.column_stack([np.interp(s, TRUE.s0, TRUE.p[:, k], period=L) for k in range(3)])
    xyz[:, :2] += RNG.normal(0, 0.6, (len(xyz), 2))  # GPS like noise, metres
    pos = pd.DataFrame({"t": pt, "x": xyz[:, 0] * 10, "y": xyz[:, 1] * 10, "z": xyz[:, 2] * 10, "status": "OnTrack"})
    ct, cd = sample(t, d, 0.24)
    sp = speed_at(cd) * (1 + 0.01)  # 1 % speed sensor scale error, the fusion must absorb it
    rel = (cd % L) - APEX
    car = pd.DataFrame({"t": ct, "speed": np.round(sp), "brake": (rel >= BRAKE_AT) & (rel < -10), "true_d": cd})
    lap_starts = np.interp(np.arange(0, 4) * L, d, t)
    return pos, car, lap_starts


def test_centre_line_matches_truth():
    laps = []
    for _ in range(4):
        p = TRUE.p[::7] + np.column_stack([RNG.normal(0, 0.8, (len(TRUE.p[::7]), 2)), np.zeros(len(TRUE.p[::7]))])
        laps.append(np.roll(p, RNG.integers(-3, 3), axis=0))
    line = CentreLine(build_centre_line(laps, n=4000))
    assert abs(line.length - L) / L < 0.005
    _, dist = line.project(TRUE.p[::50])
    assert np.median(dist) < 1.0


def test_fusion_and_corner_metrics():
    pos, car, starts = make_frames()
    pos = pos_distance(pos, TRUE)
    lap = fuse_lap(car, pos, starts[1], starts[2], TRUE)
    assert lap is not None
    inl = lap[lap["in_lap"]]
    err = inl["lap_dist_m"].to_numpy() - (inl["true_d"].to_numpy() - L)
    assert np.percentile(np.abs(err), 95) < 3.0, np.percentile(np.abs(err), 95)

    m = corner_metrics(lap, APEX)
    assert m is not None
    # one car sample is about 7 m at 100 kph and 20 m at 300 kph; onset is placed between two samples
    assert abs(m["brake_point_m"] - BRAKE_AT) < 12.0, m
    assert abs(m["min_speed_kph"] - 101) < 6.0, m
    assert abs(m["min_speed_at_m"]) < 10.0, m
    assert m["n_samples"] > 20
