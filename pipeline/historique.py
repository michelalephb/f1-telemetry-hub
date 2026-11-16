"""GP Historique: all time statistics from F1DB, published as static JSON for the site.

Each public.historique_<name>() function (migration 20261116000002) returns one document; this writes
historique/<name>.json to the public web bucket with the F1DB release it came from.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)
NAMES = ["grid", "teammates", "lineage", "families", "eras", "grand_slams", "climbs", "circuits"]


def build(sb, bucket: str) -> dict[str, int]:
    source = sb.rpc("historique_source", {}).execute().data or {}
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": f"F1DB {source.get('version', '?')} (CC BY 4.0, https://github.com/f1db/f1db)",
        "f1db_released_at": source.get("released_at"),
    }
    sizes = {}
    for name in NAMES:
        data = sb.rpc(f"historique_{name}", {}).execute().data
        if data is None or (isinstance(data, list) and not data):
            raise RuntimeError(f"historique_{name} returned nothing")
        body = json.dumps({**meta, "data": data}, separators=(",", ":"), ensure_ascii=False).encode()
        sb.storage.from_(bucket).upload(f"historique/{name}.json", body,
                                        {"content-type": "application/json", "cache-control": "3600", "upsert": "true"})
        sizes[name] = len(body)
        log.info("historique/%s.json: %d bytes", name, len(body))
    return sizes
