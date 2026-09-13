"""质量裁决端口。提示词和幂等在 quality，模型只负责生成文本。"""

from typing import Protocol

from verso_common.enums import ReviewVerdict


class AnswerJudge(Protocol):
    def judge(self, *, want_text: str, answer: str) -> ReviewVerdict: ...
