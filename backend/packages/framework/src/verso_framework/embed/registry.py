"""Embedder 注册与按名选取。"""

from __future__ import annotations

from collections.abc import Callable

from verso_framework.config.app import AppSettings, get_app_settings
from verso_framework.embed.openai_compat import build_openai_compat_embedder
from verso_framework.embed.protocol import Embedder

EmbedderFactory = Callable[[AppSettings], Embedder]

_REGISTRY: dict[str, EmbedderFactory] = {
    "openai_compat": build_openai_compat_embedder,
}


def register_embedder(name: str, factory: EmbedderFactory) -> None:
    clean = name.strip()
    if not clean:
        raise ValueError("embedder name must not be empty")
    _REGISTRY[clean] = factory


def get_embedder_factory(name: str) -> EmbedderFactory:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        known = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise ValueError(f"unknown embedder {name!r}; known: {known}") from exc


def build_embedder(
    settings: AppSettings | None = None,
    *,
    provider: str = "openai_compat",
) -> Embedder:
    """按 provider 名构建 Embedder；维度只来自全站 settings，调用时不可改。"""
    resolved = settings if settings is not None else get_app_settings()
    return get_embedder_factory(provider)(resolved)
