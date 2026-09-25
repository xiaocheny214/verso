# Proposal: 用消息任务解耦慢作业

状态：**草案，待评审。** 本文只定第一刀：哪些调用改成消息任务、生产者和消费者怎样一起保证「业务效果只发生一次」。评审通过并明确开工之前，不改代码、不引入 RocketMQ 依赖。

## 1. Summary

仓库里没有 RocketMQ 方案。`verso_framework.mq` 只声明了 `MqPublisher` / `MqConsumer`，注释写「本期 Redis Stream，以后换 RocketMQ」，但没有任何实现，也没有任何文档。

现有异步只有画像同步：Redis List（`RPUSH` / `BLPOP`）加一把 pending 锁，和这个端口无关。文档处理、质量评估仍在 HTTP 请求里同步做完。

本提案把「必须跟一次数据库提交绑在一起、又不能堵在请求里」的慢作业，收成同一种投递结构。可靠性由生产者的本地消息表和消费者的消费记录共同完成。Broker 负责持久化和重投，不负责端到端只生效一次。

## 2. User Stories / Motivation

- 用户点「处理文档」。切块、embedding、写入 Milvus 可能要几十秒。请求应先记下「已受理」，完成后用现有 `document_process_runs` 查询结果。
- 用户登录后画像过期。同步要拉知乎并跑分类，不能挡住登录。失败后必须还能再跑，不能弹出队列就当成功。
- 同一份处理请求因超时被重投时，不能把同一篇文档写进 Milvus 两次，也不能把同一次低质判定扣两次成色。

共同需要：业务状态和「有一份待执行作业」要么一起提交，要么都不提交；作业可以投递多次，业务效果只应用一次。

## 3. Current Workaround

| 路径 | 今天怎么做 | 缺口 |
|---|---|---|
| 画像同步 | 登录后 `PortraitSyncQueue.enqueue`：`SET NX` pending，再 `RPUSH`。Worker `BLPOP` 后处理，`finally` 里 `ack` | 弹出后进程崩溃，消息已离开 List，pending 锁还在，直到 TTL 才可能再入队。处理失败也会 `ack`。数据库提交和入队不是同一个事务 |
| 文档处理 | `POST .../process` 同步跑完切块、embedding、Milvus | 请求时长等于外部调用时长。没有「已受理」和执行中的互斥 |
| 质量评估 | `QualityService.submit` 在同一次请求里调用模型，并写 review、改成色 | 模型慢，但判定和成色必须是一次提交。拆成两条消息会留下「有评审、没扣分」 |
| 匹配 | 条件配对成功后，同一次流程里 `exchange.open` | 配上了却没开会话，比慢更糟 |

`collect.enqueue_listed_contents` 只是把知乎列表写成采集记录，不是消息队列。`exchange` 里的留言是这对用户的持久化对话，也不进消息队列。

## 4. Goals

- 慢作业和 HTTP 请求拆开，调用方只依赖 `MqPublisher`。
- 一次业务提交附带一条待投递记录，投递失败可以重试，且 `event_id` 不变。
- 消费者在业务提交成功之后才确认消息。重复投递不再次改变业务结果。
- 所有作业共用一个事件结构。正文、向量、对话全文不放进消息。

## 5. Out of Scope

- 本提案不选择 RocketMQ 的部署形态，不写客户端，不改 `docker-compose`。
- 不把匹配和 `exchange.open` 拆开。
- 不把质量判定和成色改成两条消息。质量评估是否改成异步，留到用户能接受「先受理、再出结论」时另开提案。
- 不把 exchange 留言、采集列表登记、在场 / 房间 / Feed / Map 放进队列。后三类已退出 MVP。
- 不建设通用事件总线。没有第二个消费者的事实，先不发。

## 6. Proposal

### 6.1 Design Rule

一条规则：

**和数据库提交绑定的作业，先写入本地消息表，再由投递器发给 Broker。消费者先记下 `event_id`，再在同一事务里做业务，提交成功后才 ack。**

Broker 的承诺是至少投递一次。业务侧的承诺是同一 `event_id` 只生效一次。两边加起来，才是这里说的可靠性。只加强生产者、或只在消费者里去重，都盖不住另一半失败。

| 失败点 | 谁补上 |
|---|---|
| 业务已提交，消息没发出去 | 生产者：本地消息表与业务同一事务；投递器重试，沿用同一个 `event_id` |
| 消息已发出，业务事务回滚 | 不会发生：投递器只读已提交的本地消息 |
| 业务已生效，ack 前崩溃，Broker 再次投递 | 消费者：`consumed_events.event_id` 唯一约束，冲突则空提交并 ack |
| 还没生效就 ack | 禁止。确认必须在业务提交之后 |
| Broker 把同一条再投一次 | 消费者幂等，不依赖「Broker 绝不重复」 |

画像队列今天在 `finally` 里 ack，处理失败也算消费完成。迁到这套规则后，可重试失败不 ack；不可重试失败写下失败状态后再 ack，避免无限重投。

### 6.2 哪些服务解耦

第一刀只做两类作业。它们都是慢的外部调用，调用方不需要在同一个响应里拿到最终结果，并且已有或可以有状态可查。

| 作业 | `event_type` | 原因 | 幂等依据 |
|---|---|---|---|
| 文档处理 | `knowledge.document.process_requested` | 切块 + embedding + Milvus，现为同步 HTTP | `document_id` + 本次 `run_id`。同一 run 重复投递直接 ack。文档向量按 document 先删后写，串行重跑覆盖旧向量 |
| 画像同步 | `portrait.sync_requested` | 已异步，但 List 弹出即可能丢失 | `user_id`。同步本身是覆盖写。同一用户同时只允许一个 running |

仍保持同步、不发消息：

| 调用 | 原因 |
|---|---|
| `match` 配对成功后 `exchange.open` | 两个写在同一次数据库流程里。丢失其中一步，用户看到「配上了但没有会话」 |
| `quality.submit` 写 review 并改成色 | 判定和成色是一次业务。`(exchange_id, reviewee_id)` 已防重复评审。模型耗时是延迟问题，不是解耦问题 |
| exchange 留言 | 持久化对话，查询以数据库为准 |
| 采集列表登记 | 写的是采集记录行，不是后台作业 |

文档处理的 HTTP 行为改为：同一事务里插入 `document_process_runs`（`pending`）和本地消息行，响应返回这次 run。已有 `running` 的文档再收到请求时拒绝，不另开一条消息。调用方继续用现有 process-runs 接口看结果。

画像同步替换现有 Redis List，不两套并存。过期扫描改为插入本地消息，不再 `RPUSH`。

### 6.3 事件结构

消息体是作业，不是领域事实。事实（「处理成功」）有第二个消费者之后再加类型，结构不变。

```json
{
  "event_id": "8f1c...",
  "event_type": "knowledge.document.process_requested",
  "schema_version": 1,
  "occurred_at": "2026-09-25T09:40:00Z",
  "producer": "knowledge",
  "aggregate_type": "knowledge_document",
  "aggregate_id": "document-uuid",
  "payload": {
    "user_id": "user-uuid",
    "knowledge_base_id": "kb-uuid",
    "document_id": "document-uuid",
    "run_id": "run-uuid"
  }
}
```

规则：

- `event_id` 在插入本地消息表时生成，投递重试不得更换。消费者用它去重。
- `payload` 只放标识。消费者按标识读数据库和对象存储里的当前正文。文档正文、向量、留言全文不进消息。
- `schema_version` 不认识时进入死信，不猜测字段。
- 同一业务动作的多次用户请求是多条消息（新的 `run_id` / 新的 `event_id`）。同一次提交的投递重试是同一条。

### 6.4 本地消息表

要建。它不是第二套队列，也不是消费者表。它解决「数据库和 Broker 不能在一个事务里提交」。

`outbox_messages` 与业务写在同一个数据库事务里：

| 列 | 含义 |
|---|---|
| `event_id` | 主键，也是消息去重键 |
| `event_type` | 上表中的类型 |
| `schema_version` | 从 1 开始 |
| `aggregate_type` / `aggregate_id` | 作业作用的对象 |
| `payload` | JSON，只有标识 |
| `status` | `pending` / `published` / `failed` |
| `created_at` / `published_at` | 投递器按未发布且创建时间重试 |

投递器读已提交的 `pending` 行，发给 Broker，成功后改为 `published`。发布失败保持 `pending`。同一行再次发送时 `event_id` 不变，消费者把第二次当成已处理。

不需要本地消息表的情况：没有数据库状态变化的纯通知。第一刀里没有这种消息，所以不另开旁路。

### 6.5 消费者幂等

Broker 做不到「永不重复投递」。重复消费指的是业务效果不能做第二次。

`consumed_events`：

| 列 | 含义 |
|---|---|
| `event_id` | 主键 |
| `event_type` | 便于排查 |
| `consumed_at` | 写入时间 |

处理顺序：

1. 收到消息，开启数据库事务。
2. 插入 `consumed_events.event_id`。唯一约束冲突：提交空事务并 ack。
3. 做业务。文档处理用 run 状态从 `pending` 条件更新到 `running`，更新不到就结束。画像按用户覆盖写。
4. 提交事务。
5. ack。

可重试错误（embedding 超时、Milvus 短暂不可用）：回滚，不插入消费记录，不 ack，交给 Broker 重投。超过重试次数后把 run / 同步记为失败，写入消费记录并 ack，消息进死信供排查。

不可重试错误（文档不存在、授权过期）：写下失败原因，写入消费记录，ack。

成色这类计数在第一刀不走消息。若以后质量评估改为作业，扣分必须和 review 插入、`consumed_events` 插入在同一事务里，重复投递命中已有 review 时不得再调用 `apply_poor`。

### 6.6 Boundary Cases

| 情况 | 行为 |
|---|---|
| 用户对同一文档在已有 `pending` 或 `running` 时再次点击处理 | 拒绝，不写第二行 outbox |
| 处理已成功，用户再次点击 | 新的 run、新的 `event_id`。这是一次新作业，不是重复投递 |
| 投递器发出后、标记 `published` 前崩溃 | 再次发送同一 `event_id`。消费者看到消费记录后 ack |
| 两个消费者同时拿到重投 | `consumed_events` 主键只有一个事务能插入 |
| 画像 pending 锁 TTL 过期导致再入队 | 迁走 Redis List 后不再使用这把锁。同一用户的 running 同步未完成时，新消息记下后等当前同步结束再覆盖，不并行打知乎 |
| 未知 `schema_version` | 死信，不执行 payload |

## 7. Error Handling

| 条件 | 行为 |
|---|---|
| 业务事务失败 | outbox 与业务一起回滚，用户看到失败，没有幽灵消息 |
| Broker 持续不可用 | outbox 停在 `pending`，投递器重试。请求已经返回受理，状态接口仍显示 pending |
| 消费者处理超时 | 不 ack。重投后靠 `event_id` 或 run 状态避免第二次写入 |
| 消息体缺标识 | 记失败并 ack，不重试 |

## 8. Compatibility

第一刀是新增通道，匹配、交换、质量、声望的同步行为不变。

文档处理的响应从「处理完成后的结果」变为「已创建的 run」。这是接口变化，实现时要单独改 OpenAPI，并让前端改为看 process-runs。评审未同意这一变化前，不改该接口。

画像对外接口不变。Redis List 在画像消费者切到新通道后删除，不双写。

## 9. Alternatives Considered

### 9.1 只换 RocketMQ，不建本地消息表

业务提交和发送仍是两次操作。提交成功、发送失败时作业丢失。RocketMQ 的同步刷盘只保护已经到达 Broker 的消息。

### 9.2 用本地消息表代替 Broker

投递和消费都扫数据库，少一个组件，也没有积压、重试和死信。画像现在的 Redis List 已经证明专用队列会和端口注释分叉。Broker 仍负责传输；表只负责和业务事务对齐。

### 9.3 消费者记忆 Broker 的 message id

生产者超时重发时，Broker 会把它当成新消息，message id 变了。去重键必须是业务侧生成、重试不变的 `event_id`。

### 9.4 第一刀就做完质量评估和匹配的异步化

质量判定和成色、配对和开会话，都是一次业务里的两个写。拆开增加的是不一致，不是解耦收益。

## 10. Testing Strategy

实现阶段再写测试。评审时用这些例子验收设计，而不是现在加测试：

| 例子 | 期望 |
|---|---|
| 文档处理事务回滚 | `document_process_runs` 和 outbox 都没有新行 |
| 同一 `event_id` 投递两次 | Milvus 写入路径只执行一次，第二次 ack |
| 处理抛出可重试错误 | 无消费记录，消息可再次投递 |
| 已有 running 的文档再次请求 | 不产生新 `event_id` |
| 画像同步失败 | 不 ack；授权过期则记失败并 ack |
| 匹配成功 | 仍然同一次流程 `exchange.open`，没有 outbox 行 |

## 11. Summary of Changes

评审通过并明确开工之后才会动这些位置。现在不动。

| 区域 | 以后的改动 |
|---|---|
| `verso_framework.mq` | 实现发布端口；注释与真实传输一致 |
| 数据库 | 增加 `outbox_messages`、`consumed_events` |
| knowledge process API | 受理并返回 run，执行移到消费者 |
| portrait queue | Redis List 换成本地消息 + 同一消费者规则 |
| worker | 投递器与上述两类消费者 |
| match / exchange / quality | 不改 |

## 12. Open Questions

1. 第一刀是否同意只做文档处理和画像同步这两类作业？
2. 文档处理接口改为「返回 run、调用方自己查状态」，是否接受？
3. 质量评估保持同步，直到产品接受异步结论。是否同意？
4. 本地消息表用 PostgreSQL 里的两张表（`outbox_messages`、`consumed_events`），不在 Redis 再做一份。是否同意？
