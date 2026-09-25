"""纯切分门面：按策略名查表调用具体实现。"""

from __future__ import annotations

from collections.abc import Sequence

from verso_app.server.chunk.registry import get_chunk_strategy
from verso_app.server.chunk.types import (
    ChunkSplitResult,
    ChunkStrategyParams,
    TextChunk,
)
from verso_common.enums import BizCode, ChunkStrategy
from verso_common.enums.chunk import LEGACY_CHUNK_STRATEGY
from verso_common.exceptions import BizException


class ChunkService:
    """确定性切分。字符下标为 Python str，半开区间 [char_start, char_end)。"""

    def split(self, text: str, params: ChunkStrategyParams) -> ChunkSplitResult:
        impl = get_chunk_strategy(params.strategy)
        chunk_size, overlap = impl.resolve_size_overlap(params.chunk_size, params.overlap)
        chunks = impl.split(text, chunk_size=chunk_size, overlap=overlap)
        return ChunkSplitResult(
            chunks=tuple(chunks),
            strategy=params.strategy,
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
    # 提前校验该策略是否已注册，并校验 size/overlap 组合
    get_chunk_strategy(resolved).resolve_size_overlap(chunk_size, overlap)
    return ChunkStrategyParams(strategy=resolved, chunk_size=chunk_size, overlap=overlap)
