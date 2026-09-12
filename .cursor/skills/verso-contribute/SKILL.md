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

**填空结构不要写在本文件里。** 先读 GitHub 模板再填，禁止凭记忆另造一套章节：

| 要写什么 | 去读 |
|---|---|
| 模块规格 / 完整提案 | `.github/ISSUE_TEMPLATE/proposal.md` |
| 小改动提案 | `.github/ISSUE_TEMPLATE/proposal-short.md` |
| 按已通过规格实现 | `.github/ISSUE_TEMPLATE/feat.md` |
| PR 正文 | `.github/PULL_REQUEST_TEMPLATE.md` |

提案思考模型以 [writing-proposals](https://github.com/minorcell/skills/tree/main/skills/writing-proposals) 为准（来源 [minorcell/skills](https://github.com/minorcell/skills)，安装：`npx skills add minorcell/skills`）。落地步骤仍走本文件。

## 权威文档

| 层级 | 去哪看 | 不要做 |
|---|---|---|
| 产品 | [#1](https://github.com/xiaocheny214/verso/issues/1) / `docs/product-proposal.md` | 把 incoming / 明确不做的能力夹带进 PR |
| 工程分层 | [#5](https://github.com/xiaocheny214/verso/issues/5) / `docs/architecture.md` | 在提案 PR 里写实现代码 |
| 模块规格 | `docs/<module>.md`（如 `docs/identity.md`） | 实现时另猜表结构或登录方案 |

知乎 `Access Secret` / OAuth `app_key` / token **禁止**写入仓库、Issue、PR、截图、前端、Agent 回复。只用占位符。

## 先分清：提案还是实现

| 类型 | Issue 模板 | 标签 | 分支 | PR 内容 |
|---|---|---|---|---|
| 产品 / 模块规格 | `proposal.md` | `proposal` + `FullSpec` | `docs/#<n>-<slug>` | **只含文档**（通常 `docs/*.md`） |
| 小改动提案 | `proposal-short.md` | `proposal` | `docs/#<n>-<slug>` | 只含文档 |
| 按已通过规格写代码 | `feat.md` | `feat`（不要标 `proposal`） | `feat/#<n>-<slug>` | 实现 + 测试；不改无关流程文档 |
| 修门禁 / 文案 | （无专用模板则按 `CONTRIBUTING.md`） | `ci` / `docs` / `fix` | 对应 type | 范围与 Issue 一致 |

同一件事拆两个 Issue：先提案（如 identity [#10](https://github.com/xiaocheny214/verso/issues/10)），通过后再开 feat。不要把骨架代码塞进提案 PR（[#5](https://github.com/xiaocheny214/verso/issues/5) 文档 vs [#8](https://github.com/xiaocheny214/verso/issues/8) 骨架）。

## 工作流

复制并勾选：

```text
- [ ] 读 #1 / architecture，确认本期范围
- [ ] 读对应 `.github/ISSUE_TEMPLATE/`，写一份增量提案
- [ ] 用同一份模板开 Issue：正文与文档同一份
- [ ] 从 origin/main 开分支
- [ ] 提交仅提案文件（或仅实现文件）
- [ ] 读 PR 模板，推送并开 PR：Closes #<n>
- [ ] 指定 reviewer；修门禁
- [ ] 提案改过之后同步 PATCH Issue 正文
```

### 1. 写提案

一个提案只定 **一个增量**。模块规格（登录、表、协议）用 `proposal.md`；小改动用 `proposal-short.md`。

1. **Read** 对应 Issue 模板全文，按里面的章节填，不要从本 skill 复述目录。
2. 正文写进 `docs/<name>.md`：只取模板里从提案标题起的正文。**不要**写入 YAML frontmatter，也**不要**写入模板顶部的 Issue 说明。
3. 开 Issue 时再用同一份模板：顶部说明 + 文档全文，与 `docs/` **同一份**。

规则：

- 先用户故事和一条 Design Rule，再展开接口与表。
- 例子即规范（当前形态 / 提案形态 / 无效形态），不要当装饰。
- `Out of Scope` 必写。不确定的放 `Open Questions`，不要假装已闭合。
- 仓库对外文案不要引用内部阅读材料（教程站、私人笔记）。结论写成项目自己的理由。
- 提案要短到能评审；DDL 和接口表留给实现分支，不要再写教程腔。

### 2. 开 Issue

Issue **就是**给 reviewer 看的提案，必须与 `docs/` 文件对齐。

1. 先写好 `docs/*.md`。
2. 用对应模板开 Issue（`gh issue create --template proposal.md` 或 `proposal-short.md` / `feat.md`）。本机没有 `gh` 时：读仓库里的模板文件，按它填进 API。
3. Issue 标题具体，禁止空泛。
4. 提案：标签与模板 frontmatter 一致；指定 assignee。文档后来改了：立刻 PATCH Issue，保持同一份。不要把 Issue 收成「请看 PR」的短链——reviewer 常从 Issue 进。
5. 实现 Issue 用 `feat.md`：写背景、目标、验收，并链到已合入规格；不要贴成提案。

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

1. **Read** `.github/PULL_REQUEST_TEMPLATE.md`，按它填 Summary、`Closes #<n>`、Test plan。
2. 标题与范围对应该 Issue；提案 PR **禁止**夹带 `backend/` / `frontend/` 实现。
3. 指定至少一名有写权限的 reviewer。合入 `main` 必须他人 Approve。
4. 未合并代码禁止部署演示 / 生产。

GitHub：优先 `gh`。本机没有时用 API + `git credential fill` 的 token，**不要**把 token 打进回复或文件。

## 模块提案（identity 一类）

`docs/architecture.md` 已切模块时，下一刀只定该模块：

- 与上下游的边界（identity 不写文章表，只发 `article.sync`）
- 实现者能直接开工的契约：HTTP、表、Redis、错误表
- 知乎协议按黑客松 / 开放平台事实源，不要猜通用 OAuth 或爬 v4

实现另开 `feat` Issue（模板 `feat.md`），按已合入的 `docs/<module>.md` 开发。

## 完整示例

identity 提案循环见 [examples.md](examples.md)。
