"""Caption templates. Numbers only come from the computed story, so nothing is invented."""
from __future__ import annotations

import re

import numpy as np

from .story import QualiStory, RaceStory, corner_label

FOOTER = ("Every lap, every corner: f1telemetryhub.com (link in bio)\n"
          "Data: OpenF1. Unofficial fan analysis, not associated with Formula 1.")


def event_tag(event: str) -> str:
    return "#" + re.sub(r"[^A-Za-z0-9]", "", event.replace("Grand Prix", "GP"))


def tags(event: str, *codes: str) -> str:
    return " ".join(["#F1", "#Formula1", "#F1Telemetry", event_tag(event), *[f"#{c}" for c in codes if c], "#DataViz"])


def quali(st: QualiStory, meta: dict, kind: str, rewind: bool = False) -> str:
    a, b, g = st.a.code, st.b.code, st.best_a
    pole = "Sprint pole" if meta["code"] == "SQ" else "pole"
    lead = f"Season rewind, round {meta['round']}. " if rewind else ""
    lines = [f"{lead}{a} takes {pole} at the {meta['event']} by {st.official_gap_s:.3f} s over {b}.",
             "",
             f"Biggest gain: {corner_label(g.corner)}, worth {g.gain_s:.2f} s "
             f"({a} {g.apex_a:.0f} vs {b} {g.apex_b:.0f} km/h at the apex)."]
    if st.best_b:
        lines.append(f"{b} hit back in {corner_label(st.best_b.corner)} ({abs(st.best_b.gain_s):.2f} s).")
    lines += ["", "Same clock, same lap. Watch where the gap opens." if kind == "reel" else "Swipe for the full lap trace and the corners that decided it.",
              "", FOOTER, "", tags(meta["event"], a, b)]
    return clean("\n".join(lines))


def race(st: RaceStory, meta: dict, kind: str) -> str:
    w = st.winner["code"]
    what = "Sprint" if meta["code"] == "S" else meta["event"]
    lines = [f"{w} wins the {what}.", ""]
    for p in st.podium[1:]:
        g = st.gaps.get(p["code"])
        if g is not None and np.isfinite(g[-1]):
            lines.append(f"P{p['position']} {p['code']} +{g[-1]:.3f} s")
    if st.mover:
        m = st.mover
        lines += ["", f"Biggest climb: {m['code']}, P{m['grid']} on the grid to P{m['position']} at the flag."]
    lines += ["", "Gap to the leader, lap by lap." if kind == "reel" else "Swipe for the gaps lap by lap and the biggest climb.",
              "", FOOTER, "", tags(meta["event"], w, st.mover["code"] if st.mover else "")]
    return clean("\n".join(lines))


def clean(s: str) -> str:
    """House style: no hyphens or dashes in captions. Instagram limit: 2,200 characters."""
    s = s.replace("—", ",").replace("–", " to ").replace("-", " ")
    if len(s) > 2200:
        raise ValueError(f"caption is {len(s)} characters")
    return s
