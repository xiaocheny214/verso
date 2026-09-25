"""投递消息体。只放标识，正文和向量由消费者按 id 回读。

``event_id`` 是雪花号的十进制字符串。JSON 不用数字，避免超过 2^53 后被截断。
同一业务动作的重试沿用同一个 ``event_id``；新的一次请求才新发号。
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from verso_common.ids import Snowflake


class JobEventType(StrEnum):
    KNOWLEDGE_DOCUMENT_PROCESS = "knowledge.document.process_requested"
    PORTRAIT_SYNC = "portrait.sync_requested"


class KnowledgeProcessPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    knowledge_base_id: str
    document_id: str
    run_id: str


class PortraitSyncPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str


class DeliveryEvent(BaseModel):
    event_id: str
    event_type: JobEventType
    schema_version: Literal[1] = 1
    occurred_at: datetime
    producer: str
    aggregate_type: str
    aggregate_id: str
    payload: KnowledgeProcessPayload | PortraitSyncPayload

    @model_validator(mode="after")
    def _payload_matches_type(self) -> DeliveryEvent:
        expected = {
            JobEventType.KNOWLEDGE_DOCUMENT_PROCESS: KnowledgeProcessPayload,
            JobEventType.PORTRAIT_SYNC: PortraitSyncPayload,
        }[self.event_type]
        if not isinstance(self.payload, expected):
            raise ValueError("payload 与 event_type 不一致")
        return self


def new_knowledge_process_event(
    snowflake: Snowflake,
    *,
    user_id: str,
    knowledge_base_id: str,
    document_id: str,
    run_id: str,
    occurred_at: datetime | None = None,
) -> DeliveryEvent:
    return DeliveryEvent(
        event_id=str(snowflake.next_id()),
        event_type=JobEventType.KNOWLEDGE_DOCUMENT_PROCESS,
        occurred_at=occurred_at or datetime.now(UTC),
        producer="knowledge",
        aggregate_type="knowledge_document",
        aggregate_id=document_id,
        payload=KnowledgeProcessPayload(
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            document_id=document_id,
            run_id=run_id,
        ),
    )


def new_portrait_sync_event(
    snowflake: Snowflake,
    *,
    user_id: str,
    occurred_at: datetime | None = None,
) -> DeliveryEvent:
    return DeliveryEvent(
        event_id=str(snowflake.next_id()),
        event_type=JobEventType.PORTRAIT_SYNC,
        occurred_at=occurred_at or datetime.now(UTC),
        producer="portrait",
        aggregate_type="user",
        aggregate_id=user_id,
        payload=PortraitSyncPayload(user_id=user_id),
    )


def parse_delivery_event(body: bytes | str) -> DeliveryEvent:
    return DeliveryEvent.model_validate_json(body)
