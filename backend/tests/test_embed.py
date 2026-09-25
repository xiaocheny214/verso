from __future__ import annotations

import pytest

from verso_framework.config.app import AppSettings
from verso_framework.embed import (
    HashingEmbedder,
    build_embedder,
    get_embedder_factory,
    register_embedder,
)
from verso_framework.embed.openai_compat import OpenAICompatEmbedder


def test_hashing_embedder_is_deterministic_and_ordered() -> None:
    embedder = HashingEmbedder(dims=4)
    assert embedder.dimensions == 4
    texts = ["hello", "world", "hello"]
    first = embedder.embed_documents(texts)
    second = embedder.embed_documents(texts)
    assert first == second
    assert len(first) == 3
    assert first[0] == first[2]
    assert first[0] != first[1]
    assert embedder.embed_documents([]) == []
    assert len(embedder.embed_query("hello")) == 4


def test_build_embedder_requires_model() -> None:
    settings = AppSettings(
        _env_file=None,
        llm_embedding_model="",
        llm_api_key="k",
        llm_base_url="http://localhost:4000",
    )
    with pytest.raises(ValueError, match="VERSO_LLM_EMBEDDING_MODEL"):
        build_embedder(settings)


def test_build_embedder_rejects_invalid_dimensions() -> None:
    settings = AppSettings(
        _env_file=None,
        llm_embedding_model="text-embedding-3-small",
        llm_embedding_dimensions=0,
    )
    with pytest.raises(ValueError, match="VERSO_LLM_EMBEDDING_DIMENSIONS"):
        build_embedder(settings)


def test_build_embedder_openai_compat(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeOpenAIEmbeddings:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[float(len(text))] for text in texts]

        def embed_query(self, text: str) -> list[float]:
            return [float(len(text))]

    monkeypatch.setattr(
        "verso_framework.embed.openai_compat.OpenAIEmbeddings",
        FakeOpenAIEmbeddings,
    )
    settings = AppSettings(
        _env_file=None,
        llm_embedding_model="text-embedding-3-small",
        llm_embedding_dimensions=1024,
        llm_api_key="secret",
        llm_base_url="http://litellm.local/v1",
    )
    embedder = build_embedder(settings, provider="openai_compat")
    assert isinstance(embedder, OpenAICompatEmbedder)
    assert embedder.dimensions == 1024
    assert captured["model"] == "text-embedding-3-small"
    assert captured["api_key"] == "secret"
    assert captured["base_url"] == "http://litellm.local/v1"
    assert captured["dimensions"] == 1024
    assert embedder.embed_documents(["ab", "c"]) == [[2.0], [1.0]]
    assert embedder.embed_query("xyz") == [3.0]


def test_build_embedder_omits_dimensions_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeOpenAIEmbeddings:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[1.0] for _ in texts]

        def embed_query(self, text: str) -> list[float]:
            return [1.0]

    monkeypatch.setattr(
        "verso_framework.embed.openai_compat.OpenAIEmbeddings",
        FakeOpenAIEmbeddings,
    )
    settings = AppSettings(
        _env_file=None,
        llm_embedding_model="text-embedding-3-small",
        llm_embedding_dimensions=None,
    )
    embedder = build_embedder(settings)
    assert embedder.dimensions is None
    assert "dimensions" not in captured


def test_register_custom_embedder() -> None:
    def factory(settings: AppSettings) -> HashingEmbedder:
        dims = settings.llm_embedding_dimensions or 2
        return HashingEmbedder(dims=dims)

    register_embedder("hashing_test", factory)
    assert get_embedder_factory("hashing_test") is factory
    built = build_embedder(
        AppSettings(_env_file=None, llm_embedding_dimensions=3),
        provider="hashing_test",
    )
    assert isinstance(built, HashingEmbedder)
    assert built.dimensions == 3
    assert len(built.embed_query("a")) == 3
