"""fixed_size：字符窗口滑动切分。"""

from __future__ import annotations

from verso_app.server.chunk.types import TextChunk
from verso_common.constants import RETRIEVAL_CHUNK_CHARS, RETRIEVAL_CHUNK_OVERLAP
from verso_common.enums import BizCode, ChunkStrategy
from verso_common.exceptions import BizException


class FixedSizeStrategy:
    @property
    def name(self) -> ChunkStrategy:
        return ChunkStrategy.FIXED_SIZE

    def resolve_size_overlap(self, chunk_size: int | None, overlap: int | None) -> tuple[int, int]:
        size = chunk_size if chunk_size is not None else RETRIEVAL_CHUNK_CHARS
        if overlap is not None:
            resolved_overlap = overlap
        elif size <= RETRIEVAL_CHUNK_OVERLAP:
            resolved_overlap = max(0, size // 5)
        else:
            resolved_overlap = RETRIEVAL_CHUNK_OVERLAP
        if resolved_overlap >= size:
            raise BizException("overlap 必须小于 chunk_size", code=BizCode.BAD_REQUEST)
        return size, resolved_overlap

    def split(self, text: str, *, chunk_size: int, overlap: int) -> list[TextChunk]:
        if not text:
            return []
        step = chunk_size - overlap
        chunks: list[TextChunk] = []
        start = 0
        index = 0
        length = len(text)
        while start < length:
            end = min(start + chunk_size, length)
            chunks.append(
                TextChunk(index=index, text=text[start:end], char_start=start, char_end=end)
            )
            index += 1
            if end >= length:
                break
            start += step
        return chunks
