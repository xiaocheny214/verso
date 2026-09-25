"""切块策略名。"""

from enum import StrEnum


class ChunkStrategy(StrEnum):
    FIXED_SIZE = "fixed_size"
    STRUCTURE_AWARE = "structure_aware"


# 历史占位名，读到时按 fixed_size 处理
LEGACY_CHUNK_STRATEGY = "paragraph_window"
