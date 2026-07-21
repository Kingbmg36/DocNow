"""Tests for object storage (local backend) — doctor license documents.

Local backend uses only stdlib (no boto3, no Mongo, no network), so these run
anywhere. S3 paths are exercised on the platform where credentials exist.
Run with:
    cd /app/backend && python -m pytest tests/test_storage.py -v
"""
import os
import uuid
import tempfile
import importlib

import pytest

os.environ["STORAGE_BACKEND"] = "local"
os.environ["STORAGE_LOCAL_DIR"] = tempfile.mkdtemp(prefix="docnow_storage_test_")


@pytest.fixture
def st():
    import storage_service
    importlib.reload(storage_service)
    return storage_service


def test_backend_is_local(st):
    assert st.backend_name() == "local"
    assert st.is_s3() is False


@pytest.mark.asyncio
async def test_put_get_roundtrip(st):
    key = f"licenses/doc1/{uuid.uuid4().hex}.pdf"
    blob = b"%PDF-1.4 fake license bytes"
    res = await st.put(key, blob, "application/pdf")
    assert res["size"] == len(blob)
    assert res["backend"] == "local"
    assert await st.exists(key) is True
    assert await st.get_bytes(key) == blob


@pytest.mark.asyncio
async def test_missing_key_returns_none(st):
    assert await st.get_bytes("licenses/none/missing.pdf") is None
    assert await st.exists("licenses/none/missing.pdf") is False


@pytest.mark.parametrize("bad", ["../etc/passwd", "/abs/path", "a/../../b", ""])
def test_safe_key_rejects_traversal(st, bad):
    with pytest.raises(ValueError):
        st._safe_key(bad)


def test_safe_key_allows_normal(st):
    assert st._safe_key("licenses/doc1/abc.pdf") == "licenses/doc1/abc.pdf"
