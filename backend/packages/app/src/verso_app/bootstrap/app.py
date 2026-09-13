"""FastAPI 应用工厂。装配路由、异常处理；领域逻辑仍只放 server。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from verso_common.result import Response
from verso_framework.config import get_app_settings
from verso_framework.db import Base, get_engine

from verso_app.web.api import auth_router, match_router
from verso_app.web.handler import register_exception_handlers


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_app_settings()
    if settings.create_tables:
        from verso_app.server.identity import models as identity_models  # noqa: F401
        from verso_app.server.match import models as match_models  # noqa: F401
        from verso_app.server.reputation import models as reputation_models  # noqa: F401

        Base.metadata.create_all(bind=get_engine())
    yield


def create_app() -> FastAPI:
    settings = get_app_settings()
    app = FastAPI(title="Verso", version="0.1.0", lifespan=lifespan)
    register_exception_handlers(app)
    if settings.public_origin:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[settings.public_origin],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.include_router(auth_router)
    app.include_router(match_router)

    @app.get("/health", include_in_schema=False)
    def health() -> Response[dict[str, str]]:
        return Response.success({"status": "ok"})

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("verso_app.bootstrap.app:app", host="0.0.0.0", port=8000, reload=True)
