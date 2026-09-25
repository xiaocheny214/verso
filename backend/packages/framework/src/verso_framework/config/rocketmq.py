"""RocketMQ 5 代理连接配置。

字段前缀 ``ROCKETMQ_``。默认对齐仓库根 ``docker-compose.yml`` 的 gRPC 代理端口。
import 本模块不连 Broker；建连在 ``verso_framework.mq``。
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from verso_common.ids import MAX_WORKER_ID


class RocketMqSettings(BaseSettings):
    """代理地址、主题、消费组和雪花机器号。"""

    model_config = SettingsConfigDict(
        env_prefix="ROCKETMQ_",
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    endpoints: str = "localhost:8081"
    access_key: str = ""
    secret_key: str = ""
    topic: str = "verso-job"
    consumer_group: str = "verso-worker"
    request_timeout_sec: int = 3
    await_duration_sec: int = 20
    invisible_duration_sec: int = 30
    max_message_num: int = 16
    # 同一时刻每个进程一个机器号。多进程部署时必须错开，范围 0..1023。
    worker_id: int = Field(default=1, ge=0, le=MAX_WORKER_ID)


@lru_cache
def get_rocketmq_settings() -> RocketMqSettings:
    return RocketMqSettings()
