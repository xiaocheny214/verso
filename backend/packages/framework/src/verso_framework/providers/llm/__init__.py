from typing import Protocol


class ChatModel(Protocol):
    """模板降级与真实模型走同一端口。禁止在心跳路径调用。"""

    async def complete(self, prompt: str) -> str: ...
