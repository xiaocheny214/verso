"""专门评估「这次想学什么 ↔ 对方答了什么」。用 LangChain 拿结构化分数。"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from verso_common.constants import (
    QUALITY_GOOD_ABOVE,
    QUALITY_POOR_BELOW,
    QUALITY_SCORE_MAX,
    QUALITY_SCORE_MIN,
)
from verso_common.enums import ReviewVerdict
from verso_framework.config.app import AppSettings
from verso_framework.providers.llm import build_chat_model

from verso_app.server.quality.ports import Judgement

SYSTEM_PROMPT = """你是 Verso 的回答质量评审员，只做一件事：围绕学习者这次想学的问题，评估对方留下的回答有没有对准这个主题、有没有实质内容。

不要把语气、态度或主观好恶当成质量。不要扩写、不要给建议，只打分。

百分制：
- 低于 60：敷衍、过短、空洞，或明显答非所问。
- 60 到 80（含）：有在回答，但信息不足或含糊，无法确认是否真帮到这次想学的问题。
- 高于 80：对准这次想学的问题，给出了可执行或有实质信息的回答。

只输出结构化结果：score 是 0 到 100 的整数，reason 用一两句话说明依据。
"""

USER_PROMPT = """这次想学的问题：
{want_text}

对方留下的回答：
{answer}
"""


class AnswerScore(BaseModel):
    score: int = Field(ge=QUALITY_SCORE_MIN, le=QUALITY_SCORE_MAX)
    reason: str = Field(min_length=1)


def verdict_from_score(score: int) -> ReviewVerdict:
    if score < QUALITY_POOR_BELOW:
        return ReviewVerdict.POOR
    if score > QUALITY_GOOD_ABOVE:
        return ReviewVerdict.GOOD
    return ReviewVerdict.UNCLEAR


class UnclearJudge:
    def judge(self, *, want_text: str, answer: str) -> Judgement:
        return Judgement(verdict=ReviewVerdict.UNCLEAR)


class LlmAnswerJudge:
    def __init__(self, model: BaseChatModel) -> None:
        self._structured = model.with_structured_output(AnswerScore)

    def judge(self, *, want_text: str, answer: str) -> Judgement:
        try:
            raw = self._structured.invoke(
                [
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(
                        content=USER_PROMPT.format(want_text=want_text, answer=answer)
                    ),
                ]
            )
        except Exception:  # noqa: BLE001
            return Judgement(verdict=ReviewVerdict.UNCLEAR)
        scored = raw if isinstance(raw, AnswerScore) else AnswerScore.model_validate(raw)
        return Judgement(
            verdict=verdict_from_score(scored.score),
            score=scored.score,
            reason=scored.reason,
        )


def build_judge(settings: AppSettings) -> UnclearJudge | LlmAnswerJudge:
    if settings.llm_api_key and settings.llm_model:
        return LlmAnswerJudge(build_chat_model(settings))
    return UnclearJudge()
