"""OpenF1 client (https://openf1.org). Free historical data from 2023, no key.

Free tier limit: 3 requests per second and 30 per minute, so every call is spaced
by MIN_INTERVAL_S and 429 responses back off.
"""
from __future__ import annotations

import logging
import time
from urllib.parse import quote

import pandas as pd
import requests

BASE = "https://api.openf1.org/v1"
HEADERS = {"User-Agent": "f1-telemetry-hub/0.2 (+https://github.com/michelalephb/f1-telemetry-hub)"}
MIN_INTERVAL_S = 2.1

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
            r = self.http.get(url, timeout=120)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:  # OpenF1 answers 404 when nothing matches
                return []
            if r.status_code in (429, 500, 502, 503, 504):
                back = 10 * (attempt + 1)
                log.warning("OpenF1 %s on %s, retrying in %ss", r.status_code, path, back)
                time.sleep(back)
                continue
            r.raise_for_status()
        raise RuntimeError(f"OpenF1 gave up on {url}")

    def frame(self, path: str, filters: list[str] | None = None, **params) -> pd.DataFrame:
        return pd.DataFrame(self.get(path, filters, **params))
