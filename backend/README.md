# Verso backend

uv workspace：`common → framework → app`。分层说明见 [`docs/architecture.md`](../docs/architecture.md)。
产品模块以 [#30](https://github.com/xiaocheny214/verso/issues/30) / [#31](https://github.com/xiaocheny214/verso/issues/31) 为准：`identity` / `match` / `exchange` / `quality` / `reputation`。

```bash
cp .env.example .env
docker compose up -d
cd backend
uv sync --all-packages
uv run uvicorn verso_app.bootstrap.app:app --reload
uv run python -m verso_app.bootstrap.worker
```

本地默认：Postgres `localhost:5432`（库/用户 `verso`，密码 `verso_dev`），Redis `localhost:6379/0`。

HTTP 统一返回 `{code, message, data}`，HTTP 状态码恒 200，业务对错看 `code`。领域错误抛 `BizException`。

入口：

- Web / WS：`verso_app.bootstrap.app`
- Worker（以后可单独部署）：`verso_app.bootstrap.worker`
