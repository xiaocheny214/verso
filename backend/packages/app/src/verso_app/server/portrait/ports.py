"""portrait 向 auth 读取授权 token 的端口。"""

from typing import Protocol


class GrantReader(Protocol):
    def load_grant(self, user_id: str) -> str | None: ...
