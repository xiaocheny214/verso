# Verso 后端架构

产品规格以 [`product-proposal.md`](product-proposal.md) 与 [#1](https://github.com/xiaocheny214/verso/issues/1) 为准。工程分层以 [#5](https://github.com/xiaocheny214/verso/issues/5) 为准。本文只定包边界和扩展位，不夹带实现代码。
单机可跑，worker 以后可单独部署。

本期仍是一条 Demo 主路径（登录 → 摸鱼流 → 在场邀请 → 限时房间 → 战绩 / 纪要）。目录先按 SaaS 切开，实现按 MVP 填，不把占位做成第二套系统。

---

## 一、仓库

```text
verso/
├── frontend/                 # React + TypeScript + Vite（前端负责人分层）
├── backend/                  # uv workspace，三个包
│   ├── packages/
│   │   ├── common/
│   │   ├── framework/
│   │   └── app/
│   ├── tests/
│   └── pyproject.toml
├── docs/
└── docker-compose.yml        # 落地时补：web / api / worker / postgres / redis
```

技术栈：FastAPI、PostgreSQL、Redis、Docker Compose。权威身份是站内 **Cookie Session**。知乎 OAuth 只负责发卡。

---

## 二、包分层

依赖只能向下。`web` 与 `worker` 同层，互不引用。`server` 内是同一层业务模块，**允许互相调用**（含 `map` 调用 `llm_pipeline`）。局内提示词和管线放 `server.llm_pipeline`，不塞进 `map` 的业务规则里。

```text
verso_app.bootstrap
verso_app.web  |  verso_app.worker
verso_app.server
verso_framework
verso_common
```

| 包 | 职责 | 禁止 |
|---|---|---|
| `verso-common` | 枚举、异常、DTO/VO、统一返回、常量 | 依赖 FastAPI / DB / Redis / 知乎 |
| `verso-framework` | 配置、DB、Redis、MQ 端口、实时频道、知乎/LLM **提供方**、Trace 端口 | 写邀请/房间/纪要状态机 |
| `verso-app` | 业务与入口：`server` 领域，`web` HTTP/WS，`worker` 消费，`bootstrap` 装配 | 在 router 里堆领域逻辑 |

### `framework`

- `config`：进程配置（库、Redis、OAuth、模型）。密钥不进仓库。
- `db` / `redis`：连接与会话。WS 生命周期不得占用一条 ORM 连接。
- `mq`：生产者 / 延迟消息 **端口**。本期可用 Redis Stream 或进程内实现；以后换 RocketMQ 只改这里。
- `realtime`：按频道订阅（`article:{id}` / `user:{id}` / `room:{id}`），不是全站广播。
- `providers.zhihu`：`KeyPool` 端口 + 单 key 实现。业务只调 Client，不读死环境变量。
- `providers.llm`：Chat 端口。只负责「怎么调模型」，不含开局/纪要规则。
- `observability`：`trace_id`。本期打日志，以后接 OpenTelemetry。

### `app`

- **`server`**：身份、文章池、在场、邀请、房间、地图、战绩、用户偏好、Feed 排序。对外发布领域事件（邀请超时、关房、同步文章），不碰 socket。
- **`server.map`**：局内地图**业务**——何时开局话题、是否拉回、关房要不要生成纪要、结果怎么落到房间/战绩。生成文案走 `MapPipeline`（可由 `llm_pipeline` 实现，`map` 也可以直接调用同层的 `llm_pipeline`）。
- **`server.llm_pipeline`**：易变的生成管线（P0 模板，P2 接 `framework.providers.llm`，以后加提示词版本）。与 `map` / `room` 同层，其他 server 模块可以调用。
- **`web`**：REST、WebSocket 适配、session 中间件。邀请 accept/reject 走 HTTP，避免与 WS 两套状态机。
- **`worker`**：消费 MQ：纪要生成、文章同步、邀请过期、房间到期。以后独立镜像、单独扩容，仍只调 `server`。
- **`bootstrap`**：装配 web 进程与 worker 进程；可以把 `TemplateMapPipeline` 注入 `MapService`。

---

## 三、主路径怎么穿过这些包

```text
web  ──session──► server.identity
web  ──打开文章──► server.presence ──► framework.realtime  article:{id}
web  ──发邀请──► server.invite ──► realtime user:{id}
                 └── 到期事件 ──► framework.mq ──► worker
web  ──accept──► server.invite → server.room ──► realtime room:{id}
关房 ──快照 Redis 消息──► server.match
                 └── enqueue summary ──► worker ──► server.match ──► server.map
                                                              └── MapPipeline（server.llm_pipeline）
                 └── 按 preferences 写入 / 提示保存
```

未登录：可看摸鱼流与冷启动名片，不上报在场，不进业务 WS。
已登录：session 有效且 presence 挂在某 `article_id` 上，才是可邀请对象。

---

## 四、会话

在场要的是服务端能指认「谁在哪篇文章」。用 **HTTP-only Cookie Session**（session id 存 Redis）。WebSocket 带同一 cookie，或先换短活 ticket。不要把 JWT 当在线状态。

---

## 五、实时：防连接打满

耗的是 FD / 反代并发 / 进程内存，不是 Postgres 连接池。禁止全站一条连接广播所有在场。

| 场景 | 频道 | 本期 |
|---|---|---|
| 摸鱼流在读人数 | 可不订 | 短轮询或进详情再订 |
| 文下可邀请列表 | `article:{id}` | 仅详情页 |
| 邀请弹窗 | `user:{id}` | 每用户一条连接 |
| 房内聊天 / 倒计时 | `room:{id}` | 两人 |

约束：每用户 1 条业务连接；心跳丢则离场；离开页面退订文章频道；进房后退订文章、只留房间。ORM 连接禁止绑在 WS 上。

人数上去后拆 Realtime Gateway，协议不变。`framework.realtime` 先进程内直推，多副本再 Redis Pub/Sub。

---

## 六、消息队列与 worker

`framework.mq` 只提供发布、延迟、消费循环。`server` 发领域事件，`worker` 调 `server` 用例。

本期事件：`invite.expire`、`room.close`、`map.summary`、`article.sync`。

Compose 可先把 worker 和 api 放同一镜像、两个进程。拆开时只换 `bootstrap.worker` 的部署单元。

---

## 七、纪要与用户配置

关房快照对话后 **按房生成一次**。是否写入自己的战绩看偏好（用户中心 → 匹配机制 → 纪要）：

| 配置 | 行为 |
|---|---|
| 自动生成 | 关则本用户不生成、不提示（对方仍按其配置；两人都关则跳过 LLM） |
| 生成后自动保存 | 开：写入自己的 `match_participants.summary_text` |
| 未开自动保存 | 房间结束前提示是否保存 |

战绩条始终写。默认不保存纪要。

---

## 八、文章池与 Feed

独立文章池 ≠ 本期做推荐。`server.feed` 只留 `FeedRanker` 端口：站内层优先、在场人数、最近同步。冷启动 `source=zhihu_search`，UI 标明；未入驻作者不可邀。推荐算法仍是 incoming。

---

## 九、表与 Redis

**Postgres：** `users`（含纪要偏好）、`articles`、`invites`、`rooms`（无消息列）、`matches`、`match_participants`。

**以后可加、现在不建：** `provider_credentials`、落库 outbox、推荐特征表。

**Redis：** session、presence、invite TTL、房内消息、realtime 频道。关房丢消息。

---

## 十、接口（契约仍由 FastAPI 生成一份 OpenAPI）

身份：`GET /auth/zhihu/url`、`GET /auth/zhihu/callback`、`GET /me`、偏好 PATCH。

文章：`GET /articles`、`GET /articles/{id}`、`POST /articles/sync`。

邀请：`POST /invites`、`accept` / `reject` / `cancel`。

房间 / 战绩：`GET /rooms/{id}`、`POST /rooms/{id}/leave`、`GET /matches`、`POST /matches/{id}/summary`。

WS：只收 `presence.join/leave`、`heartbeat`、`room.send`；其余由服务端按频道推。

---

## 十一、占位与明确不做

**占位（接口先在，实现可薄）：** KeyPool、LLM provider、JobQueue、FeedRanker、Trace、Realtime 多副本。

**本期不做：** Agent、RAG、真实推荐、动态 key 管理台、完整 IM、Go 第二后端、全站 WS 广播。密钥与知乎额度禁止写进心跳路径。
