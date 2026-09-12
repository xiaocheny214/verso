# Proposal: 文章池、授权同步与冷启动来源标记

本提案对应 [#12](https://github.com/xiaocheny214/verso/issues/12)。产品以 [#1](https://github.com/xiaocheny214/verso/issues/1) / [`product-proposal.md`](product-proposal.md) 为准；分层以 [#5](https://github.com/xiaocheny214/verso/issues/5) / [`architecture.md`](architecture.md) 为准；登录与 `article.sync` 事件以 [#10](https://github.com/xiaocheny214/verso/issues/10) / [`identity.md`](identity.md) 为准。本文只定 article 这一个增量，不夹带实现代码。

## 1. Summary

给 Verso 加上站内文章池：登录后的 `article.sync` 用知乎 `user/contents` 把授权用户的公开创作 upsert 进 `articles`；池空时用 `zhihu_search` 预填演示文，且 **响应与表都必须带 `source=zhihu_search`**。没有可入池条目时 **不写空行**。本期 **不建评论表**。

## 2. User Stories / Motivation

- 两名读者打开摸鱼流，能看到可点开的文章（标题、摘要、原文链接、作者），并能用同一篇当地图开局。
- 刚授权的答主，其公开文章 / 回答出现在站内层；作者已入驻，文下可以邀请（仍须在场，由 `presence` 判断）。
- 刚授权但没有任何公开创作的用户，登录成功、有 `users` 行，流里 **不出现** 空白卡片，库里 **没有** 挂在他名下的空文章。
- 评审能一眼看出哪些条目来自搜索冷启动：UI 标明来源，未入驻作者不可邀。

共同需要：服务端有一份可当房间地图的文章索引，来源可分、身份可对上、空结果可安全忽略。

## 3. Current Workaround

`server.article` 只有占位。没有池则演示只能手工塞文章 ID；授权后的创作进不了站内层；搜索结果若当正文用，会和已入驻作品混在一起，也说不清「立足于知乎」的边界。

## 4. Goals

- 消费 `article.sync` 与 `POST /articles/sync`，按 `user/contents` upsert 站内层。
- 池不足以撑 Demo 时，用 `zhihu_search` 种子冷启动层，列表 / 详情带 `source`。
- `GET /articles`、`GET /articles/{id}` 能给摸鱼流和地图用；匿名可读。
- 空列表、缺字段条目、非地图类型一律不落库。
- 明确不建 `comments` / `article_comments`。

## 5. Out of Scope

- 克隆知乎首页、站内全文搜索框、每次列表请求打搜索。
- 未授权拉取任意知乎用户的完整创作；爬 `www.zhihu.com/api/v4`。
- 关注 / 收藏入池；`pin` / `zvideo` / `question` 入池。
- 评论楼、精选评论落库、把知乎评论当在场或邀请对象。
- `FeedRanker` 真实推荐；读者—文章关系表（那是 `presence`）。
- 站内发布文章；写入知乎。
- 实现 `presence` / `invite` / `room`。

## 6. Proposal

### 6.1 Design Rule

**文章池是索引，不是知乎镜像。能当地图的才入库；来源必须可分；评论不是本域。**

```text
identity 发 article.sync {user_id}
  → worker 读 oauth:zhihu:{user_id}
  → user/contents（仅 article / answer）
  → 有 Title + 可解析身份 → upsert articles（source=user_contents）
  → Items 空或全不可用 → 成功，零行写入

池仍不够撑 Demo
  → 一次性 zhihu_search 种子
  → source=zhihu_search，UI 必标明
  → 不按昵称把作者判成已入驻

评论数可作快照；评论正文不进 Postgres。
```

同一知乎内容一行。冷启动行被作者本人同步到时，**升级**为 `user_contents` 并挂 `author_user_id`，不降级、不复制。

### 6.2 Syntax / API / Interface

| 方法 | 路径 | 谁可调 | 行为 |
|---|---|---|---|
| `GET` | `/articles` | 匿名 | 分页列表；站内层优先，其次冷启动；每条带 `source` |
| `GET` | `/articles/{id}` | 匿名 | 地图字段 + 作者入驻标记 + `source`；无评论列表 |
| `POST` | `/articles/sync` | 已登录 | 同步当前用户 `user/contents`；与登录事件走同一用例 |

冷启动 **不是** 新的公开 HTTP。Worker / bootstrap 在池为空（或站内层为零）时跑 `article.seed`，禁止在 `GET /articles` 里现场搜。

包边界：`web.api.articles` 只做 HTTP；用例在 `server.article`；知乎 HTTP 在 `framework.providers.zhihu` 的 Contents / Search 客户端。`web` / `worker` 不直连知乎。`server.feed` 只提供默认 `FeedRanker`（站内层 > 冷启动，再 `synced_at` 倒序）；算法仍是 incoming。

```text
VERSO_COLD_START_QUERIES          # 种子关键词；未配置则不搜、不写假文
VERSO_ARTICLE_SYNC_MAX_ITEMS      # 单次同步上限，建议 100
VERSO_ARTICLE_SYNC_DEBOUNCE_SEC   # 同用户去抖
```

客户端（业务只吃 DTO，不读原始 JSON 大小写）：

```text
ContentsClient.list_contents(access_token, content_type, offset, limit)
  → { items: [ContentCard], next_offset?, is_end }

SearchClient.search(query, count)
  → [SearchCard]

ContentCard / 入池最小集：
  content_type, url, title, summary?, created_at?
  # user/contents 无作者字段：作者 = 当前 users 行
  # 无 ContentID：从 canonical URL 解析；失败则丢弃

SearchCard：
  content_type, content_id, url, title, summary
  author_name, author_avatar_url
  # 搜索通常无 author url_token：author_user_id 保持空
```

`ContentType` 规范成小写。只接受 `article`、`answer`。

### 6.3 Examples as Specification

**当前：** 无文章表、无同步。

**提案主路径（规范，不是示意）：**

```text
登录成功
  publish article.sync { user_id }

worker
  grant = Redis oauth:zhihu:{user_id}
  无 grant → 跳过，不写库，不改成调用方自己的创作
  GET /api/v1/user/contents
      ContentType=article|answer（可两次或 all 再过滤）
      Authorization: Bearer <Access Secret>
      X-OAuth-Token: <user access_token>
      X-Request-Timestamp: <unix>
  对每条：
      规范化 URL（去掉 utm_*）
      解析 (content_type, content_id)
      title 空白或无法解析身份 → skip
      UPSERT articles
        source = user_contents
        author_user_id = 当前用户
        author_url_token / display_name / avatar 来自 users
  Items=[] → commit 零行，记 Redis 去抖，返回 synced=0
```

**冷启动种子：**

```text
COUNT(*) articles == 0 或 source=user_contents 的行数为 0
  且配置了 VERSO_COLD_START_QUERIES
  GET /api/v1/content/zhihu_search?Query=...&Count<=10
      Authorization: Bearer <Access Secret>
      # 不传 X-OAuth-Token
  可入池条目 UPSERT，source=zhihu_search，author_user_id=NULL
  搜索空 → 仍零行，不插入占位文
```

**`GET /articles` 条目（已登录或匿名相同形状）：**

```json
{
  "id": "uuid",
  "source": "user_contents",
  "content_type": "article",
  "title": "…",
  "summary": "…",
  "canonical_url": "https://zhuanlan.zhihu.com/p/123",
  "comment_count": 12,
  "author": {
    "user_id": "uuid",
    "display_name": "…",
    "avatar_url": "https://…",
    "url_token": "…",
    "settled": true
  }
}
```

冷启动条目：`"source": "zhihu_search"`，`author.user_id` 为 `null`，`settled: false`。前端必须展示来源，不能只靠作者昵称暗示入驻。

不返回 Access Secret、OAuth token、搜索 `CommentInfoList`。

**等价形态：** 同一 `(content_type, content_id)` 再次同步 → 更新标题 / 摘要 / `synced_at`，**不**新建 `articles.id`。先搜索、后作者登录同步 → **同一行** `source` 改为 `user_contents`，补上 `author_user_id`。

**无效：** 无 title；URL 无法解析身份；`pin` / `zvideo` / `question`；用作者昵称匹配 `users.display_name` 当作入驻。均不入库或不得把 `settled` 打成 true。

### 6.4 Boundary Cases

| 情况 | 行为 |
|---|---|
| 用户无公开 article/answer | 同步成功，`synced=0`，不写空 title/url 行，不删他人文章 |
| 部分条目缺字段、其余合法 | 只 upsert 合法条；非法条跳过 |
| 知乎 token 过期 / 无 grant | 跳过同步；已有池保留；提示重新授权（文案由 identity 侧） |
| 匿名读列表 | 可以；含冷启动；不能 `POST /articles/sync` |
| 冷启动作者与某 `users.display_name` 同名 | 仍 `settled=false`；入驻只认 `url_token` / 本人 `user/contents` |
| 搜索 URL 带 UTM | 入库前剥掉；与授权同步的 canonical URL 对得上则同一行 |
| 池已有站内层，仍想补搜索 | 不在每次 GET 补；种子只在「不够撑 Demo」的显式 `article.seed` |
| 读者打开文章 | 不在 `articles` 写阅读关系；交给 `presence` |
| `comment_count` 变化 | 同步时覆盖快照；不因此建评论行 |
| 搜索带回 `CommentInfoList` | 丢弃，不落库、不进 API |

入驻作者能否被邀：`settled=true` 只表示作者有 `users` 行。能否出现在邀请列表仍看该 `article_id` 上的在场。

## 7. Error Handling

| 条件 | 行为 |
|---|---|
| 未登录调 `POST /articles/sync` | 未认证，不打知乎 |
| 无 grant / 用户数据 `20001` | 跳过；不写空文；不冒充调用方创作 |
| `user/contents` 或搜索 `30001` / `30002` | 中止本轮，保留已 upsert 的合法行；下次去抖后再试 |
| 冷启动未配置关键词 | 不调用搜索，不写占位文 |
| 详情 ID 不存在 | 404；不拿该字符串去搜知乎 |
| 密钥出现在日志 / 前端 / 仓库 | 视为缺陷 |

## 8. Compatibility

加法。依赖 `users`（[#10](https://github.com/xiaocheny214/verso/issues/10)）已存在才能挂 `author_user_id`。实现顺序：identity 表 → 本模块迁移 → 再接事件。当前无文章数据、无迁移冲突。回滚：停同步与种子即可；已写入的 `articles` 可留。

## 9. Alternatives Considered

### 9.1 建评论表，详情下挂知乎评论

`user/contents` 只有 `CommentCount`，没有评论文本 API。搜索的 `CommentInfoList` 是精选片段，不是楼中楼。产品地图字段是标题 / 摘要 / 链接 / 作者；社交在场是 `presence` + `invite`，房内消息在 Redis 且销毁。再建评论表等于镜像知乎，且无稳定回源协议。故 **不建**。需要外链讨论时用 `canonical_url`。

### 9.2 无创作的用户插一行空文章，避免「没数据」

空 title / 空 URL 不能当地图，列表会出现空白卡片，邀请会绑到无效 `article_id`。空同步的正确语义是 **零行**。用户仍在 `users` 里，可以去读别人的文、上报在场。

### 9.3 列表接口现场 `zhihu_search`

额度会打在每一次摸鱼下滑上。冷启动是种子，结果进 Postgres，GET 只读库。来源靠 `source` 字段，不靠「这次是不是搜来的」。

### 9.4 读者—文章多对多表

「谁在读这篇」是在场，有 TTL，不是所有权。所有权用 `author_user_id` 一列即可。

## 10. Testing Strategy

| 用例 | 方法 |
|---|---|
| 有创作账号同步后列表出现其文，`source=user_contents`，`settled=true` | 单测 mock ContentsClient |
| `Items=[]` 或全是 pin：零 INSERT，用户行仍在 | 单测断言 SQL / 仓储未写 |
| 缺 title / 不能解析 ID 的条目跳过，其余入库 | 夹具混合页 |
| 搜索种子 `source=zhihu_search`，API 带该字段；同名不 settled | mock SearchClient |
| 先搜索后本人同步：同一 `articles.id`，source 升级 | upsert 单测 |
| 无 grant 不写库、不改他人文 | 与 identity 事件约定对齐 |
| GET 不触发搜索；未配关键词不调用搜索 | 调用计数 |
| 响应与仓库无密钥、无 `CommentInfoList` | 契约夹具 |

## 11. Summary of Changes

| 区域 | 变更 |
|---|---|
| 本文 | 冻结 article 契约；后续 `feat` 按此实现 |
| 以后才写的代码 | 迁移 `articles`；Contents/Search 客户端；`ArticleService`；3 个 HTTP；消费 `article.sync`；空池 `article.seed` |
| 不改 | identity 协议、`presence` 状态机、前端仓库（前端只消费 `source`） |
| 不建 | `comments`、`article_comments`、`user_articles` |

实现顺序：客户端 mock → `articles` 迁移 → upsert / 空跳过 → 事件消费 → 列表详情 → 种子。缺 grant 不要写库。

---

## Data model

Postgres 只加 **一张** `articles`。不建评论表，不建读者关联表。

```sql
CREATE TYPE article_source AS ENUM ('user_contents', 'zhihu_search');
CREATE TYPE zhihu_content_type AS ENUM ('article', 'answer');

CREATE TABLE articles (
    id                   UUID PRIMARY KEY,
    source               article_source NOT NULL,
    zhihu_content_type   zhihu_content_type NOT NULL,
    zhihu_content_id     TEXT NOT NULL,
    canonical_url        TEXT NOT NULL,
    title                TEXT NOT NULL,
    summary              TEXT NOT NULL DEFAULT '',
    author_user_id       UUID REFERENCES users (id),
    author_url_token     TEXT,
    author_display_name  TEXT NOT NULL,
    author_avatar_url    TEXT,
    comment_count        INTEGER NOT NULL DEFAULT 0,
    published_at         TIMESTAMPTZ,
    synced_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT articles_zhihu_identity_key UNIQUE (zhihu_content_type, zhihu_content_id),
    CONSTRAINT articles_canonical_url_key UNIQUE (canonical_url),
    CONSTRAINT articles_title_not_blank CHECK (length(btrim(title)) > 0),
    CONSTRAINT articles_url_not_blank CHECK (length(btrim(canonical_url)) > 0),
    CONSTRAINT articles_author_name_not_blank CHECK (length(btrim(author_display_name)) > 0)
);

CREATE INDEX articles_source_synced_idx
    ON articles (source, synced_at DESC);
CREATE INDEX articles_author_user_id_idx
    ON articles (author_user_id)
    WHERE author_user_id IS NOT NULL;
```

| 列 | 含义 |
|---|---|
| `id` | 站内主键；在场 / 邀请 / 房间都引用它 |
| `source` | `user_contents` 站内层；`zhihu_search` 冷启动，UI 必标 |
| `zhihu_content_type` + `zhihu_content_id` | 知乎身份；upsert 键 |
| `canonical_url` | 去 UTM 后的原文链接；地图外链 |
| `title` / `summary` | 地图文案；summary 可空字符串，title 不可空 |
| `author_user_id` | 已入驻才有；冷启动为 NULL |
| `author_url_token` | 入驻匹配键；搜索常缺，禁止用昵称补 |
| `comment_count` | 知乎侧计数快照，**不是**评论实体 |

```text
article:sync:{user_id}    TTL=去抖窗口    上次成功同步（含 synced=0）
article:seed:lock         短 TTL          防止并发种子
```

不建：`comments`、`article_comments`、`user_articles`、全文列、推荐特征表。

URL 解析（实现时按实测补正则，失败则 skip）：

| 类型 | canonical 形态 | `zhihu_content_id` |
|---|---|---|
| article | `https://zhuanlan.zhihu.com/p/{id}` | `{id}` |
| answer | `https://www.zhihu.com/answer/{id}` 或 `.../question/{q}/answer/{id}` | 回答 `{id}` |

搜索结果优先用返回的 `ContentID`，仍要与剥 UTM 后的 URL 一致。

## Architecture

| 模块 | article 提供 / 依赖 |
|---|---|
| `identity` | 发 `article.sync`；本模块读 grant，不写 `users` |
| `web` | 三个 HTTP；列表可匿名 |
| `worker` | 消费 `article.sync`、跑 `article.seed` |
| `presence` | 只认 `articles.id`；本模块不写在场 |
| `invite` / `room` / `map` | 用地图字段；无文章不建房（由它们校验） |
| `feed` | 默认排序端口；本模块不实现推荐 |

回滚：关掉同步与种子即回到空池。已写入行可留。

## Open Questions

1. `user/contents` 的 URL 是否还有未覆盖形态。适配器解析失败就丢弃该条；若大量丢弃导致 Demo 无文，再补解析，不改表模型。
2. Demo 种子关键词不写死在本规格，只走配置。选哪些词由演示脚本另定。
3. 平台若日后提供评论列表 API，仍须单独提案；本模块的「不建评论表」不自动放开。
