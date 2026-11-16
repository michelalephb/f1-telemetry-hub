"""Instagram API with Instagram Login (graph.instagram.com): containers, status polling, publish.

Flow per Meta's Content Publishing guide: POST /<IG_ID>/media (one container per image, then a
CAROUSEL container, or one REELS container), poll /<container>?fields=status_code until FINISHED,
then POST /<IG_ID>/media_publish. Media must be at public URLs, so files go to the public "web"
bucket first. The access token is never logged.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)
HOST = "https://graph.instagram.com"
VERSION = os.environ.get("IG_API_VERSION", "v26.0")   # version shown in Meta's examples, Nov 2026
POLL_S = 10
POLL_MAX_S = 600
NOT_READY = 2207027   # "media is not ready for publishing": wait and retry


class IGError(Exception):
    pass


class Instagram:
    def __init__(self, token: str, user_id: str | None = None, session: requests.Session | None = None):
        self.token = token
        self.http = session or requests.Session()
        self.user_id = user_id or self.call("GET", "me", fields="user_id")["user_id"]

    def call(self, method: str, path: str, **params) -> dict:
        url = f"{HOST}/{VERSION}/{path}"
        params["access_token"] = self.token
        r = self.http.request(method, url, params=params if method == "GET" else None,
                              data=None if method == "GET" else params, timeout=60)
        try:
            body = r.json()
        except ValueError:
            body = {"error": {"message": r.text[:300]}}
        if r.status_code >= 400 or "error" in body:
            e = body.get("error", {})
            err = IGError(f"{method} {path}: HTTP {r.status_code} code {e.get('code')} subcode {e.get('error_subcode')}: {e.get('message')}")
            err.subcode = e.get("error_subcode")
            raise err
        return body

    def quota_left(self) -> int | None:
        try:
            d = self.call("GET", f"{self.user_id}/content_publishing_limit", fields="quota_usage,config")["data"][0]
            return int(d["config"]["quota_total"]) - int(d["quota_usage"])
        except Exception as e:
            log.warning("publishing limit unknown: %s", e)
            return None

    def wait(self, container: str) -> None:
        t0 = time.monotonic()
        while True:
            st = self.call("GET", container, fields="status_code,status")
            code = st.get("status_code")
            if code in ("FINISHED", "PUBLISHED"):
                return
            if code in ("ERROR", "EXPIRED"):
                raise IGError(f"container {container}: {code} {st.get('status')}")
            if time.monotonic() - t0 > POLL_MAX_S:
                raise IGError(f"container {container}: still {code} after {POLL_MAX_S} s")
            time.sleep(POLL_S)

    def publish(self, container: str) -> str:
        for attempt in range(6):
            try:
                return self.call("POST", f"{self.user_id}/media_publish", creation_id=container)["id"]
            except IGError as e:
                if getattr(e, "subcode", None) != NOT_READY or attempt == 5:
                    raise
                time.sleep(POLL_S * (attempt + 1))

    def permalink(self, media_id: str) -> str | None:
        try:
            return self.call("GET", media_id, fields="permalink").get("permalink")
        except IGError:
            return None

    def post_carousel(self, image_urls: list[str], caption: str) -> tuple[str, str]:
        if not 2 <= len(image_urls) <= 10:
            raise IGError(f"a carousel needs 2 to 10 items, got {len(image_urls)}")
        kids = [self.call("POST", f"{self.user_id}/media", image_url=u, is_carousel_item="true")["id"] for u in image_urls]
        for k in kids:
            self.wait(k)
        parent = self.call("POST", f"{self.user_id}/media", media_type="CAROUSEL", children=",".join(kids), caption=caption)["id"]
        self.wait(parent)
        return parent, self.publish(parent)

    def post_reel(self, video_url: str, cover_url: str | None, caption: str) -> tuple[str, str]:
        p = {"media_type": "REELS", "video_url": video_url, "caption": caption, "share_to_feed": "true"}
        if cover_url:
            p["cover_url"] = cover_url
        c = self.call("POST", f"{self.user_id}/media", **p)["id"]
        self.wait(c)
        return c, self.publish(c)


def refresh_token(token: str, session: requests.Session | None = None) -> tuple[str, int]:
    """New long lived token and its lifetime in seconds (GET /refresh_access_token, grant ig_refresh_token)."""
    http = session or requests.Session()
    r = http.get(f"{HOST}/refresh_access_token", params={"grant_type": "ig_refresh_token", "access_token": token}, timeout=60)
    body = r.json()
    if r.status_code >= 400 or "access_token" not in body:
        e = body.get("error", {})
        raise IGError(f"token refresh failed: HTTP {r.status_code} {e.get('message')}")
    return body["access_token"], int(body.get("expires_in", 0))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
