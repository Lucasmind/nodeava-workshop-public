"""Tests for the /v1/ingest route.

We can't run the real compiler in unit tests (it needs an API key and
takes minutes). So we patch the runner's `ingest_file` to a fast fake
and verify the route's wrap behavior — file save, response shape, error
mapping — works correctly.
"""
import io
import pytest

from orchestrator.ingest.runner import IngestResult


async def test_ingest_writes_file_and_runs_compiler(app_client, monkeypatch, tmp_path):
    """Happy path: file gets saved to raw/uploads/, runner is invoked,
    response contains pages_changed."""
    # Point RAW_DIR at a tmp_path for this test
    from orchestrator.ingest import runner as runner_module
    from orchestrator.routes import ingest as ingest_route
    monkeypatch.setattr(runner_module, "RAW_DIR", tmp_path)
    monkeypatch.setattr(ingest_route, "RAW_DIR", tmp_path)

    captured: dict = {}

    async def fake_ingest(source_path):
        captured["source_path"] = source_path
        return IngestResult(
            ok=True,
            pages_changed=["concepts/new-page.md"],
            stdout="compiled 1 page",
            stderr="",
            error=None,
        )

    # The route imports `ingest_file` at module load time — patch it there.
    monkeypatch.setattr(ingest_route, "ingest_file", fake_ingest)

    files = {"file": ("notes.md", io.BytesIO(b"# Some notes\nHello world."), "text/markdown")}
    resp = await app_client.post("/v1/ingest", files=files)

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "concepts/new-page.md" in body["pages_changed"]
    assert body["stdout_tail"] == "compiled 1 page"

    # File was written to raw/uploads/
    target = tmp_path / "uploads" / "notes.md"
    assert target.is_file()
    assert target.read_bytes() == b"# Some notes\nHello world."

    # Runner was called with the right path
    assert captured["source_path"] == target


async def test_ingest_sanitizes_unsafe_filename(app_client, monkeypatch, tmp_path):
    """Filenames like '../../etc/passwd' get sanitized — written to a
    safe-renamed file under raw/uploads/ (not the original path)."""
    from orchestrator.ingest import runner as runner_module
    from orchestrator.routes import ingest as ingest_route
    monkeypatch.setattr(runner_module, "RAW_DIR", tmp_path)
    monkeypatch.setattr(ingest_route, "RAW_DIR", tmp_path)

    async def fake_ingest(source_path):
        return IngestResult(ok=True, pages_changed=[], stdout="", stderr="", error=None)

    monkeypatch.setattr(ingest_route, "ingest_file", fake_ingest)

    files = {
        "file": ("../../etc/passwd", io.BytesIO(b"sensitive"), "text/plain"),
    }
    resp = await app_client.post("/v1/ingest", files=files)
    assert resp.status_code == 200

    # The target file should be under raw/uploads/ with a sanitized name
    saved = list((tmp_path / "uploads").iterdir())
    assert len(saved) == 1
    saved_path = saved[0]
    # Sanitized name should NOT be ../../etc/passwd
    assert "passwd" in saved_path.name or "etc" in saved_path.name
    assert ".." not in saved_path.name
    assert "/" not in saved_path.name
    # And the file is under raw/uploads (no path escape)
    assert saved_path.is_relative_to(tmp_path / "uploads")


async def test_ingest_compiler_failure_returns_500(app_client, monkeypatch, tmp_path):
    """If the runner reports ok=False, the route returns 500 with error details."""
    from orchestrator.ingest import runner as runner_module
    from orchestrator.routes import ingest as ingest_route
    monkeypatch.setattr(runner_module, "RAW_DIR", tmp_path)
    monkeypatch.setattr(ingest_route, "RAW_DIR", tmp_path)

    async def fake_ingest(source_path):
        return IngestResult(
            ok=False,
            pages_changed=[],
            stdout="",
            stderr="ANTHROPIC_API_KEY env var not set",
            error="compiler exited with code 2",
        )

    monkeypatch.setattr(ingest_route, "ingest_file", fake_ingest)

    files = {"file": ("notes.md", io.BytesIO(b"x"), "text/plain")}
    resp = await app_client.post("/v1/ingest", files=files)
    assert resp.status_code == 500
    body = resp.json()
    assert body["ok"] is False
    assert "compiler exited" in body["error"]
    assert "ANTHROPIC_API_KEY" in body["stderr_tail"]


async def test_ingest_rejects_oversized_upload(app_client, monkeypatch, tmp_path):
    """Uploads larger than the 5 MB size cap are rejected with 413."""
    from orchestrator.ingest import runner as runner_module
    from orchestrator.routes import ingest as ingest_route
    monkeypatch.setattr(runner_module, "RAW_DIR", tmp_path)
    monkeypatch.setattr(ingest_route, "RAW_DIR", tmp_path)

    big_payload = b"x" * (5 * 1024 * 1024 + 1)  # 5 MB + 1 byte
    files = {"file": ("big.bin", io.BytesIO(big_payload), "application/octet-stream")}
    resp = await app_client.post("/v1/ingest", files=files)
    assert resp.status_code == 413
    body = resp.json()
    assert "exceeds" in body["error"].lower() or "limit" in body["error"].lower()
