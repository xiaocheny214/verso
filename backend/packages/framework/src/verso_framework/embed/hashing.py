"""测试用确定性假嵌入（不访问网络）。"""

from __future__ import annotations


class HashingEmbedder:
    """把文本 hash 成固定维度向量，便于单测。"""

    def __init__(self, *, dims: int = 8) -> None:
        if dims < 1:
            raise ValueError("dims must be >= 1")
        self._dims = dims

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        vec = [0.0] * self._dims
        if not text:
            return vec
        for index, char in enumerate(text):
            vec[index % self._dims] += (ord(char) % 97) / 97.0
        norm = sum(value * value for value in vec) ** 0.5
        if norm <= 0:
            return vec
        return [value / norm for value in vec]
