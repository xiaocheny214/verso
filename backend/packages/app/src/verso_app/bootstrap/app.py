def create_app():
    from fastapi import FastAPI

    from verso_app.server.llm_pipeline import TemplateMapPipeline
    from verso_app.server.map import MapService

    app = FastAPI(title="Verso", version="0.1.0")
    app.state.map = MapService(TemplateMapPipeline())

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("verso_app.bootstrap.app:app", host="0.0.0.0", port=8000, reload=True)
