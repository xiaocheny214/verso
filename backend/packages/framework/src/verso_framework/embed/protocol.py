"""文本向量化端口：texts → vectors。不读写 DB / Milvus。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    """可替换的 embedding 实现（LiteLLM / 假实现 / 以后其他厂商）。"""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量嵌入。空列表返回空列表；顺序与输入一致。"""

    def embed_query(self, text: str) -> list[float]:
        """单条查询向量。"""
