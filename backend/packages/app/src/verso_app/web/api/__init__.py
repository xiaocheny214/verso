"""REST routers. OpenAPI is generated from these."""

from verso_app.web.api.auth import router as auth_router
from verso_app.web.api.collect import router as collect_router
from verso_app.web.api.exchange import router as exchange_router
from verso_app.web.api.knowledge import router as knowledge_router
from verso_app.web.api.match import router as match_router
from verso_app.web.api.portrait import router as portrait_router
from verso_app.web.api.quality import router as quality_router
from verso_app.web.api.reputation import router as reputation_router

__all__ = [
    "auth_router",
    "collect_router",
    "exchange_router",
    "knowledge_router",
    "match_router",
    "portrait_router",
    "quality_router",
    "reputation_router",
]
