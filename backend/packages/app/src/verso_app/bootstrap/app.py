"""FastAPI 应用工厂。装配路由、异常处理；领域逻辑仍只放 server。"""

from fastapi import FastAPI
from verso_common.result import Response

from verso_app.web.handler import register_exception_handlers


def create_app() -> FastAPI:
    app = FastAPI(title="Verso", version="0.1.0")
    register_exception_handlers(app)

    @app.get("/health", include_in_schema=False)
    def health() -> Response[dict[str, str]]:
        return Response.success({"status": "ok"})

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("verso_app.bootstrap.app:app", host="0.0.0.0", port=8000, reload=True)
