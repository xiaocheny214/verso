# Proposal: FeedRanker 端口（全员规则序，不建表）

本提案对应 [#24](https://github.com/xiaocheny214/verso/issues/24)。产品以 [#1](https://github.com/xiaocheny214/verso/issues/1) / [`product-proposal.md`](product-proposal.md) 为准；分层以 [#5](https://github.com/xiaocheny214/verso/issues/5) / [`architecture.md`](architecture.md) 为准；用户主键以 [#10](https://github.com/xiaocheny214/verso/issues/10) / [`identity.md`](identity.md) 为准；文章主键以 [#12](https://github.com/xiaocheny214/verso/issues/12) / [`article.md`](article.md) 为准；在场人数以 [#16](https://github.com/xiaocheny214/verso/issues/16) / [`presence.md`](presence.md) 为准。本文只定 feed 这一个增量，不夹带实现代码，不实现推荐、主题归一、`map` / `invite` / `room`。

## 1. Summary

给 Verso 加上摸鱼流排序：**`server.feed` 只留 `FeedRanker` 端口**。列表仍走已有的 `GET /articles`，不新增 `/feed`，**不建任何表，不写 Redis，不读当前用户**。

排序是全员同一规则序，三键字典序：

1. **站内层优先**（`source=user_contents` 整层压过 `zhihu_search`）
2. **这篇上现在的在场人数**（`PresenceReader.count`，降序）
3. **最近同步**（`articles.synced_at` 降序）

人与人的桥是文章：流把人带到有人的地图上，邀请仍在文下发生。这不是推荐系统。知乎赞数、关注、收藏、embedding、`topic_key` 都不进排序键。`like_count` 可出现在卡片上，但 **不是** 排序信号。

## 2. User Stories / Motivation

- 摸鱼读者打开首页：下滑同一份池子。先看到已入驻作者的文；同层里，文下正在有人的排前面；没人的文仍在，方便第一个人点进去把在场点亮。
- 匿名和下一位登录用户看到的顺序相同。换账号不会变成另一条「为你推荐」。
- 卡片上能看到「在读 N 人」。点进详情才出现可邀请名单（仍由 `presence.list` 提供）。
- 冷启动文撑浏览，且必须带 `source=zhihu_search`；哪怕下面围了人，也排在全部站内层之后。未入驻作者仍不可邀。
- 实现者不需要猜「要不要建打分表」：读文章池 + 读在场人数 + 进程内排序 + 切片。

共同需要：入口是内容，不是兴趣模型。规则要短、全员同一、能在 Demo 规模当场算完。

## 3. Current Workaround

[#12](https://github.com/xiaocheny214/verso/issues/12) 把 `GET /articles` 写成站内层优先、再 `synced_at` 倒序，并声明默认 `FeedRanker` 暂不读在场。[#5](https://github.com/xiaocheny214/verso/issues/5) 已要求三键（站内层 / 在场人数 / 最近同步），人数留给 feed × presence。[#16](https://github.com/xiaocheny214/verso/issues/16) 已提供 `count`，且禁止把人数反写 `articles`。

没有本端口时，列表实现会在 article 里 `ORDER BY source, synced_at`，P2「列表下滑、在读人数」只能靠详情或假数据。人数一变，SQL 序与真实相遇机会就拧开。

## 4. Goals

- 冻结 `FeedRanker.rank`：纯函数、无 IO、签名不含 `user_id`。
- `GET /articles` 的列表用例由 `server.feed.list_page` 编排：读池窗口 → 读 `count` → 排序 → 分页。
- 列表条目在 [#12](https://github.com/xiaocheny214/verso/issues/12) 卡片上 **加** `presence_count`；匿名可见人数，不可见成员。
- 明确不建表、不物化排行榜、不按兴趣过滤。
- 缺 presence 真实现时，`count` 恒 0，退化为 [#12](https://github.com/xiaocheny214/verso/issues/12) 的 source + `synced_at`。

## 5. Out of Scope

- 推荐算法、协同过滤、embedding、信息茧房治理、多样性重排。
- 新 HTTP `GET /feed` / `GET /for-you`；查询参数 `q` / `sort` / `topic` / `for_you`。
- 写入 `articles.topic_key`；按主题过滤；跨域互补自动配人。
- 用 `like_count` / `comment_count` / 知乎 `RankingScore` 排序。
- 把在场人数反写 Postgres；为 feed 建 Redis ZSET / 缓存键。
- 摸鱼流全站 WS 推人数；列表展示可邀请成员。
- 只展示 `presence_count > 0` 的文（会让第一位读者永远进不了空文）。
- 实现 `article` 同步 / 种子、`presence` join、邀请 / 房间。
- 克隆知乎首页；每次 GET 打 `zhihu_search`。

## 6. Proposal

### 6.1 Design Rule

**摸鱼流是文章池的规则序，不是推荐。全员同一排序键；数据从已有模块读；算完即丢。**

```text
GET /articles?offset=&limit=
  匿名可调；不 join、不续租、不订频道
  用例在 server.feed，不在 router 里 ORDER BY

list_page
  cards = ArticleReader.candidates(WINDOW_MAX)
  对每个 id：n = PresenceReader.count(id)    # 只读；与 list 同一套「活着且倒排指向该文」
  FeedRanker.rank(cards with n)               # 无 IO、无 user_id
  切片 [offset, offset+limit)
  每条带 presence_count=n；其它字段从卡片透传

排序键（升序比较；人数与时间取负）
  0 if source==user_contents else 1
  -presence_count
  -unix(synced_at)
  id 字符串                                    # 稳定平手，不用赞数

不要做
  按当前用户重排
  先 SQL 分页再按人数重排（翻页会错）
  为排序 INSERT / UPDATE 任何表
  把 GET 列表当成 presence.join
```

人数是热状态，join / leave 下一跳 GET 就会变。不维护排行榜，就不必在心跳路径上改 feed。

### 6.2 Syntax / API / Interface

| 方法 | 路径 | 谁可调 | 行为 |
|---|---|---|---|
| `GET` | `/articles` | 匿名 | 分页摸鱼流；规则序；每条带 `source` 与 `presence_count` |

`GET /articles/{id}`、`POST /articles/sync` 仍属 `article`，本模块不接管。

查询参数：

```text
offset   默认 0；整数 ≥ 0
limit    默认 VERSO_FEED_PAGE_SIZE；1..PAGE_SIZE
```

没有 `sort`。没有搜索框参数。

```text
VERSO_FEED_WINDOW_MAX     # 参与排序的候选上限，建议 200
VERSO_FEED_PAGE_SIZE      # 单页条数上限，建议 20
```

包边界：`web.api.articles` 的列表路由只做协议；**用例是 `server.feed.list_page`**。`web` 不直连表、不直连 Redis、不在 router 排序。本模块 **读** article 候选与 presence `count`；**写零行**。不发知乎请求，不调 LLM，不读 session 里的 `user_id` 做排序。

端口（对方未实现时用假实现）：

```text
ArticleReader.candidates(limit) -> [ArticleCard]
  # 最多 limit 条可当地图的池内文
  # 须含：id, source, synced_at, 以及列表要透传的卡片字段（[#12]）
  # SQL 可用 (source, synced_at DESC) 预序，以便截 WINDOW_MAX 时丢掉的是更旧的冷启动
  # 假实现：[]

PresenceReader.count(article_id) -> int     # 已有；禁止改成裸 ZCARD
  # 假实现：恒 0 → 排序退化为 source, synced_at, id

FeedRanker.rank(candidates) -> [FeedCandidate]
  # 纯函数。入参已带 presence_count。禁止接收 user_id / session
  # 默认实现：上表三键 + id
  # 假实现若直接原样返回，视为缺陷（实现 feat 必须接 DefaultFeedRanker）

FeedService.list_page(offset, limit) -> { items, offset, limit, total }
  # total = 实际参与排序的候选数（≤ WINDOW_MAX），不是表里全部行数
```

`ArticleCard` 的展示字段以 [#12](https://github.com/xiaocheny214/verso/issues/12) 为准（含 `topic_key` 本期恒可空、作者 `settled`）。本模块不改 upsert 键，不填 `topic_key`。

实现可用 pipeline 把多次 `count` 收成一轮 Redis；不要求本提案改 presence 的 key。日后若 presence 增加 `counts(ids)`，feed 只换调用，不改排序键。

### 6.3 Examples as Specification

**当前：** 列表若已实现，只有 source + `synced_at`；无 `presence_count`；人数在详情。

**提案主路径（规范，不是示意）：**

```text
池内四篇（WINDOW_MAX=200）

  B  source=user_contents   count=3   synced_at=09:00  id=b
  A  source=user_contents   count=0   synced_at=10:00  id=a
  C  source=zhihu_search    count=8   synced_at=11:00  id=c
  D  source=zhihu_search    count=0   synced_at=12:00  id=d

GET /articles?offset=0&limit=20
  candidates ← ArticleReader.candidates(200)
  count(B)=3 … count(D)=0
  rank → B, A, C, D
    B 先于 A：同层，人数多
    A 先于 C：站内层整层优先，尽管 C 有 8 人
    C 先于 D：同层，人数多
```

**列表响应：**

```json
{
  "items": [
    {
      "id": "uuid-b",
      "source": "user_contents",
      "content_type": "article",
      "title": "…",
      "summary": "…",
      "canonical_url": "https://zhuanlan.zhihu.com/p/1",
      "topic_key": null,
      "like_count": 40,
      "comment_count": 12,
      "presence_count": 3,
      "author": {
        "user_id": "uuid",
        "display_name": "…",
        "avatar_url": "https://…",
        "url_token": "…",
        "settled": true
      }
    }
  ],
  "offset": 0,
  "limit": 20,
  "total": 4
}
```

`like_count` 仅展示。冷启动条目 `source=zhihu_search`，`author.settled=false`，`presence_count` 仍按真实在场（通常为 0，因为未入驻作者不能 join；已入驻读者仍可在冷启动文下在场）。

不返回成员列表、token、sid、知乎凭证、搜索 `RankingScore`。

**匿名与登录同一序：**

```text
Cookie 空 与 Cookie=A 连续两次 GET，池与 count 未变
  items[].id 序列相同
  Ranker 调用栈无 user_id
```

**presence 假实现：**

```text
count 恒 0
  序 = user_contents 按 synced_at 新→旧，再 zhihu_search 按 synced_at 新→旧
  上例变为 A, B, D, C
```

**翻页（规范）：**

```text
WINDOW 内 25 篇已 rank 完
GET offset=20&limit=20 → items 为第 21–25 条，total=25
禁止：SQL LIMIT 20 得到页 1，再按 count 重排；页 2 用另一批 SQL 行
```

**窗口截断：**

```text
表有 500 行。candidates(200) 按 article 预序取 200
total=200。第 201 行不出现在任何 offset
Demo 池远小于窗口则无感
```

**列表不产生在场：**

```text
GET /articles
  0 次 PresenceWriter
  0 次 ZADD
  Redis 仅只读 count（及 count 内部的过期裁剪，属 presence 读路径）
```

**等价形态：** `offset=0&limit` 缺省与显式 `limit=PAGE_SIZE` 同一页。重复 GET 在 count 未变时稳定。

**无效：** `GET /feed`；`?sort=likes`；`?for_you=1`；按 `like_count` 重排；把 viewer 关注话题插到最前；列表返回 `members`；GET 触发 `zhihu_search`；为这次排序 UPDATE `articles`。均不得作为本模块行为。

### 6.4 Boundary Cases

| 情况 | 行为 |
|---|---|
| 空池 | `{ items: [], total: 0 }`；不现场搜索 |
| 全部 `count=0` | 退化为 source + `synced_at` + `id` |
| 站内层 0 人 vs 冷启动 10 人 | 站内层仍全部在前 |
| 两篇同层、同人数、同时戳 | `id` 字典序；禁止用赞数打平手 |
| 匿名 | 200 + `presence_count`；无成员；不能 sync |
| 已登录 | 同一序；仍不把「我写的文」置顶 |
| `banned` / 未登录 | 与匿名相同可看流 |
| 文章在窗口内但随后被删 | 本页已取出的候选仍可排；下一跳 candidates 不再包含 |
| `count` 读路径裁掉过期成员 | 允许；列表以这次读到的数为准 |
| 超过 `LIST_MAX` 的文下人数 | 仍用真实 `count`，不是截断后的 members 长度 |
| `offset` 超过 `total` | `items=[]`，`total` 不变 |
| `limit` > PAGE_SIZE 或 ≤ 0 | 400，不读池 |
| 窗口 > WINDOW_MAX 的行 | 本模块看不见；不保证全表有序 |
| 详情页 | 本模块不管；人数/名单走 presence |
| 作者在自己文下 | 计入 `count`，无额外加权 |
| 进房后 leave 文下 | 下一跳 GET 人数下降；不需要 feed 钩子 |

## 7. Error Handling

| 条件 | 行为 |
|---|---|
| `offset` / `limit` 非法 | 400，无 IO |
| `ArticleReader` 失败 | 请求失败，不返回半页假序 |
| `PresenceReader.count` 失败 | 请求失败；**禁止**改用裸 `ZCARD` 或随机序顶上。测试假实现恒 0 不算失败 |
| 某 id 在 candidates 中但文章已不存在 | 丢掉该条，不 404 整页 |
| 列表路径出现密钥 | 视为缺陷 |
| 列表路径打知乎 / LLM | 视为缺陷 |
| `FeedRanker.rank` 接收 `user_id` | 视为缺陷 |
| GET 列表写入 `articles` / feed 表 / 排行榜 key | 视为缺陷 |

## 8. Compatibility

加法，改的是 `GET /articles` 的**序**和列表条目多一个 `presence_count`。[#12](https://github.com/xiaocheny214/verso/issues/12) 的卡片其余字段不变；upsert 键不变。

依赖：`articles` 表至少能 `candidates`；presence 可假（全 0）。实现顺序：article 主键与读端口 → 本模块 rank + `list_page` 接上 `GET /articles` → presence 真 `count` 自动让人数生效。不要等推荐方案。

回滚：列表改回只按 source + `synced_at`；去掉 `presence_count` 字段。没有表可丢。

[#12](https://github.com/xiaocheny214/verso/issues/12) 写「默认 FeedRanker = 站内层 > 冷启动，再 `synced_at`」视为 **presence 全 0 时的退化**，不是第二套官方序。三键以 [#5](https://github.com/xiaocheny214/verso/issues/5) 与本文为准。`like_count` 在 [#12](https://github.com/xiaocheny214/verso/issues/12) 挂钩表里可作为展示，**不**进入 DefaultFeedRanker。

列表 JSON 若 [#12](https://github.com/xiaocheny214/verso/issues/12) 尚未冻分页信封，以本文 `items` / `offset` / `limit` / `total` 为准。

## 9. Alternatives Considered

### 9.1 建 `feed_scores` 表或 Redis 排行 ZSET

人数随心跳变。物化分数就要在 join / leave / 过期时回写 feed，等于给推荐系统打底层，且和「不把人数抄进 `articles`」拧着。Demo 窗口内当场算完即可。

### 9.2 按用户兴趣 / embedding / 关注收藏排序

产品假设 1：要的是文下房间，不是更好的推荐流。个性化是 incoming，也是茧房入口。[#10](https://github.com/xiaocheny214/verso/issues/10) 已写 `feed` 不读身份。Ranker 签名去掉 `user_id`，避免实现时「顺便」个性化。

### 9.3 用 `like_count` 当热度

那是知乎侧快照，会把摸鱼流收成知乎热榜，把「现在这篇下有人」挤掉。展示可以留赞数；排序键不收。

### 9.4 隐藏 `presence_count=0` 的文

空文下永远没有第一位读者，在场点不亮，邀请主路径冻死。零人数文必须在，只是同层靠后。

### 9.5 新资源 `GET /feed`

架构把摸鱼流放在 `GET /articles`。第二套列表会让前端猜该打哪条，也像推荐产品。路由不改。

### 9.6 只 SQL `ORDER BY source, synced_at`，人数仅展示

P2 要的是用人数**找人**，不是在错序的卡片上挂一个数字。人数必须进排序键。展示也要带上，否则用户看不见为什么这篇在前。

### 9.7 加权公式（0.5 来源 + 0.3 人数 + 0.2 时间）

无法向评审讲清「冷启动 8 人会不会压过站内层 0 人」。字典序一条规则：站内层永远整层优先。权重留给 incoming 推荐提案。

### 9.8 列表短轮询或全站频道推人数

架构：摸鱼流可不订频道。本模块每次 GET 读当前 `count`。前端是否定时刷新列表是 UI，不在本端口加 `feed:*` 频道。

### 9.9 `server.article` 列表里直接调 presence

article 是池，不该依赖在场。人数排序是 feed 的存在理由。article 只出 `ArticleReader.candidates`。

## 10. Testing Strategy

| 用例 | 方法 |
|---|---|
| 6.3 四篇序为 B,A,C,D | 单测 Ranker，冻 count |
| 匿名与登录同一 `id` 序列 | 契约夹具，count 冻结 |
| `count` 恒 0 时序为 source + `synced_at` + `id` | 单测 |
| 先 SQL 20 条再重排 的实现不得通过翻页夹具 | 两页 count 分布相反 |
| GET 列表 0 次知乎 / LLM | mock 计数 |
| GET 列表 0 次 PresenceWriter / 0 次 INSERT articles | mock / SQL |
| `rank` 形参无 `user_id` | 类型 / 调用检查 |
| 响应有 `presence_count`，无 `members`，无密钥 | 契约 |
| 非法 `limit` 为 400 | HTTP |
| 空池 `items=[]` 且不调搜索 | 调用计数 |
| 窗口 200：第 201 篇从不出现 | 夹具 |
| 假 count=0 时与 [#12](https://github.com/xiaocheny214/verso/issues/12) 退化序一致 | 对照 |

## 11. Summary of Changes

| 区域 | 变更 |
|---|---|
| 本文 | 冻结 feed 契约；后续 `feat` 按此实现 |
| 以后才写的代码 | `DefaultFeedRanker`；`FeedService.list_page`；`GET /articles` 改走该用例；透传卡片 + `presence_count` |
| 不改 | `articles` DDL、presence key、identity 协议、邀请 / 房间 |
| 不建 | feed 表、打分表、排行榜 Redis、`GET /feed` |

实现顺序：`FeedRanker` 纯函数单测 → `list_page` 接假 `candidates` / 假 `count` → 接到真 `GET /articles` → presence 真 `count`。缺文章主键不要发明第二份列表。缺在场则全 0，不要用赞数顶上。

---

## Data model

Postgres **不加表**。Redis **不加** `feed:*` 键。没有物化分数。

```text
读
  articles 行（经 ArticleReader.candidates）
  presence:article / presence:user（经 PresenceReader.count，本模块不直接拼 key）

写
  无
```

不建：`feed_items`、`feed_scores`、`article_impressions`、`user_article_features`、推荐特征表、`metadata JSONB`。不 UPDATE `articles.topic_key`。

**给其他模块的挂钩（本期只保证这些，不实现对方逻辑）：**

| 挂钩 | 谁写 | 谁读 |
|---|---|---|
| `articles` 卡片 + `source` / `synced_at` | article | feed `candidates` |
| `PresenceReader.count` | presence | feed 排序键与 `presence_count` |
| `GET /articles` 列表序 | feed | 前端摸鱼流 |
| `topic_key` / 兴趣 / embedding | 不是本期 | incoming 推荐或主题提案 |
| 文下成员 | presence `list` | 详情邀请；**不是**本列表 |

后续若做推荐：另开提案换 `FeedRanker` 实现，仍禁止改 `articles.id`。必须显式处理「还是不是全员同一序」和茧房；默认实现不预留加权列。

## Architecture

```text
web ──GET /articles──► server.feed.list_page
                         ├── ArticleReader.candidates(WINDOW_MAX)
                         ├── PresenceReader.count（只读）
                         └── FeedRanker.rank          # 无 IO

web ──GET /articles/{id}──► server.article            # 本模块不碰
web ──POST /articles/sync──► server.article
web ──GET /articles/{id}/presence──► server.presence  # 详情名单
```

| 模块 | feed 提供 / 依赖 |
|---|---|
| `article` | 提供 `candidates`；不在本模块排序；同步 / 种子仍归 article |
| `presence` | 提供 `count`；列表不得 `join` |
| `identity` | 匿名可看流；Ranker 不读用户 |
| `invite` / `room` / `match` | 不读 feed；相遇仍从详情在场发生 |
| `web` | 仅 `GET /articles` 列表改走本用例 |
| `worker` | 无 feed 事件 |

回滚：列表路由改回 article 自排（或停人数键）。无表可清。Redis 无 feed 键可丢。

## Open Questions

1. `WINDOW_MAX` 200 对 Demo 过大还是刚好。只改配置。池真到数百再考虑是否加 `counts(ids)`，不先建排行榜。
2. 前端列表要不要短轮询刷新人数。属 UI，不改变本端口；禁止为此加全站频道。
3. 冷启动文下若已有已入驻读者，人数仍只在冷启动层内起作用——是否过硬。本期与「MVP 匹配对象是站内层」对齐；要混层加权另开提案。
4. 列表信封若与尚未合入的 article feat 草稿不一致，以本文为准，在 article 实现 PR 里对齐，不在本提案加第二套字段名。
