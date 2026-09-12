# Proposal: 文下在场（Redis 热集合，不是读详情副作用）

本提案对应 [#16](https://github.com/xiaocheny214/verso/issues/16)。产品以 [#1](https://github.com/xiaocheny214/verso/issues/1) / [`product-proposal.md`](product-proposal.md) 为准；分层以 [#5](https://github.com/xiaocheny214/verso/issues/5) / [`architecture.md`](architecture.md) 为准；用户主键以 [#10](https://github.com/xiaocheny214/verso/issues/10) / [`identity.md`](identity.md) 为准；文章主键以 [#12](https://github.com/xiaocheny214/verso/issues/12) / [`article.md`](article.md) 为准；邀请只读本模块端口，以 [#14](https://github.com/xiaocheny214/verso/issues/14) / [`invite.md`](invite.md) 为准。本文只定 presence 这一个增量，不夹带实现代码，不实现 `invite` / `room` / `match`。

## 1. Summary

给 Verso 加上文下在场：已登录且 `active` 的用户，**打开文章详情并显式 join** 之后，才进入该 `article_id` 的在场集合。邀请候选人只来自这份集合。权威状态在 **Redis + 租约 TTL**，不建 Postgres 在场表。`GET /articles/{id}` 只读地图，**不得**因读详情而写入在场。

进场由前端在详情页就绪后发 `join`；离场由前端发 `leave`（路由离开、关页、进房）。后端感知不到浏览器关页是常态，因此 **心跳租约到期 = 离场**，不把「前端是否诚实」当成唯一依据。

## 2. User Stories / Motivation

- 两名已登录读者打开同一篇池内文章，文下看见对方，名单随进进出出更新；未打开该文的人不会出现。
- 未登录可以读详情，但不上报在场、不进业务 WS、不能当邀请对象。
- 关标签、回摸鱼流、崩溃、断网：对方应在租约内从名单消失，而不是永远占坑。
- `invite` 创建与 accept 问「是否仍在这篇上」；本模块给布尔与名单，不写邀请行。

共同需要：一份按文章分片、可过期、可推送的热集合；服务端能指认「谁在哪篇」。

## 3. Current Workaround

`server.presence` 只有占位。没有在场则邀请只能假装全员可邀，或把读详情当成在场——匿名、预取、重试、爬虫都会脏数据，且没有离场。

## 4. Goals

- 显式 `join` / `leave` / `heartbeat`；同一用户同一时刻最多一篇文章。
- Redis 租约：心跳续期；到期从该文集合删除并推 `article:{id}`。
- 详情页可拉快照；名单变更推频道，禁止全站广播。
- 提供 `PresenceReader` 给 invite / feed：`is_present`、`list`、`count`。
- 心跳路径禁止打知乎或 LLM。

## 5. Out of Scope

- 实现 `invite` / `room` / `match` / `feed` 排序。只给端口。
- 因离场去改 `invites.status`（[#14](https://github.com/xiaocheny214/verso/issues/14) 已推迟该事件）。
- Postgres `article_readers` / 阅读历史 / 时长统计。
- 未登录「隐身围观」进名单；跨文章全局在线墙。
- 多端同时在场（identity 已是一用户一 session）。
- 把在场抄进 `articles` 或 `invites`。
- 短轮询作为主推协议（产品允许备用；本期主路径是 WS 频道 + HTTP 快照）。

## 6. Proposal

### 6.1 Design Rule

**在场是会话上的租约，不是读地图的副作用。前端负责意图（打开 / 离开），后端负责真相（TTL）。**

```text
GET /articles/{id}
  匿名可读；只返回地图
  不 join、不续租、不订阅

已登录用户停在详情页（前端编排，不是后端中间件）
  详情 2xx 且路由仍是该文
  → join(article_id)
  → 订 article:{id}
  → 定时 heartbeat

离开该详情（路由变化 / 关页 / 进房）
  → leave（WS 或 HTTP / sendBeacon）
  → 退订 article:{id}

后端
  join：校验 session active、文章存在、一人一篇
  写入 Redis，刷新租约，推该文频道
  heartbeat：只刷新租约；不打知乎
  租约过期 ≡ leave
  崩溃未 leave：等 TTL，不要等浏览器
```

不要做：在 `GET /articles/{id}` 后由服务端「监听成功就入库」。读接口会被预取、重试、多端刷新；离场也发不出来。前端可以在查询成功之后 **调用** join，这是客户端时序，不是把 presence 耦合进 article 用例。

### 6.2 Syntax / API / Interface

| 方法 | 路径 | 谁可调 | 行为 |
|---|---|---|---|
| `GET` | `/articles/{id}/presence` | 已登录 | 该文快照（含自己则标 `self`）；外人要邀请看这份，不是 `GET /invites` |
| `POST` | `/presence/join` | 已登录 active | body `{ "article_id" }`；换文则先离旧文 |
| `POST` | `/presence/leave` | 已登录 | body 可带 `article_id`；省略则离开当前篇；供 sendBeacon |
| `POST` | `/presence/heartbeat` | 已登录 | 续当前租约；无人场则 409 |

WS（同一 Cookie 或短活 ticket；每用户 1 条业务连接）只收：

```text
{ "type": "presence.join", "article_id": "<uuid>" }
{ "type": "presence.leave", "article_id": "<uuid>" }   # article_id 可省略
{ "type": "heartbeat" }
```

服务端向 `article:{id}` 推（不是全站）：

```text
{ "type": "presence.snapshot", "article_id": "<uuid>", "count": 2, "members": [ ... ] }
```

`join` / `leave` 成功后推快照。`heartbeat` 不推。HTTP 与 WS 对 Redis 的效果相同；WS 额外完成订阅。未登录禁止连业务 WS。

包边界：`web.api.presence` 与 WS 适配器只做协议；用例在 `server.presence`。`web` 不直连 Redis key。本模块 **读** identity（当前用户）、article（`articles.id` 存在）；**写** Redis；**调** `framework.realtime`。不写 `invites` / `rooms`。不发知乎请求。

```text
VERSO_PRESENCE_HEARTBEAT_SEC     # 客户端间隔，建议 15
VERSO_PRESENCE_LEASE_SEC         # 租约，建议 45（≥ 2× 心跳 + 抖动）
VERSO_PRESENCE_LIST_MAX          # 快照人数上限，建议 50；超出仍准 count
```

端口（对方未实现时用假实现）：

```text
PresenceReader.is_present(user_id, article_id) -> bool
PresenceReader.list(article_id) -> [PresenceMember]   # 不超过 LIST_MAX
PresenceReader.count(article_id) -> int               # 真实人数，供 feed

PresenceWriter.leave(user_id) -> None                 # 进房 / 登出 / 封禁调用
```

`invite` 只依赖 `is_present`。`count` 不反写 `articles`。

### 6.3 Examples as Specification

**当前：** 无在场集合。读详情不等于在场。

**提案主路径（规范，不是示意）：**

```text
A、B 已登录 active。A 打开 article X：

GET /articles/X          → 200 地图；Redis 仍无 A
POST /presence/join { "article_id": X }
  session → users.id = A
  articles.id = X 存在
  若 A 已在 Y：先按 leave(Y) 再 join(X)
  Redis：
    presence:user:{A} = X
    presence:lease:{A} TTL = LEASE_SEC
    presence:article:{X} 加入 A
  realtime 订 article:{X}
  推 presence.snapshot 给该频道

B 同样 join(X)
  GET /articles/X/presence
    members 含 A、B（可含 self）
    不含未 join 的用户

A 发心跳
  仅续 presence:lease:{A}
  不碰知乎、不重推快照

A 回列表
  POST /presence/leave { "article_id": X } 或 WS presence.leave
  删 lease / user 映射 / article 集合中的 A
  推新快照（仅剩 B）
```

**快照成员（读时计算角色，不冻结）：**

```json
{
  "article_id": "uuid",
  "count": 2,
  "members": [
    {
      "user_id": "uuid",
      "display_name": "…",
      "avatar_url": "https://…",
      "role": "author",
      "self": false
    }
  ]
}
```

`role`：`user_id == articles.author_user_id` → `author`，否则 `co_reader`。不把调用方写成 `reader` 来冒充邀请快照——邀请创建时的 `from_role` / `to_role` 仍由 invite 按 [#14](https://github.com/xiaocheny214/verso/issues/14) 冻结。本列表只给「文下看见谁」。不返回 token、sid、知乎凭证。

**租约到期：**

```text
lease 键消失（TTL 或主动 leave）
  若 presence:user:{U} 仍指向 X
    从 presence:article:{X} 去掉 U
    删除 presence:user:{U}
    推 article:{X} 快照
```

读 `is_present` 时若 lease 已无，视为不在场，并可顺便清理（惰性删）。不另做分钟级全表扫，除非实现需要补偿。

**进房：**

```text
room 创建成功（非本期实现）
  PresenceWriter.leave(双方)
  退订 article:{id}，只留 room:{id}
  两人从该文邀请列表消失
```

**等价形态：** HTTP join 与 WS `presence.join` 写同一套 key。重复 join 同一篇 = 续租 + 保证在集合中，幂等。

**无效：** 未登录 join；`banned` join；文章不存在；匿名连业务 WS；把 `GET /articles/{id}` 当 join；`GET /invites` 当候选人列表。均失败或不得写入。

### 6.4 Boundary Cases

| 情况 | 行为 |
|---|---|
| 未登录读详情 | 200 地图；无 join；`GET .../presence` 未认证 |
| 已登录未 join | 不在名单；invite 创建失败（对方/自己不在场） |
| 详情预取 / 连打两次 GET | 不产生两条在场；只有 join 才写 |
| 关页来不及 WS | `navigator.sendBeacon` → `POST /presence/leave`；否则等 TTL |
| 心跳丢失超过租约 | 离场并推快照 |
| 换文 | join 新文前 leave 旧文；旧文频道推离场 |
| 第二浏览器登录 | identity 踢旧 session → 旧连接失效 → leave 或等 TTL |
| 冷启动未入驻作者 | 无 `users` 行，不能 join，不能出现在名单 |
| 作者在自己文下 join | 可以；`role=author`；可被邀、可主动邀 |
| 隐藏标签仍开着详情 | **仍在场**；继续心跳。离开指路由/关页/进房，不是 `visibilitychange=hidden` |
| 名单超过 `LIST_MAX` | `count` 仍准；`members` 截断（实现可稳定排序，如 join 时间） |
| 进房后文章页仍挂着 | 仍须 leave 文下集合；房内不等于可邀请 |
| 封禁 / 登出 | 立刻 `PresenceWriter.leave` |
| invite pending 期间离场 | 本模块只删在场；不改邀请状态 |

## 7. Error Handling

| 条件 | 行为 |
|---|---|
| 未认证 join / leave / heartbeat / 快照 | 未认证，不写 Redis |
| `status != active` | 与未登录相同；清理租约 |
| 文章不存在 | 404，不 join |
| heartbeat 时无人场 | 409；客户端应重新 join 或停心跳 |
| leave 无人场 | 幂等 204 |
| 快照 / 推送出现密钥 | 视为缺陷 |
| 心跳打知乎 / LLM | 视为缺陷 |

## 8. Compatibility

加法。依赖 `users` 与 `articles` 已存在。实现顺序：identity session → article 主键 → 本模块 Redis → invite 接真 `PresenceReader`（此前可假实现）。当前无在场数据。回滚：停 join 路由与 WS 帧即回到「看得见文但不能看见人」。Redis 丢数据 = 全员重新 join，Demo 可接受。

## 9. Alternatives Considered

### 9.1 在 `GET /articles/{id}` 成功后由后端自动 join

读地图必须匿名可开。自动 join 分不清预取、重试、爬虫；也发不出 leave。产品要的是「打开并停在这篇」，不是「请求过这篇」。前端在 2xx 之后调 join 即可，不必污染 article 用例。

### 9.2 只靠前端 leave，后端不设 TTL

关页、杀进程、断网都不可靠。没有租约，名单会有幽灵，invite accept 会误判仍在场。TTL 是真相；前端 leave 只是让名单更快干净。

### 9.3 Postgres 在场表

进进出出是秒级热状态；[#5](https://github.com/xiaocheny214/verso/issues/5) 已把 presence 放 Redis。落库要扫过期行、还要为演示持久化无查询价值的数据。阅读史若以后需要，另开提案，不复用在场表。[#12](https://github.com/xiaocheny214/verso/issues/12) 说「读者—文章关系归 presence」指 **模块边界**，不是必须建 SQL 表。

### 9.4 纯短轮询、不用 WS

产品允许。架构已定文下名单订 `article:{id}`。本期 HTTP 快照 + WS 推送；实现可用短轮询当降级，但不得再发明全站广播。

### 9.5 一人多篇同时在场

MVP 一用户一 session、一连接。多篇会让「当前在哪」对 invite 含糊。换文即换集合。

## 10. Testing Strategy

| 用例 | 方法 |
|---|---|
| GET 详情不写 Redis；随后 join 才出现 | HTTP 契约 |
| 未登录 / banned 不能 join | 中间件 |
| 两人 join 同一篇，快照互见；leave 后对方消失 | 单测 Redis |
| 换文：旧文集去掉、新文集加入 | 单测 |
| 租约到期后 `is_present` 为假 | 时间夹具 |
| heartbeat 续租；无人场 heartbeat 为 409 | 单测 |
| 心跳路径无知乎 / LLM mock 调用 | 调用计数 |
| `PresenceReader` 给 invite：不在场则 false | mock 对倒 |
| 登出 / 封禁触发 leave | 与 identity 夹具 |
| 推送只到 `article:{id}`，无全站频道 | realtime 假实现断言 |
| 响应无密钥 | 契约夹具 |

## 11. Summary of Changes

| 区域 | 变更 |
|---|---|
| 本文 | 冻结 presence 契约；后续 `feat` 按此实现 |
| 以后才写的代码 | Redis 三键；`PresenceService`；HTTP 四路由；WS 帧；租约过期清理 |
| 不改 | identity 协议、`articles` 表、invite 状态机、前端仓库（前端按本契约在详情 2xx 后 join） |
| 不建 | `article_readers` 表、在场历史、全局在线表 |

实现顺序：Redis key 与租约 → join/leave 幂等 → 快照 HTTP → WS 订阅与推送 → heartbeat → 接到 identity 登出 / 封禁。缺 session 不要 join。

---

## Data model

Postgres **不加表**。热状态只在 Redis。

```text
presence:user:{user_id}       值 = article_id        当前在哪篇
presence:lease:{user_id}      TTL = LEASE_SEC        租约；消失即离场
presence:article:{article_id} SET of user_id         该文在场集合
```

不把 `display_name` 复制进 Redis；快照时读 `users`（人数上限内可接受）。不把 `status` 复制进邀请表。

不建：`article_readers`、`presence_events` 流水、`metadata JSONB`。

**给其他模块的挂钩（本期只保证这些，不实现对方逻辑）：**

| 挂钩 | 谁写 | 谁读 |
|---|---|---|
| `is_present` | presence | invite 创建与 accept |
| 文下名单 | presence | 详情页；**不是** `GET /invites` |
| `count` | presence | 日后 `FeedRanker`；不反写 articles |
| `PresenceWriter.leave` | presence | room 进房；identity 登出 / 封禁 |

---

## Architecture

```text
web  ──GET /articles/{id}──► server.article     （无副作用）

web  ──join/leave/heartbeat──► server.presence ──► Redis
                              └── realtime article:{id}

web  ──WS 订阅 article:{id}──► 只收 snapshot

invite ──PresenceReader.is_present──► server.presence

identity 登出/封禁 ──PresenceWriter.leave──► server.presence
room 进房（非本期）──PresenceWriter.leave──► server.presence
```

| 模块 | presence 提供 / 依赖 |
|---|---|
| `identity` | 仅 `active` 可 join；登出 / 封禁必须 leave |
| `article` | 只认 `articles.id`；读详情不写在场 |
| `invite` | 只问 `is_present`；不订心跳 |
| `room` | 进房调用 `leave`；本模块不建房 |
| `feed` | 可读 `count`；本期不改排序 |
| `web` | 上表 HTTP + WS 帧 |
| `worker` | 不消费 presence 专用队列；过期靠 TTL / 惰性删 |

回滚：关掉 join 与业务 WS 即回到「能读文、看不见人」。

## Open Questions

1. 租约 45s / 心跳 15s 是否偏松。只改配置，不改 key 形状。
2. 名单截断规则（先 join 优先 vs 随机）。Demo 两人无感；超过 `LIST_MAX` 再定。
3. 匿名是否展示 `count`（不含成员）。本期快照需登录；摸鱼流人数留给 feed。
4. 实现用 Redis 7 键过期还是 lease 键 + 惰性删。规格只要求「lease 消失 ≡ 离场」。
