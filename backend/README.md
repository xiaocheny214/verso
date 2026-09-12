# Verso backend

uv workspace：`common → framework → app`。分层说明见 [`docs/architecture.md`](../docs/architecture.md)。

```bash
cd backend
uv sync --all-packages
uv run uvicorn verso_app.bootstrap.app:app --reload
uv run python -m verso_app.bootstrap.worker
```

入口：

- Web / WS：`verso_app.bootstrap.app`
- Worker（以后可单独部署）：`verso_app.bootstrap.worker`
