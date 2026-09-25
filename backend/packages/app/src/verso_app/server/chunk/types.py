"""切块瞬时类型。"""

from __future__ import annotations

from dataclasses import dataclass

from verso_common.enums import ChunkStrategy


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
