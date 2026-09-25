"""经 LiteLLM / OpenAI 兼容接口的 embedding。"""

from __future__ import annotations

from langchain_openai import OpenAIEmbeddings

from verso_framework.config.app import AppSettings
from verso_framework.embed.protocol import Embedder


class OpenAICompatEmbedder:
    """走 VERSO_LLM_*（指向 LiteLLM 代理）的 OpenAI 兼容嵌入。"""

    def __init__(
        self,
        embeddings: OpenAIEmbeddings,
        *,
        dimensions: int | None,
    ) -> None:
        self._embeddings = embeddings
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int | None:
        return self._dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return list(self._embeddings.embed_documents(texts))

    def embed_query(self, text: str) -> list[float]:
        return list(self._embeddings.embed_query(text))


def build_openai_compat_embedder(settings: AppSettings) -> Embedder:
    model = settings.llm_embedding_model.strip()
    if not model:
        raise ValueError("VERSO_LLM_EMBEDDING_MODEL is not configured")
    dimensions = settings.llm_embedding_dimensions
    if dimensions is not None and dimensions < 1:
        raise ValueError("VERSO_LLM_EMBEDDING_DIMENSIONS must be >= 1 when set")
    kwargs: dict[str, object] = {
        "model": model,
        "api_key": settings.llm_api_key or "unused",
    }
    if settings.llm_base_url:
        kwargs["base_url"] = settings.llm_base_url
    if dimensions is not None:
        kwargs["dimensions"] = dimensions
    return OpenAICompatEmbedder(OpenAIEmbeddings(**kwargs), dimensions=dimensions)
