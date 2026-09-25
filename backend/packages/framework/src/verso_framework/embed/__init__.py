"""Embedding util：可替换实现，经注册表构建。

不是 server 域模块；process / retrieve 调用本包，不在此写 Milvus 或文档状态。
"""

from verso_framework.embed.hashing import HashingEmbedder
from verso_framework.embed.openai_compat import OpenAICompatEmbedder, build_openai_compat_embedder
from verso_framework.embed.protocol import Embedder
from verso_framework.embed.registry import build_embedder, get_embedder_factory, register_embedder

__all__ = [
    "Embedder",
    "HashingEmbedder",
    "OpenAICompatEmbedder",
    "build_embedder",
    "build_openai_compat_embedder",
    "get_embedder_factory",
    "register_embedder",
]
