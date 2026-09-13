# 参与贡献 / Contributing

欢迎参与 [Verso（背叶）](https://github.com/xiaocheny214/verso)

项目按 `Proposal → Issue → 分支 → PR → Review → 合并` 推进：所有改动从 Issue 出发，代码经 PR 合入 `main`。第一次参与，按本文档顺序读下来即可跑通全流程。

产品规格以 [#30 产品策划案](https://github.com/xiaocheny214/verso/issues/30) 与 [`docs/product-proposal.md`](docs/product-proposal.md) 为准。后端包分层与领域边界以 [`docs/architecture.md`](docs/architecture.md) 与 [#31](https://github.com/xiaocheny214/verso/issues/31) 为准（提案只写文档，代码另开 feat Issue）。本期只打磨最小 MVP 主路径（认证 → 画像 → 双向互补匹配 → 异步交流 → 质量评估）。同文章在场、实时邀请、限时房间、Feed 与 Map 已退出范围，不要用 PR 夹带进来。

## 许可

本仓库使用[专有商业许可](LICENSE)。向本仓库提交代码、文档或其他材料，即表示你同意：

- 贡献按该许可由项目著作权人持有与使用；
- 不得把仓库代码用于未经授权的生产或商业分发。

评审、演示或黑客松评委查看源码，不构成任何许可授权。

## 开始之前：克隆、Fork 与上游同步

主仓库：`https://github.com/xiaocheny214/verso`

- **已加入协作者、对主仓库有写权限**：直接从 `origin` 拉 `main`、开分支、向主仓库提 PR。
- **没有写权限**：Fork 到个人账号，开发分支只放在自己的 fork 上，再向主仓库提 PR。

Fork 协作时，先把仓库拉到本地并连上上游：

```bash
git clone git@github.com:<你的账号>/verso.git
cd verso
git remote add upstream git@github.com:xiaocheny214/verso.git
```

有写权限时：

```bash
git clone git@github.com:xiaocheny214/verso.git
cd verso
```

开新分支、提 PR 之前，先同步 `main` 再开分支：

```bash
git fetch origin
# Fork 协作把 origin 换成 upstream
git checkout main
git rebase origin/main
git checkout -b <类型>/#<issue号>-<短英文名>
```

分支名示例：`feat/#34-identity-oauth`、`feat/#36-mutual-match`、`docs/#30-canonical-proposal`、`ci/#2-naming-conventions`。

指向 `main` 的 PR 会检查分支名。`main` 本身不走这条规则。

## 提交说明

提交说明使用 Conventional Commits：

```text
type(scope): subject

可选正文：说明为什么改，而不是改了哪些文件。
```

- `type` 常用：`feat`、`fix`、`docs`、`ci`、`chore`、`refactor`、`test`、`style`、`perf`、`revert`。
- `scope` 可选，小写英文，如 `contributing`、`identity`、`match`、`exchange`。
- `subject` 用现在时、不以句号结尾；中英文均可。
- 解决某个 Issue 时，在 subject 末尾或正文写 `#12` / `Closes #12`。
- 第一行建议不超过 120 个字符。

示例：

```text
docs: bootstrap repository with license and product proposal
docs(contributing): add Proposal-to-merge collaboration guide
ci: enforce commit and branch naming (#2)
```

指向 `main` 的 PR 会用 commitlint 检查该分支上相对目标分支的全部提交。

## 本地开发与联调

当前仓库已有后端 workspace 骨架（[#8](https://github.com/xiaocheny214/verso/issues/8)），启动方式见 [`backend/README.md`](backend/README.md)。在此之前：

- 不要假设已有生产 API；本地联调只连本机或组内约定的开发环境，**禁止直连生产或把知乎 Access Secret / OAuth App Key 写入仓库、截图、Issue 或前端**。
- 知乎开放平台凭证只放在本机环境变量或安全密钥库；PR 里只用占位符。
- 接口一旦落地，契约与联调方式会补进 README；有疑问先查对应 Issue / PR，不要另开一套私下协议。

## 提 Issue

- 每个 Issue 写清背景、目标和验收标准，禁止空泛标题。
- 先确认 [#30](https://github.com/xiaocheny214/verso/issues/30) 的本期范围和 [#31](https://github.com/xiaocheny214/verso/issues/31) 的模块边界：明确不做的能力不要再开功能 Issue。
- 标签按工作类型挂，不要把实现 Issue 标成 `proposal`：
  - `proposal` / `FullSpec`：产品提案与完整规格（如 [#30](https://github.com/xiaocheny214/verso/issues/30)）
  - `feat`：产品功能
  - `bug`：缺陷
  - `ci`：门禁、工作流、提交 / 分支规范
  - `docs`：文档
  - `chore`：仓库杂务、不改产品行为的配置
- 每个 Issue 至少一枚类型标签，并指定 owner（assignee）。没有 milestone 的 Issue 默认不在当前计划内。
- 关闭 Issue 时注明原因：已被 PR 解决（注明 PR 号）/ 被其他 Issue 取代（注明替代者）/ 组内确认不再需要。
- 每个 Milestone 结束时归置遗留 Issue：已完成的关闭；划入下个 Milestone 的改挂并指定 owner；其余标明暂不计划。

## 提 PR

- 每个 PR 关联对应 Issue（例如 `Closes #2`），改动范围与 Issue 一致，不夹带无关改动。
- 合入 `main` 必须走 PR，且必须有至少一人 **Approve**。GitHub 已对 `main` 开保护：作者不能自己点同意，仓库创建者 / 管理员也不能绕过。没有他人 Approve，Merge 按钮不可用。
- 指向 `main` 的 PR 会检查提交说明与分支名；禁止直推 `main`。
- 提交后在 PR 里 @ 一位有写权限的队员来 Approve。合并仍由维护者点 Merge，但前提是已经有人同意。
- **禁止把未经 review / 未合并的代码部署到演示或生产环境。**

## 接口契约

工程尚未冻结 OpenAPI。接口代码出现后，前后端以仓库内唯一契约文件为准（由 `verso_app.web` 生成，禁止长期手写两套）。

后端是 uv workspace：`verso-common` → `verso-framework` → `verso-app`。领域逻辑只放 `server`。`identity / match / exchange / quality / reputation` 各自持有自己的状态；`server` 内模块通过明确服务接口协作。`web` / `worker` 只调 `server`，不直连 LLM 提供方。分层由 import-linter 约束包边界，不要为了图快让 web 去调 framework。

- 变更路由、参数、模型或描述时，在同一 PR 里更新契约并提交。
- 契约与实现不一致时，以「先改契约 Issue、再改代码」为序，不要在前端猜字段。

在契约文件落地前，接口讨论写在对应 Issue 里，避免口头约定。

## 发版

- Tag 统一使用 `vX.Y.Z`（语义化版本：破坏性变更进 major，新功能进 minor，其余进 patch）。
- 每个 Milestone 结束发一次 Release，描述列清本轮交付。
- 对外可访问的 Demo / 生产部署必须先发版本：打 Tag → 创建 Release（写清变更）→ 再部署。**任何部署只认 Release。**
- 在自动化发布落地前，发版由维护者手动执行。

## 规范本身

本文档自写入仓库时起对组内协作生效。需要修改时，先开 Issue 讨论，达成一致后再改本文档，不要在 PR 里顺手改流程。
