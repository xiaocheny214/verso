# Verso (背叶)

Mutual-complement matching powered by each person's Zhihu knowledge footprint.

由知乎授权内容形成擅长画像，把「你会什么」与「你这次想学什么」双向配对的轻社交产品。

- English name: **Verso**
- Chinese name: **背叶**
- Repository: [xiaocheny214/verso](https://github.com/xiaocheny214/verso)
- License: proprietary commercial (see [LICENSE](LICENSE))

Verso is the other side of a page. A match succeeds only when both sides complete each other: A can teach what B wants to learn, and B can teach what A wants to learn.

The MVP flow is **Zhihu OAuth → strengths portrait → one-time learning ticket → mutual match → asynchronous exchange → human-triggered quality review**. Articles, follows, and favorites provide portrait evidence; they are not chat maps. Same-article presence, live invites, timed rooms, feed, and map are out of scope.

Status: product spec is [`docs/product-proposal.md`](docs/product-proposal.md) ([#30](https://github.com/xiaocheny214/verso/issues/30)). Backend boundaries are [`docs/architecture.md`](docs/architecture.md) ([#31](https://github.com/xiaocheny214/verso/issues/31)). How to contribute: [`CONTRIBUTING.md`](CONTRIBUTING.md).

```text
frontend/    # Next.js；镜像写出静态文件到 /var/www/verso-frontend
backend/     # uv workspace: common → framework → app
deploy/      # 宿主机 Nginx 样例
```

本地 API：[`backend/README.md`](backend/README.md)。

```bash
cp .env.example .env
docker compose up -d --build
```

前端容器把静态文件写到 `/var/www/verso-frontend` 后退出。宿主机 Nginx 用 [`deploy/nginx/verso.host.conf`](deploy/nginx/verso.host.conf)：`root` 指向该目录，API 反代到 `127.0.0.1:8000`。数据在 `./data/postgres` 与 `./data/redis`。
