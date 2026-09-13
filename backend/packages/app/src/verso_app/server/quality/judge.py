"""不满意之后的判据。模型失败记 unclear，不扣分。"""

from __future__ import annotations

from collections.abc import Callable

from verso_common.enums import ReviewVerdict
from verso_framework.config.app import AppSettings
from verso_framework.providers.llm import HttpxChatModel

PROMPT = """你在评估一次互补教学里被评人留下的回答。
学习者这次想学：{want_text}

被评人留下的内容：
{answer}

只判断内容是否敷衍、空洞、答非所问。不要把好恶当成质量。
只输出一个词：poor、good 或 unclear。
- poor：明显敷衍、过短、或与这次想学的问题无关
- good：对这次想学的问题给出了可执行或有实质信息的回答
- unclear：证据不足，无法判断
"""


def parse_verdict(raw: str) -> ReviewVerdict:
    text = (raw or "").strip().lower()
    if not text:
        return ReviewVerdict.UNCLEAR
    first = text.split()[0].strip(".,:;\"'`")
    for verdict in ReviewVerdict:
        if first == verdict.value:
            return verdict
    found = [item for item in ReviewVerdict if item.value in text]
    if len(found) == 1:
        return found[0]
    return ReviewVerdict.UNCLEAR


class UnclearJudge:
    def judge(self, *, want_text: str, answer: str) -> ReviewVerdict:
        return ReviewVerdict.UNCLEAR


class LlmAnswerJudge:
    def __init__(self, complete: Callable[[str], str]) -> None:
        self._complete = complete

    def judge(self, *, want_text: str, answer: str) -> ReviewVerdict:
        try:
            raw = self._complete(PROMPT.format(want_text=want_text, answer=answer))
        except Exception:  # noqa: BLE001
            return ReviewVerdict.UNCLEAR
        return parse_verdict(raw)


def build_judge(settings: AppSettings) -> UnclearJudge | LlmAnswerJudge:
    if settings.llm_api_key and settings.llm_base_url and settings.llm_model:
        return LlmAnswerJudge(HttpxChatModel(settings).complete)
    return UnclearJudge()
