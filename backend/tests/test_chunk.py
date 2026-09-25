from __future__ import annotations

import pytest

from verso_app.server.chunk import ChunkService, ChunkStrategyParams, parse_chunk_strategy_params
from verso_common.constants import RETRIEVAL_CHUNK_CHARS, RETRIEVAL_CHUNK_OVERLAP
from verso_common.enums import BizCode, ChunkStrategy
from verso_common.exceptions import BizException


def test_fixed_size_is_deterministic_and_overlapping() -> None:
    chunker = ChunkService()
    text = "abcdefghij"  # 10 chars
    params = ChunkStrategyParams(strategy=ChunkStrategy.FIXED_SIZE, chunk_size=4, overlap=1)
    first = chunker.split(text, params)
    second = chunker.split(text, params)
    assert first == second
    assert [c.text for c in first.chunks] == ["abcd", "defg", "ghij"]
    assert [(c.char_start, c.char_end) for c in first.chunks] == [(0, 4), (3, 7), (6, 10)]
    assert first.chunk_size == 4
    assert first.overlap == 1


def test_fixed_size_uses_site_defaults() -> None:
    chunker = ChunkService()
    text = "x" * (RETRIEVAL_CHUNK_CHARS + 10)
    result = chunker.split(text, ChunkStrategyParams(strategy=ChunkStrategy.FIXED_SIZE))
    assert result.chunk_size == RETRIEVAL_CHUNK_CHARS
    assert result.overlap == RETRIEVAL_CHUNK_OVERLAP
    assert result.chunks[0].char_count == RETRIEVAL_CHUNK_CHARS


def test_fixed_size_empty_and_cjk() -> None:
    chunker = ChunkService()
    empty = chunker.split("", ChunkStrategyParams(strategy=ChunkStrategy.FIXED_SIZE, chunk_size=5))
    assert empty.chunks == ()
    text = "中文测试文本一二三四五"
    result = chunker.split(
        text, ChunkStrategyParams(strategy=ChunkStrategy.FIXED_SIZE, chunk_size=4, overlap=0)
    )
    assert "".join(c.text for c in result.chunks) == text
    assert result.chunks[0].text == "中文测试"


def test_structure_aware_prefers_paragraphs_and_soft_cap() -> None:
    chunker = ChunkService()
    text = "# Title\n\nshort\n\n" + ("p" * 20) + "\n\n" + ("q" * 8)
    result = chunker.split(
        text,
        ChunkStrategyParams(strategy=ChunkStrategy.STRUCTURE_AWARE, chunk_size=15, overlap=0),
    )
    assert result.strategy is ChunkStrategy.STRUCTURE_AWARE
    assert result.chunks[0].text.startswith("# Title")
    # Oversized single unit is split
    long_unit = "x" * 40
    oversized = chunker.split(
        long_unit,
        ChunkStrategyParams(strategy=ChunkStrategy.STRUCTURE_AWARE, chunk_size=10, overlap=0),
    )
    assert len(oversized.chunks) == 4
    assert all(c.char_count <= 10 for c in oversized.chunks)


def test_slice_matches_split_ranges() -> None:
    chunker = ChunkService()
    text = "abcdefghijklmnopqrstuvwxyz"
    split = chunker.split(
        text, ChunkStrategyParams(strategy=ChunkStrategy.FIXED_SIZE, chunk_size=5, overlap=0)
    )
    sliced = chunker.slice(text, [(c.char_start, c.char_end) for c in split.chunks])
    assert [c.text for c in sliced] == [c.text for c in split.chunks]


def test_parse_rejects_legacy_as_input_alias_and_bad_names() -> None:
    assert (
        parse_chunk_strategy_params(strategy="paragraph_window").strategy
        is ChunkStrategy.FIXED_SIZE
    )
    with pytest.raises(BizException) as exc:
        parse_chunk_strategy_params(strategy="unknown")
    assert exc.value.code == BizCode.BAD_REQUEST
    with pytest.raises(BizException) as bad_overlap:
        ChunkService().split(
            "abcd",
            ChunkStrategyParams(strategy=ChunkStrategy.FIXED_SIZE, chunk_size=4, overlap=4),
        )
    assert bad_overlap.value.code == BizCode.BAD_REQUEST
