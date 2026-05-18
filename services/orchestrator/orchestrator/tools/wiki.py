"""Wiki tools — read-only operations on a Karpathy-style markdown wiki.

The wiki lives in a directory on disk (Settings.wiki_dir, default
repo-root `wiki/`). It has the layout:

  wiki/
    index.md            — catalog (one-line summary per page)
    log.md              — activity timeline
    concepts/
    entities/
    sources/
    comparisons/

The agent reads index.md first (via wiki.list), then opens specific
pages (via wiki.open) or greps across them (via wiki.search). No
vector embeddings, no chunking — the index is the retrieval mechanism.
"""
import logging
import re
from pathlib import Path
from typing import Any

from orchestrator.tools.base import Tool, ToolError

log = logging.getLogger("orchestrator.tools.wiki")


class WikiList(Tool):
    """Return the top-level wiki index (one-line summary of every page)."""

    name = "wiki.list"
    schema = {"type": "object", "properties": {}}

    def __init__(self, *, wiki_dir: str) -> None:
        self._wiki_root = Path(wiki_dir)

    async def execute(self, args: dict[str, Any]) -> str:
        index = self._wiki_root / "index.md"
        if not index.is_file():
            raise ToolError(
                f"wiki index.md not found at {index}. "
                "Has the wiki been initialized?"
            )
        return index.read_text(encoding="utf-8")


class WikiSearch(Tool):
    """Grep across all .md files in the wiki for a query string."""

    name = "wiki.search"
    schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Substring or regex to find (case-insensitive)",
            },
            "max_matches": {
                "type": "integer",
                "description": "Cap total matching lines returned",
                "default": 30,
            },
        },
        "required": ["query"],
    }

    def __init__(self, *, wiki_dir: str) -> None:
        self._wiki_root = Path(wiki_dir)

    async def execute(self, args: dict[str, Any]) -> str:
        query = args.get("query") or ""
        if not query:
            raise ToolError("wiki.search requires a non-empty 'query'")

        try:
            max_matches = int(args.get("max_matches", 30))
        except (TypeError, ValueError):
            max_matches = 30
        max_matches = max(1, min(max_matches, 100))

        # Workshop search strategy: split the query into words and find lines
        # containing ANY of them. This is forgiving for two common cases:
        #   1. Whisper transcribes "NodeAva" as "Node Ava" — searching for
        #      "Node Ava ports" splits to ["Node", "Ava", "ports"] and matches
        #      lines containing "NodeAva" (via the whitespace-flex variant)
        #      or "port".
        #   2. The model passes a full question phrase like "what ports does
        #      NodeAva use" — single-word matches surface the relevant lines.
        #
        # For each query word: also try whitespace-flexible variants if the
        # word contains internal capitalization that Whisper might have
        # split (e.g. "NodeAva" appears in the wiki even if STT split it).
        words = [w for w in query.split() if w]
        if not words:
            return f"No matches for: {query}"

        # Build patterns: each word as a standalone alternation, plus the
        # full query with whitespace-flex (to favor exact phrase matches).
        patterns: list[str] = []
        if len(words) > 1:
            patterns.append(r"\s*".join(re.escape(w) for w in words))
        for w in words:
            if len(w) >= 3:  # skip 1-2 char filler words like "of", "in"
                patterns.append(re.escape(w))
        if not patterns:
            patterns = [re.escape(query)]

        combined = "|".join(patterns)
        try:
            compiled = re.compile(combined, re.IGNORECASE)

            def predicate(line: str) -> bool:
                return bool(compiled.search(line))
        except re.error:
            needle = query.lower()

            def predicate(line: str) -> bool:
                return needle in line.lower()

        # Return matching lines PLUS surrounding context (4 lines before + 8
        # after) so a single wiki.search call gives the agent enough to answer
        # without a chained wiki.open. Adjacent matches are merged into one
        # contiguous block. The workshop's smaller models don't reliably chain
        # tool calls — fatter snippets keep them on track in one round.
        CONTEXT_BEFORE = 4
        CONTEXT_AFTER = 8

        snippets: list[str] = []
        total_lines = 0
        for path in sorted(self._wiki_root.rglob("*.md")):
            rel = path.relative_to(self._wiki_root)
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            # First pass: collect indices of all matching lines
            hit_idxs = [i for i, line in enumerate(lines) if predicate(line)]
            if not hit_idxs:
                continue
            # Merge overlapping context windows into contiguous ranges
            ranges: list[tuple[int, int]] = []
            for h in hit_idxs:
                start = max(0, h - CONTEXT_BEFORE)
                end = min(len(lines), h + CONTEXT_AFTER + 1)
                if ranges and start <= ranges[-1][1]:
                    ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
                else:
                    ranges.append((start, end))
            for (start, end) in ranges:
                chunk = "\n".join(
                    f"{rel}:{i + 1}: {lines[i]}" for i in range(start, end)
                )
                snippets.append(chunk)
                total_lines += end - start
                if total_lines >= max_matches * 12:  # cap total payload
                    break
            if total_lines >= max_matches * 12:
                break

        if not snippets:
            return f"No matches for: {query}"
        return "\n\n---\n\n".join(snippets)


class WikiOpen(Tool):
    """Read a single wiki page, paginated. Path is wiki-relative."""

    name = "wiki.open"
    schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Wiki-relative path, e.g. 'concepts/tts.md'. "
                    "Must not escape the wiki root."
                ),
            },
            "num_lines": {
                "type": "integer",
                "description": "Number of lines to return",
                "default": 200,
            },
            "cursor": {
                "type": "integer",
                "description": "Line offset to start from",
                "default": 0,
            },
        },
        "required": ["path"],
    }

    def __init__(self, *, wiki_dir: str) -> None:
        self._wiki_root = Path(wiki_dir).resolve()

    async def execute(self, args: dict[str, Any]) -> str:
        path = args.get("path") or ""
        if not path:
            raise ToolError("wiki.open requires a 'path' argument")

        # Guard against path traversal — the resolved path must remain
        # under wiki_root after normalization.
        candidate = (self._wiki_root / path).resolve()
        try:
            candidate.relative_to(self._wiki_root)
        except ValueError:
            raise ToolError(
                f"refusing to open {path}: target resolves outside the wiki root"
            )

        if not candidate.is_file():
            raise ToolError(f"wiki page not found: {path}")

        try:
            num_lines = int(args.get("num_lines", 200))
        except (TypeError, ValueError):
            num_lines = 200
        num_lines = max(1, min(num_lines, 2000))

        try:
            cursor = int(args.get("cursor", 0))
        except (TypeError, ValueError):
            cursor = 0
        cursor = max(0, cursor)

        try:
            text = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise ToolError(f"cannot read {path}: {e}") from e

        lines = text.splitlines()
        total = len(lines)
        end = min(cursor + num_lines, total)
        selected = lines[cursor:end]
        rel = candidate.relative_to(self._wiki_root)
        header = (
            f"Path: {rel}\n"
            f"Lines {cursor + 1}-{end} of {total}\n"
            f"---\n"
        )
        return header + "\n".join(selected)
