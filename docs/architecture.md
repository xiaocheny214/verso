# Verso 后端架构

产品规格以 [`product-proposal.md`](product-proposal.md) 和 [#30](https://github.com/xiaocheny214/verso/issues/30) 为准。领域划分以 [#31](https://github.com/xiaocheny214/verso/issues/31) 和 [`modules.md`](modules.md) 为准。

本期主路径只有一条：

```text
认证 → 画像 → 双向互补匹配 → 异步交流 → 质量评估 → 声望
```

旧的 `article / presence / invite / room / map / feed` 主路径已被取代，不再据此新增接口、表或任务。现存空包可以在后续清理 Issue 中删除，不能被当作当前规格。

## 一、仓库与运行单元

```text
verso/
├── frontend/                 # Next.js 前端
├── backend/                  # uv workspace
│   ├── packages/
│   │   ├── common/
│   │   ├── framework/
│   │   └── app/
│   ├── tests/
│   └── pyproject.toml
├── docs/
└── docker-compose.yml        # api / worker / postgres / redis
```

技术栈：FastAPI、PostgreSQL、Redis、Docker Compose。站内身份使用 HTTP-only Cookie Session；知乎 OAuth 负责认证与授权数据访问，知乎 token 只存服务端。

## 二、包分层

依赖只能向下。`web` 与 `worker` 同层且互不引用；两者只调用 `server`。领域逻辑不进入 router、provider 或任务消费者。

```text
verso_app.bootstrap
verso_app.web  |  verso_app.worker
verso_app.server
verso_framework
verso_common
```

| 包 | 职责 | 禁止 |
|---|---|---|
| `verso-common` | 枚举、异常、DTO/VO、统一响应、常量 | 依赖 FastAPI、DB、Redis 或知乎 |
| `verso-framework` | 配置、DB、Redis、任务端口、知乎/LLM provider、观测端口 | 写匹配、交流、质量或声望规则 |
| `verso-app` | `server` 领域服务、`web` HTTP 适配、`worker` 消费、`bootstrap` 装配 | 在入口层复制领域状态机 |

## 三、领域模块与所有权

| 模块 | 负责 | 不负责 |
|---|---|---|
| `auth` | OAuth、站内用户、授权数据、初始化声望 | 抽取擅长、决定匹配对象 |
| `portrait` | 从授权数据源生成擅长画像 | 登录、存 token、决定匹配对象 |
| `match` | 求知 Ticket、双向互补条件、配对结果 | 对话消息、回答质量、长期分数 |
| `exchange` | 一次配对关系、24 小时异步消息、结束状态 | 重新计算匹配、修改画像 |
| `quality` | 人先触发的回答评估、评估证据和裁决 | 自行监听每条消息、直接冻结资格 |
| `reputation` | 声望持久化、资格查询和变更 | 判断回答内容是否低质 |

`server` 内模块可以通过明确的服务接口调用，但每份状态只能有一个 owner：

- 用户、session 和授权 token 只由 `auth` 写。
- 画像只由 `portrait` 写。
- Ticket 和配对状态只由 `match` 写。
- Exchange 和消息只由 `exchange` 写。
- Review 只由 `quality` 写。
- Score 和 eligibility 只由 `reputation` 写。
- `quality` 产出裁决后调用 `reputation`，不直接更新其表。

## 四、主路径

```text
web ── OAuth ──► auth ──► 用户
web ── 授权数据 ──► portrait ──► 擅长画像
web ── 本次想学 ──► match.Ticket
match ── 双向 covers ──► Match ──► exchange.Exchange
web ── 异步留言 ──► exchange.Message
web ── 不满意 ──► quality.Review ──► reputation
```

关键约束：

- `auth` 只认账号和授权；`portrait` 的擅长画像和 `match` 的本次需求必须分开存储。
- `match(A, B)` 要求 `B.offer` 覆盖 `A.want`，同时 `A.offer` 覆盖 `B.want`。
- 用户提交未结束 Ticket 即主动进入匹配池，不通过实时在线状态找人。
- 配上后立即建立 Exchange；双方可以在不同时间留言。
- 没有人先表示不满意，`quality` 不执行模型评估。

## 五、身份与授权

身份契约由 `auth` 维护：

- OAuth intent、用户 access token 和站内 session 存 Redis，并设置 TTL。
- Access Secret、App Key、用户 token 不进入响应、日志、前端或仓库。
- Postgres 用户主键是站内稳定 ID，不能把展示名当主键。
- 登录成功时初始化 reputation 默认分；不写画像表。

画像契约由 `portrait` 维护：

- 读取 `auth` 保存的授权数据源（创作 / 关注 / 收藏），抽取 `stable` 与 `recent_7d`。
- 画像标签必须保留来源证据，并区分系统提取与用户自报。
- 外部数据读取失败不能伪装成成功画像；允许部分来源失败和显式重试。

## 六、匹配

`match` 的最小对象：

| 对象 | 含义 |
|---|---|
| `Ticket` | 用户本次想学的短描述、归一标签和生命周期 |
| `Match` | 两张互补 Ticket 的配对结果和匹配时间 |

规范条件：

```text
can_match(A, B) =
  A != B
  AND A.ticket.status == open
  AND B.ticket.status == open
  AND reputation.allows(A, B)
  AND covers(B.portrait.strengths, A.ticket.want)
  AND covers(A.portrait.strengths, B.ticket.want)
  AND no_open_exchange(A, B)
```

池子暂无匹配时保留 Ticket 并展示等待，不降级成同话题、同文章或单向答疑。

## 七、异步交流

`exchange` 持久化配对关系与其下的多轮消息：

- Exchange 只从成功 Match 创建，不能由前端直接指定任意两人。
- 消息属于某个 Exchange；不另存一份重复的“匹配关系”。
- 两边无需同时在线，离线后重新登录仍能读取消息。
- 交流有明确的开放、结束和过期状态；结束后拒绝新消息。
- MVP 是 1:1 文字互答，不做群聊、实时房间或阅后即焚。

## 八、质量与声望

顺序固定为：

```text
对方表示不满意 → quality 读取本次问题和回答 → good / poor / unclear
poor → reputation 记录影响
good / unclear / 模型失败 → 不处罚
```

- 一次 Exchange 对同一被评人只产生一次有效 Review。
- 被评人没有留下回答时，另走未回复规则，不伪造内容质量结论。
- 模型 provider 只负责调用；评估提示、判据和幂等规则属于 `quality`。
- `reputation` 对外暴露资格查询和变更用例；冻结阈值必须由产品规格或独立 Issue 冻结。

## 九、存储与异步任务

PostgreSQL 保存业务事实：用户、画像、Ticket、Match、Exchange、Message、Review、Reputation。具体表结构跟随各模块实现 Issue，不在总架构中提前冻结。

Redis 保存短期凭证、session、OAuth intent、用户授权 token、幂等键和必要缓存。它不是异步消息的唯一存储。

`worker` 只处理可重试的后台任务，例如画像同步、等待池重试、Exchange 过期和质量评估。业务状态变化仍通过对应 `server` 服务完成。

## 十、接口与契约

FastAPI 生成的 OpenAPI 是唯一接口契约。接口名称随实现 Issue 冻结，当前按资源分组：

- `auth / me` → `auth`
- `portrait` → `portrait`
- `tickets / matches` → `match`
- `exchanges / messages` → `exchange`
- `reviews` → `quality`
- `reputation / eligibility` → `reputation`

变更路由、参数、响应或状态枚举时，必须在同一 PR 更新实现、测试和生成契约。前端不得维护第二套手写模型。

## 十一、明确不做

- 同文章 Presence、在线读者列表、实时邀请、倒计时房间。
- Article Pool / Feed / Map 作为核心业务模块。
- 全站 WebSocket 在线状态和房间频道。
- AI 陪聊、每条消息实时评分、自动生成社交关系。
- RAG、推荐流、Agent 与 Agent 社交、动态密钥管理台。

任何要重新引入上述能力的改动，都必须先证明它服务双向互补主路径，并另开 Proposal；不能在实现 PR 中顺手带回。
