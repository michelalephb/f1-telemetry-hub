"""OpenF1 client (https://openf1.org). Free historical data from 2023, no key.

Free tier limit: 3 requests per second and 30 per minute, so every call is spaced
by MIN_INTERVAL_S and 429 responses back off.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

BASE = "https://api.openf1.org/v1"
HEADERS = {"User-Agent": "f1-telemetry-hub/0.2 (+https://github.com/michelalephb/f1-telemetry-hub)"}
MIN_INTERVAL_S = 2.1
# OpenF1 answers 401 to anonymous users while an F1 session is live (19 Nov 2026: from about an hour
# before FP1). Every good answer is kept on disk (the workflow carries the folder from run to run with
# actions/cache) and served when OpenF1 refuses, so race week posts keep going through the sessions.
CACHE = Path(os.environ.get("OPENF1_CACHE", ".openf1_cache"))
DIRTY = Path(os.environ.get("OPENF1_CACHE_DIRTY", "openf1_cache_dirty"))

log = logging.getLogger(__name__)


class OpenF1:
    def __init__(self, session: requests.Session | None = None):
        self.http = session or requests.Session()
        self.http.headers.update(HEADERS)
        self._last = 0.0

    def get(self, path: str, filters: list[str] | None = None, **params) -> list[dict]:
        """GET /path?k=v&...; `filters` are raw comparisons such as 'date>=2026-11-08T17:00:00'."""
        parts = [f"{k}={quote(str(v))}" for k, v in params.items()]
        parts += [quote(f, safe="=<>") for f in (filters or [])]
        url = f"{BASE}/{path}" + ("?" + "&".join(parts) if parts else "")
        for attempt in range(6):
            wait = self._last + MIN_INTERVAL_S - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self.http.get(url, timeout=120)
            except requests.RequestException as e:
                log.warning("OpenF1 %s on %s", type(e).__name__, path)
                if attempt >= 2:
                    break
                time.sleep(10 * (attempt + 1))
                continue
            if r.status_code == 200:
                data = r.json()
                self._keep(url, data)
                return data
            if r.status_code == 404:  # OpenF1 answers 404 when nothing matches
                self._keep(url, [])
                return []
            if r.status_code in (401, 403):  # live session lockout: no point retrying
                break
            if r.status_code in (429, 500, 502, 503, 504):
                back = 10 * (attempt + 1)
                log.warning("OpenF1 %s on %s, retrying in %ss", r.status_code, path, back)
                time.sleep(back)
                continue
            r.raise_for_status()
        kept = self._kept(url)
        if kept is not None:
            log.warning("OpenF1 refused %s: served the kept answer", path)
            return kept
        raise RuntimeError(f"OpenF1 gave up on {url} (nothing kept for it)")

    @staticmethod
    def _file(url: str) -> Path:
        return CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".json")

    def _keep(self, url: str, data) -> None:
        try:
            f = self._file(url)
            body = json.dumps(data, separators=(",", ":"))
            if f.exists() and f.read_text() == body:
                return
            CACHE.mkdir(parents=True, exist_ok=True)
            f.write_text(body)
            DIRTY.touch()
        except Exception as e:  # the cache must never break a post
            log.warning("OpenF1 cache write failed: %s", e)

    def _kept(self, url: str):
        try:
            f = self._file(url)
            return json.loads(f.read_text()) if f.exists() else None
        except Exception:
            return None

    def frame(self, path: str, filters: list[str] | None = None, **params) -> pd.DataFrame:
        return pd.DataFrame(self.get(path, filters, **params))
