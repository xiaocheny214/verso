# Proposal: 知乎 OAuth 登录与站内 Cookie Session

本提案对应 [#10](https://github.com/xiaocheny214/verso/issues/10)。产品以 [#1](https://github.com/xiaocheny214/verso/issues/1) / [`product-proposal.md`](product-proposal.md) 为准；分层以 [#5](https://github.com/xiaocheny214/verso/issues/5) / [`architecture.md`](architecture.md) 为准。本文只定 identity 这一个增量，不夹带实现代码。

## 1. Summary

给 Verso 加上知乎黑客松 OAuth 登录：浏览器只持有 HttpOnly Cookie；服务端用 Redis session 指认 `users.id`；知乎 `access_token` 只在后端短存，用来取名片并触发 `article.sync`。本期只建一张业务表 `users`。

## 2. User Stories / Motivation

- 两位读者用不同知乎账号打开站点，各自看到自己的昵称和头像，并能被邀请。
- 同一知乎账号第二天再登录，仍是同一个 `users.id`，战绩连续。
- 未登录可以下滑摸鱼流；不能上报在场、不能发邀请、不能进业务 WS。
- 登录成功后，该用户的公开创作应进入文章池（由 `article` 消费事件，本提案不实现拉文）。

共同需要：服务端能稳定指认「这是哪个已入驻用户」，且浏览器拿不到知乎凭证。

## 3. Current Workaround

`server.identity` 只有占位。没有登录则在场 / 邀请 / 房间都无法做；演示只能手工塞 `user_id`，两人无法用真实知乎账号走主路径。

## 4. Goals

- 走完知乎 Authorization Code，页面能展示昵称、头像。
- HTTP 与 WebSocket 共用同一 Cookie Session，登出 / 封禁立即失效。
- 按 `zhihu_url_token` upsert `users`；提供 `GET /me` 与纪要偏好 PATCH。
- 登录成功发布 `article.sync`；identity 不写文章表。

## 5. Out of Scope

- 站内 JWT、refresh token 对、把 token 交给前端。
- 邮箱密码、手机号、多 IdP、账号合并。
- RBAC 五表、运营后台、局内角色（读者 / 答主 / 同读属 `match`）。
- OAuth token 落 Postgres、`provider_credentials`、sessions 表。
- 实现 `user/contents` 同步、关注 / 收藏画像。
- 爬 `www.zhihu.com/api/v4`；用 CLI Access Secret 给访客登录。

## 6. Proposal

### 6.1 Design Rule

**知乎 OAuth 只证明「哪个知乎用户」；Verso 的登录态是 Cookie Session。**

```text
知乎 access_token  → 后端短凭证（TTL ≈ expires_in，约 1h）→ 取名片 / 供 article.sync
Cookie Session     → 站内权威身份（Redis，可撤销）
users 行           → 稳定主键与名片快照
```

认证看 session，不看知乎 token 是否还有效。授权本期只有匿名 / 已登录 / 封禁；「是否在某篇文章在场」由 `presence` / `invite` 判断，不进权限表。

### 6.2 Syntax / API / Interface

| 方法 | 路径 | 谁可调 | 行为 |
|---|---|---|---|
| `GET` | `/auth/zhihu/url` | 匿名 | 种 intent Cookie，302 知乎授权页 |
| `GET` | `/auth/zhihu/callback` | 须带 intent | 换票、upsert、种 session、发 `article.sync`、302 前端 |
| `POST` | `/auth/logout` | 已登录 | 清 session / grant / Cookie |
| `GET` | `/me` | 已登录 | 名片 + 偏好 |
| `PATCH` | `/me/preferences` | 已登录 | 只改 `summary_generate`、`summary_auto_save` |

包边界：`web.api.auth` 只做 Cookie / 302；用例在 `server.identity`；HTTP 换票与取名片在 `framework.providers.zhihu.OAuthClient`。`web` / `worker` 不直连知乎。

```text
ZHIHU_OAUTH_APP_ID
ZHIHU_OAUTH_APP_KEY            # 密钥，仅换票表单
ZHIHU_OAUTH_REDIRECT_URI       # 与活动页逐字符一致
ZHIHU_ACCESS_SECRET            # 密钥；取名片 / 用户数据
VERSO_SESSION_COOKIE=verso_session
VERSO_SESSION_TTL_SEC
VERSO_PUBLIC_ORIGIN
```

`OAuthClient`：`authorization_url(state)`、`exchange_code(code)`、`fetch_profile(access_token)`。业务只吃 `ZhihuProfile{ url_token, name, avatar_url, headline? }`。

### 6.3 Examples as Specification

**当前：** 无登录。  
**提案主路径（规范，不是示意）：**

```text
GET /auth/zhihu/url
  Set-Cookie: verso_oauth_intent=<nonce>; HttpOnly; Secure; SameSite=Lax
  302 https://openapi.zhihu.com/authorize
      ?redirect_uri={登记值}&app_id={app_id}&response_type=code&state=<nonce>

知乎回调  {redirect_uri}?authorization_code={code}

GET /auth/zhihu/callback
  POST https://openapi.zhihu.com/access_token
       grant_type=authorization_code
       code=<authorization_code>          # 表单字段名是 code
  fetch_profile(access_token)
  upsert users by zhihu_url_token
  Set-Cookie: verso_session=<sid>; HttpOnly; Secure; SameSite=Lax; Path=/
  Redis session:{sid} = {user_id}
  Redis oauth:zhihu:{user_id} TTL=expires_in
  publish article.sync {user_id}
  302 前端已登录页
```

协议按黑客松实测，不要按通用 OAuth 文档猜：

| 点 | 规范 |
|---|---|
| 回调 query | 主路径 `authorization_code`，兼容 `code` |
| 换票表单 | 字段必须叫 `code`；`grant_type` 写死，不从回调读 |
| 成功 | 看有没有 `access_token`；`code: 20000` 不是失败 |
| `state` | 我们仍发送；平台可能不回传，见 6.4 |
| 用户数据 | `Authorization: Bearer <Access Secret>` + `X-OAuth-Token` + `X-Request-Timestamp` |
| 凭证 | `app_id` / `app_key` / OAuth token / Access Secret 不混用 |

**等价形态：** 同一 `zhihu_url_token` 再次登录 → 更新名片和 `last_login_at`，**不**新建 `users.id`。同一 `user_id` 只保留一枚 sid（新登录踢旧会话）。

**`GET /me`（已登录）：**

```json
{
  "id": "uuid",
  "display_name": "…",
  "avatar_url": "https://…",
  "headline": null,
  "zhihu_url_token": "…",
  "preferences": { "summary_generate": true, "summary_auto_save": false }
}
```

不返回 access token、sid、`app_key`、Access Secret。禁止写入 `localStorage`。

**无效：** 回调无 code；profile 无 `url_token`；无 intent Cookie；`status != active`。均不种 session。

### 6.4 Boundary Cases

| 情况 | 行为 |
|---|---|
| 匿名 | 可 `GET /articles`；`GET /me` 未认证；不上报在场 |
| 已登录且 `active` | Cookie 指向 `users.id`；可邀请 / WS |
| `banned` / `deleted` | 清 Cookie，视为匿名 |
| 知乎 token 过期、session 仍在 | 可逛、可邀请；`article.sync` 跳过，提示重新授权 |
| 平台不回 `state` | callback 必须带 `verso_oauth_intent`；nonce 对不上则拒绝 |
| 一用户两浏览器 | 后者踢前者 |
| 作者是否可邀 | 文章作者 `url_token` 已有 `users` 行；不靠昵称 |

登录 CSRF：intent Cookie 挡住「别人的 code 丢到我的浏览器」。挡不住「我已点登录后的 code 竞态」——code 一次性、换完作废。写操作另校 `Origin` / CSRF；`SameSite=Lax` 是纵深（`Strict` 会丢授权回调）。

取名片：映射只放在 `fetch_profile`。官方没有稳定「当前用户」schema；拿不到 `url_token` 则失败。禁止用 Access Secret 所属账号冒充刚授权用户。`Gender` 不落库。

## 7. Error Handling

| 条件 | 行为 |
|---|---|
| 未配置 `APP_ID` / `APP_KEY` / `REDIRECT_URI` | `/auth/zhihu/url` 失败，不 302 残缺授权页 |
| 回调无授权码 / 换票失败 / 无 `url_token` | 停，不写库，不种 session |
| 用户拒绝授权 | 保持匿名 |
| 用户数据 `20001` 或 token 失效 | 删 grant；session 可留；同步失败 |
| 重复点回调 | 第二次换票失败；已有 session 则回已登录页 |
| Worker 读不到 grant | 跳过 `article.sync`，不改打成调用方自己的创作 |
| 密钥出现在日志 / 前端 / 仓库 | 视为缺陷；日志只打是否配置、长度、SHA-256 短前缀 |

## 8. Compatibility

加法。当前无登录用户、无迁移。Redis 丢数据 = 全员重新登录，Demo 可接受。`verso_common.UserPreferences` 已存在，补 `UserStatus` 即可。

## 9. Alternatives Considered

### 9.1 站内 JWT 当登录态

在场、登出、封禁、WS 都要立刻作废身份。JWT 默认做不到；做成黑名单等于再养一份 session。已有 Redis，不引入第二套机制。知乎 token 当不透明字符串，不解码、不进 Cookie。

### 9.2 Session 或 OAuth token 放浏览器 / Postgres

前端存储会被 XSS 读走。Token 进 Cookie 会把知乎凭证暴露给浏览器。Postgres 持久化 token 要加密与安全评审，本期 Redis TTL=`expires_in` 足够支撑登录后一次同步。

### 9.3 RBAC 或拆 `user_identities`

MVP 没有菜单权限。局内角色不是账号角色。一个知乎账号对应一行 `users` 即可。

## 10. Testing Strategy

| 用例 | 方法 |
|---|---|
| 两账号登录，`/me` 昵称头像不同且 `id` 稳定 | 单测 mock `OAuthClient`；演示用真 OAuth |
| 再登录不新建用户；第二浏览器踢第一 | 单测 upsert + session 替换 |
| 无 intent / 无 `url_token` / 换票失败 | 不写库、不种 Cookie |
| 登出后不能邀请；`banned` 清 Cookie | 中间件单测 |
| token 过期后 session 仍在，sync 跳过 | Redis TTL 单测 |
| 响应与仓库无密钥 | 契约 / 日志夹具 |
| 登录发一次 `article.sync` | 事件断言；不测文章入库 |

## 11. Summary of Changes

| 区域 | 变更 |
|---|---|
| 本文 | 冻结 identity 契约；后续 `feat` 分支按此实现 |
| 以后才写的代码 | 迁移 `users`；Redis intent / session / grant；`OAuthClient`；上述 5 个 HTTP；中间件；`article.sync` |
| 不改 | `article` 拉文实现、`presence` / `invite` 状态机、前端仓库 |

实现顺序：配置 → `OAuthClient`（全 mock）→ `users` 迁移 → Redis 三键 → `IdentityService` → 路由与中间件 → 发事件。缺密钥不要 302。

---

## Data model

Postgres 只加 **一张**表。Session 与 OAuth grant 不进库。

```sql
CREATE TYPE user_status AS ENUM ('active', 'banned', 'deleted');

CREATE TABLE users (
    id                  UUID PRIMARY KEY,
    zhihu_url_token     TEXT NOT NULL,
    zhihu_open_id       TEXT,
    display_name        TEXT NOT NULL,
    avatar_url          TEXT,
    headline            TEXT,
    status              user_status NOT NULL DEFAULT 'active',
    summary_generate    BOOLEAN NOT NULL DEFAULT TRUE,
    summary_auto_save   BOOLEAN NOT NULL DEFAULT FALSE,
    last_login_at       TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT users_zhihu_url_token_key UNIQUE (zhihu_url_token)
);

CREATE INDEX users_status_idx ON users (status);
```

| 列 | 含义 |
|---|---|
| `id` | Verso 主键；邀请 / 在场 / 房间 / 战绩都引用它 |
| `zhihu_url_token` | 登录幂等键；也是「作者是否入驻」的匹配键 |
| `zhihu_open_id` | 可空；平台没给就不要发明 |
| `display_name` / `avatar_url` | 每次登录可覆盖的快照 |
| `status` | `banned` 立刻不能持有 session；`deleted` 软删 |
| `summary_*` | 给 `match` 读；默认生成开、自动保存关 |

```text
oauth:intent:{nonce}       TTL 10min     ↔ Cookie verso_oauth_intent
session:{sid}              TTL 7d 滑动   ↔ Cookie verso_session
oauth:zhihu:{user_id}      TTL expires_in  加密后的 token
ws:ticket:{ticket}         ≤60s 一次性   仅当 WS 拿不到 Cookie
session:user:{user_id}     倒排当前 sid   用于踢旧会话 / 封禁
```

不建：`password_hash`、`roles`、`sessions`、`user_oauth_tokens`、`user_identities`。

## Architecture

| 模块 | identity 提供 |
|---|---|
| `web` 中间件 | `CurrentUser \| Anonymous` |
| `presence` | 仅 `active` 可 `join`；频道键 `user_id` |
| `invite` | `from_user_id` / `to_user_id` = `users.id` |
| `article` | 用 `url_token` 判断入驻；用 grant 拉 `user/contents` |
| `match` | 读两条纪要偏好 |
| `feed` | 不读身份 |

回滚：关掉 OAuth 路由即回到匿名可看流。已写入的 `users` 行可留。

## Open Questions

1. 「当前用户」profile 的官方 path / 字段仍未闭合。适配器先走联调或实测 `/user`；schema 变只改 `fetch_profile`。若长期没有 `url_token`，登录无法上线，需另开提案。
2. 平台若开始回传 `state` 或提供 PKCE / refresh / 撤销，在现有 intent 上加校验即可，不必改 session 模型。
3. 多端同时在场若成为产品需求，取消「一用户一会话」，另开提案。
