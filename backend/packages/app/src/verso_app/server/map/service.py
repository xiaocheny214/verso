"""何时开局、是否拉回、关房要不要纪要。不写提示词、不绑模型。"""

from verso_app.server.map.ports import MapPipeline


class MapService:
    def __init__(self, pipeline: MapPipeline) -> None:
        self._pipeline = pipeline

    async def opening_topics(self, title: str, excerpt: str) -> list[str]:
        return await self._pipeline.opening_topics(title, excerpt)

    async def pull_back(self, excerpt: str, last_messages: list[str]) -> str:
        return await self._pipeline.pull_back(excerpt, last_messages)

    async def summarize(self, excerpt: str, messages: list[str]) -> str:
        return await self._pipeline.summarize(excerpt, messages)
