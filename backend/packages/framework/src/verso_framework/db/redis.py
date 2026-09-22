"""Redis 客户端。

首次 ``get_redis`` 时建连接池。调用方用完不必手动关闭连接（连接归还池）。
"""

from functools import lru_cache

import redis

from verso_framework.config.redis import RedisSettings


@lru_cache
def get_redis_settings() -> RedisSettings:
    return RedisSettings()


@lru_cache
def _pool() -> redis.ConnectionPool:
    return redis.ConnectionPool.from_url(
        get_redis_settings().url,
        decode_responses=True,
        socket_timeout=None,
    )


def get_redis() -> redis.Redis:
    """获取 Redis 连接（从连接池）。"""
    return redis.Redis(connection_pool=_pool())
