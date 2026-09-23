# Verso Codebase Map

这是一份随代码演进的仓库结构记录。它记录当前已经验证过的目录、分层、启动方式、数据边界和测试入口，帮助后续开发者快速定位代码。

最后核对：2026-09-23

## 1. 仓库布局

```text
verso/
├── frontend/                 # Next.js 前端
│   ├── src/app/              # 页面路由
│   ├── src/components/       # 页面与业务组件
│   ├── src/model/            # 按领域组织的 API、类型和 mock
│   └── AGENTS.md             # 前端专用规则
├── backend/                  # uv workspace
│   ├── packages/
│   │   ├── common/           # DTO、枚举、异常、统一响应、常量
│   │   ├── framework/        # 配置、数据库、Redis、对象存储、外部 provider
│   │   └── app/              # 领域服务、HTTP API、worker、启动装配
│   ├── tests/                # 后端测试
│   ├── pyproject.toml        # workspace、pytest、ruff、import-linter
│   └── README.md             # 后端本地运行说明
├── docs/                     # 产品、架构、模块和开发记录
├── openapi/openapi.json      # FastAPI 生成的接口契约
├── docker-compose.yml        # backend、Postgres、Redis 等本地服务
└── deploy/nginx/             # Nginx 反向代理样例
```

## 2. 后端分层

后端包依赖方向如下，不能反向引用：

```text
verso_app.bootstrap
verso_app.web  |  verso_app.worker
verso_app.server
verso_framework
verso_common
```

- `verso_common` 不依赖 FastAPI、数据库、Redis 或外部 provider。
- `verso_framework` 提供基础设施和端口，不写业务状态机。
- `verso_app.server` 保存领域模型和业务规则。
- `verso_app.web` 只负责 HTTP 参数、鉴权依赖和响应适配。
- `verso_app.worker` 只负责后台任务消费和调度。
- `verso_app.bootstrap` 负责应用、路由、模型和后台组件装配。
- `web` 与 `worker` 同层，不能相互引用。

分层规则写在 `backend/pyproject.toml` 的 import-linter 配置中。

## 3. App 目录

```text
backend/packages/app/src/verso_app/
├── bootstrap/
│   ├── app.py               # FastAPI 工厂、lifespan、路由装配、建表入口
│   └── worker.py            # worker 进程入口
├── server/
│   ├── auth/                # 用户、OAuth、session 关联的业务服务
│   ├── portrait/            # 授权数据同步、画像抽取和画像队列
│   ├── article/             # user_articles 元数据和对象存储正文
│   ├── knowledge/           # 用户知识库；#104 引入
│   ├── match/               # 求知条件、互补匹配、匹配评估
│   ├── exchange/            # 配对关系和多轮留言
│   ├── quality/             # 不满意后的质量评估
│   ├── reputation/          # 声望分和匹配资格
│   └── fetch/               # URL 解析、HTML 转 Markdown 等基础领域能力
├── web/
│   ├── api/                 # 各领域 router
│   ├── middleware/          # session、当前用户和 service 依赖
│   └── handler/             # 统一异常响应
└── worker/
    └── handlers.py          # 画像同步 worker 和进程内 poller
```

每个成熟领域通常包含：

```text
server/<domain>/
├── models.py                # SQLAlchemy ORM
├── service.py               # 领域规则和用例
├── ports.py                 # 外部依赖端口（需要时）
└── __init__.py
```

HTTP 适配位于 `web/api/<domain>.py`，不要把业务状态变化直接写在 router 中。

## 4. 当前已验证的核心链路

### 登录和画像

1. `web/api/auth.py` 调用 `server/auth/service.py` 完成 OAuth 和站内用户处理。
2. session、OAuth intent、知乎授权数据由 `server/auth/session_store.py` 通过 Redis 保存。
3. 登录后由 `portrait` 异步或内联入队同步。
4. `PortraitService` 读取知乎授权数据，抽取画像并写入 `portraits`。
5. 创作列表成功时，`PortraitService` 调用 `ArchiveService.enqueue_listed_contents()` 登记文章待抓任务。

### 文章归档

`server/article` 负责：

- `UserArticle` 保存用户、来源 URL、标题、状态、哈希和对象存储 key。
- Markdown 正文保存到对象存储，不直接保存到 Postgres。
- `ArchiveService.put_markdown()` 负责 upsert、哈希去重和对象存储写入。
- `enqueue_listed_contents()` 只登记授权用户创作列表中的可归档 URL，不做匿名抓取。
- `capture_from_browser()` 接收用户在已登录知乎页面提取的 HTML，再转 Markdown。
- `/me/articles/queue` 和 `/me/articles/browser-capture` 是旧接口，必须保持兼容。

### 匹配和交流

1. `server/match` 保存本次想学的 Ticket 和配对结果。
2. 配对成功时调用 `server/exchange` 建立一对关系。
3. `server/exchange` 保存消息和关系生命周期。
4. `server/quality` 只在用户主动表示不满意后评估。
5. 质量结果交给 `server/reputation` 修改声望和资格。

## 5. 数据库和启动方式

- ORM 基类是 `verso_framework.db.base.Base`。
- 当前没有 Alembic 迁移目录。
- 测试使用 SQLite `StaticPool`，通过 `Base.metadata.create_all()` 建表。
- 本地应用在 `VERSO_CREATE_TABLES=true` 时，由 `bootstrap/app.py` 的 lifespan 导入模型并创建表。
- 生产数据库配置默认是 PostgreSQL，配置位于 `verso_framework.config.database`。
- Redis、Milvus、对象存储客户端都采用懒加载配置。

### 知识库迁移约定

`knowledge` 模块需要兼容已经存在的 `user_articles`：

- `server/knowledge/models.py` 定义 `knowledge_bases`。
- `server/knowledge/service.py` 负责 owner scope、默认知识库和删除保护。
- `server/knowledge/migration.py` 负责补旧表字段、创建默认知识库并回填旧文章。
- 应用启动时调用 `ensure_knowledge_schema()`，因此迁移逻辑必须可重复执行。

如果将来引入 Alembic，应把这里的启动迁移收敛到正式 migration，并同步更新本文档。

## 6. API 约定

- FastAPI router 是接口唯一实现来源。
- 生成的契约文件是 `openapi/openapi.json`。
- 业务错误通常通过 `BizException` 抛出。
- 全局异常处理器把业务错误包装成 HTTP 200，业务码放在响应体的 `code`。
- 当前用户通过 `get_current_user` 依赖注入。
- 用户资源查询必须同时带 `user_id`，其他用户的资源统一返回业务码 `404`。
- 领域响应 DTO 放在 `verso_common.models`，不要让 ORM 模型直接成为公共响应契约。

#104 的知识库接口：

```text
POST   /me/knowledge-bases
GET    /me/knowledge-bases
GET    /me/knowledge-bases/{id}
PATCH  /me/knowledge-bases/{id}
DELETE /me/knowledge-bases/{id}

GET    /me/knowledge-bases/{id}/articles
GET    /me/knowledge-bases/{id}/articles/queue
GET    /me/knowledge-bases/{id}/articles/failed-fetch
POST   /me/knowledge-bases/{id}/articles/browser-capture
```

## 7. 测试和检查

从 `backend/` 目录执行：

```powershell
uv run pytest
uv run ruff check packages tests
uv run python scripts/export_openapi.py ../openapi/openapi.json --check
```

测试文件按领域命名，例如：

```text
tests/test_auth.py
tests/test_portrait.py
tests/test_archive.py
tests/test_knowledge.py
tests/test_match.py
tests/test_exchange.py
tests/test_quality.py
tests/test_reputation.py
```

新增行为优先遵循：

1. 先写能够表达验收标准的失败测试。
2. 实现最小领域行为。
3. 跑目标测试，再跑全量测试。
4. 变更 API 后重新生成并检查 OpenAPI。
5. 运行 ruff 和 `git diff --check`。

## 8. 这份记录何时更新

出现以下变化时，同一个改动必须更新本文件：

- 新增或删除 package、领域模块、router、worker 或外部 provider。
- 新增 ORM 表、字段、索引、启动迁移或正式数据库迁移。
- 改变领域之间的依赖方向或资源 owner。
- 新增、删除或改变公开 API。
- 改变本地启动、测试、OpenAPI 生成或质量门禁命令。
- Issue 的验收标准已经改变现有结构，而架构文档还没有反映。

更新时保留“已验证的现状”和“计划引入的结构”的区别，不把未实现方案写成当前行为。
