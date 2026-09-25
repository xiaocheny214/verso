"""纯切分：全文 + 策略 → 瞬时 TextChunk[]。不读写 DB / 对象存储 / Milvus。"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from verso_common.constants import RETRIEVAL_CHUNK_CHARS, RETRIEVAL_CHUNK_OVERLAP
from verso_common.enums import BizCode, ChunkStrategy
from verso_common.enums.chunk import LEGACY_CHUNK_STRATEGY
from verso_common.exceptions import BizException

_HEADING_RE = re.compile(r"(?m)^(#{1,6}\s+\S.*)$")


@dataclass(frozen=True, slots=True)
class ChunkStrategyParams:
    strategy: ChunkStrategy
    chunk_size: int | None = None
    overlap: int | None = None


@dataclass(frozen=True, slots=True)
class TextChunk:
    index: int
    text: str
    char_start: int
    char_end: int

    @property
    def char_count(self) -> int:
        return self.char_end - self.char_start


@dataclass(frozen=True, slots=True)
class ChunkSplitResult:
    chunks: tuple[TextChunk, ...]
    strategy: ChunkStrategy
    chunk_size: int
    overlap: int
    source_char_count: int


class ChunkService:
    """确定性切分。字符下标为 Python str，半开区间 [char_start, char_end)。"""

    def split(self, text: str, params: ChunkStrategyParams) -> ChunkSplitResult:
        strategy = params.strategy
        chunk_size, overlap = _resolve_size_overlap(params, strategy)
        if strategy is ChunkStrategy.FIXED_SIZE:
            chunks = _fixed_size(text, chunk_size=chunk_size, overlap=overlap)
        elif strategy is ChunkStrategy.STRUCTURE_AWARE:
            chunks = _structure_aware(text, chunk_size=chunk_size, overlap=overlap)
        else:
            raise BizException("chunk_strategy 无效", code=BizCode.BAD_REQUEST)
        return ChunkSplitResult(
            chunks=tuple(chunks),
            strategy=strategy,
            chunk_size=chunk_size,
            overlap=overlap,
            source_char_count=len(text),
        )

    def slice(self, text: str, ranges: Sequence[tuple[int, int]]) -> list[TextChunk]:
        chunks: list[TextChunk] = []
        length = len(text)
        for index, (start, end) in enumerate(ranges):
            if start < 0 or end < start or end > length:
                raise BizException("切块区间无效", code=BizCode.BAD_REQUEST)
            chunks.append(
                TextChunk(index=index, text=text[start:end], char_start=start, char_end=end)
            )
        return chunks

    def resplit_at(
        self,
        text: str,
        params: ChunkStrategyParams,
        indexes: Sequence[int],
    ) -> list[TextChunk]:
        result = self.split(text, params)
        by_index = {chunk.index: chunk for chunk in result.chunks}
        missing = [i for i in indexes if i not in by_index]
        if missing:
            raise BizException("切块序号不存在", code=BizCode.BAD_REQUEST)
        return [by_index[i] for i in indexes]


def normalize_chunk_strategy(raw: str) -> ChunkStrategy:
    clean = raw.strip()
    if clean == LEGACY_CHUNK_STRATEGY:
        return ChunkStrategy.FIXED_SIZE
    try:
        return ChunkStrategy(clean)
    except ValueError as exc:
        raise BizException("chunk_strategy 无效", code=BizCode.BAD_REQUEST) from exc


def parse_chunk_strategy_params(
    *,
    strategy: str | ChunkStrategy,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> ChunkStrategyParams:
    if isinstance(strategy, ChunkStrategy):
        resolved = strategy
    else:
        resolved = normalize_chunk_strategy(strategy)
    if chunk_size is not None and chunk_size < 1:
        raise BizException("chunk_size 无效", code=BizCode.BAD_REQUEST)
    if overlap is not None and overlap < 0:
        raise BizException("overlap 无效", code=BizCode.BAD_REQUEST)
    return ChunkStrategyParams(strategy=resolved, chunk_size=chunk_size, overlap=overlap)


def _resolve_size_overlap(params: ChunkStrategyParams, strategy: ChunkStrategy) -> tuple[int, int]:
    chunk_size = params.chunk_size if params.chunk_size is not None else RETRIEVAL_CHUNK_CHARS
    if strategy is ChunkStrategy.FIXED_SIZE:
        if params.overlap is not None:
            overlap = params.overlap
        elif chunk_size <= RETRIEVAL_CHUNK_OVERLAP:
            overlap = max(0, chunk_size // 5)
        else:
            overlap = RETRIEVAL_CHUNK_OVERLAP
    else:
        overlap = params.overlap if params.overlap is not None else 0
    if overlap >= chunk_size:
        raise BizException("overlap 必须小于 chunk_size", code=BizCode.BAD_REQUEST)
    return chunk_size, overlap


def _fixed_size(text: str, *, chunk_size: int, overlap: int) -> list[TextChunk]:
    if not text:
        return []
    step = chunk_size - overlap
    chunks: list[TextChunk] = []
    start = 0
    index = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        chunks.append(TextChunk(index=index, text=text[start:end], char_start=start, char_end=end))
        index += 1
        if end >= length:
            break
        start += step
    return chunks


def _structure_units(text: str) -> list[tuple[int, int]]:
    """返回结构单元的 [start, end) 列表，覆盖全文。"""
    if not text:
        return []
    splits: list[int] = [0]
    for match in _HEADING_RE.finditer(text):
        if match.start() > 0 and match.start() not in splits:
            splits.append(match.start())
    # 空行分段（在尚未切开的区间内）
    for match in re.finditer(r"\n\s*\n", text):
        pos = match.end()
        if pos not in splits and 0 < pos < len(text):
            splits.append(pos)
    splits = sorted(set(splits))
    units: list[tuple[int, int]] = []
    for i, start in enumerate(splits):
        end = splits[i + 1] if i + 1 < len(splits) else len(text)
        if start < end:
            units.append((start, end))
    return units


def _structure_aware(text: str, *, chunk_size: int, overlap: int) -> list[TextChunk]:
    if not text:
        return []
    units = _structure_units(text)
    packed: list[tuple[int, int]] = []
    buf_start: int | None = None
    buf_end: int | None = None

    def flush() -> None:
        nonlocal buf_start, buf_end
        if buf_start is not None and buf_end is not None:
            packed.append((buf_start, buf_end))
        buf_start, buf_end = None, None

    for start, end in units:
        unit_len = end - start
        if unit_len > chunk_size:
            flush()
            # 单结构单元过大：对该段做 fixed_size
            segment = text[start:end]
            for piece in _fixed_size(segment, chunk_size=chunk_size, overlap=overlap):
                packed.append((start + piece.char_start, start + piece.char_end))
            continue
        if buf_start is None:
            buf_start, buf_end = start, end
            continue
        assert buf_end is not None
        if buf_end - buf_start + unit_len <= chunk_size:
            buf_end = end
        else:
            flush()
            buf_start, buf_end = start, end
    flush()

    return [
        TextChunk(index=i, text=text[s:e], char_start=s, char_end=e)
        for i, (s, e) in enumerate(packed)
    ]
