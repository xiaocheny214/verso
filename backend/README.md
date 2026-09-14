# Verso backend

uv workspace：`common → framework → app`。分层说明见 [`docs/architecture.md`](../docs/architecture.md)。
产品模块以 [#30](https://github.com/xiaocheny214/verso/issues/30) / [#31](https://github.com/xiaocheny214/verso/issues/31) 为准：`identity` / `match` / `exchange` / `quality` / `reputation`。

```bash
cp .env.example .env
docker compose up -d postgres redis
cd backend
uv sync --all-packages
uv run uvicorn verso_app.bootstrap.app:app --reload
uv run python -m verso_app.bootstrap.worker
```

也可以 `docker compose up -d --build` 起后端容器；前端静态文件写到 `/var/www/verso-frontend`。本地默认：Postgres `localhost:5432`（库/用户 `verso`，密码 `verso_dev`），Redis `localhost:6379/0`。

HTTP 统一返回 `{code, message, data}`，HTTP 状态码恒 200，业务对错看 `code`。领域错误抛 `BizException`。知乎回调是浏览器跳转，使用 302。

登录（[#34](https://github.com/xiaocheny214/verso/issues/34)）：

- `GET /auth/zhihu/url` 返回授权地址，并种 intent Cookie
- `GET /auth/zhihu/callback` 换票、建用户、开声望、采画像，种 session 后 302 回 `VERSO_PUBLIC_ORIGIN`
- `POST /auth/logout`
- `GET /me`
- `POST /me/portrait/sync`
- `POST /me/portrait/self-report`（创作和收藏都抽不出擅长时才允许）

匹配（[#31](https://github.com/xiaocheny214/verso/issues/31)）：

- `POST /match/conditions` 提交这次想学的（`want_text` + `want_tag`），立刻尝试互补配对
- `GET /match/conditions/me` 当前未关闭条件；配上后带对方名片（擅长现读画像，不落匹配表）
- `POST /match/conditions/cancel` 仅取消 `waiting`
- 条件表没有 `strengths`；`covers` 用 `stable ∪ recent_7d`

交换（[#31](https://github.com/xiaocheny214/verso/issues/31)）：

- 配对成功后 `exchange.open` 记下这一对（`exchanges.id` = `pair_id`）
- `GET /exchanges/me` 会话列表；对方擅长现读画像，对方 want 读匹配条件
- `GET /exchanges/{id}` / `GET /exchanges/{id}/messages`
- `POST /exchanges/{id}/messages` 多轮留言；到期或关闭后不能再发
- `POST /exchanges/{id}/close` 任一方结束
- 消息只属于这一对，不另存一份「我和谁配上了」

本地首次启动前设置 `VERSO_CREATE_TABLES=true`，应用起来时会建 `users` / `portraits` / `reputations` / `match_conditions` / `exchanges` / `messages`。

入口：

- Web / WS：`verso_app.bootstrap.app`
- Worker（以后可单独部署）：`verso_app.bootstrap.worker`
