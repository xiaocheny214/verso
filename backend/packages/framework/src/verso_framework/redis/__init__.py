"""Redis：Cookie Session、匹配等待态。留言落 Postgres，不把对话只放这里。"""

from verso_framework.db.redis import get_redis

__all__ = ["get_redis"]
