# Proposal: 文下在场（Redis 热集合，不是读详情副作用）

本提案对应 [#16](https://github.com/xiaocheny214/verso/issues/16)。产品以 [#1](https://github.com/xiaocheny214/verso/issues/1) / [`product-proposal.md`](product-proposal.md) 为准；分层以 [#5](https://github.com/xiaocheny214/verso/issues/5) / [`architecture.md`](architecture.md) 为准；用户主键以 [#10](https://github.com/xiaocheny214/verso/issues/10) / [`identity.md`](identity.md) 为准；文章主键以 [#12](https://github.com/xiaocheny214/verso/issues/12) / [`article.md`](article.md) 为准；邀请只读本模块端口，以 [#14](https://github.com/xiaocheny214/verso/issues/14) / [`invite.md`](invite.md) 为准。本文只定 presence 这一个增量，不夹带实现代码，不实现 `invite` / `room` / `match`。

## 1. Summary

给 Verso 加上文下在场：已登录且 `active` 的用户，**打开文章详情并显式 join** 之后，才进入该 `article_id` 的在场集合。权威状态是 Redis 上**成对的两份索引**，缺一不可：

- `presence:article:{article_id}`：这篇上**现在还有谁**（邀请列表 / 同地图匹配的唯一候选人来源）
- `presence:user:{user_id}`：这个人**现在在哪篇**（一人一篇、leave / 换文 / 心跳的倒排）

两份必须用 Lua 一起改。邀请、accept、日后同地图匹配都读这份热状态，不另造在线表。`GET /articles/{id}` 只读地图，**不得**因读详情而写入在场。

进场：详情就绪后 **WS `presence.join`**（写 Redis 并订频道），再 `GET` 快照做首屏。离场：换路由必须带旧 `article_id`；关页用空 body `sendBeacon`。WS 断线不等于离场。后端感知不到关页是常态，**心跳租约到期 = 离场**。

## 2. User Stories / Motivation

- 两名已登录读者打开同一篇池内文章，文下看见对方，名单随进进出出更新；未打开该文的人不会出现。这份名单就是可邀请对象，也是同地图匹配的候选池。
- 同一人从文 X 转到文 Y：必须先从 X 的名单拿掉，再出现在 Y；系统靠 `presence:user` 找回旧文，禁止只往新 ZSET 里加。
- 未登录可以读详情，但不上报在场、不进业务 WS、不能当邀请对象。
- 关标签、回摸鱼流、崩溃：对方应在租约内从名单消失。网络闪断不立刻离场。
- `invite` 创建与 accept 问「双方是否仍在这篇上」；本模块给名单、倒排和布尔，不写邀请行。

共同需要：按文章能列出在场者，按用户能指认在哪篇；两问都是主路径，不是附属缓存。

## 3. Current Workaround

`server.presence` 只有占位。没有在场则邀请只能假装全员可邀，或把读详情当成在场——匿名、预取、重试、爬虫都会脏数据，且没有离场。

## 4. Goals

- 显式 `join` / `leave` / `heartbeat`；同一用户同一时刻最多一篇文章。
- 文章正排：每篇一份 **ZSET**（谁在这篇上，score=到期时间）。
- 用户倒排：每人一条 **STRING**（在哪一篇）；leave / 换文 / 心跳必须读它。
- 写路径用 **Lua** 成对改两边；`is_present` 两边一致才为真。断线 ≠ 离场。
- 详情页可拉快照；名单变更推频道，禁止全站广播。
- 提供 `PresenceReader` 给 invite / feed：`list`、`is_present`、`current_article`、`count`。
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

**在场是一对互为倒排的热索引：文章→人们，用户→文章。不是读地图的副作用。前端负责意图，后端负责租约与两边一致。**

```text
GET /articles/{id}
  匿名可读；只返回地图
  不 join、不续租、不订阅

已登录用户停在详情页（前端编排，不是后端中间件）
  详情 2xx 且路由仍是该文
  → WS presence.join（写 Redis + 订 article:{id}）
  → GET /articles/{id}/presence（首屏名单，不等推送）
  → 定时 heartbeat（连着 WS 就走帧；否则 HTTP）

离开该详情（路由变化 / 进房）
  → WS presence.leave，body 必须带正在离开的 article_id
  → 退订 article:{id}；连接保留（还要收 user:{id} 邀请）

关页 / 杀标签
  → sendBeacon POST /presence/leave（空 body，只带 Cookie）
  → 失败则等租约，不重试 JSON CSRF

两份索引（必须成对出现、成对删除）：
  presence:article:{X}  这篇上还有谁     → 文下列表、发邀请、同地图候选
  presence:user:{U}     这个人在哪一篇   → 一人一篇、找回旧文、关页空 body leave

后端
  join / 换文 / 裁过期：Lua（MULTI 不能 GET 完再分支；
        ZREMRANGEBYSCORE 不返回 member，须先 ZRANGEBYSCORE -inf now）
  heartbeat：GET 倒排得到当前篇；无人场 → 409
             续 score + EXPIRE 倒排；裁该文过期成员（先取出 id 再删两边）
  leave(article_id)：倒排已不是这篇 → 204 不改（换文迟到 leave / Strict Mode）
  leave(空 body)：只用于 unload，按倒排清当前篇
  WS 断线 ≠ leave；租约才是在场
  崩溃未 leave：score 过期后从两边删掉
```

不要做：在 `GET /articles/{id}` 后由服务端「监听成功就入库」。读接口会被预取、重试、多端刷新；离场也发不出来。前端可以在查询成功之后 **调用** join，这是客户端时序，不是把 presence 耦合进 article 用例。

### 6.2 Syntax / API / Interface

| 方法 | 路径 | 谁可调 | 行为 |
|---|---|---|---|
| `GET` | `/articles/{id}/presence` | 已登录 | 该文快照；`list` 与 `is_present` 同一判定（倒排须指向这篇） |
| `POST` | `/presence/leave` | 已登录 | 关页用：空 body + Cookie，**不要求 CSRF 头**；按倒排离开当前篇 |
| `POST` | `/presence/heartbeat` | 已登录 | WS 不可用时的续租；无人场 409。主路径用 WS `heartbeat` |

在场主路径不走 `POST /presence/join`。HTTP join 若实现，只作运维/测试等价物，**不订频道**；产品客户端禁止 HTTP join 后再 WS join。

WS（同一 Cookie 或 identity 短活 ticket；每用户 1 条业务连接）只收：

```text
{ "type": "presence.join", "article_id": "<uuid>" }
{ "type": "presence.leave", "article_id": "<uuid>" }   # 路由离开：必带旧文 id
{ "type": "heartbeat" }
```

服务端向 `article:{id}` 推（不是全站）：

```text
{ "type": "presence.snapshot", "article_id": "<uuid>", "count": 2, "members": [ ... ] }
```

`presence.join`：写 Redis + 订 `article:{id}`（登录后那条连接应已订 `user:{id}`，本模块不改）。  
`presence.leave`：退订该文频道，**不断连接**。  
TCP / WS 断开：不 `leave`，不退在场；重连后若仍在该路由则再 `presence.join`（幂等续租+订阅）。  
`heartbeat` 仅在裁掉过期成员时推快照。未登录禁止连业务 WS。

推快照时短查 `users` 名片，立刻释放 ORM，禁止把数据库连接绑在 WS 生命周期上。

**前端契约（规范，不是建议）：**

```text
登录成功 → 一条 WS（Cookie；跨端口拿 ticket，路径由 identity / realtime 冻结）
打开文章 → GET 详情 2xx 且仍在该路由
         → WS presence.join
         → GET /articles/{id}/presence     # 首屏
         → 心跳；visibility 回到 visible 立刻心跳或再 join
离开路由 → WS presence.leave { article_id: 旧文 }
         → 仍是当前路由则 effect cleanup 不得 leave（防 Strict Mode）
关页     → sendBeacon POST /presence/leave  空 body
heartbeat 409 → 仅当仍在该文章路由才再 join，否则停心跳
后台标签 → 不保证租约；回到前台再续。Demo 用两台前台窗口
```

包边界：`web.api.presence` 与 WS 适配器只做协议；用例在 `server.presence`。`web` 不直连 Redis key。本模块 **读** identity（当前用户）、article（`articles.id` 存在）；**写** Redis；**调** `framework.realtime`。不写 `invites` / `rooms`。不发知乎请求。

```text
VERSO_PRESENCE_HEARTBEAT_SEC     # 客户端间隔，建议 15
VERSO_PRESENCE_LEASE_SEC         # 租约，建议 45（≥ 2× 心跳 + 抖动）
VERSO_PRESENCE_LIST_MAX          # 快照人数上限，建议 50；超出仍准 count
```

端口（对方未实现时用假实现）：

```text
PresenceReader.list(article_id) -> [PresenceMember]     # 文下还有谁；邀请 UI 只读这个
PresenceReader.is_present(user_id, article_id) -> bool  # 两边索引一致且未过期
PresenceReader.current_article(user_id) -> article_id|None
PresenceReader.count(article_id) -> int                 # 真实人数，供 feed

PresenceWriter.leave(user_id) -> None                   # 进房 / 登出 / 封禁：先读倒排再删两边
```

`GET /invites` 不是候选人列表。发邀请的人从 `list(article_id)` 里点；`invite` 创建与 accept 再问 `is_present`。日后同地图匹配仍读 `list`，不另建候选表。`count` 不反写 `articles`。

### 6.3 Examples as Specification

**当前：** 无在场集合。读详情不等于在场。

**提案主路径（规范，不是示意）：**

```text
A、B 已登录 active。A 打开 article X：

GET /articles/X          → 200 地图；Redis 仍无 A
WS { type: presence.join, article_id: X }
  session → users.id = A；articles.id = X 存在
  Lua：若倒排为 Y 且 Y≠X → ZREM Y，并向 article:{Y} 推快照
       ZADD presence:article:{X} score=now+LEASE member=A
       SET presence:user:{A} X EX LEASE_SEC
  订 article:{X}
  推 presence.snapshot 给 article:{X}
GET /articles/X/presence → 首屏 list(X)（含自己）
此后 list(X) 含 A；current_article(A) = X

B 同样 join(X)
  GET /articles/X/presence → list(X)
    裁过期：ZRANGEBYSCORE -inf now → 对每个 id 若倒排仍是 X 则 DEL 倒排
            再 ZREMRANGEBYSCORE -inf now
    活着：ZRANGEBYSCORE now +inf，且 GET 倒排 == X（否则丢掉并 ZREM）
    members 含 A、B；这就是可邀请 / 同地图候选

A 发心跳（WS heartbeat）
  GET presence:user:{A} → 必须为 X，否则 409
  ZADD 续 score；EXPIRE 倒排
  同上裁过期；裁掉了人才推 snapshot
  不碰知乎

A 回列表
  WS { type: presence.leave, article_id: X }
  若倒排已不是 X → 204，不删 Y
  否则 Lua：ZREM X 的 A；DEL 倒排；退订 article:{X}；推快照
  current_article(A) = None

关页
  sendBeacon POST /presence/leave   （空 body，Cookie，无 CSRF 头）
  按倒排离开；失败则等租约
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
不另做扫全库 worker。join / leave / list / count / is_present / heartbeat：
  ids = ZRANGEBYSCORE presence:article:{X} -inf now
  对每个 id：若 presence:user == X 则 DEL 倒排
  ZREMRANGEBYSCORE -inf now
  活着的人还要 GET 倒排 == X，否则 ZREM（防 STRING 先过期）
  若确实裁掉了人，再推 snapshot
```

`ZREMRANGEBYSCORE` 只返回数量，禁止「裁完却不知道删了谁」。换文 join 用 Lua，不要用 MULTI 假装能分支。

`is_present(U, X)` 两边都要成立，缺一边即假并修复：

```text
GET presence:user:{U} == X
且 ZSCORE presence:article:{X} U 存在且 > now
否则 false：
  倒排指向 X 但 ZSET 已过期 → DEL 倒排、ZREM
  ZSET 有 U 但倒排不是 X   → ZREM（幽灵）
```

不信任 keyspace 通知当离场信号。不扫全站用户来回答「这篇上还有谁」。

**进房：**

```text
room 创建成功（非本期实现）
  PresenceWriter.leave(双方)
  退订 article:{id}，只留 room:{id}
  两人从该文邀请列表消失
```

**等价形态：** 同一篇重复 `presence.join` = 续租 + 保证在集合中 + 保证已订阅，幂等。HTTP `POST /presence/leave` 空 body 与 WS leave（倒排指向该文时）写同一套 key。

**无效：** 未登录 join；`banned` join；文章不存在；匿名连业务 WS；把 `GET /articles/{id}` 当 join；HTTP join 后再 WS join；`GET /invites` 当候选人列表；leave 不带旧文 id 却用于换路由。均失败或不得写入。

### 6.4 Boundary Cases

| 情况 | 行为 |
|---|---|
| 未登录读详情 | 200 地图；无 join；`GET .../presence` 未认证 |
| 已登录未 join | 不在名单；invite 创建失败（对方/自己不在场） |
| 详情预取 / 连打两次 GET | 不产生两条在场；只有 join 才写 |
| 关页来不及 WS | `sendBeacon POST /presence/leave` 空 body + Cookie，无 CSRF 头；失败等租约 |
| WS / 网络闪断 | **不** leave；重连后仍在该路由则再 `presence.join` |
| 路由 X→Y 的迟到 leave | 必须带 `article_id=X`；倒排已是 Y 则 no-op |
| Strict Mode 假卸载 | 仍是当前路由则 cleanup 不发 leave |
| 心跳丢失超过租约 | 离场并推快照（须先取出过期 id） |
| 换文 | Lua：ZREM 旧文再 join 新文；旧文频道推离场 |
| heartbeat 409 | 仍在该文章路由 → 再 join；已离开 → 停心跳，禁止自动复活 |
| 第二浏览器登录 | identity 踢旧 session；旧连接死，新 join 覆盖倒排；旧 ZSET 靠换文 Lua 或租约 |
| 冷启动未入驻作者 | 无 `users` 行，不能 join，不能出现在名单 |
| 作者在自己文下 join | 可以；`role=author`；可被邀、可主动邀 |
| 后台 / 隐藏标签 | **不保证**仍在场（浏览器会节流 timer）；`visibility=visible` 立刻心跳或 join。Demo 用两台前台窗口 |
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
| heartbeat 时无人场 | 409；仅当客户端仍在该文章路由才再 join |
| leave 无人场 / 倒排已不是该文 | 幂等 204 |
| `POST /presence/leave` 要求 CSRF 头导致 sendBeacon 失败 | 视为缺陷；该路由只校 Cookie |
| 快照 / 推送出现密钥 | 视为缺陷 |
| 心跳打知乎 / LLM | 视为缺陷 |
| ORM 连接绑在 WS 上 | 视为缺陷 |

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

### 9.6 文章侧用 SET / HASH / LIST，而不是 ZSET

进进出出的难点不是「内存还是磁盘」，是 **成员带过期时间**。Redis `SET` 增删 O(1)，但 member 不能单独过期，心跳漏了会变成幽灵，invite 会误判仍在场。`LIST` 删除是 O(n) 且易重复。`HASH`（field=用户，value=到期时间）能滤过期，但每次都要 `HGETALL` 再逐个删。`ZSET` 的 score 就是到期时间：`ZADD` 进场/续命，`ZREM` 离场，`ZREMRANGEBYSCORE` 一次裁掉过期，`ZRANGEBYSCORE` / `ZCOUNT` 只返回还活着的人。这才是「这篇上还有谁」的存储形态。不靠 Pub/Sub 当存储（不能 `is_present`），也不把整篇名单序列化成一条 JSON 覆盖写。

### 9.7 只保留其中一份索引

只有 `presence:article`：leave / 心跳 / 进房不知道人在哪篇，只能扫所有文章 ZSET。只有 `presence:user`：要列出一篇上的人只能扫全部用户。邀请和同地图匹配问的是「这篇上还有谁」，leave 问的是「这人在哪篇」。两份都是主键，禁止做成可丢的缓存。

### 9.8 WS 断开即 leave

闪断会把邀请列表抖空。在场绑租约，不绑 TCP。断线只丢推送。

## 10. Testing Strategy

| 用例 | 方法 |
|---|---|
| GET 详情不写 Redis；随后 WS join 才出现 | HTTP + WS 契约 |
| 未登录 / banned 不能 join | 中间件 |
| 两人 join 同一篇，`list` 互见；leave 后对方从该文 ZSET 消失，倒排删除 | 单测 Redis |
| 换文：倒排从 Y 改为 X；Y 的 ZSET 去掉、X 加入；迟到 leave(Y) 不删 X | 单测 |
| `list` 不含倒排已不是该文的幽灵；与 `is_present` 一致 | 单测 |
| 裁过期先取出 member 再删倒排，禁止只 ZREMRANGEBYSCORE | Lua 夹具 |
| 只写 ZSET 不写倒排（或反过来）则 `is_present` 为假并修复 | 单测 |
| 租约到期后 `is_present` 为假，两边都清掉 | 时间夹具 |
| heartbeat 无倒排为 409；有倒排则续 ZSET score | 单测 |
| WS 断开后键仍在；重连 join 幂等 | 单测 |
| 心跳路径无知乎 / LLM mock 调用 | 调用计数 |
| invite：`list` 里的人才可被邀；不在场 `is_present` 为假 | 与 invite 夹具对照 |
| 空 body leave 不需 CSRF 头 | HTTP 契约 |
| 登出 / 封禁触发 leave | 与 identity 夹具 |
| 推送只到 `article:{id}`，无全站频道 | realtime 假实现断言 |
| 响应无密钥 | 契约夹具 |

## 11. Summary of Changes

| 区域 | 变更 |
|---|---|
| 本文 | 冻结 presence 契约；后续 `feat` 按此实现 |
| 以后才写的代码 | Lua 双索引；WS join/leave/heartbeat；`GET` 快照；空 body leave |
| 不改 | identity 协议、`articles` 表、invite 状态机、前端仓库（前端按本契约在详情 2xx 后 join） |
| 不建 | `article_readers` 表、在场历史、全局在线表 |

实现顺序：Lua 成对写 ZSET+STRING → WS join/leave 与订阅 → 快照 GET 与 `list` 过滤倒排 → heartbeat 与裁过期 → sendBeacon leave → identity 登出 / 封禁。缺 session 不要 join。缺倒排不要假装能 leave。

---

## Data model

Postgres **不加表**。热状态只在 Redis。**两份索引都是权威数据**，一起构成「用户 — 文章 — 用户」在场边。

```text
presence:article:{article_id}   ZSET          # 正排：这篇上还有谁
  member = user_id
  score  = lease_expire_at（unix 秒）
  活着：score > now
  进场/心跳：ZADD（同 member 覆盖 score）
  离场：ZREM
  过期：先 ZRANGEBYSCORE -inf now 取出 id，再 ZREMRANGEBYSCORE
  回答：可邀请 / 同地图候选 / 快照 / count

presence:user:{user_id}         STRING        # 倒排：这个人现在在哪篇
  值 = article_id
  TTL = LEASE_SEC（与 ZSET score 同一租约）
  进场：SET EX；心跳：EXPIRE；离场：DEL
  回答：一人一篇、leave 找回旧文、heartbeat 当前篇、进房清场
```

join / leave / heartbeat / 过期裁剪必须同一段 Lua 改两边。禁止只维护 ZSET、把 STRING 当可重建缓存。禁止用 `MULTI` 做换文分支。裁过期必须先 `ZRANGEBYSCORE` 拿到 id。

`list` / 快照 / `count` 的成员集合 = score>now **且** 倒排指向该文。`count` 不是裸 `ZCARD`。

不把 `display_name` 复制进 ZSET；快照时短查 `users`，立刻释放连接。不把在场抄进 `invites` / `matches`。

不建：`article_readers`、`presence_events` 流水、`metadata JSONB`。

**给其他模块的挂钩（本期只保证这些，不实现对方逻辑）：**

| 挂钩 | 谁写 | 谁读 |
|---|---|---|
| `list(article_id)` | presence | 详情邀请列表；日后同地图匹配候选；**不是** `GET /invites` |
| `is_present` | presence | invite 创建与 accept（两边索引一致） |
| `current_article` | presence | leave / 进房 / 封禁；日后若问「这人在哪篇」 |
| `count` | presence | 日后 `FeedRanker`；不反写 articles |
| `PresenceWriter.leave` | presence | room 进房；identity 登出 / 封禁 |

---

## Architecture

```text
web  ──GET /articles/{id}──► server.article     （无副作用）

web  ──WS presence.join/leave/heartbeat──► server.presence ──► Redis
                              └── realtime 订/退 article:{id}

web  ──GET /articles/{id}/presence──► server.presence   （首屏）
web  ──sendBeacon POST /presence/leave──► server.presence

详情邀请列表 ──PresenceReader.list────────► server.presence
invite 握手   ──PresenceReader.is_present──► server.presence

identity 登出/封禁 ──PresenceWriter.leave──► server.presence
room 进房（非本期）──PresenceWriter.leave──► server.presence
```

| 模块 | presence 提供 / 依赖 |
|---|---|
| `identity` | 仅 `active` 可 join；登出 / 封禁必须 leave |
| `article` | 只认 `articles.id`；读详情不写在场 |
| `invite` | 候选人来自 `list`；握手问 `is_present`；不订心跳、不抄名单进表 |
| `match` | 本期不读在场；同地图候选仍来自 `list`，不另建在线集合 |
| `room` | 进房调用 `leave`（先 `current_article`）；本模块不建房 |
| `feed` | 可读 `count`；本期不改排序 |
| `web` | 上表 HTTP + WS 帧 |
| `worker` | 不消费 presence 专用队列；过期靠 ZSET score + 读写时裁剪 |

回滚：关掉 join 与业务 WS 即回到「能读文、看不见人」。

## Open Questions

1. 租约 45s / 心跳 15s 是否偏松。只改配置，不改 key 形状。后台标签本来就不保证，不必为它把租约加到数分钟。
2. 名单截断规则（先 join 优先 vs 随机）。Demo 两人无感；超过 `LIST_MAX` 再定。
3. 匿名是否展示 `count`（不含成员）。本期快照需登录；摸鱼流人数留给 feed。
4. ~~实现用 Redis 7 键过期还是 lease 键 + 惰性删。~~ **已收口：** 文章侧 ZSET（score=到期）+ 用户侧 STRING 成对维护；过期先 `ZRANGEBYSCORE` 再删；Lua，不靠 keyspace 通知，不另开扫表 worker。
5. WS 路径与 ticket 领取挂在 identity / realtime。本模块只要求：同一条连接、join 订文章、leave 退订文章、断线不离场。
