"""structure_aware：按标题/段落结构切，过大单元再走定长窗口。"""

from __future__ import annotations

import re

from verso_app.server.chunk.fixed_size import FixedSizeStrategy
from verso_app.server.chunk.types import TextChunk
from verso_common.constants import RETRIEVAL_CHUNK_CHARS
from verso_common.enums import BizCode, ChunkStrategy
from verso_common.exceptions import BizException

_HEADING_RE = re.compile(r"(?m)^(#{1,6}\s+\S.*)$")


class StructureAwareStrategy:
    def __init__(self, fixed_size: FixedSizeStrategy | None = None) -> None:
        self._fixed_size = fixed_size if fixed_size is not None else FixedSizeStrategy()

    @property
    def name(self) -> ChunkStrategy:
        return ChunkStrategy.STRUCTURE_AWARE

    def resolve_size_overlap(self, chunk_size: int | None, overlap: int | None) -> tuple[int, int]:
        size = chunk_size if chunk_size is not None else RETRIEVAL_CHUNK_CHARS
        resolved_overlap = overlap if overlap is not None else 0
        if resolved_overlap >= size:
            raise BizException("overlap 必须小于 chunk_size", code=BizCode.BAD_REQUEST)
        return size, resolved_overlap

    def split(self, text: str, *, chunk_size: int, overlap: int) -> list[TextChunk]:
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
                segment = text[start:end]
                for piece in self._fixed_size.split(
                    segment, chunk_size=chunk_size, overlap=overlap
                ):
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


def _structure_units(text: str) -> list[tuple[int, int]]:
    """返回结构单元的 [start, end) 列表，覆盖全文。"""
    if not text:
        return []
    splits: list[int] = [0]
    for match in _HEADING_RE.finditer(text):
        if match.start() > 0 and match.start() not in splits:
            splits.append(match.start())
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
