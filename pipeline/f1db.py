"""Load F1DB (https://github.com/f1db/f1db, CC BY 4.0) into our own Supabase schema `f1db`.

The latest release's SQLite file is downloaded, then every table is replaced through the
service-role-only function public.f1db_load. The 17 F1DB views (race_result, qualifying_result,
pit_stop, ...) are defined in the migration on top of these tables.
"""
from __future__ import annotations

import io
import json
import logging
import sqlite3
import tempfile
import zipfile
from datetime import date
from decimal import Decimal

import requests

log = logging.getLogger(__name__)
RELEASE_API = "https://api.github.com/repos/f1db/f1db/releases/latest"
ASSET = "f1db-sqlite.zip"
CHUNK = 1000


def latest_release(token: str | None = None) -> dict:
    h = {"Accept": "application/vnd.github+json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    r = requests.get(RELEASE_API, headers=h, timeout=60)
    r.raise_for_status()
    rel = r.json()
    url = next(a["browser_download_url"] for a in rel["assets"] if a["name"] == ASSET)
    return {"tag": rel["tag_name"], "published_at": rel["published_at"], "url": url}


def download_sqlite(url: str, folder: str) -> str:
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        name = next(n for n in z.namelist() if n.endswith(".db"))
        z.extract(name, folder)
    return f"{folder}/{name}"


def _jsonable(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, date):
        return v.isoformat()
    return v


def table_rows(con: sqlite3.Connection, table: str):
    """Rows of one table as dicts, with SQLite 0/1 turned back into booleans where F1DB declares BOOLEAN."""
    cols = con.execute(f'PRAGMA table_info("{table}")').fetchall()
    names = [c[1] for c in cols]
    boolean = {c[1] for c in cols if (c[2] or "").upper().startswith("BOOL")}
    for row in con.execute(f'SELECT * FROM "{table}"'):
        d = {}
        for k, v in zip(names, row):
            d[k] = (None if v is None else bool(v)) if k in boolean else _jsonable(v)
        yield d


def tables(con: sqlite3.Connection) -> list[str]:
    return [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def load(db_path: str, call) -> dict[str, int]:
    """call(table, rows, wipe) inserts rows and returns how many were written."""
    con = sqlite3.connect(db_path)
    counts = {}
    for t in tables(con):
        n, batch, first = 0, [], True
        for row in table_rows(con, t):
            batch.append(row)
            if len(batch) >= CHUNK:
                n += call(t, batch, first)
                batch, first = [], False
        if batch or first:
            n += call(t, batch, first)
        expected = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        if n != expected:
            raise RuntimeError(f"{t}: wrote {n} rows, F1DB has {expected}")
        counts[t] = n
        log.info("f1db.%s: %d rows", t, n)
    return counts


def run(sb, token: str | None = None) -> dict:
    rel = latest_release(token)
    log.info("F1DB %s (%s)", rel["tag"], rel["published_at"])
    with tempfile.TemporaryDirectory() as tmp:
        path = download_sqlite(rel["url"], tmp)
        counts = load(path, lambda t, rows, wipe: int(sb.rpc("f1db_load", {"tab": t, "rows": rows, "wipe": wipe}).execute().data))
    total = sum(counts.values())
    sb.rpc("f1db_stamp", {"ver": rel["tag"], "released": rel["published_at"], "total": total}).execute()
    log.info("F1DB %s loaded: %d tables, %d rows", rel["tag"], len(counts), total)
    return {"version": rel["tag"], "tables": len(counts), "rows": total}


def as_json(rows) -> str:
    return json.dumps(rows, separators=(",", ":"))
