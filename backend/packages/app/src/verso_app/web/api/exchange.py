"""一对关系上的多轮留言。"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from verso_app.server.auth.models import User
from verso_app.server.exchange.service import ExchangeService
from verso_app.web.middleware.auth import get_current_user, get_exchange_service
from verso_common.models import ExchangeView, MessageView, PairView
from verso_common.result import ListResponse
from verso_common.result import Response as ApiResponse

router = APIRouter(tags=["exchange"])

ExchangeDep = Annotated[ExchangeService, Depends(get_exchange_service)]
UserDep = Annotated[User, Depends(get_current_user)]


class SendMessageBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.get("/exchanges/me")
def list_mine(exchange: ExchangeDep, user: UserDep) -> ListResponse[PairView]:
    return ListResponse.success(exchange.list_mine(user))


@router.get("/exchanges/{exchange_id}")
def get_exchange(
    exchange_id: UUID,
    exchange: ExchangeDep,
    user: UserDep,
) -> ApiResponse[ExchangeView]:
    return ApiResponse.success(exchange.get(user, exchange_id))


@router.get("/exchanges/{exchange_id}/messages")
def list_messages(
    exchange_id: UUID,
    exchange: ExchangeDep,
    user: UserDep,
) -> ListResponse[MessageView]:
    return ListResponse.success(exchange.list_messages(user, exchange_id))


@router.post("/exchanges/{exchange_id}/messages")
def send_message(
    exchange_id: UUID,
    body: SendMessageBody,
    exchange: ExchangeDep,
    user: UserDep,
) -> ApiResponse[MessageView]:
    return ApiResponse.success(exchange.send(user, exchange_id, text=body.text))


@router.post("/exchanges/{exchange_id}/close")
def close_exchange(
    exchange_id: UUID,
    exchange: ExchangeDep,
    user: UserDep,
) -> ApiResponse[ExchangeView]:
    return ApiResponse.success(exchange.close(user, exchange_id))
