from typing import Protocol

from verso_framework.providers.llm.httpx import HttpxChatModel

__all__ = ["ChatModel", "HttpxChatModel"]


class ChatModel(Protocol):
    """模板降级与真实模型走同一端口。禁止在心跳路径调用。"""

    async def complete(self, prompt: str) -> str: ...
