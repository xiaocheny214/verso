# Proposal: 限时邀请握手（邀请不是房间）

本提案对应 [#14](https://github.com/xiaocheny214/verso/issues/14)。产品以 [#1](https://github.com/xiaocheny214/verso/issues/1) / [`product-proposal.md`](product-proposal.md) 为准；分层以 [#5](https://github.com/xiaocheny214/verso/issues/5) / [`architecture.md`](architecture.md) 为准；用户主键以 [#10](https://github.com/xiaocheny214/verso/issues/10) / [`identity.md`](identity.md) 为准；文章主键以 [#12](https://github.com/xiaocheny214/verso/issues/12) / [`article.md`](article.md) 为准。本文只定 invite 这一个增量，不夹带实现代码，不实现 `presence` / `room` / `match`。

## 1. Summary

给 Verso 加上文下限时握手：已登录用户向**同一篇文章上在场**的另一用户发出邀请；倒计时内接受、拒绝（可带回传一句）或超时 / 取消。**只有 `accepted` 才调用 `room` 建房**；拒绝、超时、取消都不建房、不写战绩。邀请不是房间，也不是匹配引擎。候选人只来自 `presence`（已登录且打开该文才上报）；本模块不维护在线集合。

关系不是「邀请者 ↔ 被邀请者」两条边，而是产品里的三元：

```text
用户 — 文章 — 用户
```

一行邀请记下：这篇地图、双方、各自在这篇上的角色快照、`intent=same_map`、何时过期。互补本期只靠列表角色展示，用户自己选人；不另做跨域配对表。

## 2. User Stories / Motivation

- 两名已登录读者打开同一篇池内文章，文下看见对方，一方发出邀请；另一方倒计时内看到弹窗，可接受或拒绝。
- 拒绝时可写一句短回传（也可不写）；邀请人能立刻看到，刷新后仍能看到同一句。这不是私信，不能再回。
- 超时或发起人取消：不进房，邀请人得到明确终态，不是挂起的「已发出」。
- 双方同意后进入绑着这篇文章的限时房间；邀请行变成 `accepted`，房间用 `invite_id` 回指，不把聊天写回邀请表。
- 答主在自己的文下在场时可被邀、也可主动邀；战绩上的「读者 / 答主 / 同读」来自邀请创建时的角色快照，不靠关房时再猜作者。

共同需要：服务端有一份可过期、可拒绝、可回指房间的握手记录；地图和角色在创建时冻结；在场只当门卫。

## 3. Current Workaround

`server.invite` 只有占位。没有握手则演示只能假装两人已进房；拒绝和超时无法与房间区分；匹配策略也没有可挂的主键。架构已列 `POST /invites`、`accept` / `reject` / `cancel` 与事件 `invite.expire`，缺表与状态机。

## 4. Goals

- 一张 `invites` 表表达限时握手；权威状态在行上，`expires_at` 由服务端计算。
- 创建时问 `presence`：双方都在该 `article_id` 上；accept 时再问一次。不把在线状态抄进表。
- `reject` 可带一句回传，落在该行并推给邀请人；不是 IM。
- 仅 `accepted` 调用 `room.create`；`rooms.invite_id` 唯一回指。拒绝 / 超时 / 取消不写 `matches`。
- 角色快照与 `intent=same_map` 足够让后续 `match` 展示本局位置；本期不实现第二套匹配引擎。

## 5. Out of Scope

- 实现 `presence`（心跳、频道、离场）。本模块只调「是否在这篇上」端口。
- 实现 `room` / `map` / `match`（房内消息、房间倒计时、战绩、纪要）。只定义 accept 之后的调用契约。
- 跨域自动配对、带着问题找答主、同问者队列、关注 / 兴趣向量。
- 永久私信、拒绝后的来回对话、把 `reject_message` 写入房间或战绩正文。
- 多人邀请、队列抢答、好友关系表。
- 用邀请表存聊天、房间时长、在场人数。
- 未登录邀请；把冷启动未入驻名片当 `to_user_id`（没有 `users` 行，也不在场）。

## 6. Proposal

### 6.1 Design Rule

**邀请是一张地图上的限时握手。候选人来自在场；同意才建房；匹配决定就在这一行里。**

```text
两套时钟（不要写成一个数）：
  握手 TTL     invites.expires_at     默认 30s    到期 → expired，不建房
  房间时长     rooms.ends_at          10–15 min   属 room，本模块不写

谁出现在可邀请列表：
  presence（打开该文的已登录用户）
  GET /invites 是握手收件箱，不是候选人列表

创建
  identity：from = 当前 session，且 active
  article：文章存在，能当地图
  presence：from、to 都在该 article_id
  禁止 to == from
  同一 (article_id, from, to) 同时只能一条 pending
  快照 from_role / to_role；intent = same_map
  INSERT pending，expires_at = now() + TTL
  延迟事件 invite.expire；realtime 推 user:{to}

拒绝 / 取消 / 超时
  终态，不调用 room，不写 match
  reject 可写 reject_message，只给 from 看

接受
  CAS：pending 且 expires_at > now()
  presence 再确认双方仍在这篇
  status = accepted
  room.create({ invite_id, article_id, 双方, 角色快照 })
  取消同一篇文章上这两人之间另一条 pending（互邀）
  推双方切到 room:{id}
```

互补：列表标明答主 / 同读，用户自己点。系统不替用户判死。`intent` 先只放 `same_map`，避免假装已有第二套引擎。

### 6.2 Syntax / API / Interface

| 方法 | 路径 | 谁可调 | 行为 |
|---|---|---|---|
| `POST` | `/invites` | 已登录 | 对某篇上的在场用户发出握手 |
| `GET` | `/invites` | 已登录 | 自己的收件箱 / 发件箱（握手，不是在场列表） |
| `GET` | `/invites/{id}` | 参与双方 | 含倒计时与拒绝回传；外人 404 |
| `POST` | `/invites/{id}/accept` | 仅 `to_user_id` | CAS 接受 → 建房 |
| `POST` | `/invites/{id}/reject` | 仅 `to_user_id` | CAS 拒绝；body 可带 `message` |
| `POST` | `/invites/{id}/cancel` | 仅 `from_user_id` | CAS 取消；无回传 |

accept / reject / cancel 走 HTTP，不走 WS 状态机。WS 只推通知。候选人列表由 `presence` 在文章详情上提供，本模块不提供「可邀请谁」。

包边界：`web.api.invites` 只做 HTTP；用例在 `server.invite`。`web` 不直连表。本模块 **读** identity（当前用户）、article（地图是否存在）、presence 端口；**写** 本表；accept 成功后 **调用** `room` 端口。不发 socket；不写 `matches`。

```text
VERSO_INVITE_TTL_SEC                 # 握手秒数，建议 30
VERSO_INVITE_REJECT_MESSAGE_MAX      # 回传最大字数，建议 80
```

房间时长配置属于 `room`，禁止在本模块再读一套。

端口（对方未实现时用假实现，契约如下）：

```text
PresenceReader.is_present(user_id, article_id) -> bool

RoomGateway.create_from_invite(invite) -> { room_id }
  # 传入整行握手（含 article_id、双方、角色快照）
  # 本模块不传聊天、不传房间时长
```

### 6.3 Examples as Specification

**当前：** 无邀请表、无握手。

**提案主路径（规范，不是示意）：**

```text
A、B 已登录且 active，均打开 article X（presence 为真）

POST /invites
  { "article_id": X, "to_user_id": B }
  from_user_id = session.user_id = A
  PresenceReader.is_present(A, X) 且 is_present(B, X)
  角色快照见下
  INSERT invites status=pending
         expires_at = now() + VERSO_INVITE_TTL_SEC
  enqueue invite.expire { invite_id } 于 expires_at
  realtime → user:{B}  「新邀请」
```

**角色快照（创建时写死，之后不改）：**

```text
若 user_id == articles.author_user_id → author
否则：
  发起人 from → reader
  被邀请人 to → co_reader
```

作者邀同读：`from_role=author, to_role=co_reader`。同读邀作者：`from_role=reader, to_role=author`。两个非作者：`reader` / `co_reader`。禁止用昵称、禁止用 identity 的账号角色。

**`GET /invites/{id}`（参与者）：**

```json
{
  "id": "uuid",
  "article_id": "uuid",
  "from_user_id": "uuid",
  "to_user_id": "uuid",
  "from_role": "reader",
  "to_role": "author",
  "intent": "same_map",
  "status": "pending",
  "expires_at": "2026-09-12T04:00:30Z",
  "reject_message": null,
  "responded_at": null,
  "created_at": "2026-09-12T04:00:00Z"
}
```

不返回知乎 token、不返回房间聊天。`status=accepted` 时 HTTP 层可附带 `room_id`（来自 `RoomGateway` 的返回值，**不是**本表列）。

**拒绝（可带回传）：**

```text
POST /invites/{id}/reject
  { "message": "这会儿不方便" }     # 可省略或 ""

仍 pending 且 expires_at > now() 且调用方 == to
  status = rejected
  reject_message = 去掉首尾空白；空则 NULL
  超长 → 400，不改行
  responded_at = now()
  realtime → user:{from}  「已拒绝」+ 同一句
```

邀请人未在线：行上仍有 `reject_message`，之后 `GET` 能看见。双方都不能再对这句回复。超时、取消 **不写** `reject_message`。

**接受 → 建房：**

```text
POST /invites/{id}/accept
  调用方 == to
  UPDATE … SET status='accepted', responded_at=now()
    WHERE id=? AND status='pending' AND expires_at > now()
  0 行 → 冲突（已过期 / 已终态），不建房
  PresenceReader 双方仍在该文；否则回滚/保持不建房，提示离场
  RoomGateway.create_from_invite(invite) → room_id
  将同一 article_id 上、双方集合相同的其他 pending 置 cancelled
  realtime 双方 → 进入 room:{room_id}
```

**超时：**

```text
worker 消费 invite.expire
  UPDATE … SET status='expired'
    WHERE id=? AND status='pending' AND expires_at <= now()
  已终态则 no-op
  realtime 通知双方（仍 pending 才通知）
```

读路径若发现 `pending` 且 `expires_at <= now()`，按 `expired` 处理（可顺便 UPDATE）。不信任只靠 worker。

**等价形态：** 同一 `(article_id, from, to)` 在上一条已终态后再次 `POST /invites` → **新行**，新 `id`，新倒计时。不复活旧行。

**无效：** 未登录；`to == from`；对方不在这篇上；文章不存在；对非参与者 `GET`；对 `expired` 再 accept；把候选人做成 `GET /invites`。均失败或不得建房。

### 6.4 Boundary Cases

| 情况 | 行为 |
|---|---|
| 未登录 | 不能 `POST` / `accept` / `reject` / `cancel` |
| `to` 不在该文在场 | 创建失败并提示离场；不写行 |
| 创建后、accept 前对方离场 | pending 可继续到超时；accept 时再检，失败则不建房 |
| 冷启动未入驻作者 | 不是 `users` 行，不在 presence，不能当 `to` |
| 同一方向已有 pending | 创建冲突，不插第二行 |
| A→B 与 B→A 同时 pending | 允许两行；谁先 accept 谁建房，另一条 cancelled |
| 拒绝不带 message | `rejected`，`reject_message` NULL，仍通知邀请人 |
| 对已 `rejected` 再 reject | 409；不覆盖 `reject_message` |
| 发起人 cancel | `cancelled`；`reject_message` 保持 NULL |
| 被邀请人 cancel / 发起人 reject | 403 |
| 握手 TTL 与房间时长 | 只写 `expires_at`；不把 10–15 分钟写进本表 |
| 接受成功 | 只调 `room`；**不** insert `matches` |
| 拒绝 / 超时 / 取消 | 不调 `room`，不写战绩 |
| `banned` 掉了 session | 无法再 accept；行留 pending 直至过期 |
| 互为作者判定 | 只认 `articles.author_user_id`，不认昵称 |

## 7. Error Handling

| 条件 | 行为 |
|---|---|
| 未认证 | 未认证，不写库 |
| 文章不存在 | 404，不写邀请 |
| 自己邀自己 | 400 |
| 对方不在场 / accept 时已离场 | 失败并提示；accept 不建房 |
| `message` 超过上限 | 400，状态不变 |
| CAS 未改到 pending | 409（已处理或已过期） |
| `RoomGateway` 失败 | 邀请不得停在「已接受但无房」：事务内失败则仍 pending 或明确错误并告警；**禁止** `accepted` 且无 `room_id` 可查。实现须与 `room` 同事务或可补偿；细节由 feat 收口，规格要求可观测、可重试，不能静默丢房 |
| 非参与者读邀请 | 404（不泄露存在） |
| 密钥 / 知乎 token 进响应 | 视为缺陷 |

## 8. Compatibility

加法。依赖 `users`（#10）与 `articles`（#12）已存在。实现顺序：两表迁移合入 → 本模块迁移 → presence 端口可假实现 → 再接真在场。当前无邀请数据。回滚：停 HTTP 与 `invite.expire`；已写入行可留。`intent` / `map_role` 枚举只加值、不改列名。

## 9. Alternatives Considered

### 9.1 邀请只放 Redis，不建表

握手要能拒绝回传、accept CAS、房间外键、演示后仍能 `GET`。纯 TTL key 做不到回传落库，也没有稳定 `id` 给 `rooms.invite_id`。Redis 只负责叫醒过期 worker。

### 9.2 发出邀请就建房，接受后「解锁」

产品：邀请不是房间；拒绝或超时不建房。先建房会让频道、地图、开局话题在对方拒绝时已经存在，和销毁语义拧在一起。

### 9.3 拒绝 / 超时也写一条战绩（不成局）

架构把 `matches` 挂在关房上；验收是「结束后列表出现该局」。不成局的握手用 `invites.status` 查询。需要「拒绝对局历史」时另开 `match` 提案，不从邀请模块插空战绩。

### 9.4 把 A↔B 做成无向唯一，禁止互邀

方向决定谁能 accept、拒绝回传给谁。无向唯一会抹掉发起人。互邀用「先 accept 者建房、另一条取消」即可。

### 9.5 拒绝回传做成短会话

决策四：实时消息默认销毁，不做永久 IM。一句回传挂在握手行上已经够用。再回一句就是私信。

### 9.6 现在建匹配引擎表 / `intent=complement`

MVP 只落地同地图邀请。互补是叙事和角色展示。候选人仍是这篇上的在场用户。日后问题路由或跨域配对改的是**候选从哪来**，握手表加枚举值或可空外键，不先造第二套状态机。

## 10. Testing Strategy

| 用例 | 方法 |
|---|---|
| 双方在场则可创建 pending，`expires_at` 为 now+TTL | 单测 mock PresenceReader |
| 对方不在场 / 自邀 / 重复 pending：不插行 | 单测 |
| 角色：作者、同读邀作者、两非作者 | 夹具 `author_user_id` |
| reject 带 / 不带 message；超长不改状态 | HTTP 契约 |
| 过期后 accept 失败；worker 把 pending 收成 expired | 时间夹具 |
| accept 成功调用一次 RoomGateway，拒绝 / 超时调用零次 | mock 计数 |
| 互邀先 accept 建一房，另一 pending 变 cancelled | 单测 |
| 非参与者 GET 为 404；响应无密钥 | 契约夹具 |
| `GET /invites` 不含未邀请的在场用户 | 与 presence 列表对照 |

## 11. Summary of Changes

| 区域 | 变更 |
|---|---|
| 本文 | 冻结 invite 契约；后续 `feat` 按此实现 |
| 以后才写的代码 | 迁移 `invites`；`InviteService`；HTTP；`invite.expire`；调用 presence / room 端口 |
| 不改 | identity 协议、`articles` 表、前端仓库（前端按本契约接弹窗与倒计时） |
| 不建 | `invite_messages` 会话表、匹配引擎表、邀请—在场中间表、本模块内的 `rooms` / `matches` |

实现顺序：枚举与迁移 → 创建 / 过期 CAS → reject 回传 → accept 调 room 假实现 → 再接真 presence / room。缺在场端口不要假装全员可邀。

---

## Data model

Postgres 只加 **一张** `invites`。不建消息表、不建匹配候选表。房间用外键回指本表主键，本迁移 **不** `CREATE rooms`。

```sql
CREATE TYPE invite_status AS ENUM (
    'pending', 'accepted', 'rejected', 'expired', 'cancelled'
);
CREATE TYPE match_intent AS ENUM ('same_map');
CREATE TYPE map_role AS ENUM ('reader', 'author', 'co_reader');

CREATE TABLE invites (
    id               UUID PRIMARY KEY,
    article_id       UUID NOT NULL REFERENCES articles (id),
    from_user_id     UUID NOT NULL REFERENCES users (id),
    to_user_id       UUID NOT NULL REFERENCES users (id),
    from_role        map_role NOT NULL,
    to_role          map_role NOT NULL,
    intent           match_intent NOT NULL DEFAULT 'same_map',
    status           invite_status NOT NULL DEFAULT 'pending',
    expires_at       TIMESTAMPTZ NOT NULL,
    reject_message   TEXT,
    responded_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT invites_not_self CHECK (from_user_id <> to_user_id),
    CONSTRAINT invites_reject_message_only
        CHECK (reject_message IS NULL OR status = 'rejected'),
    CONSTRAINT invites_expires_after_create
        CHECK (expires_at > created_at)
);

CREATE UNIQUE INDEX invites_pending_pair_idx
    ON invites (article_id, from_user_id, to_user_id)
    WHERE status = 'pending';

CREATE INDEX invites_inbox_idx
    ON invites (to_user_id, status, expires_at);
CREATE INDEX invites_outbox_idx
    ON invites (from_user_id, status, created_at DESC);
CREATE INDEX invites_article_pending_idx
    ON invites (article_id)
    WHERE status = 'pending';
```

| 列 | 含义 |
|---|---|
| `id` | 握手主键；`rooms.invite_id` 回指它 |
| `article_id` | 地图；同地图匹配的桥。本期 NOT NULL |
| `from_user_id` / `to_user_id` | 发起人 / 被邀请人 = `users.id` |
| `from_role` / `to_role` | 这篇上的位置快照，给日后战绩用 |
| `intent` | 本期恒 `same_map`；日后可加枚举值，不改列 |
| `status` | `pending` → 四个终态之一，不回流 |
| `expires_at` | 握手截止；与房间 `ends_at` 无关 |
| `reject_message` | 仅 `rejected` 可有；一句，不是会话 |
| `responded_at` | accept / reject / cancel 的时刻；超时可由 worker 写或留空 |

```text
invite:expire:{invite_id}     延迟到 expires_at     worker 收口 pending
```

不把 `status` 复制进 Redis。不建：`invite_participants`、`invite_messages`、`metadata JSONB`、`room_id` 列（避免与 `rooms` 循环外键）。

**给其他模块的挂钩（本期只保证这些，不实现对方逻辑）：**

| 挂钩 | 谁写 | 谁读 |
|---|---|---|
| `invites.id` | invite | `rooms.invite_id` UNIQUE NOT NULL（room 提案建表时 FK） |
| `article_id` + 双方 + 角色快照 | invite（创建时） | room 开局；match 关房后抄到战绩 |
| `intent` | invite | 日后 feed / 统计；本期只有 same_map |
| 在场 | presence | invite 只在创建与 accept 时询问 |
| 战绩行 | match（关房） | 用户战绩列表；**不是**本模块在 reject 时写 |

后续 `room` 提案必须：`CREATE TABLE rooms (…, invite_id UUID NOT NULL UNIQUE REFERENCES invites (id), …)`，无消息列。后续 `match` 从关房快照写，读取邀请上的角色，不反向改邀请状态。

---

## Architecture

```text
web  ──POST /invites──► server.invite ──► realtime user:{to}
                         └── invite.expire ──► mq ──► worker

web  ──reject──► server.invite ──► realtime user:{from}   （可选 reject_message）
web  ──cancel──► server.invite ──► realtime user:{to}

web  ──accept──► server.invite
                    ├── PresenceReader（再确认）
                    └── RoomGateway.create_from_invite
                              └── realtime room:{id}

关房（room / match，非本期）──► matches；不回写 invites.status
```

| 模块 | invite 提供 / 依赖 |
|---|---|
| `identity` | `from` / `to` = `users.id`；仅 `active` 可发可应 |
| `article` | FK `articles.id`；角色靠 `author_user_id` |
| `presence` | 创建与 accept 时 `is_present`；本模块不写在场、不订心跳 |
| `room` | 仅 accepted 调用；用 `invite_id` 回指 |
| `match` | 关房后读角色快照；本模块不 insert 战绩 |
| `web` | 上表 HTTP；WS 只推 |
| `worker` | 消费 `invite.expire` |

回滚：关掉邀请路由与过期消费者即回到「看得见人但不能握手」。已写入行可留。

## Open Questions

1. 握手默认 30 秒是否偏短。只改 `VERSO_INVITE_TTL_SEC`，不改表。演示脚本可临时加大。
2. 互邀是否改为「有反向 pending 则禁止再发」。本期允许两行、先 accept 者赢；若产品觉得吵，再收紧唯一约束。
3. 拒绝后同一对在同一篇上是否要冷却。本期终态后可立即再邀。
4. `RoomGateway` 与邀请 CAS 的事务边界（同库事务 vs outbox）。规格要求禁止「accepted 且无房」；实现提案里二选一。
5. 被邀请人 pending 期间离场，要不要由 presence 事件自动 `expired`。本期不订该事件，靠 accept 再检与 TTL，以免两模块抢状态机。
