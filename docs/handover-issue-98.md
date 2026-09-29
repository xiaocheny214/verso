# Issue #98 开发与会话交接日志 (Handover Log)

- **更新时间**: 2026-09-29
- **当前任务**: GitHub Issue #98 — 单向 RAG 候选池与金字塔互补配对 (Unidirectional RAG Candidate Pool and Pyramid Pairing)
- **当前分支**: `feat/#98-unidirectional-rag-match`
- **关联设计计划文件**: `C:\Users\hohot\.claude\plans\rippling-brewing-frost.md`

---

## 1. 当前进展状态 (Current Progress)

### 已完成 (Done)
1. **数据模型扩展 (`packages/app/src/verso_app/server/match/models.py`)**：
   - 新增 `MatchCandidate` ORM 模型，包含字段：`id`, `question_id` (外键 `match_conditions.id`, ondelete="CASCADE"), `helper_id` (外键 `users.id`, ondelete="CASCADE"), `score`, `evidence`, `created_at`。
   - 增加唯一约束：`UniqueConstraint("question_id", "helper_id", name="match_candidates_question_helper")`。
   - 在 `MatchCondition` 模型中增加 `question_embedding` 字段 (`JSONType`，可空)，用于缓存提问的向量特征，供反向局部打分使用，避免重复调用外部 Embedding 模型。
2. **切片向量检索能力 (`packages/app/src/verso_app/server/knowledge/vector_store.py`)**：
   - 扩展了 `ChunkVectorStore` 协议，增加接口：
     ```python
     def search_chunks(
         self,
         *,
         query_embedding: list[float],
         user_ids: set[uuid.UUID],
         top_k: int = 20,
         min_score: float = 0.2,
     ) -> list[ChunkSearchResult]: ...
     ```
   - 在 `MemoryChunkVectorStore`（单测用）中实现了基于候选用户 `user_ids` 的余弦相似度检索与阈值过滤。
   - 在 `MilvusChunkVectorStore`（生产用）中实现了带有 `user_id in [...]` 过滤条件的向量检索逻辑。
3. **核心匹配服务改造 (`packages/app/src/verso_app/server/match/service.py`)**：
   - **依赖注入**：在 `MatchService.__init__` 支持注入 `embedder: Embedder | None` 与 `vector_store: ChunkVectorStore | None`。
   - **提问向量化与持久化**：在 `submit` 中，当配置了 `embedder` 时，计算 `mine.want_text` 的 embedding 并存入 `mine.question_embedding`。
   - **正向检索 (Forward Search)**：查询具有已就绪文档（`status == DocumentStatus.SUCCESS`）的等待中用户集合 $S$；调用 `vector_store.search_chunks`，对返回命中切片（相似度分 >= 阈值，默认 0.2）写入/更新 `match_candidates`（`question_id=mine.id, helper_id=candidate.user_id`）。
   - **反向局部打分 (Reverse Scoring)**：若当前用户自己拥有就绪文档切片，遍历等待中用户集合 $S$ 中已有 `question_embedding` 的条件；仅在当前用户的文档切片中进行匹配打分，满足阈值的写入/更新 `match_candidates`（`question_id=other.id, helper_id=mine.user_id`）。
   - **自连接与金字塔配对 (Self-Join & Capability Band)**：
     - 通过查询 `match_candidates` 找出双向均成立的配对（即 $A \to B$ 且 $B \to A$）；
     - **金字塔能力阶梯过滤**：根据声望值划分为 5 个阶梯区间（`Band 0: <60, Band 1: 60-69, Band 2: 70-79, Band 3: 80-89, Band 4: >=90`），要求双方必须处于同阶梯或相邻阶梯（阶梯差 <= 1），防止跨层过大导致头部作者被过度薅羊毛；
     - **排序规则**：以 $\min(\text{score}_{A\to B}, \text{score}_{B\to A})$ 降序为第一优先级，声望差距升序为第二优先级，创建等待时长为第三优先级；
     - **组装证据**：将命中的文档切片格式化为 `CapabilityEvidence(id="article:{doc_id}:c{chunk_index}", ...)`，送入既有双闸门 LLM 评估器 `_consider_candidate`；
     - **回退逻辑**：若未找到双向切片候选，默认保持 waiting；若全站配置 `match_title_fallback_when_no_ready = True` 且双方均无就绪正文时，才降级回退到原画像标题匹配；若未注入 `vector_store` 则完全兼容原画像匹配。
   - **候选清理 (`clean_candidates`)**：当条件状态变为 `MATCHED`、`CANCELLED` 或过期时，清理对应的 `match_candidates`。
4. **依赖注入与中间件 (`packages/app/src/verso_app/web/middleware/auth.py`)**：
   - 在 `get_match_service` 中装配 `embedder`、`MilvusChunkVectorStore` 以及 `settings` 并注入 `MatchService`。
5. **单元测试与集成测试 (`tests/test_match_rag.py`)**：
   - 编写了 9 个专项测试用例，覆盖：
     - 提问向量缓存与单人提交 waiting；
     - 双向就绪切片自连接配对与候选自动清理；
     - 单向满足时不盲目配对（保持 waiting）；
     - 金字塔跨阶梯拦截（Band 1: 62分 vs Band 3: 85分）；
     - 相邻阶梯允许配对（Band 1: 65分 与 Band 2: 75分）；
     - 取消与过期清理候选表；
     - 显式开启回退时降级画像匹配；
     - 默认关闭回退时保持 waiting；
     - 评估记录中保留 `article:...:c{n}` 切片证据 ID。
   - 全量测试 `uv run pytest`（236 passed）100% 通过，`ruff check` 与 `ruff format` 均无报警。

---

## 2. 待完成工作 (Pending Tasks)

1. 用户确认后提交 git commit 并将分支推送远端创建 PR。
2. 后续规划：在独立议题中规划和实现统一的通用检索召回模块（意图识别、多路混合召回、知识图谱等）。

---

## 3. 如何在关闭会话后恢复上下文 (How to Resume Later)

关闭当前会话后，可以通过以下几种方式无缝接续：

1. **直接告诉新会话**：
   > “继续推进 Issue #98，请查看 `docs/handover-issue-98.md` 了解当前进度并接着实现 `MatchService` 中的单向 RAG 与金字塔互补配对逻辑。”
2. **在 Claude Code 中使用内置计划模式 / 恢复计划**：
   - 计划文件已完整保存在：`C:\Users\hohot\.claude\plans\rippling-brewing-frost.md`。
   - 新会话中只需输入：`查看并继续执行 plan rippling-brewing-frost` 即可唤起之前的完整步骤设计。
3. **查看当前未提交代码**：
   - 运行 `git diff` 即可看到当前修改的文件：
     - `packages/app/src/verso_app/server/match/models.py`
     - `packages/app/src/verso_app/server/knowledge/vector_store.py`
     - `docs/handover-issue-98.md`
