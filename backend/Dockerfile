# ── 后端 Dockerfile ──────────────────────────────────────────────────
# 多阶段构建: builder 装依赖 → runtime 只拷贝产物，镜像更小

# ── 阶段 1: 构建 ──
FROM python:3.12-slim AS builder

# 安装 uv（比 pip 快 10x）
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# ── 国内网络：走镜像源 + 拉长超时 ────────────────────────────────────────
# 构建容器里访问 pypi.org 容易在下大包时 "operation timed out"。
ENV UV_DEFAULT_INDEX=https://mirrors.aliyun.com/pypi/simple/ \
    UV_HTTP_TIMEOUT=180 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# 必须与 runtime 阶段同路径 —— venv 内的 shebang/.pth 是绝对路径，跨路径拷贝会失效
WORKDIR /app

# 先拷贝依赖定义，利用 Docker layer cache
COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/packages/common/pyproject.toml packages/common/
COPY backend/packages/framework/pyproject.toml packages/framework/
COPY backend/packages/app/pyproject.toml packages/app/

# 安装第三方依赖（不含 workspace 包、不含 dev）
RUN uv sync --frozen --no-dev --no-install-workspace

# 拷贝源码并安装 workspace 包
COPY backend/packages/ packages/
COPY migration/ /app/migration/
RUN uv sync --frozen --no-dev

# ── 阶段 2: 运行时 ──
FROM python:3.12-slim AS runtime

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/packages /app/packages
COPY --from=builder /app/migration /app/migration

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "verso_app.bootstrap.app:app", "--host", "0.0.0.0", "--port", "8000"]
