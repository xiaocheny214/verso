"""REST routers. OpenAPI is generated from these."""

from verso_app.web.api.auth import router as auth_router
from verso_app.web.api.match import router as match_router

__all__ = ["auth_router", "match_router"]
