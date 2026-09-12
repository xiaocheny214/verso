# Proposal: 限时私人房间（消息只进 Redis，开房即占线）

本提案对应 [#18](https://github.com/xiaocheny214/verso/issues/18)。产品以 [#1](https://github.com/xiaocheny214/verso/issues/1) / [`product-proposal.md`](product-proposal.md) 为准；分层以 [#5](https://github.com/xiaocheny214/verso/issues/5) / [`architecture.md`](architecture.md) 为准；用户主键以 [#10](https://github.com/xiaocheny214/verso/issues/10) / [`identity.md`](identity.md) 为准；文章主键以 [#12](https://github.com/xiaocheny214/verso/issues/12) / [`article.md`](article.md) 为准；邀请以 [#14](https://github.com/xiaocheny214/verso/issues/14) / [`invite.md`](invite.md) 为准；在场以 [#16](https://github.com/xiaocheny214/verso/issues/16) / [`presence.md`](presence.md) 为准。本文只定 room 这一个增量，不夹带实现代码，不实现 `map` / `match` / `llm_pipeline`。

## 1. Summary

给 Verso 加上限时房间：`invite` **只有 `accepted` 才调用本模块建房**。房间是这一局的容器，不是邀请，也不是战绩。Postgres 一行只记地图、邀请人 / 被邀请人、访问属性、时钟和开关；**聊天一行都不进库**。创建成功立刻 `framework.mq` 预约 `room.close`（Redis 延迟集合，score=销毁时刻）。**可以提前离开**；**双方都离开则立刻销毁**，不必等倒计时。到期走同一条关房：快照热消息、丢 Redis 信道、叫 `match` 写战绩、按需叫 `map` 做纪要。

本期房间是 **私人双人局**（`access=private`）：只有邀请行上的两人能进、能说。同文其他人不能挤进来。成员在房 `open` 期间 **不能被邀、也不能发邀**——文下第三人看不见可邀对象，硬闸是 `RoomReader.is_in_open_room`。一侧提前离开也不解锁：要等这间房 `closed`（对话结束并销毁）才能再接邀请。

匹配决定已经在邀请行上（`intent` + 角色快照）。本模块抄一份冻结快照，不另做配对引擎，不在建房时 INSERT `matches`。同文可临时进入的开放局（`open_map`）是 incoming，本期不实现；消息体仍按「一条发言一个人」写，以免日后改 Redis 形状。

## 2. User Stories / Motivation

- 双方在同一篇文章上握手成功：立刻进入绑着该文的**私人**房间，看见地图、倒计时，能发文字。聊不了那么久就点离开，不必坐满 15 分钟。
- 一人提前离开：该侧立刻不能发言；另一人可待到点或也离开。**两人都离开：房间立刻销毁**（关信道、丢热消息），不等闹钟。
- A、B 在房期间，同文的 C **不能邀请他们**，他们也 **收不到、发不出** 新邀请。A 先走、B 还在聊：A 同样不能接新邀请，直到这间房关干净。
- 同文的 C 不能 `room.join` 进这间私人房。开放局（别人临时进来）本期不做。
- 话只在这一局里；刷新还能接上热消息。关房后不能再发，也不能在站内翻到逐字稿。
- 开局话题 / 拉回地图 / 局末纪要由 `map` 在这间房上做事；房间只保证 `article_id`、热消息快照和关房钩子。

共同需要：限时、可早退、双方走了就拆掉的私人容器；在局里等于占线，拆掉才能再握手。

## 3. Current Workaround

`server.room` 只有占位。`invite` 已规定 `RoomGateway.create_from_invite`，实现只能假装进房。没有 `rooms` 行则没有 `invite_id` 回指、没有 `ends_at`、没有 `room:{id}` 信道。把聊天写入邀请表或 Postgres 会变成永久私信，和决策四拧着。

## 4. Goals

- 仅从已接受邀请建房；禁止 `POST /rooms`。一人同时最多一个 `open` 房。
- `access=private`：仅 `from_user_id` / `to_user_id` 是成员；非成员 join/GET/send 为 404。
- 成员在 `status=open` 期间 `is_in_open_room=true`（**含已 leave 但房未关**）。invite 创建与 accept 必须问这一口，为真则失败。进房 `PresenceWriter.leave`，让文下列表先空掉，但不能只靠名单。
- 显式 `POST .../leave` 可提前离场。两侧都有 `left_at` → 立刻关房 `both_left`。一侧离开不关房、不解除占线。
- 一张 `rooms` 表：无消息列。`invite_id` UNIQUE NOT NULL。
- 聊天只在 Redis LIST；关房快照后删除。不把正文抄进 `rooms` / `invites` / `matches`。
- 创建时写下 `starts_at` / `ends_at`，并延迟投递 `room.close`。worker 与读/写路径都要能就地关房，不信任只靠延迟任务。
- 关房只调端口：`MatchGateway` 写战绩；`MapGateway` 开局话题 / 纪要。本模块不调 LLM、不 INSERT 战绩行。

## 5. Out of Scope

- 实现 `map` 生成文案、`llm_pipeline`、拉回地图按钮。只定 `MapGateway` / `MapReader`。
- 实现 `matches` / `match_participants`、纪要保存勾选 UI。只定 `MatchGateway.on_room_closed`。
- 开放局 `access=open_map`：同文在场者临时挤进已有房间。本期枚举只含 `private`；不实现客人 join、不建 `room_members`。
- 语音 / WebRTC、永久私信、完整 IM。
- 把 leave 做成关页 sendBeacon 默认离席（闪断会拆局）。
- 发出邀请就建房；拒绝 / 超时 / 取消建房。
- 把聊天落 Postgres、对象存储或知乎。
- 跨房间广播；全站一条 WS。
- 改 `invites.status`（关房不回写邀请）。
- 养成、装扮、房间主题皮肤。

## 6. Proposal

### 6.1 Design Rule

**房间是双方同意之后才存在的私人限时容器。行上只有地图、人和访问属性；话只在 Redis；可提前走；两人都走了立刻拆；拆掉之前占线。**

```text
两套时钟（继续分开，不要合成一个数）：
  握手 TTL     invites.expires_at     默认 30s     属 invite
  房间时长     rooms.ends_at          默认 15min   属 room；可早退

访问属性（本期只实现第一档）
  private    仅邀请双方。同文其他人不能 join。Demo / MVP 只用这个
  open_map   incoming：同文 presence.list 可临时进房。本期 ENUM 不收此值

建房入口只有一个
  RoomGateway.create_from_invite(accepted invite)
  无 POST /rooms
  匹配不在这里重做：抄 invite 的 article / 双方 / 角色 / intent
  access = private（写死，不接受客户端选开放局）

创建
  任一参与者已有 status=open 的房 → 失败，不插行
  INSERT open
    access=private
    starts_at = now()
    ends_at   = now() + VERSO_ROOM_DURATION_SEC
  mq.delay room.close { room_id }  at ends_at
    Redis 形态：延迟 ZSET，score=unix(ends_at)，不是 keyspace 通知
  PresenceWriter.leave(from)；leave(to)    # 文下列表立刻空
  MapGateway.on_open(room)                 # 不得阻塞在 LLM HTTP 上
  推双方：去房间页
  此后 is_in_open_room(A)=true、is_in_open_room(B)=true

占线（房 open 的全部时间，含一侧已 leave）
  C 对 A 或 B：POST /invites → 失败（在房内，不能被邀）
  A 或 B：POST /invites → 失败（在房内，不能发邀）
  A 或 B：accept 别人 pending → 失败
  硬闸是 RoomReader.is_in_open_room，不是「现在还在不在文下名单」
  解锁条件：status=closed（到期或双方离开，房间已销毁）
  一侧提前离开 ≠ 解锁

进房页（前端编排）
  WS room.join { room_id }     # 必须是成员；订 room:{id}，幂等
  GET /rooms/{id}
  倒计时用 ends_at 与 server_now，不另做服务端 tick 广播
  同文 C 对这间房 join / GET → 404

发言
  WS room.send { room_id, body }
  校验：open、未 leave、now < ends_at、是成员
  RPUSH room:messages:{id}；LTRIM 上限
  推 room:{id} 一条 room.message
  禁止写 Postgres

提前离席
  POST /rooms/{id}/leave       # 显式离开；关页 / 断线 ≠ leave
  记下该侧 left_at；该侧不能再 send
  一侧离开：另一侧继续到 ends_at；两人仍占线
  两侧都有 left_at → 立刻走关房（both_left），不必等闹钟

关房（到期 / 双方离开 / 读写下发现已过 ends_at，同一条）
  CAS open → closed
  已 closed → no-op
  LRANGE 热消息 → SET room:snapshot:{id} EX TTL
  DEL room:messages:{id}
  退订 room:{id}；拒绝再 send
  MatchGateway.on_room_closed(room, snapshot_key)
  推 room.closed
  is_in_open_room(A/B)=false     # 现在才能再被邀
  不回写 invites

销毁语义
  实时信道关了 = 不能再发
  热 LIST 删了 = 站内没有逐字稿
  快照只给 match / map 用一次，靠 TTL 消失
  战绩条默认有；纪要各人偏好，不进本表
  行仍在 Postgres，给战绩回指；「销毁」指信道和热消息，不是 DELETE 行
```

不要做：先 INSERT `matches` 再开房；把 LIST 的 JSON 当可重建缓存以外的权威去落库；用房间 TTL 代替 `ends_at` 行字段；只靠 presence 名单当占线；让同文第三人 join 私人房。

### 6.2 Syntax / API / Interface

| 方法 | 路径 | 谁可调 | 行为 |
|---|---|---|---|
| `GET` | `/rooms/current` | 已登录 | 自己当前 `open` 房；没有则 204。刷新重连用 |
| `GET` | `/rooms/{id}` | 仅成员 | 元数据、倒计时、地图视图、`open` 时的热消息 |
| `POST` | `/rooms/{id}/leave` | 仅成员 | 提前离席；双方都离则立刻关房。一侧离开不解除占线 |

没有 `POST /rooms`。accept 成功后的 `room_id` 来自邀请用例返回值，不是本表之外的第二条创建口。

WS（同一条业务连接）只收：

```text
{ "type": "room.join", "room_id": "<uuid>" }
{ "type": "room.send", "room_id": "<uuid>", "body": "<text>" }
```

`room.join`：必须是 **private 成员**（from / to）；`open` 则订 `room:{id}`；`closed` 可回当前状态但不订、不复活消息。同文非成员 join = 404，不进频道。重连必走 join。  
`room.send`：见 6.1；空 body / 超长 → 错误帧或 400 等价，不入 LIST。已 leave 的一侧不能 send。  
断线 ≠ leave，不退成员，不关房，也不解除占线。

服务端向 `room:{id}` 推：

```text
{ "type": "room.message", "room_id": "<uuid>", "message": { ... } }
{ "type": "room.map", "room_id": "<uuid>", "talking_points": [ ... ] }   # 开局话题就绪
{ "type": "room.closed", "room_id": "<uuid>", "close_reason": "expired"|"both_left" }
```

不推每秒倒计时。不把快照或密钥推到频道。

包边界：`web.api.rooms` 与 WS 适配器只做协议；用例在 `server.room`。`web` 不直连表或 Redis key。本模块 **读** identity（当前用户）、article（地图存在）、invite 行（只在 gateway 入参里）；**写** `rooms` + Redis 消息 / 快照；**调** `framework.realtime`、`framework.mq`、`PresenceWriter`、`MapGateway`、`MatchGateway`。不发知乎请求，不调 LLM。

```text
VERSO_ROOM_DURATION_SEC          # 房间时长，建议 900
VERSO_ROOM_MESSAGE_MAX           # 单条字数，建议 500
VERSO_ROOM_MESSAGE_LIST_MAX      # LIST 保留条数，建议 500；超出 LTRIM 最旧
VERSO_ROOM_SNAPSHOT_TTL_SEC      # 关房快照 TTL，建议 3600
```

端口（对方未实现时用假实现）：

```text
RoomGateway.create_from_invite(invite) -> { room_id }
  # 仅 invite 在 accepted CAS 成功后调用
  # 入参是整行握手；本模块不读「如何握手」

RoomReader.current_open(user_id) -> room_id|None
  # status=open 且该用户是 from 或 to（不论 left_at）
RoomReader.is_member(room_id, user_id) -> bool
RoomReader.is_in_open_room(user_id) -> bool
  # current_open 非空即为真。invite 创建与 accept 必问
  # 假实现可恒 false；接真房间后必须接真，否则占线可被绕过

PresenceWriter.leave(user_id) -> None          # 已有；进房必调

MapReader.for_room(room) -> { title, summary, canonical_url, talking_points }
MapGateway.on_open(room) -> None               # 模板可同步；LLM 必须异步，失败则 talking_points=[]
MapGateway 不在本模块里调模型

MatchGateway.on_room_closed(room, snapshot_key) -> None
  # 战绩行、是否 enqueue map.summary，由 match 读 users.summary_* 决定
  # 假实现：no-op；快照仍靠 TTL 消失
```

`invite` 不传房间时长、不传聊天、不传 `access`。实现 invite feat 时：创建与 accept 都要 `not is_in_open_room(from)` 且 `not is_in_open_room(to)`。`match` 不在建房时出现。

### 6.3 Examples as Specification

**当前：** 无 `rooms` 表。accept 只能调假 gateway。

**提案主路径（规范，不是示意）：**

```text
A 邀 B，article X，invite I 已 CAS → accepted
  from_user_id=A  from_role=reader
  to_user_id=B    to_role=author
  intent=same_map

RoomGateway.create_from_invite(I)
  无 A/B 的 open 房
  INSERT rooms
    invite_id=I UNIQUE
    article_id=X
    from_user_id=A  to_user_id=B
    from_role / to_role / intent 从 I 抄，之后不改
    access=private
    status=open
    starts_at=now()
    ends_at=now()+900s
    from_left_at=NULL  to_left_at=NULL
  mq.delay room.close { room_id=R } at ends_at
  PresenceWriter.leave(A)；leave(B)
  MapGateway.on_open(R)          # 不 await 知乎 / LLM
  realtime 双方：去 R
  返回 { room_id: R }

B 前端进房间页
  WS { type: room.join, room_id: R }   # 订 room:R
  GET /rooms/R → 200（见下）
```

**`GET /rooms/{id}`（成员，open）：**

```json
{
  "id": "uuid",
  "invite_id": "uuid",
  "article_id": "uuid",
  "status": "open",
  "access": "private",
  "intent": "same_map",
  "starts_at": "2026-09-12T04:01:00Z",
  "ends_at": "2026-09-12T04:16:00Z",
  "closed_at": null,
  "close_reason": null,
  "server_now": "2026-09-12T04:01:05Z",
  "members": [
    {
      "user_id": "uuid-A",
      "role": "reader",
      "side": "from",
      "display_name": "…",
      "avatar_url": "https://…",
      "left_at": null,
      "self": false
    },
    {
      "user_id": "uuid-B",
      "role": "author",
      "side": "to",
      "display_name": "…",
      "avatar_url": "https://…",
      "left_at": null,
      "self": true
    }
  ],
  "map": {
    "article_id": "uuid",
    "title": "…",
    "summary": "…",
    "canonical_url": "https://…",
    "talking_points": []
  },
  "messages": []
}
```

`side`：`from` = 邀请人，`to` = 被邀请人。`role` 是邀请创建时的地图位置，不是账号角色。`map.*` 来自 `MapReader`（文章字段 + 可能仍空的开局话题）；**不**把 title 复制进 `rooms`。`messages` 仅 `open` 时从 LIST 读；`closed` 恒 `[]`。不返回 token、sid、快照 key、知乎凭证。

开局话题稍后就绪：推 `room.map`；再 GET 则 `talking_points` 有值。额度紧时模板三句也走同一字段，房间不分支。

**发言：**

```text
WS { type: room.send, room_id: R, body: "这段摘要里的第二句…" }
  session 是 A 或 B
  R.open 且该侧 left_at IS NULL 且 now < ends_at
  RPUSH room:messages:{R}  {
    "id": "<uuid>",
    "room_id": R,
    "from_user_id": A,
    "body": "…",
    "created_at": "…"
  }
  LTRIM 只留最近 LIST_MAX
  推 room.message 给 room:{R}
  0 行 Postgres
```

**一侧提前离开（房未毁，仍占线）：**

```text
POST /rooms/R/leave     Cookie = A
  from_left_at = now()
  A 再 send → 拒绝
  B 仍可 send
  status 仍为 open
  is_in_open_room(A)=true
  is_in_open_room(B)=true
  GET /rooms/current：A 与 B 都仍是 R
  C POST /invites { to: A } → 失败（房间尚未销毁）
  A POST /invites { to: C } → 失败
```

**双方离开 → 立刻销毁：**

```text
B 也 POST leave
  to_left_at = now()
  走关房 close_reason=both_left
  不必等到 ends_at；已预约的 room.close 到期后 CAS 0 行，no-op
  is_in_open_room(A)=false
  is_in_open_room(B)=false
  此后 C 才能邀 A 或 B
```

**同文第三人进私人房（无效）：**

```text
C 与 A、B 同在 article X 的在场名单（A、B 进房后应已不在名单）
WS { type: room.join, room_id: R }   Cookie=C
  is_member(R,C)=false → 404，不订频道，LIST 不出现 C
GET /rooms/R Cookie=C → 404
```

**占线挡住邀请：**

```text
R 仍 open
C 对 A：POST /invites → Presence 可能已不含 A；即便 C 手里有旧 id
  RoomReader.is_in_open_room(A)=true → 创建失败，不插 pending
A 对 C：同样失败
I2 是进房前留下的 pending（to=A）
  A accept I2 → is_in_open_room(A)=true → 失败，不建第二房
R closed 之后，上述创建 / accept 才按 [#14](https://github.com/xiaocheny214/verso/issues/14) 正常走
```

**到期：**

```text
now >= ends_at
worker 消费 room.close { R }
  或 GET / send / join 发现过期
  CAS status=open → closed
       closed_at=now()
       close_reason=expired
  snap = LRANGE room:messages:{R} 0 -1
  SET room:snapshot:{R} snap EX SNAPSHOT_TTL
  DEL room:messages:{R}
  MatchGateway.on_room_closed(R, "room:snapshot:{R}")
  推 room.closed
  之后 send → 拒绝；GET messages=[]
```

**等价形态：** 同一 `invite_id` 再调 `create_from_invite` → 冲突，不插第二行（UNIQUE）。延迟任务与读路径关房幂等。重复 `room.join` = 保证已订阅。

**无效：** 未登录 join/send；非成员 GET / join；对 `pending` 邀请建房；拒绝/超时的邀请建房；把消息 INSERT 进 `rooms`；HTTP 再开一套发言 POST 当主路径；关页 sendBeacon 当 leave；对 `open` 成员发邀请。均失败或不得写入。

### 6.4 Boundary Cases

| 情况 | 行为 |
|---|---|
| 未登录 | 不能 current / GET / leave / join / send |
| 非成员 GET / leave | 404，不泄露存在 |
| 邀请未 accepted | gateway 拒绝，无行 |
| 任一成员已有 open 房 | 建房失败；邀请侧不得留下「accepted 且无房」（沿用 [#14](https://github.com/xiaocheny214/verso/issues/14)） |
| 文章已删 | 不建房；已建的房仍能关，地图字段按当时 `MapReader` |
| WS 闪断 | 不 leave、不关房；重连 `room.join` + GET 热消息 |
| 关标签 / 杀进程 | **不**自动 leave、不解除占线；对方等到 `ends_at`。要提前结束须点离开 |
| 刷新 | `GET /rooms/current` → `room.join` → GET 详情 |
| 一人提前 leave | 只禁该侧发言；房仍 open；**两人仍占线**，不能被邀 |
| 两人 leave | `both_left`，立刻销毁信道与热消息；占线解除 |
| 到期时已有一人 leave | `expired`；关房后才能被邀 |
| 到期任务晚到，读路径已关 | worker CAS 0 行，禁止再快照空 LIST 覆盖已有快照 |
| 同文 C join 私人房 | 404 |
| C 邀请仍在 open 房的 A | 邀请创建失败；不插 pending |
| A 在 open 房内发邀请 / accept 另一条 | 失败 |
| 进房后去打开另一篇文章 | 文下已 leave；若再 `presence.join` 出现在名单，invite 仍因 `is_in_open_room` 拒绝 |
| 进房后文章详情仍挂着 | 必须已从文下集合消失；房内 ≠ 可邀请 |
| `banned` / 登出 | 该侧视为 leave；若因此双方都离则关房 |
| 开局话题失败 | 房间仍 open；`talking_points=[]`；不回滚建房 |
| LIST 超过上限 | 丢最旧热消息；不是落库归档 |
| 关房后 GET | 200，`status=closed`，`messages=[]` |
| 关房后 send | 拒绝 |
| 多人想挤进同一 `invite_id` | 不可能；`access=private` 一行两人 |
| 冷启动未入驻作者 | 进不了邀请，也就进不了房 |

## 7. Error Handling

| 条件 | 行为 |
|---|---|
| 未认证 | 未认证，不写库、不写 Redis |
| 非成员 | 404 |
| 对 open 成员发邀 / 成员在房内发邀或 accept | 邀请失败（invite 读 `is_in_open_room`）；不建第二房 |
| `status != active` | 与未登录相同；若在 open 房则强制该侧 leave |
| 对 closed 房 send / leave | send 拒绝；leave 幂等 204 |
| body 空或超过 `MESSAGE_MAX` | 不入 LIST |
| `create_from_invite` 时已有该 `invite_id` | 返回已有 `room_id` 或冲突——**禁止**第二行。推荐：已有则返回该行（幂等），便于邀请重试 |
| 已有另一 open 房 | 失败，不插行 |
| 延迟任务丢失 | GET/send/join 见 `ends_at <= now()` 就地关房；worker 可扫 `open AND ends_at<=now()` 补漏 |
| `MatchGateway` 失败 | 房必须保持 `closed`，快照仍在 TTL 内；记错误可重试。**禁止**为了重试 match 而把房打回 open |
| `MapGateway.on_open` 失败 | 忽略生成，不影响 CAS |
| 快照 / 推送 / GET 出现密钥 | 视为缺陷 |
| 发言路径打知乎 / LLM | 视为缺陷 |
| ORM 连接绑在 WS 上 | 视为缺陷 |

## 8. Compatibility

加法。依赖 `users`、`articles`、`invites` 已存在（至少迁移合入）。`map_role` / `match_intent` **复用** invite 的 ENUM，禁止再 `CREATE TYPE` 一份。实现顺序：invite 表 → 本模块迁移与假 Map/Match → presence `leave` 接真 → 再实现 map/match feat。当前无房间数据。回滚：停 join/send 与 `room.close` 消费者；已写入行可留；Redis 丢消息 = 该局无热聊天，Demo 可接受。消息 JSON 增加字段只加不改名。

## 9. Alternatives Considered

### 9.1 发出邀请就建房，接受后解锁发言

产品：双方同意才建房。先建房会让频道、地图、开局话题在拒绝时已经存在，销毁语义和「未成局不写战绩」一起烂掉。[#14](https://github.com/xiaocheny214/verso/issues/14) 已否。

### 9.2 聊天落 Postgres / `room_messages` 表

决策四：实时消息默认销毁。落库就是永久私信，战绩和纪要会变成「把原文再存一遍」。热路径用 Redis LIST；关房快照只给纪要管线短活。

### 9.3 用 key TTL 当关房，不写 `ends_at`

房间行要给 `matches.room_id` 回指，也要能查 `close_reason`。TTL 丢掉的是键，不是对局。闹钟用延迟 ZSET；权威时钟是行上的 `ends_at`。

### 9.4 本期就做开放局：同文在场者可临时进入

产品 [#1] 把多人对局标成 incoming；验收脚本是两账号一邀请。开放局要解决：客人要不要握手、战绩怎么记、客人走了关不关房、占线包不包括客人。先做会把私人双人主路径拖成第二套邀请。

本期冻结 `access=private`。日后若加 `open_map`：客人来自同一 `article_id` 的 `presence.list`，`room.join` 即临时进入，不新建邀请；客人 leave 不关房；原双方都 leave 或到期仍销毁；客人同样 `is_in_open_room`。那时再加 `room_members`，LIST 元素已是 `from_user_id`，不必改形状。

### 9.5 一侧 leave 就允许再被邀请

「双方都在才占线」会让先走的人立刻再开一局，同时这行 `open` 房还占着唯一槽，`create_from_invite` 会失败。产品要的是对话结束、房间销毁之后才接邀请。故占线绑 `status=open`，不绑 `left_at`。

### 9.6 建房时同时 INSERT `matches`

架构把战绩挂在关房。未到期就写战绩，拒绝路径之外会出现「未结束的对局卡片」，时长也不稳。匹配策略已经在 `invites.intent`；战绩等关房。

### 9.7 断线或关页即 leave / 即关房

刷新和闪断会把对局掐死。在场绑租约，是因为「还在不在这篇上」必须很快干净。房间绑的是这一局：显式离开或到期才结束。关页可以重连。

### 9.8 房间模块内直接调 LLM 写开局 / 纪要

[#5](https://github.com/xiaocheny214/verso/issues/5)：文案在 `map` / `llm_pipeline`。房间若直接调模型，发言路径和关房路径都会被额度拖死。只留 gateway。

### 9.9 只靠 `PresenceWriter.leave`，invite 不问房间

进房后若客户端再 `presence.join`，名单会把人露出来，第三人就能发邀请。占线必须是房间端口；名单空掉只是让 UI 干净。

### 9.10 HTTP `POST /rooms/{id}/messages` 当主路径

架构：WS 只收 `room.send`。HTTP 发言会与 WS 两套顺序。重连用 GET 拉 LIST，不另开短轮询主路径。

## 10. Testing Strategy

| 用例 | 方法 |
|---|---|
| `accepted` 邀请建一房；`pending` / `rejected` 建零房 | mock gateway 调用方 |
| 同一 `invite_id` 第二次 create 不插第二行 | 单测 UNIQUE / 幂等 |
| 成员已有 open 房则失败 | 单测 |
| 创建后 Redis 延迟集合能在 `ends_at` 取出该 `room_id` | 假 mq 断言 |
| 进房调用两次 `PresenceWriter.leave`，不写 presence 自己的 key | mock 计数 |
| send 只 RPUSH，rooms 行消息列不存在 / 无 INSERT 正文 | schema + SQL 计数 |
| 过 `ends_at` 后 send 失败；worker 与 GET 都能把 open 收成 closed | 时间夹具 |
| 双方 leave → `both_left` 且 LIST 被删、快照键存在；随后 `is_in_open_room` 为假 | 单测 Redis |
| 一侧 leave 另一侧仍可 send；leave 后两人 `is_in_open_room` 仍为真 | 单测 |
| 断线后键与行仍在、仍占线；再 join 能 GET 到热消息 | 单测 |
| 非成员 `room.join` / GET 为 404 | 契约 |
| `is_in_open_room` 为真时 invite 创建 / accept 失败（mock invite 夹具） | 与 invite 对照 |
| 关房后 GET `messages=[]`；假 MatchGateway 被调用一次 | mock 计数 |
| 非成员 GET 为 404；响应无密钥、无 snapshot key | 契约夹具 |
| 发言 / 心跳路径无知乎 / LLM mock 调用 | 调用计数 |
| 推送只到 `room:{id}` | realtime 假实现 |
| `on_open` 抛错仍保留 open 房 | 单测 |

## 11. Summary of Changes

| 区域 | 变更 |
|---|---|
| 本文 | 冻结 room 契约；后续 `feat` 按此实现 |
| 以后才写的代码 | 迁移 `rooms`；`RoomService`；HTTP + WS；延迟 `room.close`；调 presence / map / match 端口 |
| 不改 | identity 协议、`articles` / `invites` 表、前端仓库（前端按本契约进房、join、倒计时、leave） |
| 不建 | `room_messages`、`room_members`、`matches`（本迁移）、本模块内的 LLM 调用 |

实现顺序：枚举与 `rooms` 迁移 → `create_from_invite` + 延迟关房 → Redis LIST send/join → leave / 双方关房 → `is_in_open_room` 给 invite → 接真 `PresenceWriter` → 再开 `map` / `match` feat。缺邀请表不要建房。缺占线端口不要假装能发第二封邀请。

---

## Data model

Postgres 只加 **一张** `rooms`。**无消息列。** 不建 `room_messages`、不建 `room_members`。

```sql
CREATE TYPE room_status AS ENUM ('open', 'closed');
CREATE TYPE room_close_reason AS ENUM ('expired', 'both_left');
CREATE TYPE room_access AS ENUM ('private');

CREATE TABLE rooms (
    id               UUID PRIMARY KEY,
    invite_id        UUID NOT NULL UNIQUE REFERENCES invites (id),
    article_id       UUID NOT NULL REFERENCES articles (id),
    from_user_id     UUID NOT NULL REFERENCES users (id),
    to_user_id       UUID NOT NULL REFERENCES users (id),
    from_role        map_role NOT NULL,
    to_role          map_role NOT NULL,
    intent           match_intent NOT NULL DEFAULT 'same_map',
    access           room_access NOT NULL DEFAULT 'private',
    status           room_status NOT NULL DEFAULT 'open',
    starts_at        TIMESTAMPTZ NOT NULL,
    ends_at          TIMESTAMPTZ NOT NULL,
    from_left_at     TIMESTAMPTZ,
    to_left_at       TIMESTAMPTZ,
    closed_at        TIMESTAMPTZ,
    close_reason     room_close_reason,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT rooms_not_self CHECK (from_user_id <> to_user_id),
    CONSTRAINT rooms_ends_after_start CHECK (ends_at > starts_at),
    CONSTRAINT rooms_closed_shape CHECK (
        (status = 'open'  AND closed_at IS NULL AND close_reason IS NULL)
        OR
        (status = 'closed' AND closed_at IS NOT NULL AND close_reason IS NOT NULL)
    ),
    CONSTRAINT rooms_close_reason_values CHECK (
        close_reason IS NULL OR close_reason IN ('expired', 'both_left')
    )
);

CREATE UNIQUE INDEX rooms_open_from_idx
    ON rooms (from_user_id)
    WHERE status = 'open';
CREATE UNIQUE INDEX rooms_open_to_idx
    ON rooms (to_user_id)
    WHERE status = 'open';
CREATE INDEX rooms_open_ends_at_idx
    ON rooms (ends_at)
    WHERE status = 'open';
```

一人一房由 **两列各一条部分唯一索引** 共同保证（A 当邀请人或被邀请人都算占用）。实现插入前仍应查询，避免只靠报错当控制流。

| 列 | 含义 |
|---|---|
| `id` | 房间主键；频道 `room:{id}`；日后 `matches.room_id` |
| `invite_id` | 回指握手；一行邀请最多一房 |
| `article_id` | 本局地图；与邀请创建时相同，不改 |
| `from_user_id` / `to_user_id` | 邀请人 / 被邀请人 = `users.id` |
| `from_role` / `to_role` | 从邀请抄的地图位置，给开局展示和关房后的战绩 |
| `intent` | 从邀请抄；本期恒 `same_map` |
| `access` | 本期恒 `private`。日后可加 `open_map`，不改列名 |
| `status` | `open` → `closed`，不回流 |
| `starts_at` / `ends_at` | 对局时钟；时长 = 配置，不另存一列 |
| `from_left_at` / `to_left_at` | 该侧显式离席；两侧非空则立刻关房 |
| `closed_at` / `close_reason` | 仅 `closed`；`expired` 或 `both_left` |

不把 `title`、开局话题、聊天、纪要、战绩时长存进本表。不建 `metadata JSONB`。

```text
room:messages:{room_id}     LIST JSON     # 热聊天；关房 DEL
  元素：{ id, room_id, from_user_id, body, created_at }
  发言：RPUSH；重连：LRANGE；上限：LTRIM

room:snapshot:{room_id}     STRING JSON   # 关房后短活；TTL=SNAPSHOT_TTL
  仅 match / map 读；GET /rooms 不返回此键

延迟关闭（framework.mq 端口，Redis 落地）：
  ZSET score = unix(ends_at)
  member     = room.close 事件（含 room_id）
  worker ZRANGEBYSCORE -inf now 后关房
  禁止用过期通知当关房信号
```

开局话题若需要热存，由 **map** 自管键（例如 `map:room:{id}`），本模块不占用第三套房间 key 当文案库。`MapReader.for_room` 聚合进 GET。

**给其他模块的挂钩（本期只保证这些，不实现对方逻辑）：**

| 挂钩 | 谁写 | 谁读 |
|---|---|---|
| `rooms.id` / `invite_id` / 双方 / 角色 / `article_id` | room | match 关房后抄到战绩；map 认这间房 |
| `is_in_open_room` / `current_open` | room | **invite 创建与 accept**；前端 current |
| `starts_at` / `closed_at` / `close_reason` | room | match 算时长、是否成局（成局 = 曾 open 并 closed；握手失败不进本表） |
| `room:snapshot:{id}` | room（关房） | match / map 纪要；TTL 后消失 |
| 在场 | presence | 进房 `leave`；名单不是占线硬闸 |
| 开局话题 / 纪要正文 | map | 房内展示、战绩下纪要；**不是**本表列 |
| 战绩行 | match | `GET /matches`；**不是**建房时写 |

后续 `match` 提案必须：从关房钩子写 `matches` + `match_participants`，FK `rooms.id`，**不**拷贝聊天正文。后续 `map` 提案必须：`on_open` 不堵建房；纪要读快照 + 文章，不反写 `rooms`。invite feat 必须接真 `is_in_open_room`，不要只看 presence。

---

## Architecture

```text
web ──POST /invites / accept──► server.invite
                  ├── RoomReader.is_in_open_room（占线则失败）
                  └──（仅 accepted）RoomGateway.create_from_invite
                        ├── INSERT rooms access=private
                        ├── mq.delay room.close @ ends_at
                        ├── PresenceWriter.leave × 2
                        └── MapGateway.on_open

web ──WS room.join / room.send──► server.room ──► Redis LIST
                              └── realtime 订/推 room:{id}

web ──GET /rooms/{id}──► server.room ──► 行 + LIST + MapReader
web ──POST /rooms/{id}/leave──► server.room
web ──GET /rooms/current──► server.room

worker ──room.close──► server.room.close
                         ├── snapshot + DEL LIST
                         └── MatchGateway.on_room_closed
                                   └──（日后）enqueue map.summary
```

| 模块 | room 提供 / 依赖 |
|---|---|
| `identity` | 仅 `active` 成员可进；登出 / 封禁强制该侧 leave |
| `article` | FK `articles.id`；无文章不建房 |
| `invite` | 唯一创建入口；创建/accept 必须问 `is_in_open_room`；不把时长配在邀请模块 |
| `presence` | 进房 `leave`；名单空 ≠ 占线解除 |
| `map` | `on_open` / `for_room`；关房快照给纪要。本模块不调模型 |
| `match` | 只在关房出现；本模块不 insert 战绩 |
| `web` | 上表 HTTP + WS 帧 |
| `worker` | 消费 `room.close`；可扫逾期 `open` 行补漏 |
| `realtime` | 频道 `room:{id}`，不是全站 |

回滚：关掉房间路由、`room.send` 与 `room.close` 消费者即回到「能握手但不能进房」。已写入行可留。Redis 空了则该局无热消息。

## Open Questions

1. 默认 900s 还是 600s。只改 `VERSO_ROOM_DURATION_SEC`，不改表。演示脚本可临时加大。早退不依赖这个数。
2. 快照 TTL 1h 是否偏长。只改配置。match/map 读完可 DEL。
3. `open_map` 客人要不要进战绩。本期不实现开放局，立项时再定，不在本表预埋 JSON 人数。
4. `create_from_invite` 与邀请 CAS 的事务边界仍按 [#14](https://github.com/xiaocheny214/verso/issues/14) 第 4 问：禁止 `accepted` 且无房。本模块提供幂等 create 以便邀请重试。
