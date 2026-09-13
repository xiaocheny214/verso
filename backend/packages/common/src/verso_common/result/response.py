"""统一响应封装。

提供成功 / 失败两种响应格式，字段统一为 ``code`` / ``message`` / ``data``；
``timestamp`` 可选，需要时由调用方传入，默认不携带。

- :class:`Response` -- 单元素响应，``data`` 为单个对象或 ``None``。
- :class:`ListResponse` -- 列表响应，``data`` 为 ``list[T]``，带分页字段
  ``total`` / ``page`` / ``page_size``；全量（不分页）场景 ``page_size=0``、
  ``total`` 默认取 ``len(data)``。

业务码用 :class:`verso_common.enums.biz_code.BizCode` 收敛。HTTP 恒 200，
业务对错看 body 里的 ``code``。用法::

    @router.get("/users/{uid}")
    def get_user(uid: str) -> Response[User]:
        if not (user := find(uid)):
            return Response.fail("用户不存在", code=BizCode.NOT_FOUND)
        return Response.success(user)
"""

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field, model_serializer

from verso_common.enums.biz_code import BizCode

T = TypeVar("T")


class Response(BaseModel, Generic[T]):
    """统一响应体。"""

    code: int = Field(default=BizCode.SUCCESS, description="业务状态码:成功 200,失败非 200")
    message: str = Field(default="success", description="提示信息")
    data: T | None = Field(default=None, description="业务数据")
    timestamp: datetime | None = Field(
        default=None,
        description="响应时间;默认不携带,不携带时省略",
    )

    @model_serializer(mode="wrap")
    def _omit_null_timestamp(self, handler):
        dumped = handler(self)
        if dumped.get("timestamp") is None:
            dumped.pop("timestamp", None)
        return dumped

    @classmethod
    def success(
        cls,
        data: T | None = None,
        *,
        message: str = "success",
        code: int = BizCode.SUCCESS,
        timestamp: datetime | None = None,
    ) -> "Response[T]":
        return cls(code=code, message=message, data=data, timestamp=timestamp)

    @classmethod
    def fail(
        cls,
        message: str = "fail",
        *,
        code: int = BizCode.INTERNAL_ERROR,
        data: T | None = None,
        timestamp: datetime | None = None,
    ) -> "Response[T]":
        return cls(code=code, message=message, data=data, timestamp=timestamp)


class ListResponse(BaseModel, Generic[T]):
    """列表响应体（带分页字段）。"""

    code: int = Field(default=BizCode.SUCCESS, description="业务状态码:成功 200,失败非 200")
    message: str = Field(default="success", description="提示信息")
    data: list[T] = Field(default_factory=list, description="业务数据列表")
    total: int = Field(default=0, description="数据总数")
    page: int = Field(default=1, ge=1, description="当前页码,从 1 开始")
    page_size: int = Field(default=0, ge=0, description="每页条数;0 表示不分页")
    timestamp: datetime | None = Field(
        default=None,
        description="响应时间;默认不携带,不携带时省略",
    )

    @model_serializer(mode="wrap")
    def _omit_null_timestamp(self, handler):
        dumped = handler(self)
        if dumped.get("timestamp") is None:
            dumped.pop("timestamp", None)
        return dumped

    @classmethod
    def success(
        cls,
        data: list[T] | None = None,
        *,
        total: int | None = None,
        page: int = 1,
        page_size: int = 0,
        message: str = "success",
        code: int = BizCode.SUCCESS,
        timestamp: datetime | None = None,
    ) -> "ListResponse[T]":
        items = data or []
        return cls(
            code=code,
            message=message,
            data=items,
            total=total if total is not None else len(items),
            page=page,
            page_size=page_size,
            timestamp=timestamp,
        )

    @classmethod
    def fail(
        cls,
        message: str = "fail",
        *,
        code: int = BizCode.INTERNAL_ERROR,
        data: list[T] | None = None,
        total: int = 0,
        page: int = 1,
        page_size: int = 0,
        timestamp: datetime | None = None,
    ) -> "ListResponse[T]":
        return cls(
            code=code,
            message=message,
            data=data or [],
            total=total,
            page=page,
            page_size=page_size,
            timestamp=timestamp,
        )
