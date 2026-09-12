# Proposal: 战绩条与按人保存的纪要

本提案对应 [#20](https://github.com/xiaocheny214/verso/issues/20)。产品以 [#1](https://github.com/xiaocheny214/verso/issues/1) / [`product-proposal.md`](product-proposal.md) 为准；分层以 [#5](https://github.com/xiaocheny214/verso/issues/5) / [`architecture.md`](architecture.md) 为准；用户主键与纪要偏好以 [#10](https://github.com/xiaocheny214/verso/issues/10) / [`identity.md`](identity.md) 为准；文章快照以 [#12](https://github.com/xiaocheny214/verso/issues/12) / [`article.md`](article.md) 为准；角色与 intent 以 [#14](https://github.com/xiaocheny214/verso/issues/14) / [`invite.md`](invite.md) 为准；关房钩子以 [#18](https://github.com/xiaocheny214/verso/issues/18) / [`room.md`](room.md) 为准。本文只定 match 这一个增量，不夹带实现代码，不实现 `map` / `llm_pipeline`。

## 1. Summary

给 Verso 加上关房后的回顾面：`room` 只在 `closed` 时调用 `MatchGateway.on_room_closed`。本模块写 **两张表**——`matches` 是这一局的战绩条（双方共享事实、各人从个人中心看到投影），`match_summaries` 是按人保存的纪要正文。聊天一行都不进库。纪要按房生成一次（`map` 读关房快照 + 文章），每人独立决定是否写入自己的行。社交卡片只公开 **把数**；配置中心一键可对他人隐藏战绩与把数。

本模块不打分、不养等级。有效会话用快照计数冻结；主题是否贴文由纪要条目体现。LLM 质检若以后要做，走 `llm_pipeline`，评的是纪要相对地图，不写进用户可见的战绩列。

## 2. User Stories / Motivation

- 一局结束：双方个人中心都出现一张短卡片——哪篇文章、对方是谁、自己这局什么位置、聊了多久、双方开没开口。刷新几天后还能找到。
- 想带走结论的人勾选保存：只看到若干条纪要，看不到逐字稿。对方没保存则对方战绩下没有纪要。默认不保存。
- 打开自己的主页 / 社交卡片：看见「N 把」。关掉「公开战绩」后，别人看不到把数，也翻不到列表；自己在个人中心仍能看。
- 拒绝、超时、取消的邀请：战绩里没有这一局（没有房间）。
- 额度紧或模型失败：战绩条仍在；纪要可以是空，不强行打一个分数凑完整。

共同需要：房毁之后还能回想碰过谁、从哪篇开的局；结论可选带走；对外展示可关。不要把销毁掉的对话再存一遍，也不要给用户打段位。

## 3. Current Workaround

`server.match` 只有占位。`MatchGateway` 在 room 提案里是假实现（no-op）。关房后没有列表，演示脚本停在「一局聊天」。纪要偏好已经写在 `users.summary_*`，但无人读取、无处可存。

## 4. Goals

- 仅从 `on_room_closed` 建战绩；禁止 `POST /matches`。`rooms.id` UNIQUE 回指，二次关房不插第二行。
- 两张表：`matches` 不存聊天、不存纪要正文；`match_summaries` 仅本人可读、可取消保存。
- 列表挂在当前用户：`GET /matches`。他人只有 `GET /users/{id}/match-card`（把数，受 `match_history_visible` 闸）。
- 读 `users.summary_generate` / `summary_auto_save` 决定是否 `enqueue map.summary`、是否自动 INSERT 纪要行。未开自动保存则房末可 `POST .../summary`；TTL 过后草稿消失。
- 战绩行冻结：时长、角色、名片与文章标题 / 链接、两侧发言条数。不回写 `rooms` / `invites`。
- 配置中心增加 `match_history_visible`（默认公开）。隐藏后他人看不到把数与任何战绩投影。

## 5. Out of Scope

- 实现 `map` 生成文案、`llm_pipeline` 提示词、直答 / Chat 调用。只定 `MapGateway.summarize` 与 `map.summary` 事件。
- 给用户打分、ELO、命中率、等级、养成、徽章。LLM-as-judge 质检管线。
- 永久私信、逐字稿回放、24h 聊天归档。
- 开放局 `open_map` 客人进战绩；不建 `match_participants` / `room_members`。
- 公开他人的战绩列表、站内关注、完整个人主页除把数以外的字段。
- 用户删除整条战绩（会拆掉对方的卡片）。只能取消自己的纪要。
- 改 `users.summary_*` 的默认值语义；不另做第二套配置中心。
- 按局隐藏（只有全局开关）。编辑纪要正文、多人协作总结。

## 6. Proposal

### 6.1 Design Rule

**战绩是关房投影，不是用户 POST 出来的资源。纪要按人保存，生成按房一次。模型不给用户打分。**

```text
成局
  有 closed 房间  →  必有一行 matches
  握手失败        →  无房，无战绩（invites.status 不是战绩）

两张表
  matches            一局一行。双方共享事实
  match_summaries    (match_id, user_id) 至多一行。有行 = 该人已保存

个人中心（本人）
  GET /matches              自己的卡片列表（投影：对手 = 另一侧）
  GET /matches/{id}         成员可看卡片；纪要只返回自己已保存的
  POST /matches/{id}/summary    把草稿写入自己的纪要行
  DELETE /matches/{id}/summary  取消保存；不删 matches 行

社交卡片（他人）
  GET /users/{id}/match-card
  history_visible=true  → { match_count }
  history_visible=false → { history_visible: false }，无把数、无列表
  禁止 GET /users/{id}/matches

配置中心（与纪要偏好同一处）
  PATCH /me/preferences
    summary_generate / summary_auto_save / match_history_visible
  隐藏只挡他人；本人 GET /matches 不受影响

关房钩子（room 已定，本模块实现）
  MatchGateway.on_room_closed(room, snapshot_key)
    INSERT matches（幂等：已有该 room_id 则 return）
    从快照计 from_message_count / to_message_count，不拷贝 body
    任一侧 summary_generate=true → mq.publish map.summary
    两侧都关生成 → 不 enqueue、不调模型

生成（worker，不在 HTTP 请求里调 LLM）
  MapGateway.summarize(room, snapshot_key) → { headline, bullets[] }
  SET match:draft:{match_id} EX TTL（与快照同量级，建议 3600）
  对每个 summary_auto_save=true 的成员：INSERT match_summaries（拷草稿）
  对 generate 开、auto_save 关的成员：推 user:{id} match.summary_ready
  草稿不是表行；TTL 后 POST save 失败

有效会话（无模型）
  duration_sec            closed_at - starts_at
  from/to_message_count   快照里该侧非空发言条数
  both_spoke              两侧计数都 > 0
  冷场局仍写战绩，把数仍 +1

主题 / 「学到没」（无分数）
  纪要 bullets = 这局贴着地图聊了什么
  不另存 topic_hit_rate、depth_score、用户段位
  以后若质检：llm_pipeline 用纪要对文章做 faithfulness，结果只进日志 / 管线指标
```

不要做：建房时 INSERT `matches`；把 LIST JSON 落进 `matches`；把纪要正文放进 `matches` 让没保存的人日后再看；用分数填满「好像学到了」；为开放局预建 `match_participants`。

### 6.2 Syntax / API / Interface

| 方法 | 路径 | 谁可调 | 行为 |
|---|---|---|---|
| `GET` | `/matches` | 已登录 | 自己的战绩条，新在前。游标分页 |
| `GET` | `/matches/{id}` | 仅该局成员 | 卡片 + 自己的纪要（未保存则 `summary=null`） |
| `POST` | `/matches/{id}/summary` | 仅该局成员 | 从草稿保存到自己的 `match_summaries`。已保存则幂等 |
| `DELETE` | `/matches/{id}/summary` | 仅该局成员 | 删自己的纪要行。无行则 204 |
| `GET` | `/users/{id}/match-card` | 已登录 | 把数卡片；目标用户隐藏则无 `match_count` |
| `PATCH` | `/me/preferences` | 已登录 | identity 已有路径；本增量允许第三键 `match_history_visible` |

没有 `POST /matches`、没有 `DELETE /matches/{id}`、没有他人列表。

`GET /matches` 查询：`limit`（默认 20，最大 50）、`cursor`（`closed_at` + `id`）。不提供按分数 / 按主题筛选。

包边界：`web.api.matches` 只做 HTTP；用例在 `server.match`。`web` 不直连表或 Redis 草稿键。本模块 **读** identity（当前用户、三键偏好、名片）、article（关房时抄标题 / 链接）、room 行与快照键；**写** `matches` / `match_summaries` / 草稿键；**调** `framework.mq`、`framework.realtime`（`user:{id}`）、`MapGateway.summarize`（仅 worker）。不发知乎请求，不调 `framework.providers.llm`。

```text
VERSO_MATCH_SUMMARY_DRAFT_TTL_SEC    # 纪要草稿 TTL，建议 3600，与房间快照同量级
VERSO_MATCH_LIST_DEFAULT             # 列表默认条数，建议 20
```

端口：

```text
MatchGateway.on_room_closed(room, snapshot_key) -> None
  # room 关房路径调用。假实现：no-op
  # 真实现：幂等 INSERT matches；按偏好 enqueue map.summary

MapGateway.summarize(room, snapshot_key) -> { headline: str, bullets: list[str] }
  # 模板可同步；LLM 必须在 llm_pipeline / 异步 worker 里
  # 失败 → headline="" bullets=[]，不抛到关房路径
  # 本模块不实现；map 未就绪时假实现返回空

IdentityReader.preferences(user_id) -> { summary_generate, summary_auto_save, match_history_visible }
IdentityReader.card(user_id) -> { display_name, avatar_url }
```

`map.summary` 事件载荷：`{ match_id, room_id, snapshot_key }`。worker 调 `MatchService.ingest_summary` → `MapGateway.summarize` → 写草稿 / 按人落库。禁止在 `on_room_closed` 里同步 HTTP 调模型。

`PATCH /me/preferences` 允许集合变为：

```text
summary_generate        BOOLEAN    # 已有；默认 true
summary_auto_save       BOOLEAN    # 已有；默认 false
match_history_visible   BOOLEAN    # 本增量；默认 true
```

路由仍挂 identity。本迁移 `ALTER users ADD COLUMN match_history_visible`。GET `/me` 的 `preferences` 必须带上第三键。本 PR 不改 `docs/identity.md`；identity 合入后补一行允许列表（见 §8）。

### 6.3 Examples as Specification

**当前：** 关房调假 `MatchGateway`。无表。个人中心无列表。

**提案主路径（规范，不是示意）：**

```text
房间 R 已 CAS → closed；快照 room:snapshot:{R}
  from_user_id=A  from_role=reader   display_name 当时是 "甲"
  to_user_id=B    to_role=author     display_name 当时是 "乙"
  article_id=X    title="…"  canonical_url="https://…"
  starts_at, closed_at, close_reason=expired
  快照 21 条：A 12 条，B 9 条

MatchGateway.on_room_closed(R, snapshot_key)
  无 matches.room_id=R
  INSERT matches
    room_id=R UNIQUE
    抄 article_id、双方、角色、intent
    冻结 article_title / article_url
    冻结 from_display_name / to_display_name
    duration_sec = closed_at - starts_at
    from_message_count=12  to_message_count=9
  A.summary_generate=true  B.summary_generate=true
    publish map.summary { match_id, room_id, snapshot_key }
  不 INSERT match_summaries

worker 消费 map.summary
  MapGateway.summarize → { headline, bullets[3] }
  SET match:draft:{match_id} EX 3600
  A.summary_auto_save=false → 推 user:A match.summary_ready
  B.summary_auto_save=true  → INSERT match_summaries (match_id, B, headline, bullets)

A：GET /matches
  一条卡片：opponent=乙，my_role=reader，both_spoke=true，summary_saved=false

A：POST /matches/{id}/summary
  草稿仍在 → INSERT match_summaries (match_id, A, 同一份草稿)
  再 POST → 204 幂等，不改 body

B：GET /matches/{id}
  summary = B 已保存的那份
  看不到 A 是否保存、看不到草稿键、看不到快照

C：GET /users/A/match-card
  A.match_history_visible=true → { history_visible: true, match_count: 1 }
C：GET /matches 仍只是 C 自己的列表
C：GET /matches/{A的id} → 404（非成员）
```

**隐藏：**

```text
A：PATCH /me/preferences { "match_history_visible": false }
C：GET /users/A/match-card → { "user_id": A, "history_visible": false }
  无 match_count
A：GET /matches → 仍有那一条
```

**等价形态：** 同一 `room_id` 第二次 `on_room_closed` → 不插行、不重复 enqueue。已有草稿可覆盖写（同一 match_id）。

**无效：** 客户端 `POST /matches`；把 `body` 写进 matches；非成员 GET 详情；隐藏后把把数仍返回给 C；未保存的人在 TTL 后仍 GET 到纪要。

### 6.4 Boundary Cases

| 情况 | 行为 |
|---|---|
| 快照缺失 / 空 LIST | 仍 INSERT matches；两侧 message_count=0；`both_spoke=false`；仍可按偏好 enqueue（纪要可能为空） |
| 两侧 `summary_generate=false` | 不 enqueue、不写草稿、不提示 |
| 一侧 generate、一侧关闭 | 仍生成一次；只给 generate 侧推送 / 按该侧 auto_save 落库 |
| `summarize` 空结果 | 不 INSERT 空纪要；草稿可为空对象；POST save 若无 headline 且 bullets 空 → 400 |
| 草稿 TTL 过期后 POST | 404 等价「无可保存」；战绩行仍在 |
| `summary_auto_save` 但 generate 关 | 不生成、不保存。auto_save 只在有草稿时生效 |
| 用户改名 | 已关闭局仍显示冻结的 `*_display_name`；卡片头像可现查 `users` |
| 文章后改标题 | 战绩仍显示冻结的 `article_title` / `article_url` |
| `status != active` | 与未登录相同，不能读自己的写接口；已写入行保留 |
| 目标用户不存在 | `GET /users/{id}/match-card` → 404 |
| 匿名 | 未认证；不能看把数（本期卡片要登录，避免未入驻爬取） |
| 开放局客人 | 本期无此行；立项时再定是否进 `matches` |

关房弹窗由前端订 `user:{id}` 的 `match.summary_ready` 或关房后轮询 `GET /matches/{id}`（`summary_available=true` 表示草稿仍在）。不把草稿正文推到频道。

## 7. Error Handling

| 条件 | 行为 |
|---|---|
| 未认证 | 未认证，不写库 |
| 非该局成员 GET/POST/DELETE 详情或纪要 | 404（不暴露存在性） |
| `on_room_closed` 时 `rooms.status` 不是 closed | 拒绝写入；room 实现不得在 open 时调用 |
| 重复 `room_id` | 幂等成功，不 enqueue 第二次 |
| `MapGateway.summarize` 失败 | 记错误；matches 行保留；可按 match_id 重试 worker。**禁止**把房间打回 open |
| POST save 无草稿 | 无可保存 |
| POST save 空纪要 | 不插行 |
| PATCH 未知偏好键 | 忽略或 400（与 identity 现约一致，禁止静默写进 JSON 垃圾列） |
| 响应出现 snapshot key / 草稿 key / 对方纪要 | 视为缺陷 |
| 关房或列表路径打知乎 / LLM | 视为缺陷 |

## 8. Compatibility

加法。依赖 `users`、`articles`、`rooms` 已存在（至少迁移合入）。`map_role` / `match_intent` / `room_close_reason` **复用**已有 ENUM，禁止再 `CREATE TYPE` 一份。

实现顺序：room 关房钩子可先假 match → 本模块迁移与幂等 INSERT → 列表 / 卡片 HTTP → 再接真 `map.summary` worker。缺房间表不要写战绩。缺 map 时：战绩仍写，纪要恒空，Demo 可先手写 POST 夹具（仅测试，不进生产路由）。

`users.match_history_visible`：本迁移 ALTER。identity [#10] 的 PATCH 允许列表需补第三键；GET `/me` 同步。在 identity.md 合入后另开一行文档补丁，或实现 identity feat 时按本文。不要并行再发明 `/me/match-settings`。

回滚：停 `MatchGateway` 真实现与 `/matches` 路由即回到「关房无回顾」。已写入行可留。Redis 草稿丢了 = 未保存的纪要无法补救，已保存行不受影响。

## 9. Alternatives Considered

### 9.1 `match_participants.summary_text` 一张参与者表兼纪要

[#5](https://github.com/xiaocheny214/verso/issues/5) 把纪要列放在 `match_participants`。战绩与纪要生命周期不同：战绩必写、双方共享事实；纪要可选、仅本人、可取消。混在一列会让「没保存」变成 NULL 语义打架，也会诱使列表查询带出大文本。私人双人局与 `rooms` 同构，双方已经在 `matches` 行上。开放局再拆参与者表，不在本期预埋。

[#18](https://github.com/xiaocheny214/verso/issues/18) 写过「matches + match_participants」。本提案用 `matches` + `match_summaries` 落实「两套表」：前者是战绩，后者是纪要。不建第三张 `match_participants`。

### 9.2 用 LLM 给这局打分（深度 / 主题命中 / 是否学到）

业界常见做法是 LLM-as-judge：拿对话或摘要对照原文，评 groundedness / faithfulness（G-Eval、纪要质检），或从摘要抽原子事实再做蕴含。那是 **管线质检**，不是用户战绩。

产品决策一：模型不当第三个网友；养成 / 等级明确不做。把分数挂到个人中心或社交卡片，会变成段位。额度紧时分数还不稳定。

本模块能诚实记录的「效果」是：时长、是否双方开口、纪要若干条。若以后要质检，评 **已生成纪要相对文章**，结果留在 `llm_pipeline` 日志，不进 `matches`。

### 9.3 对原始聊天打分，纪要只做展示

关房后快照短活。评分若依赖原文，必须在 TTL 内跑完，且要把原文送进模型，成本高、也更像在保存对话。纪要已经是「这局说了什么」的压缩。质检应对着纪要 + 地图，而不是把 LIST 再喂一遍。本期连质检都不做。

### 9.4 客户端 `POST /matches` 或用户删除战绩

战绩是关房副作用。客户端创建会伪造未成局卡片。删除会让对方列表出现空洞。隐藏用全局开关，不提供按行删除。

### 9.5 他人可翻完整战绩列表

用户要的是社交卡片把数，不是把回顾流做成公开动态。列表含对手与文章，默认公开列表等于公开阅读与社交关系。故他人只读卡片；隐藏后连把数也没有。

### 9.6 建房时写战绩 / 把聊天落库

[#18](https://github.com/xiaocheny214/verso/issues/18) 已否。未结束局没有稳定时长；落库等于永久私信。

### 9.7 按局隐藏，或把开关做成 Redis

隐藏是个人中心配置，不是一局一个秘密。走 `users` 列，与纪要偏好一起 PATCH，刷新、多端一致。不另做 settings 表。

## 10. Testing Strategy

| 用例 | 方法 |
|---|---|
| closed 房写一行 matches；pending 邀请写零行 | mock gateway 调用方 |
| 同一 `room_id` 第二次 on_room_closed 不插第二行、不二次 enqueue | UNIQUE + 事件计数 |
| 快照 12+9 条 → 两侧计数正确；body 不出现在任何 INSERT | SQL 夹具 |
| 两侧 generate 关 → 无 `map.summary` | 事件断言 |
| auto_save 仅给开了的那一侧插 `match_summaries` | 行计数 |
| GET /matches 只看到自己为 from 或 to 的局；投影 opponent 正确 | 契约 |
| 非成员 GET 详情 404；成员看不到对方 summary 行 | 契约 |
| POST save 拷草稿；TTL 后 POST 失败；DELETE 后再 GET summary=null | Redis 时间夹具 |
| `match_history_visible=false` 时他人 match-card 无 count；本人列表仍在 | 契约 |
| 列表 / 卡片路径无知乎 / LLM mock | 调用计数 |
| 关房路径不因 summarize 抛错而失败（worker 独立） | 单测隔离 |

## 11. Summary of Changes

| 区域 | 变更 |
|---|---|
| 本文 | 冻结 match 契约；后续 `feat` 按此实现 |
| 以后才写的代码 | 迁移 `matches` / `match_summaries`；ALTER `users.match_history_visible`；`MatchService`；上表 HTTP；`map.summary` 消费者 |
| 不改 | room 关房状态机、invite 表、前端仓库（前端按本契约做个人中心、关房勾选、配置开关、把数卡片） |
| 不建 | `match_participants`、`match_scores`、聊天正文列、本模块内的 LLM 调用 |

实现顺序：表与幂等 `on_room_closed`（计数 + 冻结快照）→ `GET /matches` 与 match-card → 偏好第三键 → 草稿 + POST/DELETE summary → 再接真 map worker。缺 map 时列表验收仍可做。

---

## Data model

Postgres 加 **两张**表，并给 `users` 加一列。不建 `match_participants`、不建分数表。

```sql
ALTER TABLE users
    ADD COLUMN match_history_visible BOOLEAN NOT NULL DEFAULT TRUE;

CREATE TABLE matches (
    id                   UUID PRIMARY KEY,
    room_id              UUID NOT NULL UNIQUE REFERENCES rooms (id),
    article_id           UUID NOT NULL REFERENCES articles (id),
    from_user_id         UUID NOT NULL REFERENCES users (id),
    to_user_id           UUID NOT NULL REFERENCES users (id),
    from_role            map_role NOT NULL,
    to_role              map_role NOT NULL,
    intent               match_intent NOT NULL DEFAULT 'same_map',
    article_title        TEXT NOT NULL,
    article_url          TEXT NOT NULL,
    from_display_name    TEXT NOT NULL,
    to_display_name      TEXT NOT NULL,
    starts_at            TIMESTAMPTZ NOT NULL,
    closed_at            TIMESTAMPTZ NOT NULL,
    duration_sec         INTEGER NOT NULL,
    close_reason         room_close_reason NOT NULL,
    from_message_count   INTEGER NOT NULL DEFAULT 0,
    to_message_count     INTEGER NOT NULL DEFAULT 0,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT matches_not_self CHECK (from_user_id <> to_user_id),
    CONSTRAINT matches_duration_nonneg CHECK (duration_sec >= 0),
    CONSTRAINT matches_counts_nonneg CHECK (
        from_message_count >= 0 AND to_message_count >= 0
    )
);

CREATE INDEX matches_from_closed_idx ON matches (from_user_id, closed_at DESC, id DESC);
CREATE INDEX matches_to_closed_idx   ON matches (to_user_id,   closed_at DESC, id DESC);

CREATE TABLE match_summaries (
    id            UUID PRIMARY KEY,
    match_id      UUID NOT NULL REFERENCES matches (id),
    user_id       UUID NOT NULL REFERENCES users (id),
    headline      TEXT NOT NULL,
    bullets       TEXT[] NOT NULL,
    saved_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT match_summaries_match_user UNIQUE (match_id, user_id),
    CONSTRAINT match_summaries_not_empty CHECK (
        length(trim(headline)) > 0 OR cardinality(bullets) > 0
    )
);

CREATE INDEX match_summaries_user_idx ON match_summaries (user_id, saved_at DESC);
```

| 列 | 含义 |
|---|---|
| `matches.id` | 战绩主键；列表与纪要 FK |
| `room_id` | 回指已关闭房间；一行房间最多一条战绩 |
| `article_id` | 本局地图；标题 / 链接另冻结，防文章后改 |
| `from_*` / `to_*` | 与房间同侧；角色来自关房时的房间行 |
| `duration_sec` | 冻结时长，不每次用 now 重算 |
| `*_message_count` | 有效会话信号；不存正文 |
| `match_summaries.user_id` | 保存者；只能是该局 from 或 to（应用层校验） |
| `headline` / `bullets` | 地图 + 对话压成的短纪要；不是逐字稿 |
| `users.match_history_visible` | 他人能否看见把数；默认 true |

不把开局话题、聊天、对方纪要、模型分数存进 `matches`。不建 `metadata JSONB`、不建 `score` 列。

```text
match:draft:{match_id}     STRING JSON    # 按房一份草稿；TTL=DRAFT_TTL
  { headline, bullets }
  仅 match 写、该局成员 save 时读
  GET /matches 不返回此键；GET 详情最多返回 summary_available: bool
```

列表 JSON（本人，投影后）：

```json
{
  "id": "uuid",
  "article": { "id": "uuid", "title": "…", "canonical_url": "https://…" },
  "opponent": { "id": "uuid", "display_name": "乙", "avatar_url": "https://…" },
  "my_role": "reader",
  "their_role": "author",
  "intent": "same_map",
  "duration_sec": 720,
  "close_reason": "expired",
  "my_message_count": 12,
  "their_message_count": 9,
  "both_spoke": true,
  "summary_saved": false,
  "summary_available": true,
  "closed_at": "2026-09-12T08:00:00Z"
}
```

`GET /matches/{id}` 另加 `"summary": { "headline": "…", "bullets": ["…"] } | null`。  
`summary_available` 表示草稿未过期且自己尚未保存；他人请求不存在此字段。

社交卡片：

```json
{ "user_id": "uuid", "history_visible": true, "match_count": 12 }
```

隐藏：

```json
{ "user_id": "uuid", "history_visible": false }
```

实时（订 `user:{id}`，已有邀请频道）：

```text
{ "type": "match.summary_ready", "match_id": "<uuid>" }
```

不推纪要正文、不推草稿、不推每秒。

**给其他模块的挂钩：**

| 挂钩 | 谁写 | 谁读 |
|---|---|---|
| `MatchGateway.on_room_closed` | room | match 建行 |
| `users.summary_*` / `match_history_visible` | identity PATCH | match |
| `room:snapshot:{id}` | room | match 计数；map 纪要；TTL 后消失 |
| `map.summary` 事件 | match | worker → map.summarize → match 落草稿 / 行 |
| `GET /matches` | match | web 个人中心 |
| `GET /users/{id}/match-card` | match | web 社交卡片 |

后续 `map` 提案必须：`summarize` 不堵关房；读快照 + 文章，不反写 `rooms` / `matches` 事实列。identity feat 必须允许 PATCH 第三键。

---

## Architecture

```text
worker ──room.close──► server.room.close
                         └── MatchGateway.on_room_closed
                               ├── INSERT matches
                               └──（按偏好）mq.publish map.summary

worker ──map.summary──► server.match.ingest_summary
                         ├── MapGateway.summarize     # 假或真；真则进 llm_pipeline
                         ├── SET match:draft:{id}
                         ├── 按人 auto_save → match_summaries
                         └── realtime user:{id} match.summary_ready

web ──GET  /matches──► server.match
web ──GET  /matches/{id}
web ──POST /matches/{id}/summary
web ──DELETE /matches/{id}/summary
web ──GET  /users/{id}/match-card
web ──PATCH /me/preferences──► server.identity   # 含 match_history_visible
```

| 模块 | match 提供 / 依赖 |
|---|---|
| `identity` | 当前用户；三键偏好；名片。本模块 ALTER 一列 |
| `article` | 关房时抄 title / url；不在列表路径打知乎 |
| `invite` | 不读。拒绝局不进本表 |
| `room` | 唯一创建入口；本模块不改房间状态 |
| `map` | `summarize`；本模块不调模型 |
| `llm_pipeline` | 只被 map 调用。本模块不引用 |
| `web` | 上表 HTTP |
| `worker` | 消费 `map.summary` |
| `realtime` | `user:{id}` 一条 `match.summary_ready` |

回滚：关掉 match 路由与真 gateway 即回到「能关房但不能回顾」。已写入行可留。

## Open Questions

1. 社交卡片要不要附「最近一局文章标题」。附上会多漏一次阅读关系；本期只把数。要展示再开补丁，仍受 `match_history_visible` 闸。
2. 草稿 TTL 是否与快照 TTL 绑死。只改配置。match 读完快照后可 DEL 快照，草稿独立过期。
3. `open_map` 客人进不进把数。本期无开放局，不在 `matches` 预埋人数 JSON。
4. 把数是否排除冷场（`both_spoke=false`）。本期 **计入**。若演示觉得虚，只改卡片查询，不改表。
