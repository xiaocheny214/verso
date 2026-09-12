from typing import Any, Protocol


class KeyLease(Protocol):
    key: str

    def report(self, *, used: int = 1, failed: bool = False) -> None: ...


class KeyPool(Protocol):
    """本期单环境变量；以后 provider_credentials 轮换日额度。"""

    def acquire(self) -> KeyLease: ...
