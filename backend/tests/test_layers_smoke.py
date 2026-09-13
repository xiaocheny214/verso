import asyncio

from verso_app.server.llm_pipeline import TemplateMapPipeline
from verso_app.server.map import MapService
from verso_common.constants import REPUTATION_INITIAL_SCORE
from verso_common.enums import StrengthTag, TicketStatus


def test_enums_are_stable() -> None:
    assert StrengthTag.INTERNET == "互联网"
    assert TicketStatus.MATCHED == "matched"
    assert REPUTATION_INITIAL_SCORE == 3


def test_template_pipeline_opening_topics() -> None:
    topics = asyncio.run(TemplateMapPipeline().opening_topics("t", "一篇关于匹配的文章"))
    assert len(topics) == 3


def test_map_service_delegates_to_pipeline() -> None:
    class Fake:
        async def opening_topics(self, title: str, excerpt: str) -> list[str]:
            return ["fixed"]

        async def pull_back(self, excerpt: str, last_messages: list[str]) -> str:
            return ""

        async def summarize(self, excerpt: str, messages: list[str]) -> str:
            return ""

    topics = asyncio.run(MapService(Fake()).opening_topics("t", "x"))
    assert topics == ["fixed"]
