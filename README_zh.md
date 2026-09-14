# Verso / 背叶

**Verso 匹配的是能力互补的人，不是臭味相投的人。**

> 多数社交产品会把信息茧房越织越厚：把领域相近、口味相近、认知相近的人配在一起。Verso 反过来做。它借助一个问题，把能互相教一块的两个人配上——领域不同，认知不同——让双方都能带走自己原本没有的东西。

[快速开始](#快速开始) · [English](README.md)

中文名是 **背叶**，即书页的背面。两边看起来对立，合上才是一张纸。

---

## 匹配条件

只有两边同时补上对方，才算匹配：

| 这一侧 | 得到什么 |
| --- | --- |
| 你擅长的 | 教给还不会的人 |
| 你这次想学的 | 从对方那里学到 |

![Verso 互补匹配](docs/assets/verso-complementary-match.zh.svg)

同话题、同一篇文章、同一个问题配人，都不在范围内。授权后的知乎文章、关注、收藏只用来生成擅长画像，不是聊天地图，也不是匹配条件本身。

---

## Verso 做什么

| 能力 | 做什么 |
| --- | --- |
| Auth | 知乎 OAuth；保存账号和授权后的公开创作 |
| Portrait | 把授权内容收成擅长画像 |
| Match | 按双方擅长是否覆盖对方这次想学的问题来配对 |
| Exchange | 配上之后，在这一对下面异步互留 1:1 消息 |
| Quality | 只有对方先表示不满意，才评估回答 |
| Reputation | 持久化声望分和匹配资格 |

核心链路：**认证 → 画像 → 互补匹配 → 异步交流 → 质量评估 → 声望**。

---

## 规格

产品和模块边界写在 GitHub Issue 里。Agent 和开发者去读 Issue，不要在 `/docs` 再抄一份。

- 产品策划案：[#30](https://github.com/xiaocheny214/verso/issues/30)
- 模块划分：[#31](https://github.com/xiaocheny214/verso/issues/31)
- 如何参与：[CONTRIBUTING.md](CONTRIBUTING.md)

---

## 快速开始

```bash
cp .env.example .env
docker compose up -d --build
```

本地 API 说明见 [backend/README.md](backend/README.md)。

前端容器把静态文件写到 `/var/www/verso-frontend` 后退出。宿主机 Nginx 用 [`deploy/nginx/verso.host.conf`](deploy/nginx/verso.host.conf)：`root` 指向该目录，API 反代到 `127.0.0.1:8000`。数据在 `./data/postgres` 与 `./data/redis`。

---

## 仓库结构

```text
verso/
├── frontend/           # Next.js；镜像写出静态文件到 /var/www/verso-frontend
├── backend/            # uv workspace: common → framework → app
├── deploy/             # 宿主机 Nginx 样例
└── docker-compose.yml
```

---

## 许可

专有商业许可，见 [LICENSE](LICENSE)。
