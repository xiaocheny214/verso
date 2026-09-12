from typing import Protocol


class MapPipeline(Protocol):
    """局内文案怎么生成。map 只依赖这个端口，提示词与管线换实现即可。"""

    async def opening_topics(self, title: str, excerpt: str) -> list[str]: ...

    async def pull_back(self, excerpt: str, last_messages: list[str]) -> str: ...

    async def summarize(self, excerpt: str, messages: list[str]) -> str: ...
