"""质量裁决：百分制打分后映射为 poor / unclear / good。"""

from dataclasses import dataclass
from typing import Protocol

from verso_common.enums import ReviewVerdict


@dataclass(frozen=True, slots=True)
class Judgement:
    verdict: ReviewVerdict
    score: int | None = None
    reason: str = ""


class AnswerJudge(Protocol):
    def judge(self, *, want_text: str, answer: str) -> Judgement: ...
