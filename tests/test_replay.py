import numpy as np
import pandas as pd

from pipeline import replay

L = 4300.0


def trace(speed, t0, laps, hole=None):
    rows = []
    for lap in range(1, laps + 1):
        for d in np.arange(-60, L + 60, 20.0):
            t = t0 + ((lap - 1) * L + d) / speed
            if hole and hole[0] < t < hole[1]:
                continue
            rows.append((lap, t, d))
    return pd.DataFrame(rows, columns=["lap_number", "t", "lap_dist_m"])


def test_round_trip_and_gaps():
    df = replay.build({"1": trace(60, 100, 3), "44": trace(55, 101, 2, hole=(150, 170))}, L)
    assert list(df.columns) == ["_t", "1", "44"]
    dec = replay.decode(df).set_index("_t")
    assert abs(dec.loc[149.0, "1"] - (149 - 100) * 60) <= 1          # on the 1 s grid
    assert abs(dec.loc[160.0, "44"] - (160 - 101) * 55) <= 2         # a hole in the data is bridged
    assert np.isnan(dec.loc[299.0, "44"])                            # after its last sample: absent
    assert (np.diff(dec["1"].dropna().to_numpy()) >= 0).all()         # never backwards


def test_overlap_at_the_line_does_not_go_backwards():
    # the same moment appears at the end of lap 1 (d = L + 40) and start of lap 2 (d = -20)
    tr = pd.DataFrame({"lap_number": [1, 1, 2, 2], "t": [10.0, 10.5, 10.4, 11.0], "lap_dist_m": [4290.0, 4340.0, -20.0, 30.0]})
    t, m = replay.covered(tr, L)
    assert (np.diff(m) >= 0).all() and (np.diff(t) > 0).all()
