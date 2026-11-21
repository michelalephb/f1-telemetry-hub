"""Caption templates. Numbers only come from the computed story, so nothing is invented."""
from __future__ import annotations

import re

import numpy as np

from .story import QualiStory, RaceStory, corner_label, sector_text

FOOTER = ("🔗 Every lap, every corner: f1telemetryhub.com (link in bio)\n\n"
          "📊 Data: OpenF1. Unofficial fan analysis, not associated with Formula 1.")

# Team colour dot for a driver, from the team colour in the timing data, so it works for any team and season.
_DOTS = [("🔴", (225, 6, 0)), ("🟠", (255, 128, 0)), ("🟡", (245, 200, 0)), ("🟢", (34, 153, 113)),
         ("🔵", (54, 113, 198)), ("🩵", (39, 220, 230)), ("🟣", (130, 60, 200)), ("🩷", (255, 120, 200)),
         ("⚪", (235, 235, 235)), ("🩶", (150, 155, 160)), ("⚫", (25, 25, 25)), ("🟤", (130, 80, 40))]


def dot(color: str | None) -> str:
    """Nearest coloured circle emoji for a team colour hex (e.g. '#E8002D' -> red)."""
    if not color:
        return "🏎️"
    h = color.lstrip("#")
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return "🏎️"
    return min(_DOTS, key=lambda e: sum((x - y) ** 2 for x, y in zip((r, g, b), e[1])))[0]


def drv(code: str, colors: dict | None) -> str:
    """Driver code with its team colour dot: '🔴 LEC'."""
    return f"{dot((colors or {}).get(code))} {code}" if code else ""


def paragraphs(*blocks) -> str:
    """Join non empty paragraphs with a blank line between them (Instagram keeps blank lines)."""
    out = []
    for b in blocks:
        if isinstance(b, (list, tuple)):
            b = "\n".join(x for x in b if x)
        if b:
            out.append(b)
    return "\n\n".join(out)


def event_tag(event: str) -> str:
    return "#" + re.sub(r"[^A-Za-z0-9]", "", event.replace("Grand Prix", "GP"))


MAX_TAGS = 5                     # Instagram caps posts at 5 hashtags (since December 2025)


def tags(event: str, *codes: str) -> str:
    """At most MAX_TAGS hashtags: brand, event, then the drivers in the story."""
    return " ".join(["#F1", "#F1Telemetry", event_tag(event), *[f"#{c}" for c in codes if c]][:MAX_TAGS])


def quali(st: QualiStory, meta: dict, kind: str, rewind: bool = False) -> str:
    a, b, c = st.a.code, st.b.code, st.best_a
    col = {st.a.code: st.a.color, st.b.code: st.b.color}
    pole = "Sprint pole" if meta["code"] == "SQ" else "pole"
    lead = f"⏪ Season rewind, round {meta['round']}. " if rewind else "⏱️ "
    secs = [f"S{k + 1}: {sector_text(g, a, b)}" for k, g in enumerate(st.sector_gaps)]
    apex = [f"🏁 Biggest apex speed gap: {corner_label(c.corner)}",
            f"{drv(a, col)} {c.min_a:.0f} km/h vs {drv(b, col)} {c.min_b:.0f} km/h"]
    if st.best_b:
        d = st.best_b
        apex.append(f"↩️ {drv(b, col)} was quicker through {corner_label(d.corner)}: {d.min_b:.0f} vs {d.min_a:.0f} km/h")
    return clean(paragraphs(
        f"{lead}{drv(a, col)} takes {pole} at the {meta['event']} by {st.official_gap_s:.3f} s over {drv(b, col)}",
        ["📐 Sector by sector"] + secs,
        apex,
        "🎥 Same clock, same lap. Watch where the gap opens." if kind == "reel"
        else "👉 Swipe for the sectors, the speed trace and the corners.\n💾 Save it for the race.",
        "💬 Which corner decided it? Tell us below.",
        "📤 Send it to the friend who called a different pole.",
        FOOTER, tags(meta["event"], a, b)))


def race(st: RaceStory, meta: dict, kind: str) -> str:
    w = st.winner["code"]
    col = st.colors or {}
    what = "Sprint" if meta["code"] == "S" else meta["event"]
    pod = [f"🥇 {drv(w, col)}"]
    for p, medal in zip(st.podium[1:], ("🥈", "🥉")):
        g = st.gaps.get(p["code"])
        gap = f" +{g:.3f} s" if g is not None and np.isfinite(g) else ""
        pod.append(f"{medal} {drv(p['code'], col)}{gap}")
    mover = None
    if st.mover:
        m = st.mover
        mover = f"🚀 Biggest climb: {drv(m['code'], col)}, P{m['grid']} on the grid to P{m['position']} at the flag"
    return clean(paragraphs(
        f"🏆 {drv(w, col)} wins the {what}",
        pod,
        mover,
        "🎥 The top 5, lap by lap." if kind == "reel"
        else "👉 Swipe for the running order lap by lap and the biggest climb.\n💾 Save it.",
        "💬 Driver of the day? Tell us below.",
        "📤 Send it to the friend who backed someone else.",
        FOOTER, tags(meta["event"], w, st.mover["code"] if st.mover else "")))


def clean(s: str) -> str:
    """House style: no hyphens or dashes in captions. Instagram limit: 2,200 characters."""
    s = s.replace("—", ",").replace("–", " to ").replace("-", " ")
    if len(s) > 2200:
        raise ValueError(f"caption is {len(s)} characters")
    return s
