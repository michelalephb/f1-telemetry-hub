"""Measure and optimise for growth.

metrics (twice a day): per post numbers from Upload-Post for everything we published in the last 21 days,
plus the profile (followers, reach) once a day, into Supabase (ig_metrics, ig_profile_daily).

optimize (weekly, Sunday night): scores each story group on the last 14 days and sets its weight in the
race week rotation (social_weights: 3 for the best, 2 for the runner up, 1 for the rest). Guardrails: a group
needs 3 measured posts to be ranked, weights move by at most 1 a week, and no group ever drops out.

Score = (3 x saves + 3 x shares + 2 x comments + likes) per 100 reached accounts: saves and shares are what
Instagram rewards most for reach to non followers. When a post has no interaction numbers (stories may not),
reach per post is used instead, compared only within the same kind.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

log = logging.getLogger(__name__)

GROUPS = ("preview", "strategy", "braking", "conditions", "history", "lap", "gears", "raceday")


def score(m: dict) -> float | None:
    reach = m.get("reach") or m.get("views") or 0
    inter = sum((m.get(k) or 0) * w for k, w in (("saves", 3), ("shares", 3), ("comments", 2), ("likes", 1)))
    if reach <= 0:
        return None
    return 100.0 * inter / reach if inter else None


def _int(v):
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def cmd_metrics(a) -> int:
    import os

    from .. import store
    from .publish import UploadPost

    sb = store.client()
    up = UploadPost(os.environ["UPLOADPOST_API_KEY"], os.environ.get("UPLOADPOST_USER") or "f1telemetryhub")
    since = (datetime.now(timezone.utc) - timedelta(days=21)).isoformat()
    rows = sb.table("ig_posts").select("session_id,kind,container_id,content").eq("status", "published") \
        .gte("created_at", since).execute().data
    today = date.today().isoformat()
    done = fail = 0
    for r in rows:
        rid = (r.get("container_id") or "").removeprefix("up:")
        if not rid or rid == r.get("container_id"):
            continue
        try:
            m = up.post_analytics(rid)
        except Exception as e:                   # one bad post must not stop the rest
            log.warning("no metrics for %s: %s", r["session_id"], e)
            fail += 1
            continue
        if m is None:
            continue
        sb.table("ig_metrics").upsert({
            "session_id": r["session_id"], "kind": r["kind"], "day": today,
            **{k: _int(m.get(k)) for k in ("likes", "comments", "saves", "shares", "reach", "views")}, "raw": m,
        }, on_conflict="session_id,kind,day").execute()
        done += 1
    try:
        prof = up.profile_analytics()
        if prof:
            sb.table("ig_profile_daily").upsert({
                "day": today, "followers": _int(prof.get("followers")), "reach": _int(prof.get("reach")),
                "views": _int(prof.get("views")), "profile_views": _int(prof.get("profileViews")),
                **{k: _int(prof.get(k)) for k in ("likes", "comments", "shares", "saves")}, "raw": prof,
            }, on_conflict="day").execute()
            log.info("profile: %s followers", prof.get("followers"))
    except Exception as e:
        log.warning("no profile analytics: %s", e)
    print(f"{'metrics':>20}  {done} posts measured, {fail} failed, {len(rows)} published in 21 days")
    return 0


def rank(rows: list[dict]) -> dict[str, tuple[float, int]]:
    """Mean score per story group from joined post rows ({content, kind, metrics...}); latest day per post."""
    latest: dict[str, dict] = {}
    for r in rows:
        if r["session_id"] not in latest or r["day"] > latest[r["session_id"]]["day"]:
            latest[r["session_id"]] = r
    by: dict[str, list[float]] = {}
    for r in latest.values():
        grp = (r.get("content") or "").split(" ")[0]
        if grp not in GROUPS:
            continue
        s = score(r)
        if s is None and r.get("reach"):
            s = float(r["reach"])            # stories without interaction numbers: reach
        if s is not None:
            by.setdefault(grp, []).append(s)
    return {g: (sum(v) / len(v), len(v)) for g, v in by.items()}


def new_weights(ranked: dict[str, tuple[float, int]], old: dict[str, int]) -> dict[str, int]:
    eligible = sorted((g for g, (_, n) in ranked.items() if n >= 3), key=lambda g: ranked[g][0], reverse=True)
    target = {g: 1 for g in GROUPS}
    if eligible:
        target[eligible[0]] = 3
    if len(eligible) > 1:
        target[eligible[1]] = 2
    out = {}
    for g in GROUPS:
        o = old.get(g, 1)
        t = target[g]
        out[g] = max(1, min(3, o + (1 if t > o else -1 if t < o else 0)))   # one step a week
    return out


def cmd_optimize(a) -> int:
    from .. import store
    sb = store.client()
    since = (date.today() - timedelta(days=14)).isoformat()
    met = sb.table("ig_metrics").select("*").gte("day", since).execute().data
    # a story keeps gaining reach until it expires after 24 h: only score posts whose numbers are final
    final = (datetime.now(timezone.utc) - timedelta(hours=26)).isoformat()
    posts = {r["session_id"]: r.get("content") for r in
             sb.table("ig_posts").select("session_id,content").eq("status", "published")
             .lt("created_at", final).execute().data}
    met = [m for m in met if m["session_id"] in posts]
    for m in met:
        m["content"] = posts.get(m["session_id"])
    ranked = rank([m for m in met if m["kind"] == "story"])
    old = {r["grp"]: r["weight"] for r in sb.table("social_weights").select("*").execute().data}
    w = new_weights(ranked, old)
    for g, wt in w.items():
        sc, n = ranked.get(g, (None, 0))
        sb.table("social_weights").upsert({"grp": g, "weight": wt, "score": sc, "n": n,
                                           "updated_at": datetime.now(timezone.utc).isoformat()},
                                          on_conflict="grp").execute()
    print(f"{'weights':>20}  " + ", ".join(f"{g} {w[g]} ({ranked.get(g, (0, 0))[1]} posts)" for g in GROUPS))
    return 0


def weights(sb) -> dict[str, int]:
    try:
        return {r["grp"]: int(r["weight"]) for r in sb.table("social_weights").select("grp,weight").execute().data}
    except Exception:
        return {}
