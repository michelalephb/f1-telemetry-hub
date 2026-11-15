"""Supabase access: table upserts and Parquet uploads. Uses the service role key (server side only)."""
from __future__ import annotations

import io
import math
import os

import pandas as pd

BUCKET = "telemetry"
CHUNK = 500


def client():
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if v is pd.NaT:
        return None
    if hasattr(v, "item"):  # numpy scalar
        v = v.item()
        if isinstance(v, float) and math.isnan(v):
            return None
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    return v


def records(df: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in row.items()} for row in df.to_dict(orient="records")]


def upsert(sb, table: str, rows: list[dict], on_conflict: str) -> None:
    for i in range(0, len(rows), CHUNK):
        sb.table(table).upsert(rows[i : i + CHUNK], on_conflict=on_conflict).execute()


def delete_session_rows(sb, session_id: str) -> None:
    """Clear derived rows before a re ingest so stale laps or corners do not linger."""
    for table in ("corner_metrics", "corners", "laps", "drivers"):
        sb.table(table).delete().eq("session_id", session_id).execute()


WEB_BUCKET = "web"  # public: per driver traces the website reads directly


def upload_parquet(sb, path: str, df: pd.DataFrame, bucket: str = BUCKET) -> str:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, compression="zstd")
    sb.storage.from_(bucket).upload(
        path, buf.getvalue(), {"content-type": "application/vnd.apache.parquet", "upsert": "true"}
    )
    return path
