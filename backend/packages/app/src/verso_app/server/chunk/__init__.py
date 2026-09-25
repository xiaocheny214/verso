"""文档切块领域：纯文本策略，无持久化。"""

from verso_app.server.chunk.registry import get_chunk_strategy, register_chunk_strategy
from verso_app.server.chunk.service import (
    ChunkService,
    normalize_chunk_strategy,
    parse_chunk_strategy_params,
)
from verso_app.server.chunk.strategy import ChunkSplitStrategy
from verso_app.server.chunk.types import ChunkSplitResult, ChunkStrategyParams, TextChunk

__all__ = [
    "ChunkService",
    "ChunkSplitResult",
    "ChunkSplitStrategy",
    "ChunkStrategyParams",
    "TextChunk",
    "get_chunk_strategy",
    "normalize_chunk_strategy",
    "parse_chunk_strategy_params",
    "register_chunk_strategy",
]
