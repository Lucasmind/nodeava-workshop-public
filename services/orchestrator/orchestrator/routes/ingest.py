"""POST /v1/ingest — workshop attendees drop a file, agent compiles it into the wiki.

Plan #6 ships synchronous compilation — the request blocks until the
compiler finishes or aborts. Plan #10 may add async polling if needed.

Request: multipart/form-data with a single `file` part.
Response (200): {ok: true, pages_changed: [...], summary: "..."}
Response (4xx): {error: "..."}
Response (5xx): {error: "..."}
"""
import logging
import re

from fastapi import APIRouter, UploadFile
from fastapi.responses import JSONResponse

from orchestrator.ingest.runner import RAW_DIR, IngestResult, ingest_file

log = logging.getLogger("orchestrator.routes.ingest")

router = APIRouter()


_SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


@router.post("/v1/ingest")
async def ingest(file: UploadFile) -> JSONResponse:
    if not file.filename:
        return JSONResponse({"error": "missing filename"}, status_code=400)

    safe_name = _SAFE_FILENAME_RE.sub("_", file.filename).strip("._")
    if not safe_name:
        return JSONResponse({"error": "filename produced empty safe form"}, status_code=400)

    target_dir = RAW_DIR / "uploads"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe_name

    # Save the upload to disk
    MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
    try:
        contents = await file.read()
        if len(contents) > MAX_UPLOAD_BYTES:
            return JSONResponse(
                {"error": f"upload exceeds {MAX_UPLOAD_BYTES} bytes limit"},
                status_code=413,
            )
        target.write_bytes(contents)
        size = len(contents)
    except Exception as e:
        log.warning("failed to write upload: %s", e)
        return JSONResponse({"error": f"failed to save upload: {e}"}, status_code=500)

    log.info("Ingest received %s (%d bytes) → %s", file.filename, size, target)

    result: IngestResult = await ingest_file(target)

    payload = {
        "ok": result.ok,
        "pages_changed": result.pages_changed,
        "source_path": str(target),
        "stdout_tail": result.stdout[-1000:] if result.stdout else "",
    }
    if not result.ok:
        payload["error"] = result.error or "compile failed"
        payload["stderr_tail"] = result.stderr[-1000:] if result.stderr else ""
        return JSONResponse(payload, status_code=500)

    return JSONResponse(payload, status_code=200)
