"""Tests for /send_results gzip upload path and plain-text size limits."""

import gzip
import io

import pytest
from fastapi.testclient import TestClient

import web.app as app_module
from web.app import app

client = TestClient(app, raise_server_exceptions=False)

_MINIMAL_PDB = (
    "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00  0.00           C\n"
    "END\n"
)


@pytest.fixture(autouse=True)
def mock_resend(monkeypatch):
    monkeypatch.setattr(app_module, "_resend_send", lambda payload: (True, "ok"))


# ── _safe_gzip_decompress unit tests ──────────────────────────────────────────


def test_safe_gzip_decompress_happy_path():
    data = b"hello bilbo\n" * 100
    compressed = gzip.compress(data)
    result = app_module._safe_gzip_decompress(compressed)
    assert result == data


def test_safe_gzip_decompress_bomb(monkeypatch):
    monkeypatch.setattr(app_module, "_MAX_GZ_DECOMPRESS_BYTES", 100)
    data = b"\x00" * 1024
    compressed = gzip.compress(data)
    with pytest.raises(ValueError, match="exceeds limit"):
        app_module._safe_gzip_decompress(compressed)


# ── /send_results endpoint tests ──────────────────────────────────────────────


def _gz(text: str) -> bytes:
    return gzip.compress(text.encode("utf-8"))


def test_send_results_plain_text():
    resp = client.post(
        "/send_results",
        data={"to_email": "test@example.com", "lang": "en", "pdb": _MINIMAL_PDB},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_send_results_pdb_gz_valid():
    resp = client.post(
        "/send_results",
        data={"to_email": "test@example.com", "lang": "en"},
        files={"pdb_gz": ("pdb.gz", io.BytesIO(_gz(_MINIMAL_PDB)), "application/octet-stream")},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_send_results_pdb_gz_corrupt():
    resp = client.post(
        "/send_results",
        data={"to_email": "test@example.com", "lang": "en"},
        files={"pdb_gz": ("pdb.gz", io.BytesIO(b"not gzip data"), "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert "decompress" in resp.json()["error"].lower()


def test_send_results_pdb_gz_oversized_compressed(monkeypatch):
    monkeypatch.setattr(app_module, "_MAX_GZ_UPLOAD_BYTES", 10)
    resp = client.post(
        "/send_results",
        data={"to_email": "test@example.com", "lang": "en"},
        files={"pdb_gz": ("pdb.gz", io.BytesIO(_gz(_MINIMAL_PDB)), "application/octet-stream")},
    )
    assert resp.status_code == 413


def test_send_results_pdb_gz_bomb(monkeypatch):
    monkeypatch.setattr(app_module, "_MAX_GZ_DECOMPRESS_BYTES", 10)
    resp = client.post(
        "/send_results",
        data={"to_email": "test@example.com", "lang": "en"},
        files={"pdb_gz": ("pdb.gz", io.BytesIO(_gz(_MINIMAL_PDB)), "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_send_results_gro_gz_corrupt_returns_400():
    resp = client.post(
        "/send_results",
        data={"to_email": "test@example.com", "lang": "en", "pdb": _MINIMAL_PDB},
        files={"gro_gz": ("gro.gz", io.BytesIO(b"bad"), "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_send_results_topology_gz_corrupt_returns_400():
    resp = client.post(
        "/send_results",
        data={"to_email": "test@example.com", "lang": "en", "pdb": _MINIMAL_PDB},
        files={"topology_gz": ("topology.gz", io.BytesIO(b"bad"), "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_send_results_plain_text_oversized(monkeypatch):
    monkeypatch.setattr(app_module, "_MAX_FORM_TEXT_BYTES", 10)
    resp = client.post(
        "/send_results",
        data={"to_email": "test@example.com", "lang": "en", "pdb": _MINIMAL_PDB},
    )
    assert resp.status_code == 413
