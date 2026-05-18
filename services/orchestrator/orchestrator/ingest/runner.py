"""Shell out to the wiki-compiler with a newly-uploaded source file.

Runs synchronously. Returns the captured stdout/stderr + a list of pages
that changed on disk, by snapshotting wiki/ mtimes before/after.

Uses asyncio.create_subprocess_exec (NOT shell) — the compiler path and
source path are passed as separate argv elements. User-controlled filenames
cannot inject shell commands.
"""
import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("orchestrator.ingest.runner")


# Paths inside the container. For the Dockerized orchestrator, /app/wiki
# is the bind-mount target from Plan #3. The wiki-compiler lives in a
# sibling directory at /app/wiki-compiler (Plan #6 Dockerfile update).
WIKI_DIR = Path(os.environ.get("WIKI_DIR", "/app/wiki"))
RAW_DIR = Path(os.environ.get("RAW_DIR", "/app/raw"))
COMPILER_PATH = Path(
    os.environ.get("WIKI_COMPILER_PATH", "/app/wiki-compiler/compile_wiki.py")
)


@dataclass
class IngestResult:
    ok: bool
    pages_changed: list[str]
    stdout: str
    stderr: str
    error: str | None = None


async def ingest_file(source_path: Path) -> IngestResult:
    """Run the compiler against a single source file.

    `source_path` must already exist (the route writes it before calling).
    Returns IngestResult with pages_changed populated from a mtime diff.
    """
    if not COMPILER_PATH.is_file():
        return IngestResult(
            ok=False,
            pages_changed=[],
            stdout="",
            stderr="",
            error=f"compiler not found at {COMPILER_PATH}",
        )
    if not source_path.is_file():
        return IngestResult(
            ok=False,
            pages_changed=[],
            stdout="",
            stderr="",
            error=f"source file not found: {source_path}",
        )

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return IngestResult(
            ok=False,
            pages_changed=[],
            stdout="",
            stderr="",
            error="ANTHROPIC_API_KEY env var not set in the orchestrator container",
        )

    pre_snapshot = _snapshot_mtimes(WIKI_DIR)
    log.info("Ingest: running compiler against %s", source_path)

    # asyncio.create_subprocess_exec — argv-style invocation, no shell.
    # User-supplied paths are passed as separate list elements; they cannot
    # be interpreted as shell metacharacters.
    proc = await asyncio.create_subprocess_exec(
        "python",
        str(COMPILER_PATH),
        "--ingest",
        str(source_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(COMPILER_PATH.parent),
    )
    stdout_b, stderr_b = await proc.communicate()
    stdout = stdout_b.decode(errors="replace")
    stderr = stderr_b.decode(errors="replace")

    post_snapshot = _snapshot_mtimes(WIKI_DIR)
    changed = [
        p for p, mtime in post_snapshot.items()
        if pre_snapshot.get(p) != mtime
    ]
    log.info("Ingest done (rc=%d, %d pages changed)", proc.returncode, len(changed))

    if proc.returncode != 0:
        return IngestResult(
            ok=False,
            pages_changed=changed,
            stdout=stdout,
            stderr=stderr,
            error=f"compiler exited with code {proc.returncode}",
        )
    return IngestResult(
        ok=True,
        pages_changed=changed,
        stdout=stdout,
        stderr=stderr,
        error=None,
    )


def _snapshot_mtimes(root: Path) -> dict[str, float]:
    """Map of relative path -> mtime for all *.md files under root."""
    if not root.is_dir():
        return {}
    out: dict[str, float] = {}
    for md in root.rglob("*.md"):
        try:
            out[str(md.relative_to(root))] = md.stat().st_mtime
        except OSError:
            continue
    return out
