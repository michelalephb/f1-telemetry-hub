"""Story Reels (Michel, 22 Nov): one idea per scene, numbers that count up, a narrated voice track.

Modelled on the scene by scene data stories that work on Instagram: a kicker, a headline, one animated element
(tiles, a duel of two bars, a lap strip, a verdict), the source in every footer. Every number comes from the data
passed in. Narration is generated per scene with a local Piper voice (PIPER_VOICE, an .onnx model path); without a
voice the Reel is silent and otherwise identical. Scene length follows its narration so voice and picture line up.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from . import preview as P
from .render import FPS, H_REEL, Reel

_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen " \
        "seventeen eighteen nineteen".split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def words(x: float, dec: int = 1) -> str:
    """A number as the voice should say it: 17.6 -> seventeen point six, 349 -> three hundred forty nine."""
    def whole(n: int) -> str:
        if n < 20:
            return _ONES[n]
        if n < 100:
            return _TENS[n // 10] + ("" if n % 10 == 0 else " " + _ONES[n % 10])
        if n < 1000:
            return _ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + whole(n % 100))
        return whole(n // 1000) + " thousand" + ("" if n % 1000 == 0 else " " + whole(n % 1000))
    s = f"{abs(x):.{dec}f}"
    a, _, b = s.partition(".")
    out = whole(int(a)) if int(a) or not b else ("" if b else "zero")
    if b and int(b):
        out = (out + " point " if out else "point ") + " ".join(_ONES[int(d)] for d in b.rstrip("0"))
    return out.strip()


def _ease(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def _frame(p, tag: str, src: str):
    c = P.Card(H_REEL, story=True)
    c.header(p)
    c.text(0.94, 0.835, tag.upper(), 12, color=P.MUTED, weight=600, ha="right", track=True)
    c.text(0.06, 0.170, "@F1TELEMETRYHUB", 12, color=P.MUTED, weight=600, ha="left", track=True)
    c.text(0.94, 0.170, src.upper(), 12, color=P.MUTED, weight=600, ha="right", track=True)
    c.footer()
    return c


def _head(c, kicker: str, headline: list[str], colors: list[str] | None = None, y: float = 0.74):
    c.text(0.06, y, kicker.upper(), 20, color=P.CYAN, weight=700, ha="left", track=True)
    out = []
    for k, line in enumerate(headline):
        out.append(c.text(0.06, y - 0.062 - k * 0.056, line, 62, color=(colors or [P.TEXT] * 9)[k], weight=800, ha="left"))
    return out


def _box(c, x, y, w, h, fc="#141923", ec="#232D3F"):
    r = plt.Rectangle((x, y), w, h, transform=c.fig.transFigure, fc=fc, ec=ec, lw=1.2)
    c.fig.add_artist(r)
    return r


def scene_title(c, s):
    a = c.text(0.5, 0.58, s["a"].upper(), 92, color=s["ca"], weight=900)
    v = c.text(0.5, 0.52, "vs", 28, color=P.MUTED, weight=400)
    b = c.text(0.5, 0.46, s["b"].upper(), 92, color=s["cb"], weight=900)
    sub = c.text(0.5, 0.38, s.get("sub", "").upper(), 20, color=P.CYAN, weight=600, track=True)

    def upd(e):
        a.set_x(0.5 - 0.6 * (1 - _ease(e * 3))), b.set_x(0.5 + 0.6 * (1 - _ease(e * 3 - 0.3)))
        v.set_alpha(_ease(e * 3 - 0.6)), sub.set_alpha(_ease(e * 3 - 0.9))
    return upd


def scene_tiles(c, s):
    _head(c, s["kicker"], s["headline"])
    tiles = s["tiles"]
    spots = [(0.06, 0.42, 0.425), (0.515, 0.42, 0.425), (0.06, 0.27, 0.88)]
    arts = []
    for (x, y, w), t in zip(spots, tiles):
        _box(c, x, y, w, 0.13)
        c.fig.add_artist(plt.Line2D([x, x + w], [y + 0.13, y + 0.13], transform=c.fig.transFigure, color=t["color"], lw=5))
        n = c.text(x + 0.03, y + 0.082, "", 76, color=t["color"], weight=800, ha="left")
        lab = c.text(x + 0.03, y + 0.027, t["label"], 19, color=P.TEXT, weight=400, ha="left")
        arts.append((n, lab, t))

    def upd(e):
        for k, (n, lab, t) in enumerate(arts):
            q = _ease(e * 2.2 - k * 0.25)
            n.set_text(t["fmt"].format(t["value"] * q) if q > 0 else "")
            lab.set_alpha(q)
    return upd


def scene_duel(c, s):
    _head(c, s["kicker"], s["headline"])
    rows, top = s["rows"], max(r["value"] for r in s["rows"])
    lo = s.get("floor", 0.0)
    arts = []
    for k, r in enumerate(rows):
        y = 0.50 - k * 0.14
        c.text(0.06, y + 0.045, r["name"].upper(), 24, color=r["color"], weight=800, ha="left", track=True)
        _box(c, 0.06, y - 0.028, 0.88, 0.055, fc="#10151E", ec="#10151E")
        bar = plt.Rectangle((0.06, y - 0.028), 0, 0.055, transform=c.fig.transFigure, fc=r["color"])
        c.fig.add_artist(bar)
        val = c.text(0.94, y + 0.045, "", 40, color=P.TEXT, weight=800, ha="right")
        arts.append((bar, val, r))
    note = c.text(0.06, 0.26, s.get("note", ""), 20, color=P.MUTED, weight=400, ha="left")

    def upd(e):
        for k, (bar, val, r) in enumerate(arts):
            q = _ease(e * 2 - k * 0.2)
            bar.set_width(0.88 * (lo + (r["value"] - lo) * q - lo) / (top - lo) if top > lo else 0)
            val.set_text(s["fmt"].format(lo + (r["value"] - lo) * q) if q > 0 else "")
        note.set_alpha(_ease(e * 2 - 0.8))
    return upd


def scene_strip(c, s):
    """Who led along the lap: a strip that fills left to right in the leader's colour, with passes marked."""
    _head(c, s["kicker"], s["headline"])
    S, lead, cols = np.asarray(s["dist"]), np.asarray(s["lead"]), s["colors"]
    f0 = s.get("from", 0.0)                       # zoom: only the part of the lap where it happened
    keep_ = S >= f0 * S[-1]
    S, lead = (S[keep_] - f0 * S[-1]) / (1 - f0), lead[keep_]
    L = S[-1] if S[-1] > 0 else 1
    x0, w, y, h = 0.06, 0.88, 0.42, 0.09
    _box(c, x0, y, w, h, fc="#10151E", ec="#232D3F")
    segs = []
    edges = np.flatnonzero(np.diff(lead)) + 1
    starts = np.concatenate([[0], edges])
    ends = np.concatenate([edges, [len(S) - 1]])
    for a, b in zip(starts, ends):
        r = plt.Rectangle((x0 + w * S[a] / L, y), 0, h, transform=c.fig.transFigure, fc=cols[int(lead[a])])
        c.fig.add_artist(r)
        segs.append((r, S[a] / L, S[b] / L))
    marks = []
    for fr, lab in s.get("marks", []):
        fr = (fr - f0) / (1 - f0)
        if fr < 0:
            continue
        c.fig.add_artist(plt.Line2D([x0 + w * fr] * 2, [y - 0.012, y + h + 0.012], transform=c.fig.transFigure,
                                    color="#5D6573", lw=1))
        c.text(x0 + w * fr, y - 0.03, lab, 16, color=P.MUTED, weight=600, track=True)
    for j, (fr, lab, col) in enumerate(s.get("passes", [])):
        fr = (fr - f0) / (1 - f0)
        t = c.text(x0 + w * fr, y + h + 0.040 + 0.035 * (j % 2), lab, 20, color=col, weight=800)
        a_ = c.fig.add_artist(plt.Line2D([x0 + w * fr] * 2, [y + h, y + h + 0.025], transform=c.fig.transFigure, color=col, lw=3))
        marks.append((fr, t, a_))
    legend = [c.text(0.06, 0.32, s["legend"][0][0], 22, color=s["legend"][0][1], weight=700, ha="left"),
              c.text(0.94, 0.32, s["legend"][1][0], 22, color=s["legend"][1][1], weight=700, ha="right")]

    def upd(e):
        f = _ease(e * 1.4)
        for r, a, b in segs:
            r.set_width(w * max(0.0, min(f, b) - a))
        for fr, t, a_ in marks:
            on = 1.0 if f >= fr else 0.0
            t.set_alpha(on), a_.set_alpha(on)
        for lg in legend:
            lg.set_alpha(_ease(e * 2))
    return upd


def scene_verdict(c, s):
    hs = _head(c, s["kicker"], [], y=0.60)
    l1 = c.text(0.06, 0.52, s["lines"][0], 56, color=P.TEXT, weight=800, ha="left")
    l2 = c.text(0.06, 0.465, s["lines"][1], 56, color=s["color"], weight=800, ha="left")
    q = c.text(0.06, 0.34, s.get("question", ""), 28, color=P.MUTED, weight=400, ha="left")

    def upd(e):
        l1.set_alpha(_ease(e * 3)), l2.set_alpha(_ease(e * 3 - 0.8)), q.set_alpha(_ease(e * 3 - 1.4))
    return upd


SCENES = {"title": scene_title, "tiles": scene_tiles, "duel": scene_duel, "strip": scene_strip, "verdict": scene_verdict}


def _say(text: str, wav: Path, voice: str) -> float:
    subprocess.run(["python3", "-m", "piper", "-m", voice, "-f", str(wav), "--length_scale", "0.92"],
                   input=text.encode(), check=True, capture_output=True)
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(wav)],
                         capture_output=True, text=True, check=True).stdout
    return float(out)


def build(p, scenes: list[dict], out: Path, tag: str, src: str, voice: str | None = None) -> Path:
    """Render the scenes into one Reel; with a voice, narrate each scene and mux the track in."""
    voice = voice or os.environ.get("PIPER_VOICE")
    voice = voice if voice and Path(voice).exists() else None
    tmp = Path(tempfile.mkdtemp())
    lens, wavs = [], []
    for k, s in enumerate(scenes):
        d = s.get("dur", 3.0)
        if voice and s.get("say"):
            wav = tmp / f"s{k}.wav"
            d = max(d, _say(s["say"], wav, voice) + 0.7)
            wavs.append((wav, d))
        else:
            wavs.append((None, d))
        lens.append(d)
    silent = out.with_suffix(".silent.mp4") if voice else out
    r = Reel(silent)
    for s, d in zip(scenes, lens):
        c = _frame(p, tag, src)
        upd = SCENES[s["type"]](c, s)
        n = int(d * FPS)
        for i in range(n):
            ts = i / FPS
            upd(ts / d if s["type"] == "strip" else ts / 2.5)     # animations settle early, then hold for the voice
            r.add(c.fig)
        plt.close(c.fig)
    r.close()
    if not voice:
        return out
    parts = []
    for k, (wav, d) in enumerate(wavs):
        seg = tmp / f"p{k}.wav"
        src_ = ["-i", str(wav)] if wav else ["-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono"]
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *src_, "-af", f"adelay=250|250,apad", "-t", f"{d:.3f}",
                        "-ar", "44100", "-ac", "1", str(seg)], check=True)
        parts.append(seg)
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{q}'\n" for q in parts))
    track = tmp / "voice.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), str(track)], check=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(silent), "-i", str(track), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-af", "loudnorm=I=-16:TP=-1.5", "-shortest",
                    "-movflags", "+faststart", str(out)], check=True)
    silent.unlink(missing_ok=True)
    return out


def duel_scenes(D: dict, ref_len: float, segments: list, names: dict, race: str) -> list[dict]:
    """Scenes for a two car lap duel from deploy_data (Max against Antonelli, Las Vegas lap 47)."""
    F, O = D["focus"], D["other"]
    cF, cO = D["colors"][F], D["colors"][O]
    if cF.lower() == cO.lower():
        cO = P.TEXT
    S = np.asarray(D["S"], float)
    vf, vo = np.asarray(D["f"]["v"]), np.asarray(D["o"]["v"])
    tf, to_ = np.asarray(D["f"]["t"]), np.asarray(D["o"]["t"])
    L = float(ref_len)                                  # same lap length as the published deployment Reel
    seg = {nm: (S >= a * L) & (S <= b * L) for nm, a, b in segments}
    strip_nm = max(seg, key=lambda nm: float(np.mean(vo[seg[nm]] - vf[seg[nm]])))      # where the rival gained most
    end_nm = max(seg, key=lambda nm: float(np.mean(vf[seg[nm]] - vo[seg[nm]])))        # where the focus gained most
    gO = float(np.mean(vo[seg[strip_nm]] - vf[seg[strip_nm]]))
    gF = float(np.mean(vf[seg[end_nm]] - vo[seg[end_nm]]))
    topO, topF = float(vo[seg[strip_nm]].max()), float(vf[seg[strip_nm]].max())
    eF, eO = float(vf[seg[end_nm]].max()), float(vo[seg[end_nm]].max())
    lead = np.where(tf < to_, 0, 1)
    sw = list(np.flatnonzero(np.diff(lead)) + 1)
    keep, k = [], 0
    while k < len(sw):                                   # side by side swaps within 200 m cancel out
        if k + 1 < len(sw) and S[sw[k + 1]] - S[sw[k]] < 200:
            k += 2
            continue
        keep.append(sw[k])
        k += 1
    passes = [(S[i] / S[-1], f"{(F if lead[i] == 0 else O)} PASSES", cF if lead[i] == 0 else cO) for i in keep]
    gap = abs(tf[-1] - to_[-1])
    win = F if tf[-1] < to_[-1] else O
    nF, nO = names.get(F, F), names.get(O, O)
    marks = [(a, nm.split(" to ")[0].replace("The ", "").upper()) for nm, a, b in segments if a > 0] + [(1.0, "LINE")]
    return [
        {"type": "title", "a": nF, "b": nO, "ca": cF, "cb": cO, "sub": f"{race}, lap {D['lap']}", "dur": 2.6,
         "say": f"{nF} against {nO}. {race}, lap {words(D['lap'], 0)}."},
        {"type": "tiles", "kicker": f"Lap {D['lap']}", "headline": ["Passed, then", "back in front"], "dur": 4.5,
         "tiles": [{"value": gO, "fmt": "+{:.1f}", "color": cO, "label": f"km/h {O} faster, {strip_nm}"},
                   {"value": gF, "fmt": "+{:.1f}", "color": cF, "label": f"km/h {F} faster, {end_nm}"},
                   {"value": gap, "fmt": "{:.2f} s", "color": cF if win == F else cO, "label": f"{win} ahead at the line"}],
         "say": f"{nO} was {words(gO)} kilometres an hour faster on {strip_nm.lower().replace('the ', 'the ')}. "
                f"{nF} was {words(gF)} faster from {end_nm.lower().replace('t16', 'turn sixteen')}."},
        {"type": "duel", "kicker": f"{strip_nm}, top speed", "headline": [f"{nO} flies", "down the Strip" if "Strip" in strip_nm else ""],
         "rows": [{"name": nO, "value": topO, "color": cO}, {"name": nF, "value": topF, "color": cF}],
         "fmt": "{:.0f} km/h", "floor": 250.0, "dur": 4.0,
         "say": f"Top speed on {strip_nm.lower()}: {nO} {words(topO, 0)}, {nF} {words(topF, 0)}."},
        {"type": "strip", "kicker": "Who led, metre by metre", "headline": ["One lap,", "two passes"],
         "dist": S.tolist(), "lead": lead.tolist(), "colors": [cF, cO], "marks": marks, "passes": passes,
         "legend": [(f"{F} ahead", cF), (f"{O} ahead", cO)], "dur": 5.0, "from": 0.5,
         "say": f"{nO} takes the lead on {strip_nm.lower()}. {nF} takes it back before turn seventeen."},
        {"type": "duel", "kicker": end_nm.replace("T16", "Turn 16") + ", top speed", "headline": [f"{nF} attacks", "at the end"],
         "rows": [{"name": nF, "value": eF, "color": cF}, {"name": nO, "value": eO, "color": cO}],
         "fmt": "{:.0f} km/h", "floor": 250.0, "dur": 4.0,
         "say": f"From turn sixteen to the line: {nF} {words(eF, 0)}, {nO} {words(eO, 0)}."},
        {"type": "verdict", "kicker": "The verdict", "lines": [f"Slower on {strip_nm.replace('The ', 'the ')}.", "Faster where it counted."],
         "color": cF, "question": "Who was your favourite driver today?", "dur": 4.0,
         "say": f"{names.get(win, win)} crosses the line {words(gap, 2)} seconds ahead. Slower on the Strip. Faster where it counted."},
    ]
