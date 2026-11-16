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


# ---------------------------------------------------------------- Upload-Post (no Facebook account needed)

UP_HOST = "https://api.upload-post.com/api"


class UploadPost:
    """Publishes through Upload-Post, which runs its own approved Meta app: the Instagram account is
    connected once on upload-post.com with Instagram login. Files are sent directly (no public URLs,
    so nothing is stored in our bucket). Uploads run async with our own request_id; the id is saved
    before the call so a run that dies mid upload checks that id next time instead of posting twice.
    """

    sends_files = True

    def __init__(self, api_key: str, user: str, session: requests.Session | None = None):
        self.key = api_key
        self.user = user
        self.http = session or requests.Session()

    def _headers(self, request_id: str | None = None) -> dict:
        h = {"Authorization": f"Apikey {self.key}"}
        if request_id:
            h["Idempotency-Key"] = request_id
        return h

    def _post(self, path: str, data: list, files: list, request_id: str) -> dict:
        r = self.http.post(f"{UP_HOST}/{path}", headers=self._headers(request_id), data=data, files=files, timeout=300)
        try:
            body = r.json()
        except ValueError:
            body = {"message": r.text[:300]}
        if r.status_code >= 400 or body.get("success") is False:
            raise IGError(f"upload-post {path}: HTTP {r.status_code}: {body.get('message') or body.get('error')}")
        return body

    def status(self, request_id: str) -> tuple[str, dict | None]:
        """('pending' | 'in_progress' | 'completed', the Instagram result once there is one)."""
        r = self.http.get(f"{UP_HOST}/uploadposts/status", headers=self._headers(), params={"request_id": request_id}, timeout=60)
        if r.status_code >= 400:
            raise IGError(f"upload-post status: HTTP {r.status_code}: {r.text[:200]}")
        body = r.json()
        ig = next((x for x in body.get("results") or [] if x.get("platform") == "instagram"), None)
        return body.get("status", "pending"), ig

    def wait(self, request_id: str, max_s: float | None = None) -> dict:
        t0 = time.monotonic()
        while True:
            st, ig = self.status(request_id)
            if ig is not None and ig.get("success") is False:
                raise IGError(f"instagram rejected the post: {ig.get('error') or ig.get('message')}")
            if st == "completed" and ig is not None:
                return ig
            if time.monotonic() - t0 > (POLL_MAX_S if max_s is None else max_s):
                raise TimeoutError(f"upload-post {request_id}: still {st} after {POLL_MAX_S} s")
            time.sleep(POLL_S)

    def _common(self, caption: str, request_id: str) -> list:
        return [("user", self.user), ("platform[]", "instagram"), ("title", caption), ("instagram_title", caption),
                ("async_upload", "true"), ("request_id", request_id)]

    def send_reel(self, video: str, cover: str | None, caption: str, request_id: str) -> None:
        data = self._common(caption, request_id) + [("media_type", "REELS"), ("share_to_feed", "true")]
        with open(video, "rb") as v:
            files = [("video", ("reel.mp4", v, "video/mp4"))]
            if cover:
                c = open(cover, "rb")
                files.append(("cover_image", ("cover.jpg", c, "image/jpeg")))
            try:
                self._post("upload", data, files, request_id)
            finally:
                if cover:
                    c.close()

    def send_story(self, image: str, request_id: str) -> None:
        """One image as one Instagram story (Upload-Post media_type=STORIES)."""
        data = [("user", self.user), ("platform[]", "instagram"), ("title", "story"), ("media_type", "STORIES"),
                ("async_upload", "true"), ("request_id", request_id)]
        with open(image, "rb") as h:
            self._post("upload_photos", data, [("photos[]", ("story.jpg", h, "image/jpeg"))], request_id)

    def send_carousel(self, images: list[str], caption: str, request_id: str) -> None:
        if not 2 <= len(images) <= 10:
            raise IGError(f"a carousel needs 2 to 10 items, got {len(images)}")
        handles = [open(p, "rb") for p in images]
        try:
            files = [("photos[]", (f"slide_{i + 1}.jpg", h, "image/jpeg")) for i, h in enumerate(handles)]
            self._post("upload_photos", self._common(caption, request_id), files, request_id)
        finally:
            for h in handles:
                h.close()
