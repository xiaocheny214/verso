from typing import Protocol

from verso_framework.providers.zhihu.oauth import (
    HttpxOAuthClient,
    OAuthClient,
    ZhihuProfile,
    ZhihuToken,
)
from verso_framework.providers.zhihu.user_data import (
    HttpxUserDataClient,
    UserDataClient,
    ZhihuCollection,
    ZhihuContent,
    ZhihuFollowee,
)


class KeyLease(Protocol):
    key: str

    def report(self, *, used: int = 1, failed: bool = False) -> None: ...


class KeyPool(Protocol):
    """本期单环境变量；以后 provider_credentials 轮换日额度。"""

    def acquire(self) -> KeyLease: ...


__all__ = [
    "HttpxOAuthClient",
    "HttpxUserDataClient",
    "KeyLease",
    "KeyPool",
    "OAuthClient",
    "UserDataClient",
    "ZhihuCollection",
    "ZhihuContent",
    "ZhihuFollowee",
    "ZhihuProfile",
    "ZhihuToken",
]
