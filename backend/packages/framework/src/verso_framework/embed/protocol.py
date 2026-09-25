"""文本向量化端口：texts → vectors。不读写 DB / Milvus。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    """可替换的 embedding 实现（LiteLLM / 假实现 / 以后其他厂商）。

    向量维度在构建时由全站配置锁定；调用 embed_* 时不再传 dimensions。
    """

    @property
    def dimensions(self) -> int | None:
        """配置的输出维；None 表示使用模型默认维（构建时未指定）。"""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量嵌入。空列表返回空列表；顺序与输入一致。"""

    def embed_query(self, text: str) -> list[float]:
        """单条查询向量。"""
