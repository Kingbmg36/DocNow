"""Object storage for DocNow.NG — pluggable local/S3 backend.

STORAGE_BACKEND=local (default) → files under STORAGE_LOCAL_DIR. Zero external deps,
  good for dev. Downloads are streamed by the API (auth enforced at the route).
STORAGE_BACKEND=s3 → boto3 to an S3 (or S3-compatible) bucket. boto3 is imported
  lazily so local mode needs nothing installed.

Access is always mediated by the API (bytes streamed through an authorised route),
never a public/presigned URL — license documents are sensitive PII.
"""
import os
import asyncio
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local").lower()
STORAGE_LOCAL_DIR = os.environ.get("STORAGE_LOCAL_DIR", str(Path(__file__).parent / "uploads"))
S3_BUCKET = os.environ.get("STORAGE_S3_BUCKET", "")
S3_REGION = os.environ.get("STORAGE_S3_REGION", "us-east-1")
S3_ENDPOINT = os.environ.get("STORAGE_S3_ENDPOINT") or None


def is_s3() -> bool:
    return STORAGE_BACKEND == "s3" and bool(S3_BUCKET)


def backend_name() -> str:
    return "s3" if is_s3() else "local"


def _safe_key(key: str) -> str:
    """Reject path traversal. Keys are server-generated, but defend in depth."""
    if not key or key.startswith("/") or ".." in Path(key).parts:
        raise ValueError(f"Unsafe storage key: {key!r}")
    return key


# ---------- S3 client (lazy singleton) ----------
_s3 = None


def _client():
    global _s3
    if _s3 is None:
        import boto3  # lazy — only needed in s3 mode
        _s3 = boto3.client("s3", region_name=S3_REGION, endpoint_url=S3_ENDPOINT)
    return _s3


def _local_path(key: str) -> Path:
    return Path(STORAGE_LOCAL_DIR) / _safe_key(key)


# ---------- Operations ----------
async def put(key: str, data: bytes, content_type: str = "application/octet-stream") -> dict:
    _safe_key(key)
    if is_s3():
        def _do():
            _client().put_object(Bucket=S3_BUCKET, Key=key, Body=data, ContentType=content_type)
        await asyncio.to_thread(_do)
    else:
        def _do():
            p = _local_path(key)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        await asyncio.to_thread(_do)
    log.info("stored %s (%d bytes) → %s", key, len(data), backend_name())
    return {"key": key, "size": len(data), "backend": backend_name()}


async def get_bytes(key: str) -> Optional[bytes]:
    """Return the object's bytes, or None if it does not exist."""
    _safe_key(key)
    if is_s3():
        def _do():
            try:
                obj = _client().get_object(Bucket=S3_BUCKET, Key=key)
                return obj["Body"].read()
            except Exception as e:  # NoSuchKey etc.
                log.warning("s3 get_bytes miss for %s: %s", key, e)
                return None
        return await asyncio.to_thread(_do)
    p = _local_path(key)
    if not p.exists():
        return None
    return await asyncio.to_thread(p.read_bytes)


async def exists(key: str) -> bool:
    _safe_key(key)
    if is_s3():
        def _do():
            try:
                _client().head_object(Bucket=S3_BUCKET, Key=key)
                return True
            except Exception:
                return False
        return await asyncio.to_thread(_do)
    return _local_path(key).exists()
