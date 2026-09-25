"""framework 配置。

Postgres / Redis / 对象存储 / Milvus / RocketMQ 用各自前缀；应用密钥用 ``VERSO_``。
engine / Redis / Milvus / RocketMQ 客户端懒创建，import 本包不连库。
"""

from verso_framework.config.app import AppSettings, get_app_settings
from verso_framework.config.database import DatabaseSettings
from verso_framework.config.milvus import MilvusSettings, get_milvus_settings
from verso_framework.config.redis import RedisSettings
from verso_framework.config.rocketmq import RocketMqSettings, get_rocketmq_settings
from verso_framework.config.storage import StorageSettings, get_storage_settings

# 兼容旧入口：``from verso_framework.config import get_settings``
get_settings = get_app_settings
Settings = AppSettings

__all__ = [
    "AppSettings",
    "DatabaseSettings",
    "MilvusSettings",
    "RedisSettings",
    "RocketMqSettings",
    "Settings",
    "StorageSettings",
    "get_app_settings",
    "get_milvus_settings",
    "get_rocketmq_settings",
    "get_settings",
    "get_storage_settings",
]
