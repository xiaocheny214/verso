# 示例：identity 提案

对照 [#10](https://github.com/xiaocheny214/verso/issues/10) 与 [PR #11](https://github.com/xiaocheny214/verso/pull/11)。

## 做对的

1. 产品 [#1] 要知乎登录；工程 [#5] 已定 Cookie Session。本增量只定 identity，不重写整仓架构。
2. `docs/identity.md` 按 `.github/ISSUE_TEMPLATE/proposal.md` 写完整规格：一条规则（OAuth 发卡、Session 记登录）、接口表、主路径例子、`users` DDL。
3. 提案 PR 只有 `docs/identity.md`。登录代码留给后续 `feat`。
4. Issue 正文贴文档全文，reviewer 不用只靠「请看 PR」。
5. 提交说明过长导致 commitlint 失败后，收成一条短提交再推。

## 不要做的

- 在对外提案里引用内部教程链接。
- 把 Issue 收成短摘要，与 `docs/identity.md` 两套正文。
- 从 `feat/#8-...` 开 `docs/#10-...`，把骨架 diff 带进提案 PR。
- 提案 PR 里同时加 migration / OAuth 客户端。
