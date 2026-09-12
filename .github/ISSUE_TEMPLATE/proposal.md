---
name: 模块提案（完整规格）
about: 工程提案，不是实现任务。正文与 docs/<module>.md 同一份。
title: ""
labels: ["proposal", "FullSpec"]
---

本 Issue 是 **<模块> 的工程提案**，不是实现任务。正文与 PR 中 `docs/<file>.md` **同一份**。
请按此评审。通过后合入该文档；不要在本 Issue 里开写实现。

---

<!--
docs/<file>.md 只保留下面从「# Proposal」起的正文。
不要把本文件的 YAML frontmatter 和上面三行 Issue 说明写入文档。
架构 / 数据模型 / 协议按需补 DDL、Redis key、包边界、Open Questions；不需要的章节删掉。
-->

# Proposal: <具体变化>

## 1. Summary

一段话：改什么、作用范围、本提案只定哪一个增量。

## 2. User Stories / Motivation

具体故事或工作流。再写出它们底下的共同需求。

## 3. Current Workaround

现在怎么做，以及还剩哪些重复劳动或不一致。没有则写 `none`。

## 4. Goals

- Goal 1
- Goal 2

## 5. Out of Scope

- 本提案故意不解决的
- 留给后续提案的
- 这里不改的相邻系统

## 6. Proposal

### 6.1 Design Rule

一条核心规则或不变量。

### 6.2 Syntax / API / Interface

实现者能直接开工的契约（HTTP、表、Redis、错误表等）。

### 6.3 Examples as Specification

例子即规范，不要当装饰。写清：当前形态 / 提案形态 / 无效形态。

### 6.4 Boundary Cases

合法、非法、缺省、冲突、回退。

## 7. Error Handling

| Condition | Behavior |
|---|---|
|  |  |

## 8. Compatibility

加性 / 破坏性 / 可选 / 需迁移 / 按版本开关。

## 9. Alternatives Considered

### 9.1 <Alternative>

为何考虑、为何不用。

## 10. Testing Strategy

| Test case | Method |
|---|---|
| 正常路径 |  |
| 错误路径 |  |
| 兼容性 |  |

## 11. Summary of Changes

| Area | Change |
|---|---|
|  |  |

## Open Questions

不确定的放这里，不要假装已闭合。没有则删本节。
