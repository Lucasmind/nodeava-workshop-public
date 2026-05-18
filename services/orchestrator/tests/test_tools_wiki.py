"""Tests for wiki tools."""
from pathlib import Path

import pytest

from orchestrator.tools.base import ToolError
from orchestrator.tools.wiki import WikiList, WikiSearch, WikiOpen


@pytest.fixture
def wiki_dir(tmp_path: Path) -> Path:
    """A throwaway wiki directory laid out the same as the real one."""
    (tmp_path / "index.md").write_text("# Wiki Index\n\nFake index content.\n")
    (tmp_path / "log.md").write_text("# Log\n")
    for sub in ("concepts", "entities", "sources", "comparisons"):
        (tmp_path / sub).mkdir()
    return tmp_path


async def test_list_returns_index_verbatim(wiki_dir):
    tool = WikiList(wiki_dir=str(wiki_dir))
    out = await tool.execute({})
    assert out.startswith("# Wiki Index")
    assert "Fake index content." in out


async def test_list_missing_index_raises(tmp_path: Path):
    tool = WikiList(wiki_dir=str(tmp_path))
    with pytest.raises(ToolError) as exc:
        await tool.execute({})
    assert "index.md" in str(exc.value)


@pytest.fixture
def populated_wiki(wiki_dir: Path) -> Path:
    """A wiki with a few real-looking pages we can grep against."""
    (wiki_dir / "concepts" / "tts.md").write_text(
        "# Text To Speech\n\nKokoro is a fast TTS engine used by NodeAva.\nIt emits PCM with word timestamps.\n"
    )
    (wiki_dir / "concepts" / "stt.md").write_text(
        "# Speech To Text\n\nWhisper transcribes audio to text. NodeAva uses base.en.\n"
    )
    (wiki_dir / "entities" / "kokoro.md").write_text(
        "# Kokoro\n\nKokoro-82M is the default TTS model.\n"
    )
    return wiki_dir


async def test_search_finds_matches_across_pages(populated_wiki):
    tool = WikiSearch(wiki_dir=str(populated_wiki))
    out = await tool.execute({"query": "Kokoro"})
    # The two pages that mention Kokoro should both appear in results.
    assert "concepts/tts.md" in out
    assert "entities/kokoro.md" in out


async def test_search_case_insensitive(populated_wiki):
    tool = WikiSearch(wiki_dir=str(populated_wiki))
    out = await tool.execute({"query": "kokoro"})
    assert "Kokoro" in out  # original case preserved in result lines


async def test_search_no_matches(populated_wiki):
    tool = WikiSearch(wiki_dir=str(populated_wiki))
    out = await tool.execute({"query": "zoological-asdf"})
    assert "No matches" in out


async def test_search_requires_query(populated_wiki):
    tool = WikiSearch(wiki_dir=str(populated_wiki))
    with pytest.raises(ToolError):
        await tool.execute({})


async def test_search_skips_non_md_files(populated_wiki):
    """search should skip raw assets / images / etc."""
    (populated_wiki / "entities" / "logo.png").write_bytes(b"\x89PNG\x0d\x0a\x1a\x0a...")
    tool = WikiSearch(wiki_dir=str(populated_wiki))
    out = await tool.execute({"query": "Kokoro"})
    assert "logo.png" not in out


async def test_open_returns_page_with_header(populated_wiki):
    tool = WikiOpen(wiki_dir=str(populated_wiki))
    out = await tool.execute({"path": "concepts/tts.md"})
    assert "Path: concepts/tts.md" in out
    assert "Kokoro is a fast TTS engine" in out


async def test_open_paginates(populated_wiki):
    """num_lines + cursor work like browser.open's pagination."""
    big = populated_wiki / "concepts" / "long.md"
    big.write_text("\n".join(f"line {i}" for i in range(50)))
    tool = WikiOpen(wiki_dir=str(populated_wiki))
    out = await tool.execute({"path": "concepts/long.md", "num_lines": 5, "cursor": 10})
    assert "Lines 11-15 of 50" in out
    assert "line 10" in out
    assert "line 14" in out
    assert "line 20" not in out


async def test_open_missing_page_raises(populated_wiki):
    tool = WikiOpen(wiki_dir=str(populated_wiki))
    with pytest.raises(ToolError) as exc:
        await tool.execute({"path": "does/not/exist.md"})
    assert "exist.md" in str(exc.value)


async def test_open_rejects_path_traversal(populated_wiki):
    """`../../../etc/passwd` must not escape the wiki root."""
    tool = WikiOpen(wiki_dir=str(populated_wiki))
    with pytest.raises(ToolError) as exc:
        await tool.execute({"path": "../../../etc/passwd"})
    assert "outside the wiki" in str(exc.value).lower() or "outside" in str(exc.value).lower()


async def test_open_requires_path(populated_wiki):
    tool = WikiOpen(wiki_dir=str(populated_wiki))
    with pytest.raises(ToolError):
        await tool.execute({})
