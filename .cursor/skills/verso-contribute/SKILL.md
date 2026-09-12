---
name: verso-contribute
description: >-
  Runs Verso's Proposal → Issue → branch → PR → review loop for module specs
  and implementation. Use when writing proposals, opening GitHub issues, landing
  docs-only or feat PRs, aligning Issue 正文 with docs/, fixing commitlint, or
  when the user says 提案、开 Issue、提 PR、写模块规格、identity、architecture.
---

# Verso 交付流程

本仓库按 `Proposal → Issue → 分支 → PR → Review → 合并` 推进。提案要让 reviewer 能拍板、实现者能开工、门禁能过。克隆与标签等细节以仓库根目录 `CONTRIBUTING.md` 为准；本 skill 补提案落地时容易漏的步骤。

## 权威文档

| 层级 | 去哪看 | 不要做 |
|---|---|---|
| 产品 | [#1](https://github.com/xiaocheny214/verso/issues/1) / `docs/product-proposal.md` | 把 incoming / 明确不做的能力夹带进 PR |
| 工程分层 | [#5](https://github.com/xiaocheny214/verso/issues/5) / `docs/architecture.md` | 在提案 PR 里写实现代码 |
| 模块规格 | `docs/<module>.md`（如 `docs/identity.md`） | 实现时另猜表结构或登录方案 |

知乎 `Access Secret` / OAuth `app_key` / token **禁止**写入仓库、Issue、PR、截图、前端、Agent 回复。只用占位符。

## 先分清：提案还是实现

| 类型 | Issue 标签 | 分支 | PR 内容 |
|---|---|---|---|
| 产品 / 模块规格 | `proposal` + `FullSpec` | `docs/#<n>-<slug>` | **只含文档**（通常 `docs/*.md`） |
| 按已通过规格写代码 | `feat`（不要标 `proposal`） | `feat/#<n>-<slug>` | 实现 + 测试；不改无关流程文档 |
| 修门禁 / 文案 | `ci` / `docs` / `fix` | 对应 type | 范围与 Issue 一致 |

同一件事拆两个 Issue：先提案（如 identity [#10](https://github.com/xiaocheny214/verso/issues/10)），通过后再开 feat。不要把骨架代码塞进提案 PR（[#5](https://github.com/xiaocheny214/verso/issues/5) 文档 vs [#8](https://github.com/xiaocheny214/verso/issues/8) 骨架）。

## 工作流

复制并勾选：

```text
- [ ] 读 #1 / architecture，确认本期范围
- [ ] 写一份增量提案（见下）
- [ ] 开 Issue：正文 = 提案全文
- [ ] 从 origin/main 开分支
- [ ] 提交仅提案文件（或仅实现文件）
- [ ] 推送并开 PR：Closes #<n>；Issue 与文件保持同一份
- [ ] 指定 reviewer；修门禁
- [ ] 提案改过之后同步 PATCH Issue 正文
```

### 1. 写提案

一个提案只定 **一个增量**。模块规格（登录、表、协议）用完整规格模板；小改动用短模板。

正文写进 `docs/<name>.md`，结构：

```md
# Proposal: <具体变化>

## 1. Summary
## 2. User Stories / Motivation
## 3. Current Workaround
## 4. Goals
## 5. Out of Scope
## 6. Proposal
### 6.1 Design Rule
### 6.2 Syntax / API / Interface
### 6.3 Examples as Specification
### 6.4 Boundary Cases
## 7. Error Handling
## 8. Compatibility
## 9. Alternatives Considered
## 10. Testing Strategy
## 11. Summary of Changes
```

架构 / 数据模型 / 协议再补：表 DDL、Redis key、包边界、Open Questions。

规则：

- 先用户故事和一条 Design Rule，再展开接口与表。
- 例子即规范（当前形态 / 提案形态 / 无效形态），不要当装饰。
- `Out of Scope` 必写。不确定的放 `Open Questions`，不要假装已闭合。
- 仓库对外文案不要引用内部阅读材料（教程站、私人笔记）。结论写成项目自己的理由。
- 提案要短到能评审；DDL 和接口表留给实现分支，不要再写教程腔。

提案思考模型以 [writing-proposals](https://github.com/minorcell/skills/tree/main/skills/writing-proposals) 为准（来源 [minorcell/skills](https://github.com/minorcell/skills)，安装：`npx skills add minorcell/skills`）。落地步骤仍走本文件。

### 2. 开 Issue

Issue **就是**给 reviewer 看的提案，必须与 `docs/` 文件对齐。

1. 先写好 `docs/*.md`。
2. Issue 标题具体，禁止空泛。
3. 正文 = 三行说明 + 文档全文：

```md
本 Issue 是 **<模块> 的工程提案**，不是实现任务。正文与 PR 中 `docs/<file>.md` **同一份**。
请按此评审。通过后合入该文档；不要在本 Issue 里开写实现。

---

<docs/<file>.md 全文>
```

4. 标签：`proposal` + `FullSpec`；指定 assignee。
5. 文档后来改了：立刻 PATCH Issue，保持同一份。不要把 Issue 收成「请看 PR」的短链——reviewer 常从 Issue 进。

实现 Issue 写背景、目标、验收；不要贴成提案。

### 3. 分支与提交

从 **最新 `origin/main`** 开分支（提案 PR 不要叠在未合并的 feat 分支上，否则会把别人的代码带进 diff）。

```text
<type>/#<issue>-<slug>
```

`type`：`feat` | `fix` | `docs` | `ci` | `chore` | `refactor` | `test` | `style` | `perf` | `revert`。slug 仅小写字母、数字、连字符。

提交说明 Conventional Commits。指向 `main` 的 PR 会用 `@commitlint/config-conventional` 检查 **范围内每一条** 提交：

- header 与 **正文每一行** ≤ 100 字符（比 CONTRIBUTING 写的 120 更严，以门禁为准）
- `type(scope): subject`，现在时，句末无句号
- 关联 Issue：`#12` 或 PR 正文 `Closes #12`

失败时：在本功能分支 `git reset --soft origin/main` 收成一条合规提交，再 `git push --force-with-lease`（禁止对 `main` 强推）。

### 4. 开 PR

- 标题与范围对应该 Issue；提案 PR **禁止**夹带 `backend/` / `frontend/` 实现。
- 正文写 Summary、`Closes #<n>`、Test plan（提案：能按文档实现；无实现文件）。
- 指定至少一名有写权限的 reviewer。合入 `main` 必须他人 Approve。
- 未合并代码禁止部署演示 / 生产。

GitHub：优先 `gh`。本机没有时用 API + `git credential fill` 的 token，**不要**把 token 打进回复或文件。

## 模块提案（identity 一类）

`docs/architecture.md` 已切模块时，下一刀只定该模块：

- 与上下游的边界（identity 不写文章表，只发 `article.sync`）
- 实现者能直接开工的契约：HTTP、表、Redis、错误表
- 知乎协议按黑客松 / 开放平台事实源，不要猜通用 OAuth 或爬 v4

实现另开 `feat` Issue，按已合入的 `docs/<module>.md` 开发。

## 完整示例

identity 提案循环见 [examples.md](examples.md)。
