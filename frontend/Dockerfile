# ── 前端构建容器 ─────────────────────────────────────────────────────
# 容器只负责生成静态产物，宿主机 nginx 直接读取挂载目录。
# 仓库暂无 frontend-ci；Next 16 要求 Node 20+，钉 22 LTS。
FROM node:22-alpine

# 国内网络:走镜像源,与 backend/Dockerfile 换阿里 pypi 源同因
ENV NPM_CONFIG_REGISTRY=https://registry.npmmirror.com \
    COREPACK_NPM_REGISTRY=https://registry.npmmirror.com \
    NEXT_TELEMETRY_DISABLED=1 \
    VERSO_STATIC_EXPORT=1

WORKDIR /app

RUN corepack enable

# 先只拷依赖清单,命中 Docker layer cache —— 改源码不触发重装依赖
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

# NEXT_PUBLIC_ 前缀的变量在 next build 时就被烘进产物,运行期再往容器注环境变量对
# 已构建产物无效 —— 这是前端和 backend 在配置方式上唯一的实质差别。
# 默认空字符串：浏览器请求与页面同源，由宿主机 nginx 把 /auth /me /match/ 等转给后端，
# 构建镜像因此不与任何域名绑定，同一份产物可直接换环境跑。
# 若某个环境确实要指向外部后端,构建时传 --build-arg NEXT_PUBLIC_API_BASE=https://…,
# 但那样后端必须同步配 CORS（VERSO_PUBLIC_ORIGIN），否则浏览器预检就被拦死。
ARG NEXT_PUBLIC_API_BASE=
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE

# Next.js `output: 'export'` 固定写到 /app/out，没有 Vite 那种 --outDir。
# 构建完再同步到 Compose 挂载的宿主机目录；完成后进程退出，不启动常驻服务。
CMD ["sh", "-c", "pnpm build && mkdir -p /var/www/verso-frontend && find /var/www/verso-frontend -mindepth 1 -delete && cp -a out/. /var/www/verso-frontend/"]
