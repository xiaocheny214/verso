"""切块策略协议：一种策略一个实现。"""

from __future__ import annotations

from typing import Protocol

from verso_app.server.chunk.types import TextChunk
from verso_common.enums import ChunkStrategy


class ChunkSplitStrategy(Protocol):
    """按策略把全文切成半开区间块。不读写外部存储。"""

    @property
    def name(self) -> ChunkStrategy: ...

    def resolve_size_overlap(self, chunk_size: int | None, overlap: int | None) -> tuple[int, int]:
        """返回实际生效的 (chunk_size, overlap)。"""

    def split(self, text: str, *, chunk_size: int, overlap: int) -> list[TextChunk]:
        """切分；index 从 0 连续编号。"""
