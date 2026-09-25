"""策略注册表：按 ChunkStrategy 选取实现。"""

from __future__ import annotations

from verso_app.server.chunk.fixed_size import FixedSizeStrategy
from verso_app.server.chunk.strategy import ChunkSplitStrategy
from verso_app.server.chunk.structure_aware import StructureAwareStrategy
from verso_common.enums import BizCode, ChunkStrategy
from verso_common.exceptions import BizException

_FIXED = FixedSizeStrategy()
_STRUCTURE = StructureAwareStrategy(fixed_size=_FIXED)

_REGISTRY: dict[ChunkStrategy, ChunkSplitStrategy] = {
    ChunkStrategy.FIXED_SIZE: _FIXED,
    ChunkStrategy.STRUCTURE_AWARE: _STRUCTURE,
}


def get_chunk_strategy(name: ChunkStrategy) -> ChunkSplitStrategy:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise BizException("chunk_strategy 无效", code=BizCode.BAD_REQUEST) from exc


def register_chunk_strategy(strategy: ChunkSplitStrategy) -> None:
    """测试或扩展时注册新策略。"""
    _REGISTRY[strategy.name] = strategy
