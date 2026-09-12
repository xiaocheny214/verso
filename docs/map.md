# Proposal: 局内地图（开局话题时机、手动拉回、关房纪要按房一次）

本提案对应 [#28](https://github.com/xiaocheny214/verso/issues/28)。产品以 [#1](https://github.com/xiaocheny214/verso/issues/1) / [`product-proposal.md`](product-proposal.md) 为准；分层以 [#5](https://github.com/xiaocheny214/verso/issues/5) / [`architecture.md`](architecture.md) 为准；用户主键以 [#10](https://github.com/xiaocheny214/verso/issues/10) / [`identity.md`](identity.md) 为准；文章主键以 [#12](https://github.com/xiaocheny214/verso/issues/12) / [`article.md`](article.md) 为准；房间容器与 `MapGateway.on_open` / `MapReader` 以 [#18](https://github.com/xiaocheny214/verso/issues/18) / [`room.md`](room.md) 为准；战绩落库与 `map.summary` 以 [#20](https://github.com/xiaocheny214/verso/issues/20) / [`match.md`](match.md) 为准。本文只定 **map** 这一个增量，不夹带实现代码，不实现 `llm_pipeline` 的 P2 Chat、不改 `rooms` / `matches` 表。

## 1. Summary

给 Verso 加上局内地图**业务**：文章是这一局的地图，模型不是第三个网友。`server.map` 只定三件事的**时机**——何时开局话题、是否拉回、关房这一次要不要生成纪要。生成文案走 `MapPipeline`（P0 由同层 `llm_pipeline.TemplateMapPipeline` 注入；`map` 也可以直接调用同层 `llm_pipeline`）。`room` / `match` **不得**跳过 map 去调模型。不建表；开局 / 拉回热存在 Redis；纪要正文仍由 `match` 按人保存。

## 2. User Stories / Motivation

- 双方同意进房：还没开口，房内已经有 1–3 条围着这篇文章的讨论点。刷新后再 GET，点还在。生成失败不拆房，只是话题为空。
- 聊着聊着偏了：点「拉回地图」，频道里出现一句贴回原文的提醒。这句话不是聊天气泡、不进热 LIST、不进关房快照。对方也能看见。
- 局末：有人开了「自动生成纪要」才真正跑一次生成；两边都关则不跑。生成的是若干条纪要，不是逐字稿。保存不保存仍由 `match` 按人处理。
- 额度紧：开局用摘要截句模板也能进房；纪要可以空，战绩条仍在。

共同需要：地图绑定那一篇；用户只看见房间和文章；生成有闸、有降级，不在发言 / 心跳路径上打模型。

## 3. Current Workaround

`server.map` 在 [#8](https://github.com/xiaocheny214/verso/issues/8) 骨架里只有 `MapService` 三方法直传到 `MapPipeline`，没有时机、没有 Redis 键、没有与 `room` / `match` 的闸。`room` 已规定 `MapGateway.on_open` 不得阻塞建房，假实现可空；`match` 已规定按 `users.summary_generate` enqueue `map.summary`，假 `summarize` 返回空。没有本规格时，实现者会把提示词塞进房间、在关房 HTTP 里调模型，或自己再读一遍偏好造成双闸。

## 4. Goals

- 冻结一条规则：map 管时机与落地；pipeline 管文案；偏好闸在 match；房间只留容器。
- 兑现 `MapReader.for_room`、`MapGateway.on_open`、`MapGateway.summarize`；补上手动拉回。
- 开局 1–3 条、拉回一句、纪要 `{ headline, bullets }`，全部 grounded 在文章 `title` + `summary`（纪要 / 拉回可加消息正文，不加用户当对话对象）。
- P0 模板可同步；换成 Chat 必须异步，失败降级模板或空结果，**禁止**回滚建房 / 关房。
- 不建 Postgres 表；不把话题 / 拉回 / 纪要写进 `rooms` / `matches` 事实列。

## 5. Out of Scope

- 实现 `framework.providers.llm` Chat、知乎直答配额、提示词版本管理台。只定 P0 `TemplateMapPipeline` 与端口。
- 自动检测跑题、连续拉回、Agent 陪聊、用户 @ 模型。
- RAG / 知识库 / embedding / 按 `topic_key` 生成。
- 写 `matches` / `match_summaries` / 草稿键；读 `users.summary_*` 决定 enqueue。
- 改 `rooms` DDL、把拉回推进 `room:messages` LIST。
- 开放局 `open_map`、多人对局、语音。
- 质检 / faithfulness 分数（日后若做，日志留在 `llm_pipeline`，不进战绩列）。
- 改 identity 偏好默认值；改 feed / invite / presence。

## 6. Proposal

### 6.1 Design Rule

**地图是房间上的文章，不是第三个网友。map 决定何时生成；文案只经 MapPipeline（或同层 llm_pipeline）；偏好闸只在 match。**

```text
三件事，三个触发，禁止第四个（心跳 / send / presence）

开局话题
  触发：RoomGateway.create_from_invite 成功之后 MapGateway.on_open(room)
  不在 pending 邀请时预生成（拒绝浪费额度）
  不在 GET /rooms/{id} 时懒生成（刷新会打两次）
  每房至多成功写入一次 talking_points；重试 on_open 已有则跳过
  模板可同步；Chat 必须 mq.publish map.opening，on_open 立即返回
  失败：talking_points=[]；房间仍 open

拉回
  触发：成员显式 POST /rooms/{id}/pull-back
  不自动检测跑题
  产物是地图提醒，不是 room.message；禁止 RPUSH 热 LIST
  冷却 VERSO_MAP_PULL_BACK_COOLDOWN_SEC；已 leave / closed 不可点

纪要
  触发：仅 worker 侧 MapGateway.summarize（由 match 消费 map.summary 时调用）
  要不要跑：match 已按任一侧 summary_generate enqueue；两侧都关则根本没有事件
  map 不再读 preferences、不再自己 publish map.summary（禁止双闸）
  按房一次：同一 snapshot_key / match_id 再调，返回同一结果或空，不发明第二份
  读 room:snapshot:{id} + 文章；不反写 rooms / matches 事实列
  空结果合法；不堵关房 HTTP

生成端口
  MapPipeline.opening_topics / pull_back / summarize
  bootstrap 注入 llm_pipeline.TemplateMapPipeline
  map 允许 import 同层 llm_pipeline 调这三步
  禁止 map / room / match 调 framework.providers.llm
  禁止 room / match 绕过 MapGateway 调 llm_pipeline 做这三件事
```

不要做：把模型当房内用户发言；把开局话题存进 `rooms`；在 `on_room_closed` 同步 HTTP 调模型；map 与 match 各读一遍 `summary_generate`。

### 6.2 Syntax / API / Interface

| 方法 | 路径 | 谁可调 | 行为 |
|---|---|---|---|
| `POST` | `/rooms/{id}/pull-back` | 仅该房成员，且 `open`、该侧未 leave | 生成一句拉回；推 `room.pull_back`；写 `map:room:{id}` |

没有 `POST /maps`。开局不是 HTTP。纪要保存仍是 `POST /matches/{id}/summary`（[#20](https://github.com/xiaocheny214/verso/issues/20)），本模块不接。

`GET /rooms/{id}` 的 `map` 对象仍由房间聚合 `MapReader.for_room`，本增量约定形状为：

```json
{
  "article_id": "uuid",
  "title": "…",
  "summary": "…",
  "canonical_url": "https://…",
  "talking_points": ["…"],
  "pull_back": null
}
```

`talking_points` 未就绪则为 `[]`。`pull_back` 未点过则为 `null`。房间提案文件不在本 PR 改；实现 room feat 时透传这两个字段。

服务端向 `room:{id}` **增加**一帧（已有 `room.map` / `room.message` / `room.closed` 不改名）：

```text
{ "type": "room.map", "room_id": "<uuid>", "talking_points": [ ... ] }
{ "type": "room.pull_back", "room_id": "<uuid>", "text": "…" }
```

不把纪要正文推到 `room:{id}`（房已关）。不推提示词、快照 key、模型名。

包边界：`web.api.rooms` 的 pull-back 只做协议；用例在 `server.map`。`web` 不直连 Redis map 键。本模块 **读** article（`title` / `summary` / `canonical_url`）、room 行（认这间房、成员、open）、热 LIST 或关房快照的 **body 列表**；**写** `map:room:{id}`；**调** `MapPipeline` 或同层 `llm_pipeline`、`framework.realtime`、必要时 `framework.mq`（`map.opening`）。不发知乎请求，不 INSERT 任何业务表，不读 session 里的偏好。

```text
VERSO_MAP_TALKING_POINTS_MAX          # 开局条数上限，建议 3；少於 1 条视为空
VERSO_MAP_PULL_BACK_COOLDOWN_SEC      # 拉回冷却，建议 60
VERSO_MAP_PULL_BACK_LAST_MESSAGES     # 拉回读取最近发言条数，建议 10
VERSO_MAP_SUMMARY_BULLETS_MAX         # 纪要 bullets 上限，建议 5
VERSO_MAP_ROOM_KEY_TTL_SEC            # map:room:{id} TTL，建议 >= 房间时长 + 300
```

端口（对方未实现时用假实现）：

```text
MapReader.for_room(room) -> { title, summary, canonical_url, talking_points, pull_back }
  # title/summary/canonical_url 现查 article，不从 rooms 拷
  # talking_points / pull_back 来自 map:room:{id}；键缺失则 [] / null
  # 假实现：文章字段可空字符串，talking_points=[]，pull_back=null

MapGateway.on_open(room) -> None
  # room 建房成功后调用。模板可同步；Chat 必须异步
  # 失败忽略；禁止抛回 create_from_invite
  # 已有 talking_points 则 no-op

MapGateway.summarize(room, snapshot_key) -> { headline: str, bullets: list[str] }
  # 仅 match worker / ingest_summary 调用
  # 模板可同步；Chat 已在 worker 里，禁止再塞回关房 HTTP
  # 失败 → headline="" bullets=[]，不抛到关房路径

MapPipeline                            # map/ports.py；llm_pipeline 实现它
  opening_topics(title, summary) -> list[str]
  pull_back(summary, last_messages: list[str]) -> str
  summarize(summary, messages: list[str]) -> { headline, bullets }

ArticleReader.map_view(article_id) -> { title, summary, canonical_url }
  # 已有文章模块；假实现：空字段。summary 可空字符串，title 不可空（[#12]）
```

`map.opening` 事件载荷：`{ room_id }`。仅 Chat 路径需要。worker 调 `MapService.complete_opening`：房已 `closed` 则丢弃，不推频道。

`map.summary` 事件载荷仍由 [#20](https://github.com/xiaocheny214/verso/issues/20) 规定：`{ match_id, room_id, snapshot_key }`。**消费者是 `server.match.ingest_summary`**，再调 `MapGateway.summarize`。本模块不注册第二条 summary 消费者。

P0 `TemplateMapPipeline`（规范，不是示意）：

```text
opening_topics
  text = strip(summary) or strip(title)
  空 → 三条固定问句（结论 / 不同意 / 还想追问），不编造原文没有的事实
  非空 → 第一条带摘要截句（建议 ≤80 字）+ 两条问前提 / 用到自己场景
  返回 1..TALKING_POINTS_MAX；多了截断

pull_back
  不依赖模型。返回一句把讨论拉回「这篇文章的结论」的中文提醒
  可忽略 last_messages；禁止点名某个 user_id

summarize
  返回短中文：headline 一句 + bullets 2..BULLETS_MAX（无消息也可 1 条「本局几乎没有对原文展开」）
  禁止复述逐字稿；禁止分数
```

骨架里的 `excerpt` 参数与 `summarize -> str` 在 feat 时改成上表（`summary`、结构体）。本提案是契约；骨架不是。

### 6.3 Examples as Specification

**当前：** `on_open` / `summarize` 假实现；GET `talking_points=[]`；无拉回路由。

**提案主路径（规范，不是示意）：**

```text
RoomGateway.create_from_invite(I) 已 INSERT rooms R（article X，成员 A/B）
  MapGateway.on_open(R)
    ArticleReader.map_view(X) → title, summary, url
    TemplateMapPipeline.opening_topics(title, summary) → 3 句
    SET map:room:{R} { talking_points:[...], pull_back:null } EX KEY_TTL
    推 room:{R}  room.map { talking_points }

GET /rooms/{R}（成员）
  map.talking_points 有 3 句
  map.pull_back = null
  map.title 来自文章，不是 rooms 列

A：POST /rooms/{R}/pull-back
  open、A 未 leave、冷却未中
  读 LIST 最近 ≤10 条 body
  pipeline.pull_back(summary, bodies) → "拉回地图：……"
  SET map:room:{R} 带 pull_back
  推 room.pull_back { text }
  不 RPUSH room:messages:{R}

关房
  room 快照 + MatchGateway.on_room_closed
  A.summary_generate=true → match publish map.summary
  关房 HTTP 此时已结束

worker ──map.summary──► match.ingest_summary
  MapGateway.summarize(R, snapshot_key)
    GET snapshot → messages bodies
    pipeline.summarize(summary, bodies) → { headline, bullets[3] }
  match 写草稿 / 按人保存
  map 不 INSERT match_summaries
```

**等价形态：**

```text
on_open 时 pipeline 换成 Chat
  on_open 只 publish map.opening { room_id } 后返回
  worker 生成再 SET + 推 room.map
  在此之前 GET talking_points=[]，房已可聊

两侧 summary_generate=false
  无 map.summary 事件
  MapGateway.summarize 不被调用
```

**无效：** 客户端 `POST /maps`；GET 刷新触发第二次 `opening_topics`；拉回写入 LIST 被快照进纪要；`on_room_closed` 里 map 同步调 Chat；map 自己读 `summary_generate` 再 enqueue；把模型回复当成 `from_user_id` 发言。

### 6.4 Boundary Cases

| 情况 | 行为 |
|---|---|
| 文章 `summary` 为空、title 非空 | 开局用 title 截句；拉回 / 纪要仍可跑 |
| `map_view` 失败 / 文章已删 | 开局 `talking_points=[]`；纪要空结果；房不回滚 |
| `on_open` 抛错 | 忽略；房 open |
| 第二次 `on_open` 同一 `room_id` | 已有 talking_points 则不调 pipeline |
| Chat 开局时房已关 | worker 丢弃，不推 |
| 未登录 / 非成员 pull-back | 未认证 / 404 |
| 已 leave 的一侧 pull-back | 409 |
| `closed` 房 pull-back | 409 |
| 冷却未到 | 409；不调 pipeline |
| LIST 为空仍拉回 | 允许；pipeline 只看文章 |
| 快照缺失 / 空 LIST 的 summarize | 返回可空结构；不抛 |
| 同一 `map.summary` 重放 | summarize 可再跑，但结果仍交给 match 幂等写草稿；map 不建第二份表 |
| `talking_points` 超过 MAX | 截断后再写 Redis |
| 发言 / 心跳 / presence.join | 零次 pipeline / LLM 调用 |
| 密钥、snapshot key、提示词出现在 GET / WS | 视为缺陷 |

## 7. Error Handling

| 条件 | 行为 |
|---|---|
| 未认证 pull-back | 未认证，不写键 |
| 非成员 | 404，不泄露存在 |
| 房不存在 | 404 |
| 已 leave / closed / 冷却 | 409，不调 pipeline |
| `status != active` | 与未登录相同 |
| pipeline 超时 / 抛错（开局） | `talking_points=[]`，不拆房 |
| pipeline 超时 / 抛错（拉回） | 504 或 503 等价，不写 `pull_back`、不推 |
| pipeline 超时 / 抛错（纪要） | 空结构返回 match；战绩已存在 |
| Chat 失败 | 开局 / 拉回可降级同一套模板；纪要允许空 |
| 开局或拉回路径打知乎 / `providers.llm`（P0） | 视为缺陷 |
| map INSERT `rooms` / `matches` | 视为缺陷 |
| 两条 `map.summary` 消费者 | 视为缺陷 |

## 8. Compatibility

加法。不改已有表。依赖 `articles`、`rooms` 行至少能读；缺 map 时 room / match 假 gateway 行为不变（空话题、空纪要）。

`GET /rooms/{id}.map` 增加可选 `pull_back`；旧客户端忽略即可。新 WS 类型 `room.pull_back`：不认识的客户端忽略。

实现顺序：room 假 `on_open` → 本模块 Redis + 模板 pipeline → 接真 `MapReader` 进 GET → pull-back HTTP → match 接真 `summarize`。缺房间不要写 `map:room` 键。缺 match 时开局 / 拉回仍可验收。

回滚：停 pull-back 路由、`on_open` 真实现与 `map.opening` 消费者即回到空话题。已写入 Redis 靠 TTL 消失。不删 `matches` 行。

骨架 `MapService` 直传 pipeline：feat 时补时机与 Redis，**不要**在提案 PR 里改 Python。

## 9. Alternatives Considered

### 9.1 房间或 match 直接调 `llm_pipeline` / Chat

[#5](https://github.com/xiaocheny214/verso/issues/5) 把时机放在 map，提示词放在 `llm_pipeline`。发言路径和关房路径一旦夹模型，额度与超时会拖死主路径。[#18](https://github.com/xiaocheny214/verso/issues/18) §9.8 已否房间内调 LLM。match 只负责偏好闸与落库。

允许 map **同层**调用 `llm_pipeline`，是为了装配简单；不允许 room / match 走这条捷径。

### 9.2 map 再读一遍 `summary_generate` 决定要不要纪要

架构口吻是「关房要不要生成纪要」在 map。[#20](https://github.com/xiaocheny214/verso/issues/20) 已经把 enqueue 写进 `MatchGateway.on_room_closed`。两处都读偏好会在「一侧开一侧关」上分叉。本提案把「要不要跑」留在 match，「怎么生成 / 空结果」留在 map。

### 9.3 自动检测跑题后拉回

产品 MVP 是手动按钮 + 一次生成。自动检测要在每条 `room.send` 上跑模型，直接违反「禁止每次按键调用」。日后若做，另开提案，且必须离开发言热路径（抽样 / 异步）。

### 9.4 拉回写成系统 `room.message`

进 LIST 就会进快照、进纪要，模型变成局内发言者，和「不当第三个网友」拧着。拉回只走独立帧和 `map:room` 字段。

### 9.5 pending 邀请时预热开局话题

拒绝 / 超时不建房。预热等于对未成局烧额度，且话题会在没有房间的键上残留。只在 `on_open`。

### 9.6 建 `map_generations` 表

话题与拉回随房销毁；纪要落在 `match_summaries`。再加一张生成史等于把短活文案永久化。本期 Redis 足够。

## 10. Testing Strategy

| 用例 | 方法 |
|---|---|
| 建房后 `on_open` 写入 1–3 句并推 `room.map`；建房不因 pipeline 延迟而失败 | 假 pipeline 阻塞仍立即返回（Chat 路径）/ 模板路径可同步断言键 |
| 第二次 `on_open` 不调 pipeline | mock 计数 |
| GET `map` 含文章字段 + talking_points；无 snapshot key | 契约 |
| pull-back 推 `room.pull_back` 且 LIST 长度不变 | Redis 夹具 |
| 非成员 / leave / closed / 冷却 → 不调 pipeline | 单测 |
| 两侧 generate 关 → `summarize` 调用次数 0 | 与 match 对照 |
| 一侧 generate → `summarize` 一次；空结果不由 map INSERT 纪要 | mock match |
| send / heartbeat / presence 路径 pipeline 调用次数 0 | 调用计数 |
| Chat 失败开局仍 open，`talking_points=[]` 或模板降级 | 单测 |
| 响应与频道无提示词、无密钥 | 契约夹具 |

## 11. Summary of Changes

| 区域 | 变更 |
|---|---|
| 本文 | 冻结 map 时机与 `MapPipeline` 契约；后续 `feat` 按此实现 |
| 以后才写的代码 | `MapService` 时机；Redis `map:room:{id}`；pull-back HTTP；`map.opening` 消费者；注入 `TemplateMapPipeline`；接真 room / match 端口 |
| 不改 | `rooms` / `matches` / `users` DDL、invite / presence / feed、前端仓库（前端按本契约展示话题、拉回按钮、忽略未知 WS） |
| 不建 | `map_generations` 表、房内 AI 用户、本模块内的知乎 / Chat HTTP（P0） |

实现顺序：端口对齐 room / match 假实现 → Redis 键 + 模板 pipeline → `on_open` 不堵建房 → pull-back → `summarize` 给 match worker。缺文章字段不要编造话题事实。P2 Chat 另开 `feat`，只换 `llm_pipeline`。

---

## Data model

Postgres **不加表**。

```text
map:room:{room_id}     STRING JSON     TTL=VERSO_MAP_ROOM_KEY_TTL_SEC
  {
    "talking_points": ["…"],     # 0..MAX
    "pull_back": "…" | null,
    "pull_back_at": "<unix>" | null
  }
  仅 map 写；MapReader / GET 聚合；关房后靠 TTL 消失，不拷进 matches

map.opening            mq 事件         { room_id }
  仅 Chat 开局需要；模板路径不发

map.summary            mq 事件         { match_id, room_id, snapshot_key }
  match 发布、match 消费；map 只提供 summarize
```

不占用 `room:messages` / `room:snapshot` 当文案库。读快照只取 `body` 列表。不建 `metadata JSONB`。

| 挂钩 | 谁写 | 谁读 |
|---|---|---|
| `rooms.article_id` / 成员 / `status` | room | map 认房、校验 pull-back |
| `articles.title` / `summary` / `canonical_url` | article | `MapReader`、pipeline 入参 |
| `map:room:{id}` | map | room GET 聚合；前端话题 / 拉回 |
| `room:snapshot:{id}` | room | map.summarize 读 body；match 计数 |
| `MapGateway.on_open` | room 调用 | map |
| `MapGateway.summarize` | match worker 调用 | map |
| `users.summary_*` | identity | **仅 match** |
| `match_summaries` / `match:draft:{id}` | match | 本人 GET；map 不写 |

---

## Architecture

```text
web ──accept──► invite → room.create_from_invite
                            └── MapGateway.on_open
                                  ├──（P0）MapPipeline.opening_topics
                                  │         或同层 llm_pipeline
                                  ├── SET map:room:{id}
                                  └── realtime room.map
                                  └──（P2 Chat）mq.publish map.opening

worker ──map.opening──► server.map.complete_opening
                            └── 房仍 open 才 SET + 推

web ──GET /rooms/{id}──► server.room ──► MapReader.for_room

web ──POST /rooms/{id}/pull-back──► server.map.pull_back
                                      ├── 冷却 / 成员 / open
                                      ├── 读 LIST bodies（不写 LIST）
                                      ├── MapPipeline.pull_back
                                      └── realtime room.pull_back

worker ──room.close──► match.on_room_closed
                         └──（按偏好）mq.publish map.summary

worker ──map.summary──► match.ingest_summary
                         └── MapGateway.summarize
                               └── MapPipeline.summarize
```

| 模块 | map 提供 / 依赖 |
|---|---|
| `article` | 只读 `map_view`；不写池 |
| `room` | 被 `on_open` 调用；GET 聚合 `for_room`；提供 LIST / 快照只读 |
| `match` | 只在 worker 调 `summarize`；偏好闸与落库不在本模块 |
| `llm_pipeline` | 同层；实现 `MapPipeline`；P0 模板、P2 才碰 `providers.llm` |
| `identity` | 仅校验当前用户是成员；不读纪要偏好 |
| `web` | pull-back HTTP；不把话题塞进 router |
| `worker` | `map.opening`（可选）；`map.summary` 仍归 match |
| `realtime` | `room:{id}` 上的 `room.map` / `room.pull_back` |

回滚：关掉 `on_open` 真实现与 pull-back 即回到空地图文案。主路径邀请 / 房间 / 战绩条不受影响。

## Open Questions

1. 拉回冷却 60s 是否改成「每房一次」。只改 `VERSO_MAP_PULL_BACK_COOLDOWN_SEC` 或加 max 计数，不改键形状。演示额度紧时可改成一次。
2. P2 用知乎直答还是自有 Chat：只换 `llm_pipeline` + `framework.providers.llm`，不改本时机表。禁止在心跳路径试额度。
3. 开局 3 句在窄屏是否太多。pipeline 可改回 1–2 句，上限配置不变。
