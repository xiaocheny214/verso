"""授权用户创作归档。正文在对象存储，元数据在 Postgres。"""

from verso_app.server.article.service import ArchiveService

__all__ = ["ArchiveService"]
